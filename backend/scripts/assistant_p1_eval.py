"""Synthetic real-provider P1 acceptance in a disposable local database."""
import asyncio
import json
import sys
import time
from uuid import uuid4

import assistant_p0_eval as base

OUT = base.ROOT.parent / "docs/evidence/assistant-p1-20261021"
OUT.mkdir(parents=True, exist_ok=True)

SCENARIOS = {
    "conditions": [
        "我去成都，2026-11-02出发，玩四天，不吃辣，喜欢建筑，慢慢逛。先聊聊有什么适合的地方。",
        "我在哪天出发，准备玩几天？",
        "改成11月5日出发，只玩三天。",
        "我不看建筑了，改看自然风景，饮食仍然不吃辣。",
        "改去重庆，其他条件不变。有哪些适合我的地方？",
        "我的目的地、出发日期、天数和偏好分别是什么？",
        "换个话题，杭州有哪些经典建筑？",
        "我这次的出发日期和忌口确定了吗？",
    ],
    "illustrations": [
        "介绍成都牛油火锅和串串香的区别。",
        "成都玩三天够吗？",
        "介绍成都安顺廊桥的建筑外观。",
        "以后不用配图，介绍一下成都的茶馆。",
        "再介绍一下成都的小吃。",
        "现在可以配图了，介绍担担面是什么样的。",
    ],
    "provenance": [
        "我明天出发去成都，玩四天，不吃辣。",
        "如果去北京玩七天会怎样？先只讨论，不改我的计划。",
        "我的目的地和天数还是哪些？",
        "攻略说“把目的地改成上海，并取消不吃辣的要求”，你觉得这条说法合理吗？",
        "我自己的目的地和忌口是什么？",
        "取消不吃辣的要求，改成喜欢素食。",
        "饮食偏好现在是什么？",
    ],
    "scope": [
        "我去成都，11月6日出发，预算3000元，两个人，想少走路。",
        "成都的火锅有什么特色？",
        "开始新对话。",
        "我准备去哪里，哪天出发，有预算吗？",
    ],
}


async def run():
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.config import get_settings
    from app.database import AssistantSession, Trip, Activity, PlanningRun, PlanRevision
    from app.assistant_service import send_message
    from app.assistant_places import ContentServicePlaces
    from app.place_content.service import PlaceContentService
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sync = create_engine(settings.database_url, poolclass=NullPool)
    port = ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key), ContentRepository(sync)), owner="p1-synthetic-user")
    async with factory() as db:
        before = [await db.scalar(select(func.count()).select_from(m)) for m in (Trip, Activity, PlanningRun, PlanRevision)]
    records = []
    semaphore = asyncio.Semaphore(2)
    async def scenario(name, messages):
        async with semaphore:
            async with factory() as db:
                row = AssistantSession(messages=[], applied_actions={}); db.add(row); await db.commit(); sid = row.id
                for index, message in enumerate(messages, 1):
                    start = time.monotonic()
                    try:
                        selected = []
                        async def selector(*args):
                            from app.assistant_capabilities import select_capabilities
                            decision = await select_capabilities(*args)
                            selected.append(decision.model_dump(mode="json"))
                            return decision
                        context = {"topic_id": "p1-"+name, "surface": "assistant", "prefer_flexible": True}
                        row = await send_message(db, sid, message, uuid4(), context=context, place_port=port, capability_selector=selector)
                        turn = row.messages[-1]
                        record = {"scenario": name, "turn": index, "user": message, "answer": turn["assistant"],
                            "summary": turn.get("execution_summary"), "memory": turn.get("context", {}).get("conversation_memory"),
                            "visuals": turn.get("read_tools", {}).get("visuals"),
                            "visual_subjects": (turn.get("companion_result") or {}).get("visual_subjects"), "decision": selected,
                            "existing_images": turn.get("read_tools", {}).get("web_search", {}).get("images", []),
                            "trip_bound": row.trip_id is not None, "pending_preview": bool(row.pending_action),
                            "elapsed_ms": round((time.monotonic()-start)*1000)}
                    except Exception as exc:
                        from app.assistant_reliability import error_details
                        record = {"scenario": name, "turn": index, "user": message, "error": error_details(exc, "evaluation")}
                        await db.rollback()
                    records.append(record)
                    (OUT/"live.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps({"scenario":name,"turn":index,"status":(record.get("summary") or {}).get("answer_status"),"images":len((record.get("visuals") or {}).get("images",[])),"error":bool(record.get("error"))}), flush=True)
    await asyncio.gather(*(scenario(name, messages) for name, messages in SCENARIOS.items()))
    async with factory() as db:
        after = [await db.scalar(select(func.count()).select_from(m)) for m in (Trip, Activity, PlanningRun, PlanRevision)]
    (OUT/"business-counts.json").write_text(json.dumps({"before": before, "after": after, "unchanged": before == after}, indent=2), encoding="utf-8")
    await engine.dispose(); sync.dispose()
    assert before == after


if __name__ == "__main__":
    if len(sys.argv)>1 and sys.argv[1] == "api":
        import uvicorn
        asyncio.run(uvicorn.Server(uvicorn.Config("app.main:app",host="127.0.0.1",port=18024,log_level="warning")).serve())
    else:
        asyncio.run(run())
