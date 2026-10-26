"""Small, deterministic read model for rejected planning decisions.

This module deliberately retrieves only explicit feedback from the same trip,
target day and formal-itinerary version.  It is request-scoped evidence, not a
long-term preference store and never calls a model or external provider.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import CandidateRouteLeg, PlanningRun, PlanRevision


async def retrieve_decision_memory(
    session: AsyncSession,
    *,
    trip_id: uuid.UUID,
    target_days: list[str],
    base_trip_version: int,
    limit: int = 3,
) -> list[dict]:
    """Return recent explicit rejection feedback eligible for this decision."""
    if not target_days:
        return []
    requested_days = set(target_days)
    rows = (await session.execute(
        select(PlanRevision, PlanningRun)
        .join(PlanningRun, PlanRevision.planning_run_id == PlanningRun.id)
        .where(
            PlanRevision.trip_id == trip_id,
            PlanRevision.status == "rejected",
            PlanningRun.base_trip_version == base_trip_version,
        )
        .order_by(PlanRevision.decided_at.desc(), PlanRevision.created_at.desc())
        .limit(24)
    )).all()
    memories: list[dict] = []
    for revision, run in rows:
        if not (revision.rejection_reason_code or revision.rejection_reason_text):
            continue
        candidate_days = {
            str(activity.get("day_date"))
            for activity in (revision.proposed_snapshot or {}).get("activities", [])
            if activity.get("day_date")
        }
        matched_days = sorted(candidate_days & requested_days)
        if not matched_days:
            continue
        route_legs = list((await session.scalars(
            select(CandidateRouteLeg).where(CandidateRouteLeg.plan_revision_id == revision.id)
        )).all())
        memories.append({
            "source_revision_id": str(revision.id),
            "source_run_id": str(run.id),
            "trip_id": str(trip_id),
            "target_day": matched_days[0],
            "decision": "rejected",
            "rejection_reason_code": revision.rejection_reason_code,
            "rejection_reason_text": revision.rejection_reason_text,
            "previous_candidate_summary": _candidate_summary(
                revision.proposed_snapshot or {}, revision.before_snapshot or {},
                route_legs, matched_days[0],
            ),
            "previous_goal_summary": (revision.difference_summary or {}).get("goal_satisfaction"),
            "base_trip_version": run.base_trip_version,
            "created_at": revision.created_at.isoformat() if revision.created_at else None,
            "retrieved_at": datetime.now().astimezone().isoformat(),
        })
        if len(memories) >= limit:
            break
    return memories


def _candidate_summary(snapshot: dict, before: dict, route_legs: list[CandidateRouteLeg], target_day: str) -> dict:
    activities = [
        item for item in snapshot.get("activities", [])
        if str(item.get("day_date")) == target_day
    ]
    day_legs = [leg for leg in route_legs if leg.day_date.isoformat() == target_day]
    replaced = {str(item["replaces_activity_id"]) for item in activities if item.get("replaces_activity_id")}
    before_ids = {
        str(item["id"]) for day in before.get("days", []) if day.get("date") == target_day
        for item in day.get("activities", []) if item.get("id")
    }
    added = [str(item["place_candidate_id"]) for item in activities if not item.get("replaces_activity_id")]
    end_time = _day_end_time(activities)
    walking = [leg for leg in day_legs if leg.mode == "walk"]
    return {
        "activity_count": len(activities),
        "end_time": end_time,
        "walking_minutes": sum(leg.duration_minutes for leg in walking) if day_legs else None,
        "route_minutes": sum(leg.duration_minutes for leg in day_legs) if day_legs else None,
        "route_distance_meters": sum(leg.distance_meters for leg in day_legs) if day_legs else None,
        "added_activity_ids": added,
        "removed_activity_ids": sorted(before_ids - replaced) if before_ids else [],
        "changed_activity_ids": sorted(replaced),
    }


def _day_end_time(activities: list[dict]) -> str | None:
    end: datetime | None = None
    for activity in activities:
        raw_start = activity.get("planned_start_time")
        duration = activity.get("duration_minutes")
        if not raw_start or not isinstance(duration, int):
            continue
        try:
            start = datetime.combine(date(2000, 1, 1), time.fromisoformat(str(raw_start)))
        except ValueError:
            continue
        candidate_end = start + timedelta(minutes=duration)
        if end is None or candidate_end > end:
            end = candidate_end
    return end.time().isoformat(timespec="minutes") if end else None
