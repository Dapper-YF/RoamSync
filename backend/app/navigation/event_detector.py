"""Pure deterministic conversion from execution projection to events."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.navigation.delay_impact import DelayImpact
from app.navigation.execution_projection import ExecutionProgressProjection


EventKind = Literal["observation", "warning", "disruption", "transition"]
EventType = Literal["eta_delayed", "arrival_risk", "missed_time_window", "itinerary_infeasible", "leg_completed"]


@dataclass(frozen=True, slots=True)
class EventPolicy:
    warning_slack_minutes: int = 15
    disruption_slack_minutes: int = -1
    consecutive_observations: int = 3
    cooldown_seconds: int = 300


@dataclass(frozen=True, slots=True)
class DetectorState:
    infeasible_observation_count: int = 0
    current_risk_state: Literal["normal", "warning", "critical", "infeasible"] = "normal"
    last_risk_transition_at: datetime | None = None
    last_event_detected_at: datetime | None = None
    last_escalation_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DetectedExecutionEvent:
    event_type: EventType
    kind: EventKind
    occurred_at: datetime
    impacted_identity: str | None
    impact_snapshot: dict


def detect_execution_events(
    *, projection: ExecutionProgressProjection,
    impact: DelayImpact | None,
    observed_at: datetime,
    policy: EventPolicy = EventPolicy(),
    previous: DetectorState = DetectorState(),
) -> tuple[list[DetectedExecutionEvent], DetectorState]:
    """No I/O, persistence, cooldown lookup, or planning side effect occurs here."""
    events: list[DetectedExecutionEvent] = []
    if projection.delay_minutes > 0:
        events.append(DetectedExecutionEvent("eta_delayed", "observation", observed_at, projection.current_leg[1], _snapshot(projection)))
    if impact:
        missed = next((stop for stop in impact.stops if stop.fixed_window and stop.delay_minutes > 0), None)
        if missed:
            events.append(DetectedExecutionEvent("missed_time_window", "disruption", observed_at, missed.activity_id, _snapshot(projection)))
            return events, _next_state(
                previous=previous,
                projection=projection,
                observed_at=observed_at,
                infeasible_count=0,
                events=events,
            )
    minimum = projection.minimum_downstream_slack_minutes
    if minimum is not None and minimum < policy.warning_slack_minutes:
        events.append(DetectedExecutionEvent("arrival_risk", "warning", observed_at, projection.first_impacted_activity_id, _snapshot(projection)))
    if minimum is None or minimum > policy.disruption_slack_minutes:
        return events, _next_state(
            previous=previous,
            projection=projection,
            observed_at=observed_at,
            infeasible_count=0,
            events=events,
        )
    count = previous.infeasible_observation_count + 1
    state = DetectorState(count)
    if count >= policy.consecutive_observations:
        events.append(DetectedExecutionEvent("itinerary_infeasible", "disruption", observed_at, projection.first_impacted_activity_id, _snapshot(projection)))
    return events, _next_state(
        previous=previous,
        projection=projection,
        observed_at=observed_at,
        infeasible_count=state.infeasible_observation_count,
        events=events,
    )


def _next_state(
    *,
    previous: DetectorState,
    projection: ExecutionProgressProjection,
    observed_at: datetime,
    infeasible_count: int,
    events: list[DetectedExecutionEvent],
) -> DetectorState:
    risk = projection.risk_level
    transition_at = (
        observed_at if risk != previous.current_risk_state else previous.last_risk_transition_at
    )
    last_event_at = observed_at if events else previous.last_event_detected_at
    escalated = any(event.kind == "disruption" for event in events)
    last_escalation_at = (
        observed_at
        if escalated and previous.last_escalation_at is None
        else previous.last_escalation_at
    )
    return DetectorState(
        infeasible_observation_count=infeasible_count,
        current_risk_state=risk,
        last_risk_transition_at=transition_at,
        last_event_detected_at=last_event_at,
        last_escalation_at=last_escalation_at,
    )


def _snapshot(projection: ExecutionProgressProjection) -> dict:
    return {"delay_minutes": projection.delay_minutes, "minimum_slack_minutes": projection.minimum_downstream_slack_minutes,
            "risk_level": projection.risk_level, "affected_activity_ids": list(projection.downstream_affected_activity_ids)}
