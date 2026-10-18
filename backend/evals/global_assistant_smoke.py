"""Opt-in public Place + real Companion smoke; no formal DB or writes.

uv run python evals/global_assistant_smoke.py --env-file E:/Study/RoamSync/.env
  --b-app-path E:/Study/RoamSync-v2-data/backend/app --output evidence.json
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path


async def main(args):
    from dotenv import dotenv_values
    for key, value in dotenv_values(args.env_file).items():
        if value is not None and (key.startswith("PLANNER_") or key == "AMAP_REST_KEY"):
            os.environ[key] = value
    if args.local_proxy_url:
        os.environ["PLANNER_PROXY_URL"] = args.local_proxy_url
    os.environ["DATABASE_URL"] = "postgresql+psycopg://disabled:disabled@127.0.0.1:1/disabled"
    os.environ["LANGGRAPH_DATABASE_URL"] = "postgresql://disabled:disabled@127.0.0.1:1/disabled"
    import app
    if args.b_app_path:
        sys.dont_write_bytecode = True
        app.__path__.append(args.b_app_path)
    from sqlalchemy import create_engine
    from app.config import get_settings
    from app.place_content.contracts import SearchQuery
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository, metadata
    from app.place_content.service import PlaceContentService
    from app.assistant_context import ContextEnvelope
    from app.assistant_places import ContentServicePlaces, load_places, place_cards
    from app.companion_runtime import CompanionRuntime
    from app.companion_provider import ModelCompanionProvider
    from app.travel_goal_router import route_travel_goal

    class ReadOnlyContext:
        async def load(self, context, need):
            return context

    report = {"formal_database": "disabled", "content_database": "sqlite_memory", "model_called": False, "model_attempted": False}
    from sqlalchemy.pool import StaticPool
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    started = time.perf_counter()
    try:
        service = PlaceContentService(AMapContentProvider(get_settings().amap_rest_key), ContentRepository(engine))
        found = await service.search(SearchQuery(query="餐厅", city="杭州", page_size=3))
        if not found.items:
            raise ValueError("no_real_place_results")
        selected = found.items[0]
        envelope = ContextEnvelope(topic_id="real-smoke", browsing_city="杭州", discussing_place_id=selected.ref.place_id)
        focus, places, gaps = await load_places(ContentServicePlaces(service), envelope, "这家值得去吗")
        if focus is None:
            raise ValueError("place_not_verified")
        report.update(place=focus.model_dump(mode="json"), model_attempted=True)
        provider = ModelCompanionProvider(capture_visible_outputs=True)
        message = "这家适合什么样的旅行者？请结合当前地点简短回答，不安排正式行程。"
        result = await CompanionRuntime(ReadOnlyContext(), provider, knowledge_strategy="general_only").run(
            session_id="public-real-smoke", turn_id="public-turn-1", message=message,
            goal=route_travel_goal(message), messages=[], assistant_context=envelope.model_dump(mode="json"),
            place_context=[p.model_dump(mode="json") for p in places])
        report.update(status="completed", model_called=bool(provider.observations),
            place=focus.model_dump(mode="json"), response=result.response_text,
            place_cards=place_cards(result, places, focus), limitations=gaps,
            observations=provider.observations, result_status=result.status)
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__, error_code=getattr(exc, "code", None))
    finally:
        engine.dispose()
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "model_called", "elapsed_seconds")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--b-app-path")
    parser.add_argument("--output", required=True)
    parser.add_argument("--local-proxy-url", help="Optional local-only model proxy override; does not modify configuration")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args))
