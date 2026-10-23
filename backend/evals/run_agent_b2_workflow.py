"""Public development workflow; real providers, isolated synthetic database.

Stops at any missing preview/run/revision. Never manufactures a candidate or
calls a database writer in place of the normal confirmation/Accept service.
"""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import UUID, uuid4

import run_agent_b2_quality as capture


async def run(args, settings):
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.database import Base, AssistantSession, Trip, Activity, DayPlan, PlanningRun, PlanRevision
    from app.assistant_service import send_message, confirm_action
    from app.assistant_capabilities import select_capabilities
    from app.assistant_places import ContentServicePlaces
    from app.place_content.service import PlaceContentService
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository, metadata
    from app.planning_graph_runtime import execute_planning_run
    from app.schemas import PlanningRunDecision
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    sync=create_engine(capture.DB,poolclass=NullPool)
    Base.metadata.create_all(sync);metadata.create_all(sync)
    engine=create_async_engine(capture.DB,poolclass=NullPool)
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as checkpoints:
        await checkpoints.setup()
    port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(sync)),owner="agent-b2-public-synthetic")
    report={"source_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=capture.ROOT,text=True).strip(),
        "synthetic":True,"real_model":True,"real_maps":True,"schema":"Base.metadata + content metadata",
        "model":settings.planner_model,"provider":settings.planner_provider,"records":[],"completed":False}
    def save():capture.dump(args.output,report)
    async def snapshot():
        async with sessions() as db:
            return {"counts":{model.__name__:await db.scalar(select(func.count()).select_from(model))
                for model in (Trip,Activity,PlanningRun,PlanRevision)},
                "trips":[{"id":str(t.id),"version":t.version,"destination":t.destination}
                    for t in (await db.scalars(select(Trip))).all()],
                "runs":[{"id":str(r.id),"status":r.status,"user_request":r.user_request,
                    "intent_resolution":r.intent_resolution,"error_code":r.error_code,"error_message":r.error_message,
                    "error_details":r.error_details,"pending_interrupt":r.pending_interrupt}
                    for r in (await db.scalars(select(PlanningRun))).all()],
                "revisions":[{"id":str(r.id),"status":r.status,"validation":r.validation_result,
                    "snapshot":r.proposed_snapshot} for r in (await db.scalars(select(PlanRevision))).all()]}
    async with sessions() as db:
        row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit();sid=row.id
    async def turn(message,context=None,*,selected_day_id=None):
        mid=uuid4();entry={"stage":"dialogue","user":message,"message_id":str(mid),"selections":[],
            "selected_day_id":str(selected_day_id) if selected_day_id else None}
        async def selector(*params):
            decision=await select_capabilities(*params)
            entry["selections"].append(decision.model_dump(mode="json"));return decision
        if context and context.get("action_target"):
            context["action_target"]["authorization_message_id"]=str(mid)
        start=time.monotonic()
        try:
            async with sessions() as db:
                row=await send_message(db,sid,message,mid,context=context or {"topic_id":"b2-public-flow","prefer_flexible":True},
                    selected_day_id=selected_day_id,place_port=port,capability_selector=selector)
                entry.update(raw=row.messages[-1],pending_action=row.pending_action,
                    trip_id=str(row.trip_id) if row.trip_id else None,run_id=str(row.latest_run_id) if row.latest_run_id else None)
        except Exception as exc:entry.update(error_type=type(exc).__name__,error=str(exc))
        entry["seconds"]=round(time.monotonic()-start,3);report["records"].append(entry);save()
        print(json.dumps({"stage":"dialogue","seconds":entry["seconds"],"error":entry.get("error_type")}),flush=True)
        return entry
    async def worker(rid):
        start=time.monotonic();entry={"stage":"worker","run_id":rid}
        try:
            await execute_planning_run(UUID(rid))
        except Exception as exc:entry.update(error_type=type(exc).__name__,error=str(exc))
        entry.update(seconds=round(time.monotonic()-start,3),snapshot=await snapshot())
        report["records"].append(entry);save();return entry
    try:
        report["before"]=await snapshot();save()
        await turn("成都人民公园和宽窄巷子分别是什么体验？先聊选择，不创建安排。")
        await turn("请查成都人民公园和宽窄巷子的位置，以及人民公园到宽窄巷子的步行路线；如果重名就列地址，不要猜。")
        entry=await turn("人民公园选小南街8号的那个，宽窄巷子选少城街道金河路口的景区。两个都想去。请创建成都2026年11月9日的一日候选，10点后出发，18点前结束，只排这两个地方，中午留一小时吃饭。先给我看，等我采用后再保存。")
        if not entry.get("pending_action"):
            report["stopped_at"]="creation_preview_missing";return
        async with sessions() as db:
            row=await confirm_action(db,sid,entry["pending_action"]["id"],True)
            rid=str(row.latest_run_id) if row.latest_run_id else None;tid=row.trip_id
        report["records"].append({"stage":"confirm_creation","run_id":rid,"snapshot":await snapshot()});save()
        if rid is None:
            report["stopped_at"]="timed_candidate_run_missing";return
        await worker(rid)
        async with sessions() as db:
            modelrun=await db.get(PlanningRun,UUID(rid))
            ready=modelrun.status=="awaiting_confirmation"
        if not ready:
            report["stopped_at"]="initial_candidate_not_ready";return
        await execute_planning_run(UUID(rid),decision=PlanningRunDecision(decision="accept"))
        report["records"].append({"stage":"accept_initial","snapshot":await snapshot()});save()
        async with sessions() as db:
            trip=await db.get(Trip,tid)
            day=await db.scalar(select(DayPlan).where(DayPlan.trip_id==tid).order_by(DayPlan.position))
            ctx={"topic_id":"b2-public-flow","prefer_flexible":True,"read_trip_id":str(tid),
                "action_target":{"trip_id":str(tid),"expected_version":trip.version,"operation":"plan_trip"}}
            day_id=day.id
        entry=await turn("只把宽窄巷子晚半小时开始，停留缩短为一小时。人民公园和午饭留白都保持不变。请实际生成可采用的调整候选，不要直接覆盖。",ctx,selected_day_id=day_id)
        if not entry.get("run_id"):
            report["stopped_at"]="modification_run_missing";return
        await worker(entry["run_id"])
        async with sessions() as db:
            modelrun=await db.get(PlanningRun,UUID(entry["run_id"]))
            ready=modelrun.status=="awaiting_confirmation"
        if not ready:
            report["stopped_at"]="modification_candidate_not_ready";return
        await execute_planning_run(UUID(entry["run_id"]),decision=PlanningRunDecision(decision="accept"))
        report["records"].append({"stage":"accept_modification_and_reload","snapshot":await snapshot()})
        report["completed"]=True
    finally:
        report["after"]=await snapshot();save();await engine.dispose();sync.dispose()


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--settings-source",required=True)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise SystemExit("Refusing to overwrite a raw workflow")
    capture.DB=capture.DB.rsplit("/",1)[0]+"/roamsync_agent_b2_public_workflow_test"
    settings=capture.configure(args.settings_source)
    if sys.platform=="win32":asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args,settings))


if __name__=="__main__":main()
