"""One synthetic real-provider turn, no database or formal itinerary writes."""
import asyncio
import json
from pathlib import Path
from time import perf_counter

from app.assistant_stream import stream_sink
from app.companion_runtime import CompanionRuntime
from app.config import get_settings
from app.travel_goal_router import route_travel_goal


class FixtureReader:
    async def load(self, context, need):
        return context.model_copy(update={
            "current_destination": "南京",
            "trip_summary": {"version": 2, "destination": "南京"},
            "saved_trip_preferences": {"pace": "balanced", "interest_categories": ["history", "museum", "nature", "food"]},
            "formal_itinerary_summary": [
                {"name": "明孝陵", "date": "2026-10-11", "time": "09:00", "duration_minutes": 120},
                {"name": "美龄宫", "date": "2026-10-11", "time": "12:30", "duration_minutes": 90},
                {"name": "南京博物院", "date": "2026-10-11", "time": "15:00", "duration_minutes": 120},
                {"name": "鸡鸣寺", "date": "2026-10-12", "time": "09:00", "duration_minutes": 120},
                {"name": "玄武湖", "date": "2026-10-12", "time": "11:41", "duration_minutes": 120},
                {"name": "总统府", "date": "2026-10-12", "time": "15:00", "duration_minutes": 120},
                {"name": "颐和路", "date": "2026-10-12", "time": "17:13", "duration_minutes": 60}],
            "saved_plan_notes": {"status": "accepted", "revision_id": "synthetic-fixture", "trip_version": 2,
                "model_notes_verified": False, "reasons": ["按区域与体验主线分天，室内户外交替。方案尚未保存，确认后由系统提交。"]}})


async def run(output):
    settings = get_settings()
    # The Docker hostname is not a native Windows host. Process-local only.
    settings.planner_proxy_url = settings.planner_proxy_url.replace("host.docker.internal", "127.0.0.1")
    started = perf_counter()
    events = []
    token = stream_sink.set(lambda e: events.append({**e, "elapsed_seconds": round(perf_counter() - started, 3)}))
    report = {"model": settings.planner_model, "fixture": "synthetic_nanjing", "database_access": False,
        "proxy_mode": "native_windows_process_local", "events": events}
    try:
        question = "为什么会这样安排？第二天会不会有些折返？"
        result = await CompanionRuntime(FixtureReader()).run(session_id="synthetic-stream", turn_id="synthetic-turn",
            message=question, goal=route_travel_goal(question), messages=[])
        report.update(status="completed", result=result.model_dump(mode="json"),
            duration_seconds=round(perf_counter() - started, 3))
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__,
            error_code=getattr(exc, "code", None), duration_seconds=round(perf_counter() - started, 3))
    finally:
        stream_sink.reset(token)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "duration_seconds")}, ensure_ascii=False))
    print("public_stream_events:", len(events))


if __name__ == "__main__":
    asyncio.run(run(Path("backend/evals/results/companion_stream_20261012/provider_smoke.json")))
