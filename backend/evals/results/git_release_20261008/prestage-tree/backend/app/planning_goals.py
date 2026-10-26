"""Structured, auditable goal extraction and post-route goal checks.

This module deliberately does not decide itinerary legality.  The existing
validator remains the sole deterministic safety boundary; this module records
whether a valid candidate meets the explicit goal of the current request.
"""
from __future__ import annotations

import re
from datetime import datetime

from app.schemas import CandidatePlanSnapshot, GoalSatisfactionResult, PlanningGoals


_END_BEFORE = re.compile(r"(?P<hour>\d{1,2})\s*(?:[:：]\s*(?P<minute>\d{2}))?\s*(?:点|时)?\s*(?:前|之前|以前)")


def extract_planning_goals(*, user_request: str, intent_resolution: dict, context: dict) -> PlanningGoals:
    """Reuse grounded intent plus explicit request wording without a model call."""
    grounded = intent_resolution.get("grounded_intent") or {}
    constraints = grounded.get("constraints") or {}
    day_by_id = {day["id"]: day["date"] for day in context.get("days", [])}
    target_days = [day_by_id[item] for item in grounded.get("target_day_ids", []) if item in day_by_id]
    if not target_days:
        target_days = [day["date"] for day in context.get("days", [])]

    match = _END_BEFORE.search(user_request)
    end_before = None
    if match:
        hour, minute = int(match.group("hour")), int(match.group("minute") or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            end_before = f"{hour:02d}:{minute:02d}"

    compact = re.sub(r"\s+", "", user_request)
    walking_requested = any(token in compact for token in ("少走路", "减少步行", "少步行", "步行少一点", "步行不超过", "最多步行"))
    minimize_walking = any(token in compact for token in ("少走路", "减少步行", "少步行", "步行少一点"))
    preserve_existing = any(token in compact for token in ("尽量保持", "不要大改", "保留现有", "尽量不改", "保持现有"))
    relaxed = constraints.get("requested_pace") == "relaxed" or any(token in compact for token in ("轻松一点", "轻松些", "放松一点"))
    explicit_max_walking = constraints.get("max_walking_minutes")
    # A stored mobility preference becomes a hard goal only when this request
    # actually asks about walking.  Promoting it for every unrelated replan
    # silently changes established planner semantics.
    if explicit_max_walking is None and walking_requested:
        explicit_max_walking = (context.get("preferences") or {}).get("max_walking_minutes")

    return PlanningGoals.model_validate({
        "target_days": sorted(set(target_days)),
        "hard_goals": {"end_before": end_before, "max_walking_minutes": explicit_max_walking},
        "soft_goals": {
            "pace": "relaxed" if relaxed else None,
            "minimize_walking": minimize_walking,
            "preserve_existing": preserve_existing,
        },
    })


def formal_route_facts(context: dict, goals: PlanningGoals) -> dict:
    """Reuse persisted formal legs; never performs another provider call."""
    selected = set(goals.target_days)
    days: list[dict] = []
    for day in context.get("days", []):
        if selected and day["date"] not in selected:
            continue
        names = {activity["id"]: activity["display_name"] for activity in day.get("activities", [])}
        legs = [
            {
                "from_activity_id": leg["from_activity_id"],
                "to_activity_id": leg["to_activity_id"],
                "from_name": names.get(leg["from_activity_id"], "正式活动"),
                "to_name": names.get(leg["to_activity_id"], "正式活动"),
                "mode": leg["mode"],
                "duration_minutes": leg["duration_minutes"],
                "distance_meters": leg["distance_meters"],
            }
            for leg in day.get("route_legs", [])
        ]
        days.append({
            "date": day["date"],
            "activity_sequence": [activity["display_name"] for activity in day.get("activities", [])],
            "route_legs": legs,
            "walking_duration_minutes": sum(leg["duration_minutes"] for leg in legs if leg["mode"] == "walk"),
            "walking_distance_meters": sum(leg["distance_meters"] for leg in legs if leg["mode"] == "walk"),
            "day_end": max((
                _end_time(activity["scheduled_time"], activity["duration_minutes"])
                for activity in day.get("activities", [])
            ), default=None),
        })
    return {"days": days}


def check_goal_satisfaction(*, goals: PlanningGoals, before_context: dict, snapshot: CandidatePlanSnapshot) -> GoalSatisfactionResult:
    selected = set(goals.target_days)
    activities = [item for item in snapshot.activities if not selected or item.day_date.isoformat() in selected]
    represented_ids = {str(item.replaces_activity_id) for item in snapshot.activities if item.replaces_activity_id is not None}
    protected_ids = set(((before_context.get("decision_context") or {}).get("protected_constraints") or {}).get("protected_activity_ids") or [])
    retained = [
        item
        for day in before_context.get("days", []) if not selected or day["date"] in selected
        for item in day.get("activities", [])
        if item["status"] != "skipped" and str(item["id"]) not in represented_ids
        and (str(item["id"]) in protected_ids or item.get("schedule_locked") or item["status"] in {"active", "completed"})
    ]
    before_facts = formal_route_facts(before_context, goals)
    before_ids = {
        activity["place_id"]
        for day in before_context.get("days", []) if not selected or day["date"] in selected
        for activity in day.get("activities", []) if activity["status"] != "skipped"
    }
    after_ids = {str(item.place_candidate_id) for item in activities} | {str(item["place_id"]) for item in retained}
    before_walking = sum(day["walking_duration_minutes"] for day in before_facts["days"])
    after_walking = sum(leg.duration_minutes for leg in snapshot.route_legs if leg.mode == "walk")
    results: list[dict] = []

    if goals.hard_goals.end_before:
        candidate_end = max(
            [_end_time(str(item.planned_start_time), item.duration_minutes) for item in activities]
            + [_end_time(str(item["scheduled_time"]), item["duration_minutes"]) for item in retained],
            default=None,
        )
        results.append({
            "goal": "end_before", "type": "hard",
            "status": "satisfied" if candidate_end is not None and candidate_end <= goals.hard_goals.end_before else "unsatisfied",
            "evidence": {"required_end_before": goals.hard_goals.end_before, "candidate_end": candidate_end},
        })
    if goals.hard_goals.max_walking_minutes is not None:
        results.append({
            "goal": "max_walking_minutes", "type": "hard",
            "status": "satisfied" if after_walking <= goals.hard_goals.max_walking_minutes else "unsatisfied",
            "evidence": {"limit_minutes": goals.hard_goals.max_walking_minutes, "candidate_walking_minutes": after_walking},
        })
    if goals.soft_goals.minimize_walking:
        results.append({"goal": "minimize_walking", "type": "soft", "status": "not_evaluable",
                        "evidence": {"before_walking_minutes": before_walking, "after_walking_minutes": after_walking}})
    if goals.soft_goals.preserve_existing:
        results.append({"goal": "preserve_existing", "type": "soft", "status": "not_evaluable", "evidence": {
            "before_activity_count": len(before_ids), "after_activity_count": len(after_ids),
            "preserved_count": len(before_ids & after_ids), "removed_count": len(before_ids - after_ids),
            "added_count": len(after_ids - before_ids),
            "changed_count": sum(1 for item in activities if item.replaces_activity_id is not None),
        }})
    if goals.soft_goals.pace == "relaxed":
        results.append({"goal": "pace_relaxed", "type": "soft", "status": "not_evaluable", "evidence": {
            "activity_count_before": len(before_ids), "activity_count_after": len(after_ids),
            "walking_minutes_before": before_walking, "walking_minutes_after": after_walking,
        }})
    return GoalSatisfactionResult.model_validate({"results": results})


def hard_goal_feedback(result: GoalSatisfactionResult) -> list[dict]:
    return [item.model_dump(mode="json") for item in result.results if item.type == "hard" and item.status == "unsatisfied"]


def can_repair_hard_goals(*, repair_count: int, result: GoalSatisfactionResult) -> bool:
    """The bounded repair policy is intentionally explicit and unit-testable."""
    return bool(hard_goal_feedback(result)) and repair_count < 1


def _end_time(start: str, duration_minutes: int) -> str:
    parsed = datetime.strptime(start[:5], "%H:%M")
    minute = parsed.hour * 60 + parsed.minute + duration_minutes
    return f"{(minute // 60) % 24:02d}:{minute % 60:02d}"
