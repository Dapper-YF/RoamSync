"""New real-model contrasts over synthetic nonprivate planning inputs.

Actual AMap POI/route and Open-Meteo responses are recorded separately from
controlled forecasts, user requirements and a synthetic locked activity.
Never reads or writes a Trip, Run, Revision, Accept or execution row.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import time
import uuid
from zoneinfo import ZoneInfo

from app.candidate_decisions import review_candidate_decisions, weather_days
from app.config import get_settings
from app.external_facts import fetch_open_meteo
from app.openai_planner import OpenAIResponsesPlanner
from app.place_content.contracts import RouteQuery, SearchQuery
from app.place_content.provider import AMapContentProvider
from evals.run_bounded_decision_eval import _state


def _minutes(value: str) -> int:
    hour, minute = value[:5].split(":")
    return int(hour) * 60 + int(minute)


async def run(output: Path) -> dict:
    settings = get_settings().model_copy(update={"planner_max_output_tokens": 6000, "planner_max_retries": 0})
    now = datetime.now(UTC)
    day_date = (now.astimezone(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)).isoformat()
    report = {"version": "next-round-real-model-v1", "started_at": now.isoformat(), "provider": settings.planner_provider,
              "model": settings.planner_model, "database_writes": 0,
              "boundary": "synthetic_nonprivate_inputs_direct_planner_no_Graph_Validator_Accept_or_execution",
              "actual_provider_facts": {}, "calls": []}
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    content = AMapContentProvider(settings.amap_rest_key)
    places = []
    for query in ("西湖风景名胜区", "中国丝绸博物馆", "雷峰塔景区"):
        result = await content.search(SearchQuery(query=query, city="杭州", page_size=5))
        exact = [item for item in result.items if item.name.removeprefix("杭州市").removeprefix("杭州") == query]
        if len(exact) != 1:
            report["actual_provider_facts"]["place_failure"] = {"query": query, "exact_count": len(exact)}
            save()
            return report
        place = exact[0]
        places.append(place)
        report["actual_provider_facts"].setdefault("places", []).append({"query": query, "id": str(place.ref.place_id),
            "external_id": place.ref.external_ref.provider_place_id, "name": place.name, "provider_type": place.provider_type,
            "rating": place.rating, "source": place.source.model_dump(mode="json")})
    routes = {}
    for place in places[:2]:
        result = await content.route(RouteQuery(origin=place.location, destination=places[2].location, mode="walk"))
        routes[str(place.ref.place_id)] = {"duration_minutes": (result.duration_seconds + 59) // 60,
            "distance_meters": result.distance_meters, "expires_at": result.source.expires_at.isoformat(),
            "provider": result.source.provider}
    report["actual_provider_facts"]["routes_candidate_to_anchor"] = routes
    try:
        weather = await fetch_open_meteo(settings, latitude=30.2741, longitude=120.1551,
                                         start_date=datetime.fromisoformat(day_date).date(),
                                         end_date=datetime.fromisoformat(day_date).date(), timezone="Asia/Shanghai")
        observed = {"weather": {"status": "available", "provider": weather.provider, "queried_at": weather.queried_at,
                                 "payload": weather.payload}}
        probe, _, _ = _state()
        probe["planning_context"]["trip"]["timezone"] = "Asia/Shanghai"
        probe["planning_context"]["days"][0]["date"] = day_date
        probe["planning_context"]["external_facts"] = observed
        report["actual_provider_facts"]["weather"] = {"status": "available", "day_summary": weather_days(probe["planning_context"]),
            "scope": "representative_city_coordinate_prediction_not_venue_observation"}
    except Exception as exc:
        report["actual_provider_facts"]["weather"] = {"status": "unavailable", "code": getattr(exc, "code", type(exc).__name__)}
    save()

    state, _, _ = _state()
    ctx = state["planning_context"]
    ctx["trip"].update(id=state["trip_id"], destination="杭州", start_date=day_date, end_date=day_date,
                       total_budget_fen=None, daily_budget_fen=None)
    day = ctx["days"][0]
    day.update(id=str(uuid.uuid4()), date=day_date)
    fixed = day["activities"][0]
    fixed.update(place_id=str(places[2].ref.place_id), display_name=places[2].name,
                 longitude=places[2].location.longitude, latitude=places[2].location.latitude,
                 scheduled_time="14:00", duration_minutes=60, status="planned", schedule_locked=True)
    ctx["preferences"].update(daily_start_time="09:00", daily_end_time="18:00", interest_categories=["nature"],
                              max_walking_minutes=1000, requirement_records=[])
    ctx["planning_goals"] = {"target_days": [day_date], "hard_goals": {}, "soft_goals": {}}
    ctx["candidates"] = [{"id": str(place.ref.place_id), "name": place.name,
        "category": "nature" if index == 0 else "culture", "neighborhood": place.district or "",
        "description": place.address or "", "longitude": place.location.longitude, "latitude": place.location.latitude,
        "suggested_duration_minutes": 120 if index == 0 else 60, "estimated_cost_fen": 0, "rating": place.rating or 0,
        "tags": (place.provider_type or "").split(";"), "source": {"id": str(uuid.uuid4()), "provider": "AMap POI",
        "url": f"https://www.amap.com/search?id={place.ref.external_ref.provider_place_id}", "confidence": "high"}}
        for index, place in enumerate(places[:2])]
    ctx["candidate_route_facts"] = [{"candidate_id": key, "date": day_date, "to_activity_id": fixed["id"],
        "direction": "candidate_to_fixed_activity", "mode": "walk", "status": "available", "is_estimated": False,
        "duration_minutes": route["duration_minutes"], "distance_meters": route["distance_meters"],
        "provider": "amap", "expires_at": route["expires_at"]} for key, route in routes.items()]

    scenarios = ("dry_baseline", "late_rain_dry_slot", "all_visit_hours_rain", "weather_missing",
                 "shorter_verified_walk", "hard_avoid_nature", "revoked_avoid_nature")
    for scenario in scenarios:
        case = deepcopy(state)
        c = case["planning_context"]
        c["effective_requirements_by_date"] = {day_date: []}
        rain = [0] * 9
        if scenario == "late_rain_dry_slot":
            rain[-1] = 80
        elif scenario == "all_visit_hours_rain":
            rain = [80] * 9
        if scenario != "weather_missing":
            c["external_facts"] = {"weather": {"status": "available", "provider": "open_meteo",
                "queried_at": datetime.now(UTC).isoformat(), "payload": {"timezone": "Asia/Shanghai",
                "hourly": {"time": [f"{day_date}T{hour:02d}:00" for hour in range(9, 18)],
                           "precipitation_probability": rain}}}}
        c["weather_sensitive"] = scenario in {"dry_baseline", "late_rain_dry_slot", "all_visit_hours_rain", "weather_missing"}
        if scenario == "shorter_verified_walk":
            c["planning_goals"]["soft_goals"] = {"minimize_walking": True}
        if scenario == "hard_avoid_nature":
            record = {"id": "eval-hard-avoid", "key": "avoid_category", "value": "nature", "text": "避开自然类",
                      "strength": "hard", "status": "active", "source": {"kind": "user_explicit", "ref": "synthetic-eval"},
                      "scope": {"kind": "day", "date": day_date}}
            c["effective_requirements_by_date"][day_date] = [record]
            c["effective_requirements"] = [record]
            c["preferences"]["requirement_records"] = [record]
        case["user_request"] = "只在14点锁定活动之前新增一个可行地点，保留建议停留和已查步行路线；偏好西湖景观摄影，若有有效硬要求则遵守。仅生成待确认候选，不声称锁定等于订票。"
        started = time.monotonic()
        entry = {"scenario": scenario, "condition_kind": "controlled_synthetic", "input_rain_probability": rain if scenario != "weather_missing" else None,
                 "requirements": [item["id"] for item in c["effective_requirements_by_date"][day_date]],
                 "walking_goal": scenario == "shorter_verified_walk"}
        try:
            planner = OpenAIResponsesPlanner(settings)
            generated = await planner.generate(case)
            chosen = [item for item in generated.snapshot.activities if str(item.place_candidate_id) in routes]
            schedule = []
            for item in chosen:
                route = routes[str(item.place_candidate_id)]
                end = _minutes(str(item.planned_start_time)) + item.duration_minutes
                fits = end + route["duration_minutes"] <= _minutes(c["days"][0]["activities"][0]["scheduled_time"])
                schedule.append({"place": next(place["name"] for place in c["candidates"] if place["id"] == str(item.place_candidate_id)),
                                 "start": str(item.planned_start_time), "duration_minutes": item.duration_minutes,
                                 "route_to_locked_minutes": route["duration_minutes"], "before_locked_with_route": fits})
            review = review_candidate_decisions(c, generated.snapshot)
            entry.update(status="completed", selected_schedule=schedule, selected_count=len(chosen),
                         token_usage=generated.token_usage, hard_errors=review["hard_errors"],
                         reliability={key: planner.last_reliability.get(key) for key in
                                      ("parse_success", "reference_resolution_success", "attempts")})
        except Exception as exc:
            entry.update(status="failed", code=getattr(exc, "code", type(exc).__name__))
        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["calls"].append(entry)
        save()
        print(json.dumps({"scenario": scenario, "status": entry["status"], "elapsed_seconds": entry["elapsed_seconds"]}), flush=True)
    report["completed_at"] = datetime.now(UTC).isoformat()
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output))
