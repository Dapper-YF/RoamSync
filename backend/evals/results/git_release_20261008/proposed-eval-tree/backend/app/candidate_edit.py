"""Explicit initial-candidate editing; draft history never becomes formal state."""
import hashlib
import json
import uuid

from sqlalchemy import select

from app.database import Activity, DayPlan, PlanningRun, PlanRevision, Trip
from app.schemas import CandidatePlanSnapshot


class CandidateEditUnavailable(ValueError):
    pass


def snapshot_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def bind_initial_candidate(session, source_run_id, run):
    if not source_run_id or not (run.intent_resolution or {}).get("grounded_intent", {}).get("target_day_ids"):
        return
    if await session.scalar(select(Activity.id).join(DayPlan).where(DayPlan.trip_id == run.trip_id).limit(1)):
        return
    source = await session.get(PlanningRun, source_run_id)
    if not source or source.trip_id != run.trip_id or source.base_trip_version != run.base_trip_version or source.status != "awaiting_confirmation":
        return
    revision = await session.scalar(select(PlanRevision).where(PlanRevision.planning_run_id == source.id, PlanRevision.status == "pending"))
    if not revision or not revision.validation_result.get("valid"):
        return
    run.trigger_snapshot = {**(run.trigger_snapshot or {}), "candidate_edit": {
        "revision_id": str(revision.id), "snapshot_hash": snapshot_hash(revision.proposed_snapshot),
    }}


async def load_initial_candidate(session, run):
    ref = (run.trigger_snapshot or {}).get("candidate_edit")
    if not ref:
        return None
    revision = await session.get(PlanRevision, uuid.UUID(ref["revision_id"]))
    source = await session.get(PlanningRun, revision.planning_run_id) if revision else None
    trip = await session.get(Trip, run.trip_id)
    has_formal = await session.scalar(select(Activity.id).join(DayPlan).where(DayPlan.trip_id == run.trip_id).limit(1))
    if (not source or source.trip_id != run.trip_id or source.status != "awaiting_confirmation"
        or revision.status != "pending" or source.base_trip_version != run.base_trip_version
        or trip.version != run.base_trip_version or has_formal
        or not revision.validation_result.get("valid") or snapshot_hash(revision.proposed_snapshot) != ref["snapshot_hash"]):
        raise CandidateEditUnavailable("candidate_edit_base_unavailable")
    return CandidatePlanSnapshot.model_validate(revision.proposed_snapshot)


def preserved_candidate_activities(base, target_dates):
    return [item for item in base.activities if item.day_date not in target_dates] if base else []


def candidate_base_from_context(state):
    value = state["planning_context"].get("candidate_edit_base")
    return CandidatePlanSnapshot.model_validate(value) if value else None
