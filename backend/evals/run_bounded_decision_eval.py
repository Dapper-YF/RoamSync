"""Six bounded real-model decisions; synthetic conditions are NEVER live facts.

Run with configured provider credentials and --output. No Trip/Run/Revision,
approval, execution or DB writes. Fixture wiring tests are a separate artifact.
"""
import argparse
import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import time
import uuid

from app.config import get_settings
from app.external_facts import fetch_open_meteo
from app.openai_planner import OpenAIResponsesPlanner
from app.candidate_decisions import review_candidate_decisions, weather_days
from app.place_content.provider import AMapContentProvider
from app.place_content.contracts import SearchQuery, RouteQuery


def _state():
    # Public synthetic eval scaffold; no saved trip or private conversation.
    identity = lambda: str(uuid.uuid4())
    return {"run_id": identity(), "trip_id": identity(), "user_request": "", "intent_resolution": {"request": {"intent": {
        "intent_type": "modify_day", "source_text": "", "time_scope": None, "protected_activity_ids": [],
        "requested_place_queries": [], "requested_pace": None, "missing_fields": [], "ambiguities": []}}},
        "planning_context": {"trip": {"accommodation": "", "currency": "CNY", "timezone": "Asia/Shanghai"},
            "preferences": {"pace": "balanced", "interest_categories": [], "transport_modes": ["walk"], "daily_start_time": "09:00",
                "daily_end_time": "18:00", "meal_preferences": "", "avoid_categories": [], "max_walking_minutes": 1000, "free_text_requirements": ""},
            "days": [{"date": "2026-10-17", "label": "测试日", "theme": "", "route_mode": "walk", "activities": [{
                "id": identity(), "place_id": identity(), "display_name": "固定测试活动", "category": "culture", "neighborhood": "",
                "longitude": 120.0, "latitude": 30.0, "scheduled_time": "14:00", "duration_minutes": 60, "importance": "normal",
                "estimated_cost_fen": 0, "status": "planned", "schedule_locked": True, "source": {"id": identity()}}]}], "candidates": []}}, None, None


