"""Application orchestration for deterministic navigation observations."""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Activity,
    ActivityExecution,
    DayPlan,
    NavigationDetectionState,
    NavigationSession,
    PlanningRun,
    RouteLeg,
    Trip,
    TripDisruptionEvent,
    TripExecution,
    TripPreferences,
)
from app.navigation.delay_impact import RemainingStop, propagate_delay
from app.navigation.disruption_service import record_disruption
from app.navigation.event_detector import (
    DetectorState,
    EventPolicy,
    detect_execution_events,
)
from app.navigation.execution_projection import project_execution_progress
from app.navigation.session_service import LIVE_STATUSES, TERMINAL_STATUSES
from app.planning_run_repository import RecoveryPlanningConflictError, create_planning_run
from app.schemas import (
    NavigationDisruptionReference,
    NavigationObservation,
    NavigationObservationResponse,
    NavigationRecoveryPlanningReference,
    PlanningRunCreate,
)


ACTIVE_RECOVERY_STATUSES = (
    "queued",
    "researching",
    "awaiting_clarification",
    "planning",
    "validating",
    "awaiting_confirmation",
)
COORDINATE_PRECISION = Decimal("0.000001")
ACCURACY_PRECISION = Decimal("0.01")


class NavigationObservationNotFoundError(Exception):
    pass


class NavigationObservationConflictError(Exception):
    pass


async def ingest_navigation_observation(
    session: AsyncSession,
    observation: NavigationObservation,
    *,
    policy: EventPolicy = EventPolicy(),
) -> NavigationObservationResponse:
    """Accept one observation and synchronously run only deterministic control logic.

    The row lock serializes observations for one navigation session. Database
    compare-and-set predicates still fence every material version at the write,
    so correctness does not depend on a Python check remaining true.
    """
    navigation = await session.scalar(
        select(NavigationSession)
        .where(NavigationSession.id == observation.session_id)
        .with_for_update()
    )
    if navigation is None:
        raise NavigationObservationNotFoundError("navigation session not found")

    fingerprint = _observation_fingerprint(observation)
    _validate_observation(navigation, observation, fingerprint)

    detection = await session.scalar(
        select(NavigationDetectionState)
        .where(NavigationDetectionState.navigation_session_id == navigation.id)
        .with_for_update()
    )
    if observation.sequence == navigation.last_location_sequence:
        if detection is None:
            raise NavigationObservationConflictError("detector state is missing for acknowledged observation")
        return await _response(
            session,
            navigation=navigation,
            detection=detection,
            replayed=True,
        )

    if detection is None:
        detection = NavigationDetectionState(
            navigation_session_id=navigation.id,
            itinerary_version=navigation.itinerary_version,
            last_processed_observation_sequence=navigation.last_location_sequence,
        )
        session.add(detection)
        await session.flush()
    if detection.itinerary_version != observation.itinerary_version:
        raise NavigationObservationConflictError("detector state belongs to another itinerary version")

    remaining_stops, daily_end = await _load_remaining_itinerary(session, navigation)
    impact = propagate_delay(
        current_eta=observation.eta,
        remaining_stops=remaining_stops,
        daily_end=daily_end,
    )
    projection = project_execution_progress(
        from_activity_id=str(navigation.from_activity_id),
        to_activity_id=str(navigation.to_activity_id),
        itinerary_version=navigation.itinerary_version,
        planned_arrival=navigation.planned_arrival_at,
        current_eta=observation.eta,
        impact=impact,
        warning_slack_minutes=policy.warning_slack_minutes,
    )
    events, next_detector = detect_execution_events(
        projection=projection,
        impact=impact,
        observed_at=observation.observed_at,
        policy=policy,
        previous=DetectorState(
            infeasible_observation_count=detection.consecutive_risk_count,
            current_risk_state=detection.current_risk_state,
            last_risk_transition_at=detection.last_risk_transition_at,
            last_event_detected_at=detection.last_event_detected_at,
            last_escalation_at=detection.last_escalation_at,
        ),
    )

    previous_sequence = navigation.last_location_sequence
    observation_write = await session.execute(
        update(NavigationSession)
        .where(
            NavigationSession.id == navigation.id,
            NavigationSession.status.in_(LIVE_STATUSES),
            NavigationSession.itinerary_version == observation.itinerary_version,
            NavigationSession.route_revision == observation.route_revision,
            NavigationSession.last_location_sequence == previous_sequence,
        )
        .values(
            last_location_sequence=observation.sequence,
            last_location_longitude=_coordinate(observation.position.longitude),
            last_location_latitude=_coordinate(observation.position.latitude),
            last_location_accuracy_meters=_accuracy(observation.location_accuracy_meters),
            last_location_at=observation.observed_at.astimezone(UTC),
            current_eta=observation.eta.astimezone(UTC),
            remaining_distance_meters=observation.remaining_distance_meters,
            remaining_duration_seconds=observation.remaining_duration_seconds,
            current_duration_minutes=math.ceil(observation.remaining_duration_seconds / 60),
            navigation_status=observation.navigation_status,
            observation_source=observation.source,
            last_observation_fingerprint=fingerprint,
            state_version=NavigationSession.state_version + 1,
        )
        .returning(NavigationSession.id)
    )
    if observation_write.scalar_one_or_none() is None:
        await session.rollback()
        raise NavigationObservationConflictError("observation lost its session/version/route fence")

    detection_write = await session.execute(
        update(NavigationDetectionState)
        .where(
            NavigationDetectionState.navigation_session_id == navigation.id,
            NavigationDetectionState.itinerary_version == observation.itinerary_version,
            NavigationDetectionState.last_processed_observation_sequence
            == detection.last_processed_observation_sequence,
        )
        .values(
            last_processed_observation_sequence=observation.sequence,
            consecutive_risk_count=next_detector.infeasible_observation_count,
            current_risk_state=next_detector.current_risk_state,
            minimum_downstream_slack_minutes=projection.minimum_downstream_slack_minutes,
            first_impacted_activity_id=(
                uuid.UUID(projection.first_impacted_activity_id)
                if projection.first_impacted_activity_id
                else None
            ),
            last_risk_transition_at=next_detector.last_risk_transition_at,
            last_event_detected_at=next_detector.last_event_detected_at,
            last_escalation_at=next_detector.last_escalation_at,
        )
        .returning(NavigationDetectionState.navigation_session_id)
    )
    if detection_write.scalar_one_or_none() is None:
        await session.rollback()
        raise NavigationObservationConflictError("observation lost its detector-state fence")

    for event in events:
        if event.kind != "disruption":
            continue
        disruption = await record_disruption(
            session,
            navigation.id,
            event,
            commit=False,
        )
        if disruption is not None:
            await _ensure_recovery_planning_run(session, navigation, disruption)

    await session.commit()
    navigation = await session.get(NavigationSession, navigation.id)
    detection = await session.get(NavigationDetectionState, navigation.id)
    return await _response(
        session,
        navigation=navigation,
        detection=detection,
        replayed=False,
    )


