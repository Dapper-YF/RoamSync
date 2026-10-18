"""Bounded, inspectable comparisons over supplied facts; no new authority.

AMap taxonomy hints are useful for ranking but are not proof of shelter,
accessibility, opening or reservation availability. Unknowns never exclude a
place. Route comparisons concern one exact directed leg, never a whole day.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import math

PLANNING_FORECAST_MAX_AGE = timedelta(minutes=30)


def _minute(value: str) -> int:
    hour, minute = str(value)[:5].split(":")
    return int(hour) * 60 + int(minute)


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _fresh_route(item: dict, *, now: datetime) -> bool:
    """A provider leg is usable only for the exact, current directed question."""
    try:
        expires = datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False
    return (item.get("status") == "available" and item.get("is_estimated") is False
            and item.get("direction") == "candidate_to_fixed_activity"
            and item.get("provider") in {"amap", "AMap Route 2.0"}
            and item.get("mode") in {"walk", "transit", "driving"}
            and _number(item.get("duration_minutes")) is not None
            and item["duration_minutes"] >= 0
            and expires.tzinfo is not None and expires > now)


def _free_intervals(day: dict, start: int, end: int) -> tuple[list[tuple[int, int]], list[dict]]:
    fixed = sorted(((_minute(item["scheduled_time"]), _minute(item["scheduled_time"]) + item["duration_minutes"], item)
                    for item in day.get("activities", []) if item.get("schedule_locked") and item.get("status") != "skipped"),
                   key=lambda entry: (entry[0], entry[1]))
    intervals, cursor = [], start
    for fixed_start, fixed_end, item in fixed:
        if cursor < min(fixed_start, end):
            intervals.append((cursor, min(fixed_start, end)))
        cursor = max(cursor, fixed_end)
    if cursor < end:
        intervals.append((cursor, end))
    return intervals, [item for _, _, item in fixed]


def _candidate_rain_risk(weather: dict, duration: int | None, intervals: list[tuple[int, int]]) -> str:
    if weather.get("status") != "available":
        return "unknown"
    probabilities = {int(hour): probability for hour, probability in (weather.get("hourly_rain_probability") or {}).items()}
    if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
        values = list(probabilities.values())
        return "elevated" if values and all(value >= 60 for value in values) else "low" if values and all(value < 60 for value in values) else "mixed_unknown_timing"
    feasible = []
    for left, right in intervals:
        starts = {left} | {hour * 60 for hour in range(24) if left <= hour * 60 <= right - duration}
        for proposed in starts:
            if proposed + duration > right:
                continue
            hours = range(proposed // 60, (proposed + duration - 1) // 60 + 1)
            if all(hour in probabilities for hour in hours):
                feasible.append(any(probabilities[hour] >= 60 for hour in hours))
    if not feasible:
        return "unknown_no_known_free_slot"
    return "elevated" if all(feasible) else "low" if not any(feasible) else "mixed_dry_slot_available"


def weather_days(context: dict, *, now: datetime | None = None) -> dict:
    """Only fresh, complete daytime predictions can affect weather ranking."""
    weather = (context.get("external_facts") or {}).get("weather") or {}
    now = now or datetime.now(UTC)
    try:
        queried = datetime.fromisoformat(weather["queried_at"].replace("Z", "+00:00"))
        fresh = queried.tzinfo is not None and timedelta(0) <= now - queried <= PLANNING_FORECAST_MAX_AGE
    except (KeyError, ValueError, TypeError):
        fresh = False
    hourly = (weather.get("payload") or {}).get("hourly") or {}
    times, probabilities = hourly.get("time") or [], hourly.get("precipitation_probability") or []
    result = {}
    preferences = context.get("preferences") or {}
    start = _minute(preferences.get("daily_start_time") or "09:00")
    end = _minute(preferences.get("daily_end_time") or "18:00")
    from zoneinfo import ZoneInfo
    local_today = now.astimezone(ZoneInfo(context.get("trip", {}).get("timezone") or "Asia/Shanghai")).date()
    for day in context.get("days", []):
        day_date = day["date"]
        expected = {hour for hour in range(24) if hour * 60 < end and (hour + 1) * 60 > start}
        values = {}
        for index, timestamp in enumerate(times):
            try:
                parsed = datetime.fromisoformat(timestamp)
            except (TypeError, ValueError):
                continue
            if parsed.date().isoformat() != day_date or parsed.minute != 0 or parsed.hour not in expected:
                continue
            probability = _number(probabilities[index]) if index < len(probabilities) else None
            if probability is not None and 0 <= probability <= 100:
                values[parsed.hour] = probability
        usable = (weather.get("status") == "available" and weather.get("provider") == "open_meteo"
                  and (weather.get("payload") or {}).get("timezone") == context.get("trip", {}).get("timezone", "Asia/Shanghai")
                  and fresh and date.fromisoformat(day_date) >= local_today and expected and set(values) == expected)
        result[day_date] = {
            "status": "available" if usable else "unknown",
            "reason": "fresh_complete_daytime_prediction" if usable else "missing_stale_past_or_incomplete_prediction",
            "provider": weather.get("provider"), "queried_at": weather.get("queried_at"),
            "nature": "provider_prediction", "coverage_hours": sorted(values),
            "hourly_rain_probability": {str(hour): probability for hour, probability in values.items()} if usable else {},
            "max_hourly_rain_probability": max(values.values()) if usable else None,
            "rain_risk": ("elevated" if all(value >= 60 for value in values.values())
                          else "low" if all(value < 60 for value in values.values())
                          else "mixed") if usable else "unknown",
            "scope": "trip_representative_coordinate_not_venue_observation",
            "freshness_policy": "planning_decision_forecast_30min_v1",
        }
    return result


def place_exposure(candidate: dict, context: dict | None = None) -> dict:
    # One reviewed stable source slice, exact bounded identity; no nationwide
    # place scoring or runtime retrieval. Source supports landscape components,
    # not a guarantee that every activity in the scenic area is outdoors.
    if (context and context.get("trip", {}).get("destination") in {"杭州", "杭州市"}
        and (candidate.get("source") or {}).get("provider") == "AMap POI"
        and (candidate.get("source") or {}).get("url") == "https://www.amap.com/search?id=B023B13L9M"
        and candidate.get("name") in {"西湖", "西湖风景名胜区", "杭州西湖风景名胜区"}
        and 120.08 <= float(candidate.get("longitude") or 0) <= 120.18
        and 30.20 <= float(candidate.get("latitude") or 0) <= 30.28):
        return {"hint": "outdoor_landscape", "confidence": "reviewed_stable_landscape_components",
                "source": "hangzhou-reviewed-v1:hz-westlake-history",
                "source_url": "https://whc.unesco.org/en/list/1334", "reviewed_at": "2026-09-29T03:36:00.603499+00:00",
                "assertion_id": "west_lake.landscape_components", "matched_tags": [],
                "limit": "lake_mountains_causeways_only_not_whole_venue_shelter_or_operations"}
    # Only exact provider taxonomy tokens, never names, descriptions or model prose.
    provider = (candidate.get("source") or {}).get("provider")
    tags = set(candidate.get("tags") or [])
    indoor, outdoor = tags & {"博物馆", "美术馆", "科技馆"}, tags & {"公园", "公园广场", "植物园", "动物园"}
    hint = "indoor_exhibition" if indoor and not outdoor else "outdoor_visit" if outdoor and not indoor else "unknown"
    if provider != "AMap POI":
        hint = "unknown"
    return {"hint": hint, "confidence": "low_confidence_taxonomy_inference" if hint != "unknown" else "unknown",
            "source": "amap_poi_exact_taxonomy" if hint != "unknown" else "unavailable",
            "source_id": (candidate.get("source") or {}).get("id"), "matched_tags": sorted(indoor | outdoor) if hint != "unknown" else [],
            "limit": "category_hint_only_not_shelter_accessibility_opening_or_booking_guarantee"}


def _requirements(context: dict, day_date: str | None = None) -> list[dict]:
    result = []
    if day_date is not None and "effective_requirements_by_date" in context:
        records = context["effective_requirements_by_date"].get(day_date, [])
    elif day_date is not None:
        from app.requirements import project_requirements
        day = next((item for item in context.get("days", []) if item["date"] == day_date), {})
        records = project_requirements(
            (context.get("preferences") or {}).get("requirement_records", context.get("effective_requirements") or []),
            trip_id=context.get("trip", {}).get("id"), city=context.get("trip", {}).get("destination"),
            target_date=day_date, day_index=context.get("days", []).index(day) + 1 if day else None,
            target_activity_ids=[str(item["id"]) for item in day.get("activities", [])],
        )
    else:
        records = context.get("effective_requirements") or []
    for item in records:
        if item.get("status") != "active" or item.get("source", {}).get("kind") not in {"user_explicit", "trip_preference"}:
            continue
        scope = item.get("scope") or {}
        if scope.get("date") and scope["date"] != day_date:
            continue
        # Activity requirements cannot constrain unrelated additions.
        if scope.get("kind") == "activity":
            continue
        result.append(item)
    return result


def _category_requirement(item: dict, candidate: dict) -> bool:
    # Narrow supported key; free text never becomes an invented hard predicate.
    return item.get("key") == "avoid_category" and item.get("value") == candidate.get("category")


def compare_candidates(context: dict, candidates: list[dict], *, allowed_dates: set[str], now: datetime | None = None) -> tuple[list[dict], dict]:
    now = now or datetime.now(UTC)
    forecasts = weather_days(context, now=now)
    research = (context.get("destination_research") or {}).get("places") or {}
    route_facts = context.get("candidate_route_facts") or []
    rows = []
    preferences = context.get("preferences") or {}
    minimize_walking = ((context.get("planning_goals") or {}).get("soft_goals") or {}).get("minimize_walking", False)
    for candidate in candidates:
        candidate_id = str(candidate["id"])
        exposure = place_exposure(candidate, context)
        per_day = []
        for day_date in sorted(allowed_dates):
            requirements = _requirements(context, day_date)
            pace = next((item.get("value") for item in requirements if item.get("key") == "pace"), None)
            walking_preference = any(item.get("key") in {"walking_preference", "max_walking_minutes"} for item in requirements)
            excluded = [item["id"] for item in requirements if item.get("strength") == "hard" and _category_requirement(item, candidate)]
            soft_avoid = [item["id"] for item in requirements if item.get("strength") == "soft" and _category_requirement(item, candidate)]
            weather = forecasts.get(day_date) or {"status": "unknown", "rain_risk": "unknown"}
            weather_sensitive = (context.get("weather_sensitive") or any(item.get("key") == "weather_sensitive" for item in requirements))
            formal_day = next((day for day in context.get("days", []) if day["date"] == day_date), {})
            day_start = _minute(preferences.get("daily_start_time") or "09:00")
            day_end = _minute(preferences.get("daily_end_time") or "18:00")
            free_intervals, fixed_activities = _free_intervals(formal_day, day_start, day_end)
            suggested = candidate.get("suggested_duration_minutes")
            candidate_rain_risk = _candidate_rain_risk(weather, suggested, free_intervals)
            rain_penalty = int(bool(weather_sensitive and candidate_rain_risk == "elevated" and exposure["hint"] in {"outdoor_visit", "outdoor_landscape"}))
            indoor_bonus = int(bool(weather_sensitive and candidate_rain_risk == "elevated" and exposure["hint"] == "indoor_exhibition"))
            fixed_ids = {str(item["id"]) for item in fixed_activities}
            routes = [item for item in route_facts if item.get("candidate_id") == candidate_id and item.get("date") == day_date
                      and str(item.get("to_activity_id")) in fixed_ids and _fresh_route(item, now=now)]
            route = min(routes, key=lambda item: item["duration_minutes"], default=None)
            max_gap = max((right - left for left, right in free_intervals), default=0)
            fixed_penalty = int(bool(fixed_activities and isinstance(suggested, int) and suggested > max_gap))
            anchor = next((item for item in fixed_activities if route and str(item["id"]) == str(route["to_activity_id"])), None)
            before_anchor = None
            if anchor and isinstance(suggested, int) and suggested > 0:
                anchor_start = _minute(anchor["scheduled_time"])
                available = max((right - left for left, right in free_intervals if right == anchor_start), default=0)
                rest_buffer = 10 if route["mode"] == "walk" and route["duration_minutes"] >= 20 else 0
                required = suggested + route["duration_minutes"]
                before_anchor = {"status": "does_not_fit_with_known_route" if required > available
                                 else "fits_without_rest_buffer_only" if required + rest_buffer > available
                                 else "fits_with_known_route_and_rest_buffer",
                                 "known_free_minutes": available, "route_minutes": route["duration_minutes"],
                                 "soft_rest_buffer_minutes": rest_buffer,
                                 "suggested_duration_minutes": suggested, "anchor_activity_id": str(anchor["id"]),
                                 "limit": "directed_leg_and_soft_rest_heuristic_only_no_full_day_route_guarantee"}
            per_day.append({"date": day_date, "eligible": not excluded, "excluded_by": excluded,
                            "pace_preference": pace, "walking_preference": walking_preference,
                            "photography_landscape_match": any(item.get("key") == "interest" and item.get("value") == "photography" for item in requirements) and exposure["hint"] == "outdoor_landscape",
                            "soft_avoid_requirements": soft_avoid, "candidate_rain_risk": candidate_rain_risk, "weather_penalty": rain_penalty,
                            "weather_indoor_bonus": indoor_bonus, "route_to_fixed_activity": route or {"status": "unknown"},
                            "fixed_time_fit": {"status": "suggested_duration_exceeds_known_free_slot" if fixed_penalty else "unknown" if not fixed_activities else "duration_fits_before_route_check",
                                               "max_free_slot_minutes": max_gap if fixed_activities else None,
                                               "suggested_duration_minutes": suggested, "penalty": fixed_penalty,
                                               "before_fixed_anchor": before_anchor or {"status": "unknown"},
                                               "source": "persisted_schedule_locked_not_booking_confirmation",
                                               "limit": "soft_duration_estimate_no_route_feasibility_guarantee"}})
        eligible = [day for day in per_day if day["eligible"]]
        best = min(eligible, key=lambda day: (len(day["soft_avoid_requirements"]), day["weather_penalty"] - day["weather_indoor_bonus"], day["fixed_time_fit"]["penalty"]), default={})
        routes = [day["route_to_fixed_activity"] for day in eligible if day["route_to_fixed_activity"].get("status") == "available"
                  and day["route_to_fixed_activity"].get("mode") == "walk"]
        # Unknown route time gets no bonus and cannot outrank a known shorter leg
        # on an assertion of proximity. It remains an eligible alternative.
        route_minutes = min((item["duration_minutes"] for item in routes), default=None)
        compare_walking = minimize_walking or any(day["walking_preference"] for day in eligible)
        pace_minutes = candidate.get("suggested_duration_minutes") or 0
        pace_key = pace_minutes if best.get("pace_preference") == "relaxed" else -pace_minutes if best.get("pace_preference") == "intensive" else 0
        soft_category = candidate.get("category") in (preferences.get("avoid_categories") or [])
        interest = candidate.get("category") in (preferences.get("interest_categories") or [])
        row = {"place_candidate_id": candidate_id, "eligible": bool(eligible), "day_comparisons": per_day,
               "exposure": exposure, "requested": bool(research.get(candidate_id, {}).get("requested")),
               "preference_category_avoid": soft_category, "interest_match": interest,
               "supported_requirement_ids": [item["id"] for item in _requirements(context) if item.get("key") == "avoid_category"],
               "unknowns": ["opening_hours", "booking_availability", "accessibility", "crowding"],
               "comparison_key": [len(best.get("soft_avoid_requirements", [])) + int(soft_category),
                                  best.get("weather_penalty", 0) - best.get("weather_indoor_bonus", 0),
                                  best.get("fixed_time_fit", {}).get("penalty", 0),
                                  (route_minutes if route_minutes is not None else 100000) if compare_walking else 0,
                                  pace_key, -int(bool(best.get("photography_landscape_match"))),
                                  -int(interest)]}
        rows.append(row)
    by_id = {row["place_candidate_id"]: row for row in rows}
    ranked = sorted([item for item in candidates if by_id[str(item["id"])]["eligible"]], key=lambda item: (
        not by_id[str(item["id"])]["requested"], *by_id[str(item["id"])]["comparison_key"],
        list(research).index(str(item["id"])) if str(item["id"]) in research else len(research),
        -float(item.get("rating") or 0), item["name"], str(item["id"])))
    return ranked, {"version": "bounded-candidate-comparison-v1", "weather_days": forecasts, "candidates": rows,
                    "ranking_policy": "requested_then_soft_avoid_feasible_visit_weather_fixed_free_slot_fresh_exact_walk_anchor_route_interest_then_research_rating",
                    "limits": ["taxonomy_is_soft_hint", "route_is_one_directed_leg_not_day_total", "mixed_weather_has_no_certain_rain_penalty", "unknown_does_not_exclude"]}


def review_candidate_decisions(context: dict, snapshot) -> dict:
    """Deterministic post-generation checks, separate from Validator safety."""
    candidates = {str(item["id"]): item for item in context.get("candidates", [])}
    # Candidate search omits places already on the itinerary. They still need
    # current requirement checks when a revision explicitly retains/replaces
    # their Activity IDs, rather than implicitly preserving protected rows.
    for formal_day in context.get("days", []):
        for formal in formal_day.get("activities", []):
            candidates.setdefault(str(formal["place_id"]), formal)
    comparison = context.get("candidate_comparison") or {}
    compared = {item["place_candidate_id"]: item for item in comparison.get("candidates", [])}
    hard_errors, observations = [], []
    represented = {str(item.replaces_activity_id) for item in snapshot.activities if item.replaces_activity_id}
    protected = set(((context.get("decision_context") or {}).get("protected_constraints") or {}).get("protected_activity_ids") or [])
    recovery = context.get("execution_recovery") or {}
    protected.update(recovery.get("protected_activity_ids") or [])
    protected.update(recovery.get("frozen_activity_ids") or [])
    for formal_day in context.get("days", []):
        for formal in formal_day.get("activities", []):
            if (str(formal["id"]) in represented or formal.get("status") == "skipped"
                or not (str(formal["id"]) in protected or formal.get("schedule_locked") or formal.get("status") in {"active", "completed"})):
                continue
            for requirement in _requirements(context, formal_day["date"]):
                if requirement.get("strength") == "hard" and _category_requirement(requirement, formal):
                    hard_errors.append({"code": "effective_requirement_protected_conflict", "message": "有效硬要求与必须保留的活动冲突，需明确解决。",
                                        "details": {"requirement_id": requirement["id"], "activity_id": str(formal["id"]), "date": formal_day["date"]}})
    for item in snapshot.activities:
        candidate = candidates.get(str(item.place_candidate_id))
        if not candidate:
            continue
        day_date = item.day_date.isoformat()
        requirements = _requirements(context, day_date)
        for requirement in requirements:
            if requirement.get("strength") == "hard" and _category_requirement(requirement, candidate):
                hard_errors.append({"code": "effective_requirement_unsatisfied", "message": "候选地点违反明确硬性类别要求。",
                                    "details": {"requirement_id": requirement["id"], "place_candidate_id": str(item.place_candidate_id), "date": day_date}})
        row = compared.get(str(item.place_candidate_id))
        day = next((day for day in (row or {}).get("day_comparisons", []) if day["date"] == day_date), None)
        weather_known = (comparison.get("weather_days", {}).get(day_date) or {}).get("status") == "available"
        exact_legs = [leg for leg in snapshot.route_legs if leg.to_activity_ref == item.candidate_id]
        observations.append({"candidate_id": item.candidate_id, "date": day_date,
                             "weather_tradeoff": ("outdoor_under_elevated_rain_prediction" if day and day["weather_penalty"]
                                                  else "mixed_rain_timing_requires_schedule_check" if day and str(day.get("candidate_rain_risk", "")).startswith("mixed")
                                                  else "no_known_weather_penalty" if weather_known and row and row["exposure"]["hint"] != "unknown"
                                                  else "unknown"),
                             "candidate_rain_risk": day.get("candidate_rain_risk", "unknown") if day else "unknown",
                             "exposure_status": (row or {}).get("exposure", {}).get("hint", "unknown"),
                             "soft_requirement_tradeoffs": day.get("soft_avoid_requirements", []) if day else [],
                             "before_fixed_anchor": day.get("fixed_time_fit", {}).get("before_fixed_anchor", {"status": "unknown"}) if day else {"status": "unknown"},
                             "route_status": "available" if exact_legs and all(not leg.is_estimated for leg in exact_legs) else "estimated" if exact_legs else "unknown",
                             "incoming_routes": [{"provider": leg.provider, "duration_minutes": leg.duration_minutes, "is_estimated": leg.is_estimated} for leg in exact_legs]})
    fixed = []
    for day in context.get("days", []):
        for item in day.get("activities", []):
            if not item.get("schedule_locked") or item.get("status") == "skipped":
                continue
            replacement = next((a for a in snapshot.activities if str(a.replaces_activity_id) == str(item["id"])), None)
            unchanged = replacement is None or (replacement.day_date.isoformat() == day["date"]
                        and str(replacement.planned_start_time)[:5] == str(item["scheduled_time"])[:5]
                        and replacement.duration_minutes == item["duration_minutes"])
            fixed.append({"activity_id": str(item["id"]), "date": day["date"], "scheduled_time": item["scheduled_time"],
                          "status": "preserved" if unchanged else "changed", "source": "persisted_schedule_locked_not_booking_confirmation"})
            if not unchanged:
                hard_errors.append({"code": "fixed_activity_changed", "message": "候选改变了固定活动时间。", "details": {"activity_id": str(item["id"])}})
    from app.planning_goals import _effective_requirement_results
    requirement_results = _effective_requirement_results(context, snapshot)
    for result in requirement_results:
        if result["type"] == "hard" and result["status"] == "unsatisfied":
            hard_errors.append({"code": "effective_requirement_unsatisfied", "message": "候选未满足有效硬要求。",
                                "details": result["evidence"]})
    return {"status": "hard_conflict" if hard_errors else "checked", "hard_errors": hard_errors,
            "selected_observations": observations, "fixed_activities": fixed,
            "effective_requirement_results": requirement_results,
            "uncheckable_requirement_ids": [item["id"] for item in context.get("effective_requirements") or []
                                           if item.get("status") == "active" and item.get("key") not in {"avoid_category", "weather_sensitive", "pace", "max_walking_minutes", "end_before", "budget_fen", "daily_budget_fen", "walking_preference"}]}


async def collect_candidate_route_facts(session, context: dict, *, target_dates: set[str], limit: int = 6) -> list[dict]:
    """Bounded reuse of the existing provider/cache, candidate -> fixed anchor.

    Estimates are recorded as unknown for ranking. No unavailable route becomes
    proof of infeasibility. The normal candidate route enrichment still runs.
    """
    import uuid
    from app.database import PlaceCandidate
    from app.maps_service import MapProviderError, resolve_route_result
    anchors_by_day = {}
    for day in context.get("days", []):
        if day["date"] not in target_dates:
            continue
        fixed = [item for item in day.get("activities", []) if item.get("schedule_locked") and item.get("status") == "planned"]
        if fixed:
            anchors_by_day[day["date"]] = min(fixed, key=lambda item: (item["scheduled_time"], str(item["id"])))
    anchors = sorted(anchors_by_day.items())
    if not anchors:
        return []
    modes = (context.get("preferences") or {}).get("transport_modes") or []
    minimize_walking = (((context.get("planning_goals") or {}).get("soft_goals") or {}).get("minimize_walking")
                        or any(item.get("key") in {"walking_preference", "max_walking_minutes"} for item in context.get("effective_requirements") or []))
    mode = "walk" if minimize_walking and "walk" in modes else next((m for m in modes if m in {"walk", "transit", "driving"}), None)
    if mode is None:
        return []
    result = []
    pairs = [(candidate, day_date, anchor) for candidate in context.get("candidates", [])
             for day_date, anchor in anchors if str(candidate["id"]) != str(anchor["place_id"])]
    for candidate, day_date, anchor in pairs[:limit]:
        base = {"candidate_id": str(candidate["id"]), "date": day_date, "to_activity_id": str(anchor["id"]),
                "direction": "candidate_to_fixed_activity", "mode": mode, "status": "unknown"}
        origin = await session.get(PlaceCandidate, uuid.UUID(str(candidate["id"])))
        destination = await session.get(PlaceCandidate, uuid.UUID(str(anchor["place_id"])))
        if origin is None or destination is None or origin.trip_id != destination.trip_id:
            result.append({**base, "reason": "place_identity_unavailable"})
            continue
        try:
            route = await resolve_route_result(session, origin, destination, mode)
            result.append({**base, "status": "unknown" if route.is_estimated else "available",
                           "reason": "estimate_not_provider_evidence" if route.is_estimated else "provider_estimated_directed_leg",
                           "duration_minutes": route.duration_minutes, "distance_meters": route.distance_meters,
                           "provider": route.provider, "is_estimated": route.is_estimated, "expires_at": route.expires_at.isoformat()})
        except MapProviderError as exc:
            result.append({**base, "reason": exc.code})
    return result