async def run(output):
    settings = get_settings().model_copy(update={"planner_max_output_tokens": 6000, "planner_max_retries": 0})
    report = {"version": "bounded-decision-real-eval-v1", "started_at": datetime.now(UTC).isoformat(),
              "provider": settings.planner_provider, "model": settings.planner_model, "reasoning_effort": settings.planner_reasoning_effort, "database_writes": 0,
              "boundary": "synthetic_nonprivate_planner_inputs_no_graph_validator_accept_or_execution",
              "live_facts": {}, "controlled_conditions": [], "calls": [], "pairs": []}
    def save():
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    save()
    content = AMapContentProvider(settings.amap_rest_key)
    places = []
    for query in ["西湖风景名胜区", "中国丝绸博物馆", "雷峰塔景区"]:
        started = time.monotonic()
        try:
            result = await content.search(SearchQuery(query=query, city="杭州", page_size=5))
            report["live_facts"].setdefault("place_search_names", {})[query] = [place.name for place in result.items]
            exact = [place for place in result.items if place.name.removeprefix("杭州市").removeprefix("杭州") == query
                     or place.name.startswith(query + "(")]
            if len(exact) != 1:
                raise ValueError("exact_place_not_unique")
            places.append(exact[0])
            report["live_facts"].setdefault("places", []).append({"query": query, "place": exact[0].model_dump(mode="json"), "elapsed_seconds": round(time.monotonic()-started, 3)})
        except Exception as exc:
            report["live_facts"]["failure"] = {"stage": "place", "query": query, "code": getattr(exc, "code", type(exc).__name__)}
            save()
            return report
    anchor = places[2]
    tomorrow = datetime.now().date() + timedelta(days=1)
    state, _, _ = _state()
    ctx = state["planning_context"]
    ctx["trip"].update(id=state["trip_id"], destination="杭州", start_date=tomorrow.isoformat(), end_date=tomorrow.isoformat(), total_budget_fen=None, daily_budget_fen=None)
    day = ctx["days"][0]
    ctx["days"] = [day]
    day.update(id=str(uuid.uuid4()), date=tomorrow.isoformat())
    fixed = day["activities"][0]
    fixed.update(place_id=str(anchor.ref.place_id), display_name=anchor.name, category="culture", status="planned", scheduled_time="14:00", duration_minutes=60,
                 longitude=anchor.location.longitude, latitude=anchor.location.latitude)
    ctx["preferences"].update(daily_start_time="09:00", daily_end_time="18:00", interest_categories=[], max_walking_minutes=1000, requirement_records=[])
    ctx["planning_goals"] = {"target_days": [tomorrow.isoformat()], "hard_goals": {}, "soft_goals": {}}
    ctx["candidates"] = [{"id": str(place.ref.place_id), "name": place.name, "category": "nature" if index == 0 else "culture", "neighborhood": place.district or "", "description": place.address or "",
        "longitude": place.location.longitude, "latitude": place.location.latitude, "suggested_duration_minutes": 120 if index == 0 else 60,
        "estimated_cost_fen": 0, "rating": place.rating or 0, "tags": (place.provider_type or "").split(";"),
        "source": {"id": str(uuid.uuid4()), "provider": "AMap POI", "confidence": "high"}} for index, place in enumerate(places[:2])]
    ctx["candidate_route_facts"] = []
    for place in places[:2]:
        try:
            route = await content.route(RouteQuery(origin=place.location, destination=anchor.location, mode="walk"))
            ctx["candidate_route_facts"].append({"candidate_id": str(place.ref.place_id), "date": tomorrow.isoformat(), "to_activity_id": fixed["id"],
                "direction": "candidate_to_fixed_activity", "mode": "walk", "status": "available", "duration_minutes": (route.duration_seconds + 59)//60,
                "distance_meters": route.distance_meters, "provider": "amap", "is_estimated": False, "expires_at": route.source.expires_at.isoformat()})
        except Exception as exc:
            ctx["candidate_route_facts"].append({"candidate_id": str(place.ref.place_id), "date": tomorrow.isoformat(), "status": "unknown", "reason": getattr(exc, "code", type(exc).__name__)})
    report["live_facts"]["routes"] = ctx["candidate_route_facts"]
    try:
        weather = await fetch_open_meteo(settings, latitude=30.2741, longitude=120.1551, start_date=tomorrow, end_date=tomorrow, timezone="Asia/Shanghai")
        ctx["external_facts"] = {"weather": {"status": "available", "provider": weather.provider, "queried_at": weather.queried_at, "latitude": weather.latitude, "longitude": weather.longitude, "payload": weather.payload}}
        report["live_facts"]["weather"] = {"status": "available", "days": weather_days(ctx), "scope": "synthetic_city_representative_WGS84_coordinate_not_venue"}
    except Exception as exc:
        report["live_facts"]["weather"] = {"status": "unavailable", "code": getattr(exc, "code", type(exc).__name__)}
    save()
    for family in ["rain", "walking", "fixed_time"]:
        selections = []
        for condition in ["baseline", "changed"]:
            case = deepcopy(state)
            c = case["planning_context"]
            c["effective_requirements"] = []
            # These forecasts are controlled fixtures, even though the model and
            # map calls are real. Actual Open-Meteo evidence is recorded above.
            rain = 80 if family == "rain" and condition == "changed" else 0
            c["external_facts"] = {"weather": {"status": "available", "provider": "open_meteo", "queried_at": datetime.now(UTC).isoformat(),
                "payload": {"timezone": "Asia/Shanghai", "hourly": {"time": [f"{tomorrow.isoformat()}T{hour:02d}:00" for hour in range(9, 18)], "precipitation_probability": [rain]*9}}}}
            c["weather_sensitive"] = family == "rain"
            if family == "rain":
                case["user_request"] = "仅新增1个地点，固定活动之前结束，不压缩建议停留。无明显雨风险优先西湖湖景摄影；若逐小时预报显示明显降雨风险，优先博物馆展览，但类型不能保证全程室内。仅生成候选。"
            elif family == "walking":
                case["user_request"] = "仅新增1个地点，在固定活动前结束，不压缩建议停留；通常优先西湖湖景。若有效要求明确少走路，则优先到固定活动步行更短的候选，不猜全天步行。仅生成候选。"
                if condition == "changed":
                    c["effective_requirements"] = [{"id": "eval_walking", "key": "walking_preference", "value": "minimal", "text": "少走路", "source": {"kind": "user_explicit", "ref": "synthetic-eval"}, "scope": {"kind": "global_preference"}, "strength": "soft", "status": "active", "supersedes": []}]
            else:
                case["user_request"] = "仅在固定活动前新增1个地点，必须预留候选到固定活动的已查询步行时间，并完整保留候选建议停留。优先西湖湖景；前置时窗不足则选博物馆。不许把新增游览放到固定活动之后；固定活动是测试输入，不代表真实预约成功。仅生成候选。"
                if condition == "changed":
                    c["days"][0]["activities"][0]["scheduled_time"] = "11:00"
            c["preferences"]["requirement_records"] = deepcopy(c["effective_requirements"])
            started = time.monotonic()
            call = {"family": family, "condition": condition, "facts_kind": "controlled_weather_and_user_schedule_real_map_evidence", "candidate_ids": [p["id"] for p in c["candidates"]], "input_rain_probability": rain, "fixed_start": c["days"][0]["activities"][0]["scheduled_time"]}
            try:
                planner = OpenAIResponsesPlanner(settings)
                generation = await planner.generate(case)
                selected = [str(item.place_candidate_id) for item in generation.snapshot.activities]
                call.update(status="completed", selected_ids=selected, selected_names=[p["name"] for p in c["candidates"] if p["id"] in selected],
                    activities=generation.snapshot.model_dump(mode="json")["activities"], token_usage=generation.token_usage,
                    reliability=planner.last_reliability, review=review_candidate_decisions(c, generation.snapshot))
                selections.append(selected)
            except Exception as exc:
                call.update(status="failed", code=getattr(exc, "code", type(exc).__name__))
                selections.append(None)
            call["elapsed_seconds"] = round(time.monotonic()-started, 3)
            report["calls"].append(call)
            save()
            print(json.dumps({key: call[key] for key in ("family", "condition", "status", "elapsed_seconds")}), flush=True)
        report["pairs"].append({"family": family, "selection_changed": selections[0] is not None and selections[1] is not None and selections[0] != selections[1],
                                "both_completed": all(item is not None for item in selections)})
        save()
    report["completed_at"] = datetime.now(UTC).isoformat()
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.output))
    print(json.dumps({"pairs": result["pairs"], "live_weather_status": result["live_facts"].get("weather", {}).get("status")}, ensure_ascii=False))
