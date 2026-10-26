"""Build an execution-aware, read-only planning projection."""
from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    ActivityExecution,
    NavigationDetectionState,
    NavigationSession,
    TripDisruptionEvent,
    TripExecution,
)


async def build_execution_recovery_context(session: AsyncSession, trip_id: uuid.UUID) -> dict:
    execution = await session.scalar(select(TripExecution).where(TripExecution.trip_id == trip_id))
    if execution is None:
        return {
            "frozen_activity_ids": [], "protected_activity_ids": [],
            "mutable_activity_ids": [], "recovery_options": [],
            "execution_state": {"status": "not_started"},
        }
    rows = list((await session.scalars(select(ActivityExecution).where(ActivityExecution.trip_execution_id == execution.id))).all())
    frozen = {str(item.activity_id) for item in rows if item.status in {"completed", "skipped"} or item.actual_ended_at is not None}
    protected = {str(item.activity_id) for item in rows if item.status in {"arrived", "in_progress"} or item.actual_started_at is not None}
    if execution.current_activity_id:
        protected.add(str(execution.current_activity_id))
    navigation = await session.scalar(select(NavigationSession).where(
        NavigationSession.trip_execution_id == execution.id,
        NavigationSession.status.in_(("active", "rerouting")),
    ))
    if navigation:
        protected.add(str(navigation.to_activity_id))
    protected -= frozen
    detection = await session.get(NavigationDetectionState, navigation.id) if navigation else None
    disruption = await session.scalar(select(TripDisruptionEvent).where(
        TripDisruptionEvent.trip_execution_id == execution.id,
        TripDisruptionEvent.status == "active",
    ).order_by(TripDisruptionEvent.detected_at.desc()).limit(1))
    delay_minutes = None
    if navigation and navigation.current_eta and navigation.planned_arrival_at:
        delay_minutes = max(0, round((navigation.current_eta - navigation.planned_arrival_at).total_seconds() / 60))
    impact = disruption.impact_snapshot if disruption else {}
    return {
        "trip_execution_id": str(execution.id),
        "frozen_activity_ids": sorted(frozen),
        "protected_activity_ids": sorted(protected),
        # IDs are classified against formal activities by planning_context.
        "mutable_activity_ids": [],
        "recovery_options": [],
        "execution_state": {
            "status": execution.status,
            "trip_execution_id": str(execution.id),
            "completed_activity_ids": sorted(frozen),
            "current_activity_id": str(execution.current_activity_id) if execution.current_activity_id else None,
            "navigation_target_activity_id": str(navigation.to_activity_id) if navigation else None,
            "current_eta": navigation.current_eta.isoformat() if navigation and navigation.current_eta else None,
            "planned_arrival": navigation.planned_arrival_at.isoformat() if navigation else None,
            "delay_minutes": delay_minutes,
            "risk_state": detection.current_risk_state if detection else ("disruption" if disruption else "unknown"),
            "minimum_downstream_slack_minutes": (
                detection.minimum_downstream_slack_minutes if detection
                else impact.get("minimum_slack_minutes")
            ),
            "first_impacted_activity_id": str(detection.first_impacted_activity_id) if detection and detection.first_impacted_activity_id
                else impact.get("first_impacted_activity_id"),
        },
    }
