"""Run inside the official API container: one synthetic turn, no database access.

Usage: Get-Content scripts/verify-streaming-provider.py -Raw |
       docker exec -i roamsync-api python -
Only timing/count metadata is printed; no generated text or credentials.
"""
import asyncio
import json
from time import perf_counter

from app.assistant_stream import stream_sink
from app.companion_provider import ModelCompanionProvider
from app.companion_runtime import CompanionRuntime
from app.config import get_settings
from app.travel_goal_router import route_travel_goal


class SyntheticReader:
    async def load(self, context, need):
        return context.model_copy(update={"current_destination": "南京"})


async def main():
    events = []
    started = perf_counter()
    token = stream_sink.set(lambda event: events.append({
        "type": event["type"], "characters": len(event.get("delta", "")),
        "seconds": round(perf_counter() - started, 4)}))
    provider = ModelCompanionProvider()
    report = {"model": get_settings().planner_model, "database_access": False,
              "synthetic_context": True}
    try:
        message = "你好，给第一次独自旅行的人两句鼓励。"
        result = await asyncio.wait_for(CompanionRuntime(SyntheticReader(), provider).run(
            session_id="stream-release-synthetic", turn_id="stream-release-synthetic-turn",
            message=message, goal=route_travel_goal(message), messages=[]), timeout=90)
        duration = round(perf_counter() - started, 4)
        answer = [event for event in events if event["type"] == "answer_delta"]
        assert answer and answer[0]["seconds"] < duration, "No live answer before completion"
        assert result.response_text and provider.observations[-1]["finish_reason"] == "stop"
        report.update(status="passed", duration_seconds=duration, event_count=len(events),
                      answer_event_count=len(answer), first_answer_seconds=answer[0]["seconds"],
                      final_characters=len(result.response_text), finish_reason="stop")
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
    finally:
        stream_sink.reset(token)
    print(json.dumps(report))
    return report["status"] == "passed"


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
