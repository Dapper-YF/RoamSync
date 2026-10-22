"""C's local acceptance runtime. Never opens the official database.

Uses an existing *test-only* PostgreSQL server on 15433, with its own database.
Provider credentials are read in memory from the canonical env and never emitted.
Run with the project's Python environment: init, seed, api or worker.
"""
import asyncio
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from app.config import Settings, get_settings

source = Settings(_env_file='E:/Study/RoamSync/.env')
for name in ('planner_provider', 'planner_api_key', 'planner_model', 'planner_base_url',
             'planner_proxy_url', 'planner_reasoning_effort', 'planner_max_candidates',
             'planner_timeout_seconds', 'planner_max_output_tokens', 'amap_rest_key',
             'tavily_api_key', 'roamsync_tavily_api_key', 'tavily_base_url', 'tavily_proxy_url'):
    value = getattr(source, name)
    value = value.get_secret_value() if hasattr(value, 'get_secret_value') else str(value)
    os.environ[name.upper()] = value.replace('host.docker.internal', '127.0.0.1')
# These fixed credentials belong solely to the existing synthetic handbook test server.
DSN = 'postgresql://handbook_test:handbook_test@127.0.0.1:15433/roamsync_product_c_test'
os.environ.update(APP_ENV='test', DATABASE_URL=DSN.replace('postgresql://', 'postgresql+psycopg://'),
                  LANGGRAPH_DATABASE_URL=DSN, ROAMSYNC_ISOLATED_INTEGRATION='1',
                  ROAMSYNC_INTEGRATION_TOKEN='product-c-isolated-only',
                  ROAMSYNC_INTEGRATION_OWNER='product-c-synthetic-user',
                  ROAMSYNC_LOCAL_ORIGINS='http://127.0.0.1:3042', ALLOW_MAP_ESTIMATES='false')
get_settings.cache_clear()

async def seed():
    import json
    from datetime import date, time
    from uuid import uuid4
    from sqlalchemy import select
    from app.database import session_factory, Trip, DayPlan, Activity
    from app.repository import create_trip
    from app.schemas import TripCreate
    from app.maps_service import search_amap_places
    from app.planner_repository import _resolve_place
    from app.arrangement_service import write_item, ItemWrite
    suffix = {'precise':' · 精确活动','review':' · 复核'}.get(sys.argv[2],'') if len(sys.argv)>2 else ''
    title = '成都 · 从容两日（C隔离验收）'+suffix
    async with session_factory() as db:
        trip = await db.scalar(select(Trip).where(Trip.title == title))
        if trip:
            print('Synthetic fixture already exists:', trip.id)
            return
        trip = await create_trip(db, TripCreate(title=title, destination='成都', start_date=date(2026,11,2), end_date=date(2026,11,3)))
        days = list((await db.scalars(select(DayPlan).where(DayPlan.trip_id==trip.id).order_by(DayPlan.date))).all())
        for query, external, clock, duration, locked, pos in [
            ('人民公园','B001C7X8QA',time(10),60,True,0),
            ('宽窄巷子','B001C7YCM4',time(13),90,False,1),
        ]:
            results = await search_amap_places(query,'成都')
            found = [p for p in results if p.provider_place_id == external]
            if len(found) != 1:
                raise ValueError('Fixture requires a unique real POI')
            place = await _resolve_place(db,days[1],None,found[0])
            await db.flush()
            db.add(Activity(id=uuid4(),day_plan_id=days[1].id,place_candidate_id=place.id,
                            scheduled_time=clock,duration_minutes=duration,estimated_cost_fen=place.estimated_cost_fen,
                            status='planned',position=pos,schedule_locked=locked))
        await db.commit()
        for values in [dict(kind='free_window',label='自由活动',day_date=days[1].date,start=time(15),end=time(16)),
                       dict(kind='selected',label='武侯祠',day_date=days[1].date),
                       dict(kind='optional',label='锦里',day_date=None)]:
            await db.refresh(trip)
            await write_item(db,trip.id,ItemWrite(expected_version=trip.version,source_ref='product-c-synthetic-fixture',**values))
        out=ROOT/'docs/evidence/product-c-20261022'
        out.mkdir(parents=True,exist_ok=True)
        (out/'fixture.json').write_text(json.dumps({'trip_id':str(trip.id),'day_id':str(days[1].id),'title':title,'schedule':'synthetic','places':'real AMap identity'},ensure_ascii=False,indent=2),encoding='utf-8')
        print('Created isolated synthetic fixture:',trip.id)

