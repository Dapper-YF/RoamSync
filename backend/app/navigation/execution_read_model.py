"""A BFF-style read model for the Web execution workspace.

It assembles persisted facts only.  It deliberately does not repeat Slack,
event-detection or recovery algorithms in a controller or in TypeScript.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Activity,
    ActivityExecution,
    NavigationDetectionState,
    NavigationSession,
    PlaceCandidate,
    PlanRevision,
    PlanningRun,
    Trip,
    TripDisruptionEvent,
)
from app.navigation.session_service import navigation_session_response
from app.activity_experience_impact import evaluate_activity_experience_time_impact
from app.schemas import ActivityExperienceProgressResponse, ExecutionReadModelResponse, RecoveryPlanningResponse
from app.trip_execution_service import get_trip_execution, projected_activity_end, total_extension_minutes


async def get_execution_read_model(session: AsyncSession, trip_id: uuid.UUID) -> ExecutionReadModelResponse:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        from app.repository import TripNotFoundError
        raise TripNotFoundError
    execution = await get_trip_execution(session, trip_id)
    navigation = None
    detection = None
    if execution.id:
        navigation = await session.scalar(select(NavigationSession).where(
            NavigationSession.trip_execution_id == execution.id,
            NavigationSession.status.in_(("active", "rerouting")),
        ).order_by(NavigationSession.updated_at.desc()).limit(1))
        if navigation:
            detection = await session.get(NavigationDetectionState, navigation.id)
    disruption = await session.scalar(select(TripDisruptionEvent).where(
        TripDisruptionEvent.trip_id == trip_id, TripDisruptionEvent.status == "active",
    ).order_by(TripDisruptionEvent.last_seen_at.desc()).limit(1))
    recovery_run = None
    revision = None
    if disruption:
        recovery_run = await session.scalar(select(PlanningRun).where(
            PlanningRun.disruption_event_id == disruption.id,
        ).order_by(PlanningRun.created_at.desc()).limit(1))
        if recovery_run:
            candidate = await session.scalar(select(PlanRevision).where(
                PlanRevision.planning_run_id == recovery_run.id,
                PlanRevision.status == "pending",
            ).order_by(PlanRevision.revision_number.desc()).limit(1))
            if candidate:
                proposed_snapshot = await _recovery_proposal_for_read_model(session, candidate)
                revision = {"id": str(candidate.id), "status": candidate.status,
                            "difference_summary": candidate.difference_summary,
                            "reason": candidate.reason,
                            # Candidate content is still a proposal.  These are
                            # persisted revision facts, not model prose copied
                            # into a Web-only representation.
                            "proposed_snapshot": proposed_snapshot,
                            # This is a display-only comparison of the persisted
                            # before/after snapshots.  Validation and commit stay
                            # exclusively in the PlanRevision service.
                            "change_summary": _recovery_change_summary(candidate.before_snapshot, proposed_snapshot)}
    names = {}
    ids = [item for item in (execution.current_activity_id, navigation.to_activity_id if navigation else None) if item]
    if ids:
        # An Activity owns schedule data but the canonical place name belongs
        # to PlaceCandidate.  The execution BFF must return a display name so
        # mobile clients do not issue a second lookup just to explain risk.
        rows = await session.execute(
            select(Activity.id, Activity.custom_name, PlaceCandidate.name)
            .join(PlaceCandidate, PlaceCandidate.id == Activity.place_candidate_id)
            .where(Activity.id.in_(ids))
        )
        names = {activity_id: custom_name or place_name for activity_id, custom_name, place_name in rows}
    impact = disruption.impact_snapshot if disruption else {}
    minimum_slack = (
        detection.minimum_downstream_slack_minutes
        if detection
        else impact.get("minimum_slack_minutes")
    )
    first_impacted = (
        detection.first_impacted_activity_id
        if detection
        else _uuid_or_none(impact.get("first_impacted_activity_id"))
    )
    delay = bool(navigation and navigation.current_eta and navigation.current_eta > navigation.planned_arrival_at)
    experience = await _current_activity_experience(session, execution)
    # A live navigation ETA is already an authoritative boundary from the
    # actual departure. Do not add the preceding activity shift to it again.
    experience_impact = (
        await evaluate_activity_experience_time_impact(session, execution.id, experience.activity_execution_id)
        if experience is not None and navigation is None
        else None
    )
    experience_run = await session.scalar(select(PlanningRun).where(
        PlanningRun.trip_id == trip_id,
        PlanningRun.trigger_type == "experience_impact",
        PlanningRun.status.in_((
            "queued", "researching", "awaiting_clarification", "planning",
            "validating", "awaiting_confirmation",
        )),
    ).order_by(PlanningRun.created_at.desc()).limit(1))
    recovery_planning = await _recovery_planning(
        session, disruption=disruption, disruption_run=recovery_run,
        experience_run=experience_run, experience=experience,
        experience_impact=experience_impact, names=names,
    )
    return ExecutionReadModelResponse(
        trip_id=trip_id, itinerary_version=trip.version, execution=execution,
        navigation_session=navigation_session_response(navigation) if navigation else None,
        current_activity_name=names.get(execution.current_activity_id),
        current_activity_experience=experience,
        experience_impact=experience_impact,
        navigation_target_name=names.get(navigation.to_activity_id) if navigation else None,
        risk_level="disruption" if disruption else "eta_delayed" if delay else "normal" if navigation else "unknown",
        minimum_downstream_slack_minutes=minimum_slack,
        first_impacted_activity_id=first_impacted,
        active_disruption=_disruption(disruption) if disruption else None,
        active_recovery_run=_run(recovery_run) if recovery_run else None,
        recovery_revision=revision, generated_at=datetime.now(UTC),
        recovery_planning=recovery_planning,
    )


async def _current_activity_experience(
    session: AsyncSession, execution
) -> ActivityExperienceProgressResponse | None:
    """Derive current dwell timing from persisted execution facts and events."""
    if execution.id is None or execution.current_activity_id is None:
        return None
    row = await session.execute(
        select(ActivityExecution, Activity)
        .join(Activity, ActivityExecution.activity_id == Activity.id)
        .where(
            ActivityExecution.trip_execution_id == execution.id,
            ActivityExecution.activity_id == execution.current_activity_id,
        )
    )
    pair = row.tuples().one_or_none()
    if pair is None:
        return None
    item, activity = pair
    total = await total_extension_minutes(session, item.id)
    ended_at = item.actual_ended_at
    elapsed = None
    if item.actual_started_at is not None:
        elapsed_end = ended_at or datetime.now(UTC)
        elapsed = max(0, int((elapsed_end - item.actual_started_at).total_seconds() // 60))
    # A completion is historical fact, not a future projection.  The current
    # activity normally advances before this view is read; this guard makes the
    # contract correct even around that transition.
    projected = None if ended_at is not None else projected_activity_end(item, activity.duration_minutes, total)
    return ActivityExperienceProgressResponse(
        activity_execution_id=item.id,
        activity_id=activity.id,
        planned_duration_minutes=activity.duration_minutes,
        actual_started_at=item.actual_started_at,
        actual_ended_at=ended_at,
        elapsed_experience_minutes=elapsed,
        total_extension_minutes=total,
        projected_end_at=projected,
    )


def _uuid_or_none(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _disruption(item: TripDisruptionEvent) -> dict:
    return {"id": str(item.id), "event_type": item.event_type, "impacted_identity": item.impacted_identity,
            "impact_snapshot": item.impact_snapshot, "detected_at": item.detected_at,
            "last_seen_at": item.last_seen_at, "itinerary_version": item.itinerary_version}


def _run(item: PlanningRun) -> dict:
    return {"id": str(item.id), "status": item.status, "disruption_event_id": str(item.disruption_event_id),
            "base_trip_version": item.base_trip_version, "error_code": item.error_code,
            "error_message": item.error_message}


async def _recovery_planning(
    session: AsyncSession, *, disruption: TripDisruptionEvent | None,
    disruption_run: PlanningRun | None, experience_run: PlanningRun | None,
    experience: ActivityExperienceProgressResponse | None, experience_impact,
    names: dict,
) -> RecoveryPlanningResponse | None:
    """Choose the one user-actionable recovery without leaking trigger JSON."""
    run = disruption_run or experience_run
    if run is None:
        return None
    candidate = await session.scalar(select(PlanRevision).where(
        PlanRevision.planning_run_id == run.id, PlanRevision.status == "pending",
    ).order_by(PlanRevision.revision_number.desc()).limit(1))
    pending = None
    if candidate:
        proposed = await _recovery_proposal_for_read_model(session, candidate)
        pending = {"id": str(candidate.id), "status": candidate.status,
                   "difference_summary": candidate.difference_summary, "reason": candidate.reason,
                   "proposed_snapshot": proposed,
                   "change_summary": _recovery_change_summary(candidate.before_snapshot, proposed)}
    status_map = {"researching": "planning", "validating": "planning", "awaiting_clarification": "planning", "cancelled": "superseded"}
    status = status_map.get(run.status, run.status)
    if status not in {"queued", "planning", "awaiting_confirmation", "accepted", "rejected", "superseded", "failed"}:
        status = "planning"
    if disruption and disruption_run and run.id == disruption_run.id:
        impact = disruption.impact_snapshot or {}
        return RecoveryPlanningResponse(
            source="navigation_disruption", status=status, planning_run_id=run.id,
            reason_summary="当前导航延误已经影响后续行程。",
            time_shift_minutes=impact.get("delay_minutes"),
            minimum_downstream_slack_minutes=impact.get("minimum_slack_minutes"),
            first_impacted_activity_id=_uuid_or_none(impact.get("first_impacted_activity_id")),
            pending_revision=pending,
            source_detail={"disruption_type": disruption.event_type, "detected_at": disruption.detected_at.isoformat(),
                           "affected_activity": disruption.impacted_identity},
        )
    if experience is None:
        return None
    impact = experience_impact
    return RecoveryPlanningResponse(
        source="activity_experience", status=status, planning_run_id=run.id,
        reason_summary="你选择继续停留，RoamSync 正在根据新的离开时间调整后续安排。",
        trigger_activity_id=experience.activity_id, trigger_activity_name=names.get(experience.activity_id),
        time_shift_minutes=impact.time_shift_minutes if impact else None,
        minimum_downstream_slack_minutes=impact.minimum_downstream_slack_minutes if impact else None,
        first_impacted_activity_id=impact.first_impacted_activity_id if impact else None,
        pending_revision=pending,
        source_detail={"total_extension_minutes": experience.total_extension_minutes,
                       "authoritative_boundary": experience.projected_end_at.isoformat() if experience.projected_end_at else None,
                       "planned_end": None, "projected_end": experience.projected_end_at.isoformat() if experience.projected_end_at else None,
                       "impact_state": impact.impact_state if impact else "unavailable"},
    )


async def _recovery_proposal_for_read_model(session: AsyncSession, revision: PlanRevision) -> dict:
    """Add stable display names without exposing a second client-side lookup path."""
    snapshot = dict(revision.proposed_snapshot)
    activities = [dict(item) for item in snapshot.get("activities", [])]
    place_ids = []
    for item in activities:
        try:
            place_ids.append(uuid.UUID(str(item.get("place_candidate_id"))))
        except (TypeError, ValueError):
            continue
    names: dict[uuid.UUID, str] = {}
    if place_ids:
        places = (await session.scalars(select(PlaceCandidate).where(PlaceCandidate.id.in_(place_ids)))).all()
        names = {item.id: item.name for item in places}
    for item in activities:
        try:
            item["place_name"] = names.get(uuid.UUID(str(item.get("place_candidate_id"))))
        except (TypeError, ValueError):
            item["place_name"] = None
    snapshot["activities"] = activities
    return snapshot


def _recovery_change_summary(before_snapshot: dict, proposed_snapshot: dict) -> dict:
    """Return only changes that can be proven from persisted snapshots.

    Candidate snapshots do not encode removals, slack-after-recovery, or route
    mode deltas.  Omitting those fields is intentional: the Web client must not
    turn an inference into a recovery guarantee.
    """
    before_by_id = {
        str(activity.get("id")): activity
        for day in before_snapshot.get("days", [])
        for activity in day.get("activities", [])
        if activity.get("id")
    }
    adjusted = []
    for activity in proposed_snapshot.get("activities", []):
        replaced_id = activity.get("replaces_activity_id")
        before = before_by_id.get(str(replaced_id)) if replaced_id else None
        if before is None:
            continue
        before_time = str(before.get("scheduled_time", ""))
        after_time = str(activity.get("planned_start_time", ""))
        before_duration = before.get("duration_minutes")
        after_duration = activity.get("duration_minutes")
        if before_time == after_time and before_duration == after_duration:
            continue
        adjusted.append({
            "activity_id": str(replaced_id),
            "name": before.get("display_name") or activity.get("place_name"),
            "before_start_time": before_time,
            "after_start_time": after_time,
            "before_duration_minutes": before_duration,
            "after_duration_minutes": after_duration,
        })
    return {"adjusted_activities": adjusted}
