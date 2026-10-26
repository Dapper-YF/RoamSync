"""Read-only application service for Activity Experience Time Impact."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, ActivityExecution, DayPlan, RouteLeg, Trip, TripExecution, TripPreferences
from app.schemas import ExperienceTimeImpactResponse
from app.timeline_impact import TimelineStop, project_timeline_impact
from app.trip_execution_service import projected_activity_end, total_extension_minutes


async def evaluate_activity_experience_time_impact(
    session: AsyncSession, trip_execution_id: uuid.UUID, activity_execution_id: uuid.UUID
) -> ExperienceTimeImpactResponse:
    """Project formal downstream time from persisted activity-experience facts.

    This is intentionally read-only: no event, disruption, PlanningRun, or
    itinerary mutation is produced here.
    """
    row = await session.execute(
        select(ActivityExecution, Activity, DayPlan, TripExecution, Trip, TripPreferences)
        .join(Activity, ActivityExecution.activity_id == Activity.id)
        .join(DayPlan, Activity.day_plan_id == DayPlan.id)
        .join(TripExecution, ActivityExecution.trip_execution_id == TripExecution.id)
        .join(Trip, TripExecution.trip_id == Trip.id)
        .join(TripPreferences, TripPreferences.trip_id == Trip.id)
        .where(ActivityExecution.id == activity_execution_id, ActivityExecution.trip_execution_id == trip_execution_id)
    )
    context = row.tuples().one_or_none()
    if context is None:
        return ExperienceTimeImpactResponse(impact_state="unavailable")
    item, current, day, execution, trip, preferences = context
    if execution.itinerary_version != trip.version:
        return ExperienceTimeImpactResponse(impact_state="unavailable")
    if item.status == "completed":
        boundary = item.actual_ended_at
    elif item.status == "in_progress":
        boundary = projected_activity_end(item, current.duration_minutes, await total_extension_minutes(session, item.id))
    else:
        boundary = None
    if boundary is None:
        return ExperienceTimeImpactResponse(impact_state="unavailable")

    timezone = ZoneInfo(trip.timezone)
    planned_current_end = datetime.combine(day.date, current.scheduled_time, tzinfo=timezone) + timedelta(minutes=current.duration_minutes)
    shift = round((boundary - planned_current_end).total_seconds() / 60)
    rows = list((await session.execute(
        select(Activity, ActivityExecution)
        .outerjoin(ActivityExecution, (ActivityExecution.activity_id == Activity.id) & (ActivityExecution.trip_execution_id == execution.id))
        .where(Activity.day_plan_id == day.id, Activity.position > current.position)
        .order_by(Activity.position)
    )).tuples())
    remaining = [(activity, state) for activity, state in rows if state is None or state.status not in {"completed", "skipped"}]
    routes = {(route.from_activity_id, route.to_activity_id): route.duration_minutes for route in (await session.scalars(select(RouteLeg).where(RouteLeg.day_plan_id == day.id))).all()}
    first_travel = routes.get((current.id, remaining[0][0].id), 0) if remaining else 0
    stops: list[TimelineStop] = []
    for index, (activity, _) in enumerate(remaining):
        travel = None
        if index < len(remaining) - 1:
            travel = routes.get((activity.id, remaining[index + 1][0].id))
            if travel is None:
                return ExperienceTimeImpactResponse(time_shift_minutes=shift, impact_state="unavailable")
        stops.append(TimelineStop(str(activity.id), datetime.combine(day.date, activity.scheduled_time, tzinfo=timezone), activity.duration_minutes, travel, activity.schedule_locked))
    daily_end = datetime.combine(day.date, preferences.daily_end_time, tzinfo=timezone)
    impact = project_timeline_impact(current_boundary_at=boundary + timedelta(minutes=first_travel), remaining_stops=stops, daily_end=daily_end)
    minimum = min((stop.slack_minutes for stop in impact.stops), default=int((daily_end - boundary).total_seconds() // 60))
    fixed_feasible = impact.fixed_window_feasible
    day_end_feasible = impact.feasible and boundary <= daily_end
    first = next((stop for stop in impact.stops if stop.slack_minutes < 15), None)
    if not stops and shift == 0:
        state = "none"
    elif not day_end_feasible or not fixed_feasible:
        state = "infeasible"
    elif shift == 0:
        state = "none"
    elif minimum < 15:
        state = "at_risk"
    else:
        state = "absorbed"
    return ExperienceTimeImpactResponse(
        time_shift_minutes=shift, impact_state=state,
        minimum_downstream_slack_minutes=minimum,
        first_impacted_activity_id=uuid.UUID(first.activity_id) if first else None,
        fixed_window_feasible=fixed_feasible, day_end_feasible=day_end_feasible,
        downstream_schedule=[{"activity_id": stop.activity_id, "projected_arrival": stop.projected_arrival, "projected_start": stop.projected_start, "projected_end": stop.projected_end, "slack_minutes": stop.slack_minutes, "fixed_window": stop.fixed_window} for stop in impact.stops],
    )
