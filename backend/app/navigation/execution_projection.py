"""Read-model projection; it never owns or rewrites itinerary state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.navigation.delay_impact import DelayImpact


@dataclass(frozen=True, slots=True)
class ExecutionProgressProjection:
    current_leg: tuple[str, str]
    projected_arrival: datetime | None
    planned_arrival: datetime
    delay_minutes: int
    minimum_downstream_slack_minutes: int | None
    first_impacted_activity_id: str | None
    downstream_affected_activity_ids: tuple[str, ...]
    feasible: bool
    risk_level: Literal["normal", "warning", "critical", "infeasible"]
    itinerary_version: int


def project_execution_progress(
    *,
    from_activity_id: str,
    to_activity_id: str,
    itinerary_version: int,
    planned_arrival: datetime,
    current_eta: datetime | None,
    impact: DelayImpact | None,
    warning_slack_minutes: int,
) -> ExecutionProgressProjection:
    stops = impact.stops if impact else ()
    slacks = [stop.slack_minutes for stop in stops]
    minimum = min(slacks) if slacks else None
    first = next((stop for stop in stops if stop.slack_minutes < warning_slack_minutes), None)
    affected = tuple(stop.activity_id for stop in stops if stop.slack_minutes < warning_slack_minutes)
    delay = 0
    if current_eta is not None:
        delay = max(0, round((current_eta - planned_arrival).total_seconds() / 60))
    risk: Literal["normal", "warning", "critical", "infeasible"] = "normal"
    if minimum is not None and minimum < 0:
        risk = "infeasible"
    elif minimum is not None and minimum < warning_slack_minutes:
        risk = "warning"
    elif delay:
        risk = "critical"
    return ExecutionProgressProjection(
        current_leg=(from_activity_id, to_activity_id), projected_arrival=current_eta,
        planned_arrival=planned_arrival, delay_minutes=delay,
        minimum_downstream_slack_minutes=minimum,
        first_impacted_activity_id=first.activity_id if first else None,
        downstream_affected_activity_ids=affected, feasible=minimum is None or minimum >= 0,
        risk_level=risk, itinerary_version=itinerary_version,
    )
