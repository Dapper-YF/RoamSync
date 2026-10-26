"""Deterministic, selected facts supplied to one planning decision.

The context is a read model assembled from existing formal-plan, execution and
provider facts.  It is deliberately not another persistence model and never
performs provider calls.
"""
from __future__ import annotations

from collections import defaultdict
from app.planning_errors import DecisionContextInvariantError


def build_decision_context(*, context: dict, goals: dict, resolution: dict, decision_memory: list[dict] | None = None) -> dict:
    """Select the target-day facts and establish one activity authority split."""
    grounded = resolution.get("grounded_intent") or {}
    target_ids = set(grounded.get("target_day_ids") or [])
    target_days = [
        day for day in context.get("days", [])
        if not target_ids or str(day.get("id")) in target_ids
    ]
    activities = [activity for day in target_days for activity in day.get("activities", [])]
    activity_ids = {str(activity["id"]) for activity in activities}
    recovery = context.get("execution_recovery") or {}

    frozen = set(recovery.get("frozen_activity_ids") or [])
    protected_sources: dict[str, set[str]] = defaultdict(set)
    for activity_id in frozen:
        protected_sources[activity_id].add("execution_completed_or_skipped")
    for activity_id in recovery.get("protected_activity_ids") or []:
        protected_sources[activity_id].add("execution_runtime_protection")
    for activity_id in (resolution.get("request") or {}).get("intent", {}).get("protected_activity_ids") or []:
        protected_sources[str(activity_id)].add("user_request_protection")
    for activity in activities:
        activity_id = str(activity["id"])
        if activity.get("schedule_locked"):
            protected_sources[activity_id].add("schedule_locked")
        if activity.get("status") in {"active", "completed", "skipped"}:
            protected_sources[activity_id].add("formal_activity_status")

    protected_ids = set(protected_sources) & activity_ids
    editable_ids = activity_ids - protected_ids
    activity_by_id = {str(activity["id"]): activity for activity in activities}
    activity_semantics = [
        {
            "activity_id": str(activity["id"]),
            "name": activity["display_name"],
            "importance": activity.get("importance", "normal"),
            "can_skip": activity.get("can_skip", activity.get("importance") != "must_do"),
            "minimum_duration_minutes": activity.get("minimum_duration_minutes"),
            "planned_duration_minutes": activity["duration_minutes"],
            "provenance": {
                "importance": activity.get("importance_source", "unknown"),
                "can_skip": activity.get("can_skip_source", "system_default"),
                "minimum_duration_minutes": activity.get("minimum_duration_source", "unknown"),
            },
        }
        for activity in activities
    ]
    formal_days = []
    for day in target_days:
        formal_days.append({
            "day_id": str(day.get("id") or day["date"]),
            "date": day["date"],
            "activities": [
                {
                    "activity_id": str(activity["id"]),
                    "name": activity["display_name"],
                    "scheduled_time": activity["scheduled_time"],
                    "duration_minutes": activity["duration_minutes"],
                    "importance": activity.get("importance", "normal"),
                    "can_skip": activity.get("can_skip", activity.get("importance") != "must_do"),
                    "minimum_duration_minutes": activity.get("minimum_duration_minutes"),
                    "category": activity["category"],
                    "longitude": activity["longitude"],
                    "latitude": activity["latitude"],
                    "schedule_locked": activity["schedule_locked"],
                    "status": activity["status"],
                }
                for activity in day.get("activities", [])
            ],
        })

    route_days = []
    for day in target_days:
        legs = []
        for leg in day.get("route_legs", []):
            legs.append({
                "from_activity_id": str(leg["from_activity_id"]),
                "to_activity_id": str(leg["to_activity_id"]),
                "mode": leg["mode"],
                "distance_meters": leg["distance_meters"],
                "duration_minutes": leg["duration_minutes"],
                "walking_distance_meters": leg["distance_meters"] if leg["mode"] == "walk" else None,
                "walking_duration_minutes": leg["duration_minutes"] if leg["mode"] == "walk" else None,
                "source": leg.get("provider") or "unavailable",
            })
        route_days.append({
            "date": day["date"],
            "route_fact_status": "available" if legs else "unavailable",
            "route_legs": legs,
        })

    execution_state = dict(recovery.get("execution_state") or {})
    current_id = execution_state.get("current_activity_id")
    if current_id:
        execution_state["current_activity"] = _activity_reference(activity_by_id.get(current_id))
    navigation_id = execution_state.get("navigation_target_activity_id")
    if navigation_id:
        execution_state["navigation_target"] = _activity_reference(activity_by_id.get(navigation_id))
    execution_state["remaining_activity_ids"] = sorted(editable_ids)

    decision_context = {
        "goal_context": goals,
        "formal_itinerary": {"days": formal_days},
        "activity_decision_semantics": activity_semantics,
        "route_context": {"days": route_days},
        "execution_context": execution_state,
        "protected_constraints": {
            "frozen_activity_ids": sorted(frozen & activity_ids),
            "protected_activity_ids": sorted(protected_ids),
            "editable_activity_ids": sorted(editable_ids),
            "provenance": {activity_id: sorted(sources) for activity_id, sources in protected_sources.items() if activity_id in activity_ids},
        },
        "user_preferences": _selected_preferences(context.get("preferences") or {}),
        "active_disruption": recovery.get("disruption"),
        "provider_facts": context.get("external_facts", {"status": "not_available"}),
        "decision_memory": decision_memory or [],
        "provenance": {
            "goals": "user_goal_and_grounded_intent",
            "formal_itinerary": "persisted_formal_itinerary",
            "activity_decision_semantics": "persisted_activity_fields_with_field_provenance",
            "route_context": "persisted_amap_route",
            "execution_context": "execution_and_navigation_projection",
            "active_disruption": "persisted_disruption_projection",
            "user_preferences": "persisted_trip_preferences",
            "provider_facts": "planning_provider_facts",
            "decision_memory": "same_trip_same_target_day_rejected_revisions",
        },
    }
    assert_decision_context_invariants(decision_context)
    return decision_context


