"""Source-neutral deterministic projection of a formal itinerary timeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class TimelineStop:
    activity_id: str
    planned_start: datetime
    duration_minutes: int
    travel_to_next_minutes: int | None = None
    fixed_window: bool = False


@dataclass(frozen=True, slots=True)
class TimelineStopImpact:
    activity_id: str
    projected_arrival: datetime
    projected_start: datetime
    projected_end: datetime
    time_shift_minutes: int
    slack_minutes: int
    fixed_window: bool

    @property
    def delay_minutes(self) -> int:
        """Navigation compatibility view; generic shifts may be negative."""
        return max(0, self.time_shift_minutes)


@dataclass(frozen=True, slots=True)
class TimelineImpact:
    current_boundary_at: datetime
    daily_end: datetime
    stops: tuple[TimelineStopImpact, ...]

    @property
    def feasible(self) -> bool:
        return all(stop.slack_minutes >= 0 for stop in self.stops)

    @property
    def fixed_window_feasible(self) -> bool:
        return all(not stop.fixed_window or stop.time_shift_minutes <= 0 for stop in self.stops)


def project_timeline_impact(*, current_boundary_at: datetime, remaining_stops: list[TimelineStop], daily_end: datetime) -> TimelineImpact:
    """Propagate one authoritative real-world boundary through formal stops.

    The boundary can originate from ETA, actual experience end, or a future
    sensor. This function deliberately has no source, persistence, or policy.
    """
    if current_boundary_at.tzinfo is None or daily_end.tzinfo is None:
        raise ValueError("current_boundary_at and daily_end must be timezone-aware")
    if not remaining_stops:
        return TimelineImpact(current_boundary_at, daily_end, ())
    if any(stop.planned_start.tzinfo is None for stop in remaining_stops):
        raise ValueError("planned starts must be timezone-aware")
    if any(stop.duration_minutes <= 0 for stop in remaining_stops):
        raise ValueError("stop duration must be positive")
    if any(stop.travel_to_next_minutes is not None and stop.travel_to_next_minutes < 0 for stop in remaining_stops):
        raise ValueError("travel duration cannot be negative")
    if any(remaining_stops[i].travel_to_next_minutes is None for i in range(len(remaining_stops) - 1)):
        raise ValueError("every non-final stop needs travel_to_next_minutes")

    latest_starts = [daily_end] * len(remaining_stops)
    for i in range(len(remaining_stops) - 1, -1, -1):
        stop = remaining_stops[i]
        latest = daily_end - timedelta(minutes=stop.duration_minutes)
        if i < len(remaining_stops) - 1:
            latest = min(latest, latest_starts[i + 1] - timedelta(minutes=stop.duration_minutes + (stop.travel_to_next_minutes or 0)))
        if stop.fixed_window:
            latest = min(latest, stop.planned_start)
        latest_starts[i] = latest

    arrival = current_boundary_at
    impacts: list[TimelineStopImpact] = []
    for i, stop in enumerate(remaining_stops):
        start = max(arrival, stop.planned_start)
        end = start + timedelta(minutes=stop.duration_minutes)
        shift = round((arrival - stop.planned_start).total_seconds() / 60)
        impacts.append(TimelineStopImpact(stop.activity_id, arrival, start, end, shift, int((latest_starts[i] - arrival).total_seconds() // 60), stop.fixed_window))
        if i < len(remaining_stops) - 1:
            arrival = end + timedelta(minutes=stop.travel_to_next_minutes or 0)
    return TimelineImpact(current_boundary_at, daily_end, tuple(impacts))