async def candidate():
    """Synthetic proposal only; actual route enrichment and Validator are mandatory."""
    import json
    from datetime import time
    from uuid import UUID
    from sqlalchemy import select
    from app.database import session_factory, Trip, DayPlan, Activity, PlaceCandidate, PlanningRun
    from app.schemas import CandidateActivity, CandidatePlanSnapshot, PlanningIntentResolution
    from app.candidate_route_service import enrich_candidate_routes
    from app.plan_revision_service import validate_candidate_plan
    from app.planning_run_repository import save_plan_revision
    out=ROOT/'docs/evidence/product-c-20261022'
    fixture=json.loads((out/'fixture.json').read_text(encoding='utf-8'))
    async with session_factory() as db:
        trip=await db.get(Trip,UUID(fixture['trip_id']))
        assert trip and trip.title.startswith('成都 · 从容两日（C隔离验收）')
        original=await db.scalar(select(PlanningRun).where(PlanningRun.trip_id==trip.id).order_by(PlanningRun.created_at.desc()))
        stale_case=sys.argv[1]=='candidate-stale'
        assert (original and original.status=='accepted') if stale_case else (not original or original.status=='failed' and original.error_code=='planner_research_unavailable')
        if original and original.status=='failed':
            (out/'precise-model-failure.json').write_text(json.dumps({'run_id':str(original.id),'user_request':original.user_request,'status':original.status,'error_code':original.error_code,'error_message':original.error_message},ensure_ascii=False,indent=2),encoding='utf-8')
        rows=list((await db.execute(select(Activity,DayPlan,PlaceCandidate).join(DayPlan,Activity.day_plan_id==DayPlan.id).join(PlaceCandidate,Activity.place_candidate_id==PlaceCandidate.id).where(DayPlan.trip_id==trip.id).order_by(DayPlan.date,Activity.position))).tuples())
        activities=[CandidateActivity(candidate_id=f'fixture-{a.id}',day_date=d.date,place_candidate_id=p.id,
                     planned_start_time=a.scheduled_time if a.schedule_locked else time(14) if stale_case else time(13,30),
                     duration_minutes=a.duration_minutes if a.schedule_locked else 60,
                     estimated_cost_fen=p.estimated_cost_fen,transport_mode_to_here='walk',
                     replaces_activity_id=a.id,source_ids=[p.source_record_id],locked=a.schedule_locked,
                     reason='合成验收：固定时间保留。' if a.schedule_locked else '合成验收：晚半小时出发，减少停留。') for a,d,p in rows]
        snapshot=await enrich_candidate_routes(db,trip.id,CandidatePlanSnapshot(activities=activities))
        resolution=PlanningIntentResolution.model_validate(original.intent_resolution) if original and original.intent_resolution else None
        result=await validate_candidate_plan(db,trip.id,snapshot,intent_resolution=resolution,required_dates={rows[0][1].date})
        assert result.valid, result.model_dump()
        run=PlanningRun(trip_id=trip.id,run_type='replan',status='validating',user_request='合成候选验收，非模型成功：只改宽窄巷子为13:30、60分钟',base_trip_version=trip.version,intent_resolution=original.intent_resolution if original else None)
        db.add(run)
        await db.flush()
        revision=await save_plan_revision(db,run.id,before_snapshot={},proposed_snapshot=snapshot,
                   reason='合成候选验收：将宽窄巷子推迟半小时，停留缩短至60分钟；固定人民公园、留白和未排程事项保留。此候选不是模型生成成功证据。',
                   difference_summary={'required_day_dates':[str(rows[0][1].date)]},validation_result=result.model_dump(mode='json'),source_ids=[p.source_record_id for _,_,p in rows],enrich_routes=False)
        (out/('synthetic-candidate-stale.json' if stale_case else 'synthetic-candidate.json')).write_text(json.dumps({'revision_id':str(revision.id),'run_id':str(run.id),'generation':'synthetic fixture, no model-success claim','route_enrichment':'actual AMap','validation':result.model_dump(mode='json')},ensure_ascii=False,indent=2),encoding='utf-8')
        print('Saved synthetic candidate through actual route enrichment and Validator:',revision.id)

if __name__ == '__main__':
    mode=sys.argv[1]
    if mode=='init':
        import psycopg
        with psycopg.connect(DSN.rsplit('/',1)[0]+'/postgres',autocommit=True) as db:
            if not db.execute("SELECT 1 FROM pg_database WHERE datname = 'roamsync_product_c_test'").fetchone():
                db.execute('CREATE DATABASE roamsync_product_c_test')
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT/'backend',check=True)
        async def checkpoints():
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            async with AsyncPostgresSaver.from_conn_string(DSN) as saver:
                await saver.setup()
        asyncio.run(checkpoints())
    elif mode=='seed':
        asyncio.run(seed())
    elif mode in {'candidate','candidate-stale'}:
        asyncio.run(candidate())
    elif mode=='api':
        import uvicorn
        asyncio.run(uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',port=18042,log_level='warning')).serve())
    elif mode=='worker':
        from app.agent_worker import main
        asyncio.run(main())
    else:
        raise ValueError('Expected init, seed, api or worker')
