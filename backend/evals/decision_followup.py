"""Fresh real-Provider/model walking contrasts; no database writes.

This direct generation diagnostic is not Graph/Validator/Accept acceptance.
Unknown venue operations and city weather remain unknown, not controlled facts.
"""
import argparse
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import time
import uuid
from zoneinfo import ZoneInfo

from app.candidate_decisions import review_candidate_decisions, unsupported_decision_claims
from app.config import get_settings
from app.openai_planner import OpenAIResponsesPlanner
from app.place_content.contracts import RouteQuery, SearchQuery
from app.place_content.provider import AMapContentProvider
from evals.run_bounded_decision_eval import _state


async def run(output: Path):
    if output.exists():
        raise FileExistsError("Preserve prior evidence")
    settings = get_settings().model_copy(update={"planner_max_output_tokens": 6000})
    report = {"started_at": datetime.now(UTC).isoformat(), "model": settings.planner_model,
              "database_writes": 0, "boundary": "direct_Planner_not_Graph_Validator_Accept",
              "calls": [], "fact_limits": ["one_directed_walk_leg_not_day_total", "no_booking_or_opening_verification"]}
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    provider = AMapContentProvider(settings.amap_rest_key)
    places = []
    for query in ("西湖风景名胜区", "中国丝绸博物馆", "雷峰塔景区"):
        response = await provider.search(SearchQuery(query=query, city="杭州", page_size=5))
        matches = [p for p in response.items if p.name.removeprefix("杭州市").removeprefix("杭州") == query]
        if len(matches) != 1:
            raise ValueError("Exact provider identity unavailable")
        places.append(matches[0])
    report["places"] = [{"id": str(p.ref.place_id), "name": p.name, "provider_id": p.ref.external_ref.provider_place_id,
                          "source": p.source.model_dump(mode="json")} for p in places]
    state, _, _ = _state()
    ctx = state["planning_context"]
    day_date = (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)).isoformat()
    ctx["trip"].update(id=state["trip_id"], destination="杭州", start_date=day_date, end_date=day_date,
                       total_budget_fen=None, daily_budget_fen=None)
    ctx["days"][0]["date"] = day_date
    anchor = ctx["days"][0]["activities"][0]
    anchor.update(place_id=str(places[2].ref.place_id), display_name=places[2].name,
        longitude=places[2].location.longitude, latitude=places[2].location.latitude)
    ctx["preferences"].update(requirement_records=[])
    ctx["planning_goals"] = {"target_days": [day_date], "hard_goals": {}, "soft_goals": {"minimize_walking": True}}
    ctx["candidates"] = [{"id": str(p.ref.place_id), "name": p.name, "category": "nature" if i == 0 else "culture",
        "neighborhood": p.district or "", "description": p.address or "", "longitude": p.location.longitude,
        "latitude": p.location.latitude, "suggested_duration_minutes": 120 if i == 0 else 60,
        "estimated_cost_fen": 0, "rating": p.rating or 0, "tags": (p.provider_type or "").split(";"),
        "source": {"id": str(uuid.uuid4()), "provider": "AMap POI", "confidence": "high", "url": p.source.source_url}}
        for i, p in enumerate(places[:2])]
    ctx["candidate_route_facts"] = []
    for p in places[:2]:
        route = await provider.route(RouteQuery(origin=p.location, destination=places[2].location, mode="walk"))
        ctx["candidate_route_facts"].append({"candidate_id": str(p.ref.place_id), "date": day_date,
            "to_activity_id": anchor["id"], "direction": "candidate_to_fixed_activity", "mode": "walk",
            "status": "available", "is_estimated": False, "provider": "amap",
            "duration_minutes": (route.duration_seconds + 59) // 60, "distance_meters": route.distance_meters,
            "expires_at": route.source.expires_at.isoformat()})
    report["routes"] = ctx["candidate_route_facts"]
    save()
    for name, interests, request in (
        ("walking_only", [], "只在14点固定活动之前新增一个地点，尽量少走路，保留建议停留。没有指定景点或类别偏好。"),
        ("walking_and_landscape", ["nature"], "只在14点固定活动之前新增一个地点，尽量少走路，但也喜欢景观摄影；保留建议停留，解释真实取舍。"),
        ("landscape_priority", ["nature"], "只在14点固定活动之前新增一个地点；景观体验比少走路更重要，可以为景观接受额外步行，保留建议停留。")):
        case = deepcopy(state)
        case["planning_context"]["preferences"]["interest_categories"] = interests
        case["user_request"] = request
        row = {"scenario": name, "request": request, "saved_interest_categories": interests}
        started = time.monotonic()
        planner = OpenAIResponsesPlanner(settings)
        try:
            result = await planner.generate(case)
            row.update(status="completed", snapshot=result.snapshot.model_dump(mode="json"),
                review=review_candidate_decisions(case["planning_context"], result.snapshot),
                claim_errors=unsupported_decision_claims(case["planning_context"], result.snapshot),
                token_usage=result.token_usage, reliability=planner.last_reliability)
        except Exception as exc:
            row.update(status="failed", code=getattr(exc, "code", type(exc).__name__), reliability=getattr(planner, "last_reliability", {}))
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["calls"].append(row)
        save()
        print(json.dumps({"scenario": name, "status": row["status"]}), flush=True)
    report["completed_at"] = datetime.now(UTC).isoformat()
    save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
