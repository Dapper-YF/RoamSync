"""Command-side policy for experience impact; never invoked by a GET."""
from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity_experience_impact import evaluate_activity_experience_time_impact
from app.database import Activity, ActivityExecution, PlanRevision, PlanningRun, TripExecution
from app.planning_run_repository import RecoveryPlanningConflictError, create_planning_run
from app.schemas import PlanningRunCreate


ACTIVE = ("queued", "researching", "awaiting_clarification", "planning", "validating", "awaiting_confirmation")


async def ensure_experience_recovery(session: AsyncSession, activity_execution_id: uuid.UUID) -> PlanningRun | None:
    """Create at most one recovery run, only for a deterministic infeasibility."""
    item = await session.scalar(select(ActivityExecution).where(ActivityExecution.id == activity_execution_id))
    if item is None:
        return None
    execution = await session.scalar(select(TripExecution).where(TripExecution.id == item.trip_execution_id))
    if execution is None:
        return None
    from app.formal_write import lock_trip
    await lock_trip(session, execution.trip_id)
    current_activity = await session.get(Activity, item.activity_id)
    if current_activity is None:
        return None
    impact = await evaluate_activity_experience_time_impact(session, execution.id, item.id)
    if impact.impact_state != "infeasible":
        return None
    snapshot = await _snapshot(session, execution, item, impact.model_dump(mode="json"))
    key = f"experience:{execution.id}:{execution.itinerary_version}:{item.id}"
    dismissed = await session.scalar(select(PlanningRun.id).where(
        PlanningRun.trip_id == execution.trip_id, PlanningRun.trigger_type == "experience_impact",
        PlanningRun.trigger_key == key, PlanningRun.trigger_fingerprint == snapshot["fingerprint"],
        PlanningRun.status == "rejected",
    ).limit(1))
    if dismissed is not None:
        return None
    existing = await session.scalar(select(PlanningRun).where(PlanningRun.trip_id == execution.trip_id, PlanningRun.trigger_key == key, PlanningRun.status.in_(ACTIVE)).with_for_update())
    if existing is not None:
        if existing.status != "awaiting_confirmation":
            existing.trigger_snapshot = snapshot
            await session.commit()
            return existing
        revision = await session.scalar(select(PlanRevision).where(PlanRevision.planning_run_id == existing.id, PlanRevision.status == "pending").with_for_update())
        if revision:
            revision.status = "superseded"
        existing.status = "cancelled"
        existing.completed_at = None
        await session.flush()
    # A navigation disruption may already own automatic recovery for this
    # formal version.  Its persisted facts and this experience fact both stay
    # available; only candidate-production ownership is serialized.
    owner = await session.scalar(select(PlanningRun).where(
        PlanningRun.trip_id == execution.trip_id,
        PlanningRun.base_trip_version == execution.itinerary_version,
        PlanningRun.trigger_type.in_(("experience_impact", "navigation_disruption")),
        PlanningRun.status.in_(ACTIVE),
    ).order_by(PlanningRun.created_at.desc()).limit(1).with_for_update())
    if owner is not None:
        return owner
    try:
        return await create_planning_run(
            session, execution.trip_id,
            PlanningRunCreate(run_type="replan", user_request="用户选择继续体验当前活动，确定性时间投影显示后续正式行程不可行；保护当前活动，仅调整后续未开始活动。", entry_point="trip_planner",
                selected_day_id=current_activity.day_plan_id),
            trigger_type="experience_impact", trigger_key=key, trigger_snapshot=snapshot,
            trigger_fingerprint=snapshot["fingerprint"],
        )
    except RecoveryPlanningConflictError:
        return await session.scalar(select(PlanningRun).where(
            PlanningRun.trip_id == execution.trip_id,
            PlanningRun.base_trip_version == execution.itinerary_version,
            PlanningRun.trigger_type.in_(("experience_impact", "navigation_disruption")),
            PlanningRun.status.in_(ACTIVE),
        ).order_by(PlanningRun.created_at.desc()).limit(1))


async def _snapshot(session: AsyncSession, execution: TripExecution, item: ActivityExecution, impact: dict) -> dict:
    facts = {"trip_execution_id": str(execution.id), "formal_itinerary_version": execution.itinerary_version,
             "activity_execution_id": str(item.id), "activity_execution_status": item.status,
             "actual_started_at": item.actual_started_at.isoformat() if item.actual_started_at else None,
             "actual_ended_at": item.actual_ended_at.isoformat() if item.actual_ended_at else None,
             "impact": impact}
    facts["fingerprint"] = hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return facts


async def refresh_experience_trigger_snapshot(session: AsyncSession, run: PlanningRun, *, update_run: bool = True) -> dict:
    """Worker-side fence: queued work must plan from the latest persisted facts."""
    trigger = run.trigger_snapshot or {}
    item = await session.get(ActivityExecution, uuid.UUID(str(trigger["activity_execution_id"])))
    execution = await session.get(TripExecution, item.trip_execution_id) if item else None
    if item is None or execution is None:
        raise ValueError("experience execution context is unavailable")
    impact = await evaluate_activity_experience_time_impact(session, execution.id, item.id)
    if impact.impact_state != "infeasible":
        raise ValueError("experience impact is no longer infeasible")
    latest = await _snapshot(session, execution, item, impact.model_dump(mode="json"))
    if update_run:
        run.trigger_snapshot = {**(run.trigger_snapshot or {}), **latest}
        run.trigger_fingerprint = latest["fingerprint"]
    return latest