def _validate_observation(
    navigation: NavigationSession,
    observation: NavigationObservation,
    fingerprint: str,
) -> None:
    if navigation.status in TERMINAL_STATUSES or navigation.status not in LIVE_STATUSES:
        raise NavigationObservationConflictError(
            f"{navigation.status} navigation session cannot accept observations"
        )
    if navigation.itinerary_version != observation.itinerary_version:
        raise NavigationObservationConflictError("observation itinerary version is stale")
    if observation.sequence < navigation.last_location_sequence:
        raise NavigationObservationConflictError("observation sequence is stale")
    if observation.sequence == navigation.last_location_sequence:
        if navigation.last_observation_fingerprint == fingerprint:
            return
        raise NavigationObservationConflictError("observation sequence was reused with different facts")
    if navigation.route_revision != observation.route_revision:
        raise NavigationObservationConflictError("observation route revision is stale")
    if navigation.coordinate_system != observation.coordinate_system:
        raise NavigationObservationConflictError("observation coordinate system does not match session")
    if (
        navigation.last_location_at is not None
        and observation.observed_at.astimezone(UTC) < navigation.last_location_at.astimezone(UTC)
    ):
        raise NavigationObservationConflictError("observation timestamp is older than accepted runtime facts")


async def _load_remaining_itinerary(
    session: AsyncSession,
    navigation: NavigationSession,
) -> tuple[list[RemainingStop], datetime]:
    trip = await session.get(Trip, navigation.trip_id)
    preferences = await session.get(TripPreferences, navigation.trip_id)
    target_row = await session.execute(
        select(Activity, DayPlan)
        .join(DayPlan, Activity.day_plan_id == DayPlan.id)
        .where(
            Activity.id == navigation.to_activity_id,
            DayPlan.trip_id == navigation.trip_id,
        )
    )
    target = target_row.tuples().one_or_none()
    if trip is None or preferences is None or target is None:
        raise NavigationObservationConflictError("formal itinerary context is unavailable")
    target_activity, day = target
    activities = list(
        (
            await session.scalars(
                select(Activity)
                .where(
                    Activity.day_plan_id == day.id,
                    Activity.position >= target_activity.position,
                    Activity.status.not_in(("completed", "skipped")),
                )
                .order_by(Activity.position)
            )
        ).all()
    )
    execution_states = {
        row.activity_id: row.status
        for row in (
            await session.scalars(
                select(ActivityExecution).where(
                    ActivityExecution.trip_execution_id == navigation.trip_execution_id
                )
            )
        ).all()
    }
    activities = [
        activity
        for activity in activities
        if activity.id == navigation.to_activity_id
        or execution_states.get(activity.id) not in {"completed", "skipped"}
    ]
    if not activities or activities[0].id != navigation.to_activity_id:
        raise NavigationObservationConflictError("navigation target is no longer executable")
    routes = {
        (route.from_activity_id, route.to_activity_id): route.duration_minutes
        for route in (
            await session.scalars(
                select(RouteLeg).where(RouteLeg.day_plan_id == day.id)
            )
        ).all()
    }
    timezone = ZoneInfo(trip.timezone)
    stops: list[RemainingStop] = []
    for index, activity in enumerate(activities):
        travel = None
        if index < len(activities) - 1:
            travel = routes.get((activity.id, activities[index + 1].id))
            if travel is None:
                raise NavigationObservationConflictError("remaining formal itinerary has no adjacent route")
        stops.append(
            RemainingStop(
                activity_id=str(activity.id),
                planned_start=datetime.combine(day.date, activity.scheduled_time, tzinfo=timezone),
                duration_minutes=activity.duration_minutes,
                travel_to_next_minutes=travel,
                fixed_window=activity.schedule_locked,
            )
        )
    daily_end = datetime.combine(day.date, preferences.daily_end_time, tzinfo=timezone)
    return stops, daily_end


