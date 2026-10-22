"""Synthetic raw-response capture with an exclusive, fixed local test database."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = "postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_agent_b_test"


def configure(source):
    from app.config import Settings, get_settings
    settings = Settings(_env_file=source)
    for name in ("planner_provider", "planner_api_key", "planner_model", "planner_base_url", "planner_proxy_url",
                 "amap_rest_key", "tavily_api_key", "roamsync_tavily_api_key", "tavily_base_url", "tavily_proxy_url"):
        value = getattr(settings, name)
        value = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
        os.environ[name.upper()] = value.replace("host.docker.internal", "127.0.0.1")
    if not os.environ.get("PLANNER_PROXY_URL"):
        # Read runtime egress only; no environment values enter the evidence.
        info = json.loads(subprocess.check_output(["docker", "inspect", "roamsync-api"]))[0]
        env = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
        os.environ["PLANNER_PROXY_URL"] = env.get("HTTP_PROXY", "").replace("host.docker.internal", "127.0.0.1")
    os.environ.update(DATABASE_URL=DB, LANGGRAPH_DATABASE_URL=DB.replace("+psycopg", ""), APP_ENV="test",
                      PLANNER_MAX_RETRIES="0", ALLOW_MAP_ESTIMATES="false")
    get_settings.cache_clear()
    return get_settings()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def dialogue_run(args, settings, output):
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.database import Base, AssistantSession, Trip, Activity, PlanningRun, PlanRevision, SavedIntention
    from app.assistant_service import send_message
    from app.assistant_places import ContentServicePlaces
    from app.assistant_capabilities import select_capabilities
    from app.place_content.service import PlaceContentService
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository, metadata as content_metadata

    assert settings.database_url == DB
    sync = create_engine(DB, poolclass=NullPool)
    Base.metadata.create_all(sync)
    content_metadata.create_all(sync)
    engine = create_async_engine(DB, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = ROOT / "evals/fixtures/agent_b_20261022.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    cases = [c for c in data[args.split] if not args.case or c["id"] == args.case]
    replay = json.loads(args.replay.read_text(encoding="utf-8")) if args.replay else None
    report = {"split": args.split, "label": args.label, "source_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "model": settings.planner_model, "provider": settings.planner_provider, "synthetic": True, "records": []}
    async def counts():
        async with factory() as db:
            return {m.__name__: await db.scalar(select(func.count()).select_from(m))
                    for m in (Trip, Activity, PlanningRun, PlanRevision, SavedIntention)}
    report["before"] = await counts()
    dump(output, report)
    semaphore = asyncio.Semaphore(2)
    async def scenario(case):
        async with semaphore:
            async with factory() as db:
                previous = [r["raw"] for r in replay["records"] if r["case"] == case["id"] and r["turn"] < args.from_turn] if replay else []
                row = AssistantSession(messages=previous, applied_actions={})
                db.add(row)
                await db.commit()
                sid = row.id
            for index, message in enumerate(case["turns"], 1):
                if index < args.from_turn:
                    continue
                calls, choices = [], []
                port = ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key), ContentRepository(sync)), owner="agent-b-synthetic")
                for name in ("get_place", "search", "research_search", "query_route"):
                    if not hasattr(port, name):
                        continue
                    original = getattr(port, name)
                    async def observed(*a, _name=name, _fn=original, **kw):
                        call = {"tool": _name, "args": a, "kwargs": kw}
                        calls.append(call)
                        start = time.monotonic()
                        try:
                            value = await _fn(*a, **kw)
                            call["result"] = [p.model_dump(mode="json") for p in value] if isinstance(value, list) else value.model_dump(mode="json") if hasattr(value, "model_dump") else value
                            return value
                        except Exception as exc:
                            call["error_type"] = type(exc).__name__
                            raise
                        finally:
                            call["seconds"] = round(time.monotonic() - start, 3)
                    setattr(port, name, observed)
                async def selector(*a):
                    value = await select_capabilities(*a)
                    choices.append(value.model_dump(mode="json"))
                    return value
                record = {"case": case["id"], "turn": index, "user": message, "session_id": str(sid)}
                start = time.monotonic()
                try:
                    async with factory() as db:
                        row = await asyncio.wait_for(send_message(db, sid, message, uuid4(),
                            context={"topic_id": "agent-b", "prefer_flexible": True},
                            place_port=port, capability_selector=selector), timeout=150)
                        record.update(raw=row.messages[-1], trip_id=str(row.trip_id) if row.trip_id else None,
                                      pending_action=row.pending_action, latest_run_id=str(row.latest_run_id) if row.latest_run_id else None)
                except Exception as exc:
                    record["error_type"] = type(exc).__name__
                record.update(seconds=round(time.monotonic() - start, 3), choices=choices, calls=calls)
                report["records"].append(record)
                dump(output, report)
                print(json.dumps({"case": case["id"], "turn": index, "seconds": record["seconds"], "error": record.get("error_type")}), flush=True)
    try:
        await asyncio.gather(*(scenario(case) for case in cases))
        report["after"] = await counts()
        dump(output, report)
    finally:
        await engine.dispose()
        sync.dispose()


async def matched_run(args, settings, output):
    from app.assistant_context import ContextEnvelope
    from app.assistant_memory import apply_memory, MemoryUpdate
    from app.assistant_places import PlaceView
    from app.assistant_research import research, LookupIntent
    from app.assistant_reliability import TurnDiagnostics, active_turn
    from app.external_facts import SearchFact
    # Explicitly synthetic supplied material, held identical before/after.
    places = [PlaceView(place_id=uuid4(), name=name, city="柳州", category="food", address="合成测试地址",
                       reference_cost_yuan=cost, source="https://example.org/synthetic", retrieved_at="2026-10-22T08:00:00Z")
              for name, cost in (("测试甲店", 95), ("测试乙店", 42), ("测试丙店", None))]
    class Port:
        async def research_search(self, **kw):
            return places
    async def judge(*a):
        return LookupIntent(needed=True, city="柳州", query="餐厅", category="food", read_pages=False)
    async def no_search(*a, **kw):
        return SearchFact("fixture", "2026-10-22", "synthetic", {"results": []})
    env, _, _ = apply_memory(ContextEnvelope(browsing_city="柳州"), [], "完全不吃辣，晚饭人均最多60元", uuid4(), [
        MemoryUpdate(field="preferences", operation="add", value="完全不吃辣", source_quote="完全不吃辣"),
        MemoryUpdate(field="budget", value="晚饭人均最多60元", source_quote="晚饭人均最多60元")])
    # Condition source falls outside Research's eight-message prompt window.
    history = [{"user": "完全不吃辣，晚饭人均最多60元"}, *[{"user": "先聊城市文化"} for _ in range(9)]]
    report = {"label": args.label, "synthetic_material_configured_real_model_pipeline": True, "records": []}
    for name, current in (("bounded-budget", env), ("budget-withdrawn", apply_memory(env, history,
        "取消晚饭预算，忌口保留", uuid4(), [MemoryUpdate(field="budget", operation="clear", source_quote="取消晚饭预算")])[0])):
        turn = TurnDiagnostics(str(uuid4()))
        token = active_turn.set(turn)
        started = time.monotonic()
        try:
            bundle = await research(settings, "按我的条件比较这三家，先选晚餐候选", history, current, Port(), judge=judge, search=no_search)
            report["records"].append({"case": name, "raw": bundle, "seconds": time.monotonic()-started, "trace": turn.summary("captured")})
        finally:
            active_turn.reset(token)
        dump(output, report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "holdout", "matched"), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--settings-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case")
    parser.add_argument("--from-turn", type=int, default=1)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    if args.from_turn != 1 and (not args.replay or not args.case):
        raise SystemExit("Tail replay requires a source trace and one named development case")
    if args.split == "holdout" and (args.replay or args.case or args.from_turn != 1):
        raise SystemExit("Holdout must run intact")
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an earlier raw run")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    settings = configure(args.settings_source)
    asyncio.run(matched_run(args, settings, args.output) if args.split == "matched" else dialogue_run(args, settings, args.output))


if __name__ == "__main__":
    main()