def assert_decision_context_invariants(decision_context: dict) -> None:
    """Reject malformed context before a model can consume it."""
    codes: list[str] = []
    formal_days = decision_context.get("formal_itinerary", {}).get("days", [])
    activity_ids = {
        str(activity["activity_id"])
        for day in formal_days for activity in day.get("activities", [])
    }
    semantic_ids = {str(item["activity_id"]) for item in decision_context.get("activity_decision_semantics", [])}
    if "activity_decision_semantics" in decision_context and semantic_ids != activity_ids:
        codes.append("activity_semantics_mismatch")
    for item in decision_context.get("activity_decision_semantics", []):
        if item.get("importance") == "must_do" and item.get("can_skip"):
            codes.append("must_do_activity_skippable")
        minimum = item.get("minimum_duration_minutes")
        if minimum is not None and minimum > item.get("planned_duration_minutes", 0):
            codes.append("minimum_duration_exceeds_planned")
    contract = decision_context.get("protected_constraints", {})
    protected = set(contract.get("protected_activity_ids") or [])
    editable = set(contract.get("editable_activity_ids") or [])
    if protected & editable:
        codes.append("protected_editable_overlap")
    if (protected | editable) - activity_ids:
        codes.append("activity_contract_references_unknown_activity")
    for day in decision_context.get("route_context", {}).get("days", []):
        for leg in day.get("route_legs", []):
            if str(leg["from_activity_id"]) not in activity_ids or str(leg["to_activity_id"]) not in activity_ids:
                codes.append("route_leg_references_unknown_activity")
    execution = decision_context.get("execution_context") or {}
    for key in ("current_activity_id", "navigation_target_activity_id", "first_impacted_activity_id"):
        value = execution.get(key)
        if value and str(value) not in activity_ids:
            codes.append("execution_references_unknown_activity")
            break
    target_days = set((decision_context.get("goal_context") or {}).get("target_days") or [])
    itinerary_days = {day["date"] for day in formal_days}
    if target_days and not target_days <= itinerary_days:
        codes.append("goal_target_day_not_in_formal_itinerary")
    if codes:
        raise DecisionContextInvariantError(codes)


def _activity_reference(activity: dict | None) -> dict | None:
    if activity is None:
        return None
    return {"activity_id": str(activity["id"]), "name": activity["display_name"], "scheduled_time": activity["scheduled_time"]}


def _selected_preferences(preferences: dict) -> dict:
    return {key: preferences.get(key) for key in (
        "pace", "interest_categories", "transport_modes", "daily_start_time",
        "daily_end_time", "meal_preferences", "avoid_categories", "max_walking_minutes",
    )}