async def _ensure_recovery_planning_run(
    session: AsyncSession,
    navigation: NavigationSession,
    disruption: TripDisruptionEvent,
) -> PlanningRun:
    existing = await session.scalar(
        select(PlanningRun)
        .where(
            PlanningRun.disruption_event_id == disruption.id,
            PlanningRun.status.in_(ACTIVE_RECOVERY_STATUSES),
        )
        .order_by(PlanningRun.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if existing is not None:
        return existing
    # A recovery is owned by the formal trip/version, not by a particular
    # reality source.  Preserve this navigation disruption, but let an already
    # active experience recovery remain the sole candidate-producing owner.
    existing = await session.scalar(
        select(PlanningRun)
        .where(
            PlanningRun.trip_id == navigation.trip_id,
            PlanningRun.base_trip_version == navigation.itinerary_version,
            PlanningRun.trigger_type.in_(("experience_impact", "navigation_disruption")),
            PlanningRun.status.in_(ACTIVE_RECOVERY_STATUSES),
        )
        .order_by(PlanningRun.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if existing is not None:
        return existing
    execution = await session.get(TripExecution, navigation.trip_execution_id)
    try:
        return await create_planning_run(
            session,
            navigation.trip_id,
            PlanningRunCreate(
            run_type="replan",
            user_request="导航执行事实表明当前正式行程已不可行，请仅调整尚未完成的活动。",
            entry_point="trip_planner",
            selected_day_id=execution.current_day_plan_id if execution else None,
            disruption_event_id=disruption.id,
            ),
            commit=False,
        )
    except RecoveryPlanningConflictError:
        return await session.scalar(select(PlanningRun).where(
            PlanningRun.trip_id == navigation.trip_id,
            PlanningRun.base_trip_version == navigation.itinerary_version,
            PlanningRun.trigger_type.in_(("experience_impact", "navigation_disruption")),
            PlanningRun.status.in_(ACTIVE_RECOVERY_STATUSES),
        ).order_by(PlanningRun.created_at.desc()).limit(1))


async def _response(
    session: AsyncSession,
    *,
    navigation: NavigationSession,
    detection: NavigationDetectionState,
    replayed: bool,
) -> NavigationObservationResponse:
    disruption = await session.scalar(
        select(TripDisruptionEvent)
        .where(
            TripDisruptionEvent.navigation_session_id == navigation.id,
            TripDisruptionEvent.itinerary_version == navigation.itinerary_version,
            TripDisruptionEvent.status == "active",
        )
        .order_by(TripDisruptionEvent.last_seen_at.desc())
        .limit(1)
    )
    run = None
    if disruption is not None:
        run = await session.scalar(
            select(PlanningRun)
            .where(PlanningRun.disruption_event_id == disruption.id)
            .order_by(PlanningRun.created_at.desc())
            .limit(1)
        )
    return NavigationObservationResponse(
        session_id=navigation.id,
        itinerary_version=navigation.itinerary_version,
        accepted_sequence=navigation.last_location_sequence,
        replayed=replayed,
        session_status=navigation.status,
        current_eta=navigation.current_eta,
        remaining_distance_meters=navigation.remaining_distance_meters,
        remaining_duration_seconds=navigation.remaining_duration_seconds,
        risk_level=detection.current_risk_state,
        minimum_downstream_slack_minutes=detection.minimum_downstream_slack_minutes,
        first_impacted_activity_id=detection.first_impacted_activity_id,
        active_disruption=(
            NavigationDisruptionReference(
                id=disruption.id,
                event_type=disruption.event_type,
                impacted_identity=disruption.impacted_identity,
            )
            if disruption
            else None
        ),
        recovery_planning=(
            NavigationRecoveryPlanningReference(id=run.id, status=run.status)
            if run
            else None
        ),
        server_timestamp=datetime.now(UTC),
    )


def _observation_fingerprint(observation: NavigationObservation) -> str:
    canonical = observation.model_dump(mode="json")
    canonical["observed_at"] = observation.observed_at.astimezone(UTC).isoformat()
    canonical["eta"] = observation.eta.astimezone(UTC).isoformat()
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _coordinate(value: float) -> Decimal:
    return Decimal(str(value)).quantize(COORDINATE_PRECISION)


def _accuracy(value: float) -> Decimal:
    return Decimal(str(value)).quantize(ACCURACY_PRECISION)
