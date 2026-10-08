"""Project travel delay through the remaining itinerary.

The calculation is deliberately deterministic.  A routing provider supplies the
current ETA and the formal itinerary supplies stops, fixed appointments, and
travel durations.  This module answers whether the remaining plan is still
feasible; it never edits the plan or invokes a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.timeline_impact import TimelineStop, project_timeline_impact


@dataclass(frozen=True, slots=True)
class RemainingStop:
    """One not-yet-completed itinerary activity.

    ``travel_to_next_minutes`` is the formal/planned travel time from this
    activity to the next remaining activity.  It is absent on the last stop.
    A fixed window represents an appointment, departure, or other start time
    that cannot be silently moved by execution feedback.
    """

    activity_id: str
    planned_start: datetime
    duration_minutes: int
    travel_to_next_minutes: int | None = None
    fixed_window: bool = False


@dataclass(frozen=True, slots=True)
class StopImpact:
    activity_id: str
    projected_arrival: datetime
    projected_start: datetime
    projected_end: datetime
    delay_minutes: int
    slack_minutes: int
    fixed_window: bool


@dataclass(frozen=True, slots=True)
class DelayImpact:
    """A forecast from the present leg through the current execution day."""

    current_eta: datetime
    daily_end: datetime
    stops: tuple[StopImpact, ...]

    @property
    def feasible(self) -> bool:
        return all(stop.slack_minutes >= 0 for stop in self.stops)


EventType = Literal[
    "ETA_DELAYED",
    "ARRIVAL_RISK",
    "MISSED_TIME_WINDOW",
]


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    event_type: EventType
    activity_id: str
    occurred_at: datetime
    details: dict[str, int | str]
    affects_itinerary: bool


@dataclass(frozen=True, slots=True)
class ImpactPolicy:
    """Thresholds used to turn a forecast into debounced domain events.

    Persistence and debounce state belong to the later event service.  Keeping
    thresholds here makes the feasibility decision directly unit-testable.
    """

    eta_delay_minutes: int = 10
    arrival_risk_slack_minutes: int = 15


def propagate_delay(
    *,
    current_eta: datetime,
    remaining_stops: list[RemainingStop],
    daily_end: datetime,
) -> DelayImpact:
    """Navigation adapter over the source-neutral timeline core."""
    timeline = project_timeline_impact(
        current_boundary_at=current_eta,
        remaining_stops=[
            TimelineStop(stop.activity_id, stop.planned_start, stop.duration_minutes,
                         stop.travel_to_next_minutes, stop.fixed_window)
            for stop in remaining_stops
        ],
        daily_end=daily_end,
    )
    return DelayImpact(
        current_eta=current_eta,
        daily_end=daily_end,
        stops=tuple(
            StopImpact(item.activity_id, item.projected_arrival, item.projected_start,
                       item.projected_end, item.delay_minutes, item.slack_minutes,
                       item.fixed_window)
            for item in timeline.stops
        ),
    )


def detect_impact_events(
    impact: DelayImpact,
    *,
    observed_at: datetime,
    policy: ImpactPolicy = ImpactPolicy(),
) -> list[ExecutionEvent]:
    """Emit only itinerary-relevant forecast events.

    A normal ETA increase is informative but has ``affects_itinerary=False``.
    A negative slack or a missed fixed window is a Macro Replan candidate.
    Event de-duplication and cooldown checks are intentionally not hidden here:
    the forthcoming persistence service will apply them against past events.
    """
    events: list[ExecutionEvent] = []
    for stop in impact.stops:
        if stop.delay_minutes >= policy.eta_delay_minutes:
            events.append(ExecutionEvent(
                event_type="ETA_DELAYED", activity_id=stop.activity_id,
                occurred_at=observed_at,
                details={"delay_minutes": stop.delay_minutes, "slack_minutes": stop.slack_minutes},
                affects_itinerary=False,
            ))
        if stop.fixed_window and stop.delay_minutes > 0:
            events.append(ExecutionEvent(
                event_type="MISSED_TIME_WINDOW", activity_id=stop.activity_id,
                occurred_at=observed_at,
                details={"delay_minutes": stop.delay_minutes, "slack_minutes": stop.slack_minutes},
                affects_itinerary=True,
            ))
        elif stop.slack_minutes < 0:
            events.append(ExecutionEvent(
                event_type="ARRIVAL_RISK", activity_id=stop.activity_id,
                occurred_at=observed_at,
                details={"slack_minutes": stop.slack_minutes, "delay_minutes": stop.delay_minutes},
                affects_itinerary=True,
            ))
        elif stop.slack_minutes < policy.arrival_risk_slack_minutes:
            events.append(ExecutionEvent(
                event_type="ARRIVAL_RISK", activity_id=stop.activity_id,
                occurred_at=observed_at,
                details={"slack_minutes": stop.slack_minutes, "delay_minutes": stop.delay_minutes},
                affects_itinerary=False,
            ))
    return events
