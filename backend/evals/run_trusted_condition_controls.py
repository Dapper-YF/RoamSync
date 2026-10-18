"""Reproducible condition controls over the candidate comparison boundary.

No model, provider, database, or Trip writes. This records ranking behavior,
not a claim that a generated itinerary passed route/Validator/Accept checks.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from app.candidate_decisions import compare_candidates


def run() -> dict:
    now = datetime.now(UTC)
    day = (now.astimezone(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)).isoformat()
    fixed_id = "00000000-0000-4000-8000-000000000003"
    westlake = {"id": "00000000-0000-4000-8000-000000000001", "name": "杭州西湖风景名胜区", "category": "nature",
                "longitude": 120.121358, "latitude": 30.222692, "rating": 4.9, "tags": [], "suggested_duration_minutes": 120,
                "source": {"provider": "AMap POI", "id": "westlake", "url": "https://www.amap.com/search?id=B023B13L9M"}}
    museum = {"id": "00000000-0000-4000-8000-000000000002", "name": "中国丝绸博物馆", "category": "culture",
              "longitude": 120.151292, "latitude": 30.22287, "rating": 4.7, "tags": ["博物馆"], "suggested_duration_minutes": 60,
              "source": {"provider": "AMap POI", "id": "museum"}}
    base = {"trip": {"destination": "杭州", "timezone": "Asia/Shanghai"},
            "days": [{"date": day, "activities": [{"id": fixed_id, "place_id": fixed_id, "scheduled_time": "14:00",
                "duration_minutes": 60, "schedule_locked": True, "status": "planned"}]}],
            "preferences": {"daily_start_time": "09:00", "daily_end_time": "18:00"},
            "weather_sensitive": True, "effective_requirements_by_date": {day: []}}

    def forecast(ctx: dict, values: list[int]) -> None:
        ctx["external_facts"] = {"weather": {"status": "available", "provider": "open_meteo", "queried_at": now.isoformat(),
            "payload": {"timezone": "Asia/Shanghai", "hourly": {"time": [f"{day}T{hour:02d}:00" for hour in range(9, 18)],
                "precipitation_probability": values}}}}

    def route(ctx: dict, *, expiry: datetime) -> None:
        ctx["candidate_route_facts"] = [{"candidate_id": place["id"], "date": day, "to_activity_id": fixed_id,
            "direction": "candidate_to_fixed_activity", "mode": "walk", "status": "available", "is_estimated": False,
            "duration_minutes": minutes, "provider": "AMap Route 2.0", "expires_at": expiry.isoformat()}
            for place, minutes in ((westlake, 40), (museum, 10))]

    scenarios = {}
    for name in ("dry", "rain_all_visit_hours", "rain_only_late", "missing_forecast", "shorter_verified_walk",
                 "expired_walk_evidence", "hard_avoid_nature_over_soft_interest", "revoke_hard_avoid_nature", "fixed_slot_too_short"):
        ctx = deepcopy(base)
        if name == "rain_all_visit_hours":
            forecast(ctx, [80] * 9)
        elif name == "rain_only_late":
            forecast(ctx, [0] * 8 + [80])
        elif name != "missing_forecast":
            forecast(ctx, [0] * 9)
        if name in {"shorter_verified_walk", "expired_walk_evidence"}:
            ctx["planning_goals"] = {"soft_goals": {"minimize_walking": True}}
            route(ctx, expiry=now + timedelta(hours=1) if name == "shorter_verified_walk" else now - timedelta(minutes=1))
        if name in {"hard_avoid_nature_over_soft_interest", "revoke_hard_avoid_nature"}:
            ctx["preferences"]["interest_categories"] = ["nature"]
            if name == "hard_avoid_nature_over_soft_interest":
                ctx["effective_requirements_by_date"][day] = [{"id": "user-hard-avoid", "key": "avoid_category", "value": "nature",
                    "status": "active", "strength": "hard", "source": {"kind": "user_explicit", "ref": "control"}, "scope": {"kind": "day", "date": day}}]
        if name == "fixed_slot_too_short":
            ctx["days"][0]["activities"][0]["scheduled_time"] = "10:00"
            ctx["preferences"]["daily_end_time"] = "12:00"
            forecast(ctx, [0] * 9)
        ranked, evidence = compare_candidates(ctx, [westlake, museum], allowed_dates={day}, now=now)
        scenarios[name] = {"ranked_names": [place["name"] for place in ranked],
                           "weather_status": evidence["weather_days"][day]["status"],
                           "rain_risk": evidence["weather_days"][day]["rain_risk"],
                           "candidate_evidence": [{"name": place["name"], "eligible": row["eligible"],
                               "day_comparison": row["day_comparisons"][0]} for place, row in zip((westlake, museum), evidence["candidates"])]}
    return {"version": "trusted-condition-fixed-controls-v1", "run_at": now.isoformat(), "target_date": day,
            "evidence_kind": "fixed_synthetic_conditions_no_model_or_provider_calls", "database_writes": 0,
            "place_identity_note": "representative POI names and coordinates from prior recorded AMap result; no fresh lookup",
            "scenarios": scenarios}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = run()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value["ranked_names"][0] for key, value in report["scenarios"].items()}, ensure_ascii=False))
