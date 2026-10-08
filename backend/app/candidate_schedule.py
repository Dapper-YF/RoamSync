from datetime import time

from app.schemas import CandidatePlanSnapshot


def _minutes(value: str | time) -> int:
    parsed = time.fromisoformat(value) if isinstance(value, str) else value
    return parsed.hour * 60 + parsed.minute


def repair_route_schedule(
    snapshot: CandidatePlanSnapshot, context: dict, *, allow_earlier: bool = False
) -> tuple[CandidatePlanSnapshot, list[dict]]:
    """Shift stops forward using route evidence, without changing the route.

    This produces a candidate only. The caller must run the full validator again.
    Optionally use earlier free time to fit the daily window, preserving order,
    stops, duration and frozen times. Callers disable this for explicit time requests.
    """
    candidates = {item.candidate_id: item for item in snapshot.activities}
    represented = {str(item.replaces_activity_id) for item in snapshot.activities if item.replaces_activity_id}
    frozen = {item.candidate_id for item in snapshot.activities if item.locked}
    starts = {item.candidate_id: _minutes(item.planned_start_time) for item in snapshot.activities}
    durations = {item.candidate_id: item.duration_minutes for item in snapshot.activities}
    for day in context["days"]:
        for activity in day["activities"]:
            if not (activity["schedule_locked"] or activity["status"] in {"active", "completed"}):
                continue
            if str(activity["id"]) in represented:
                frozen.update(item.candidate_id for item in snapshot.activities if str(item.replaces_activity_id) == str(activity["id"]))
                continue
            ref = f"activity:{activity['id']}"
            starts[ref] = _minutes(activity["scheduled_time"])
            durations[ref] = activity["duration_minutes"]
            frozen.add(ref)

    daily_end = _minutes(context["preferences"]["daily_end_time"])
    daily_start = _minutes(context["preferences"].get("daily_start_time", "00:00"))
    legs = sorted(snapshot.route_legs, key=lambda item: (item.day_date, item.position))
    if allow_earlier:
        for ref in starts:
            if ref not in frozen:
                starts[ref] = max(starts[ref], daily_start)
    for leg in legs:
        if leg.from_activity_ref not in starts or leg.to_activity_ref not in starts:
            return snapshot, []
        required = starts[leg.from_activity_ref] + durations[leg.from_activity_ref] + leg.duration_minutes
        if starts[leg.to_activity_ref] >= required:
            continue
        if leg.to_activity_ref in frozen or (not allow_earlier and required + durations[leg.to_activity_ref] > daily_end):
            return snapshot, []
        starts[leg.to_activity_ref] = required

    if allow_earlier:
        latest = {ref: starts[ref] if ref in frozen else daily_end - duration for ref, duration in durations.items()}
        for leg in reversed(legs):
            origin, destination = leg.from_activity_ref, leg.to_activity_ref
            latest[origin] = min(latest[origin], latest[destination] - durations[origin] - leg.duration_minutes)
        for ref in starts:
            if ref in frozen and starts[ref] > latest[ref]:
                return snapshot, []
            starts[ref] = min(starts[ref], latest[ref])
            if ref in candidates and _minutes(candidates[ref].planned_start_time) - starts[ref] > 30:
                return snapshot, []
            if starts[ref] < daily_start or starts[ref] + durations[ref] > daily_end:
                return snapshot, []
        if any(starts[leg.to_activity_ref] < starts[leg.from_activity_ref] + durations[leg.from_activity_ref] + leg.duration_minutes for leg in legs):
            return snapshot, []

    adjustments = []
    updated = []
    for ref, item in candidates.items():
        start = starts[ref]
        if start == _minutes(item.planned_start_time):
            updated.append(item)
            continue
        changed_time = time(start // 60, start % 60)
        adjustments.append({
            "candidate_id": ref,
            "day_date": item.day_date.isoformat(),
            "from_time": item.planned_start_time.isoformat(timespec="minutes"),
            "to_time": changed_time.isoformat(timespec="minutes"),
        })
        updated.append(item.model_copy(update={"planned_start_time": changed_time}))
    return snapshot.model_copy(update={"activities": updated}), adjustments
