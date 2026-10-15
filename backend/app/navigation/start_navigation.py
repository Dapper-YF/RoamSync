"""Atomic navigation-start use case.

The mobile client asks for a live execution projection, never for a particular
RouteLeg database id.  This service locks the formal trip and execution,
resolves the current executable formal leg, and commits the execution/session
creation together.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, ActivityExecution, DayPlan, NavigationSession, RouteLeg, Trip, TripExecution
from app.navigation.session_service import (
    LIVE_STATUSES,
    NavigationSessionConflictError,
    NavigationSessionStateError,
    create_navigation_session,
    navigation_session_response,
)
from app.repository import TripNotFoundError
from app.schemas import NavigationSessionCreate, NavigationStartRequest, NavigationStartResponse, TripExecutionStart
from app.trip_execution_service import InvalidTripExecutionStateError, get_trip_execution, start_trip_execution


class NavigationStartConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionAnchor:
    """Stable activity-pair identity for the leg presently executable."""

    from_activity_id: uuid.UUID
    to_activity_id: uuid.UUID
    formal_route_leg_id: uuid.UUID


async def start_navigation(
    session: AsyncSession, trip_id: uuid.UUID, payload: NavigationStartRequest
) -> NavigationStartResponse:
    """Create or resume exactly one live NavigationSession in one transaction."""
    trip = await session.scalar(select(Trip).where(Trip.id == trip_id).with_for_update())
    if trip is None:
        raise TripNotFoundError
    if payload.expected_itinerary_version is not None and payload.expected_itinerary_version != trip.version:
        raise NavigationStartConflictError("正式行程已经更新，请刷新后重新开始导航")

    execution = await session.scalar(
        select(TripExecution).where(TripExecution.trip_id == trip_id).with_for_update()
    )
    if execution is not None and execution.status == "completed":
        raise NavigationStartConflictError("旅行执行已经结束，不能开始新的导航")
    if execution is not None and execution.status == "paused":
        raise NavigationStartConflictError("旅行执行已暂停，请恢复旅行后再开始导航")

    # The partial unique index remains the final invariant. This lock lets the
    # usual path return the existing session without attempting a duplicate.
    live = await session.scalar(
        select(NavigationSession)
        .where(NavigationSession.trip_execution_id == (execution.id if execution else None))
        .where(NavigationSession.status.in_(LIVE_STATUSES))
        .with_for_update()
    ) if execution is not None else None
    if live is not None:
        return NavigationStartResponse(
            navigation_session=navigation_session_response(live),
            execution=await get_trip_execution(session, trip_id),
            resumed=True,
        )

    if execution is None:
        # No commit here: execution and its first navigation projection become
        # visible together, or neither does.
        await start_trip_execution(session, trip_id, TripExecutionStart(), commit=False)
        execution = await session.scalar(
            select(TripExecution).where(TripExecution.trip_id == trip_id).with_for_update()
        )
        assert execution is not None

    anchor = await resolve_execution_anchor(session, trip_id, execution)
    if anchor is None:
        raise NavigationStartConflictError("当前没有可执行的正式路线，无法开始导航")
    try:
        navigation = await create_navigation_session(
            session,
            trip_id,
            NavigationSessionCreate(
                trip_execution_id=execution.id,
                from_activity_id=anchor.from_activity_id,
                to_activity_id=anchor.to_activity_id,
            ),
            commit=False,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise NavigationStartConflictError("当前旅行执行已有有效导航会话") from exc
    return NavigationStartResponse(
        navigation_session=navigation_session_response(navigation),
        execution=await get_trip_execution(session, trip_id),
        resumed=False,
    )


async def resolve_execution_anchor(
    session: AsyncSession, trip_id: uuid.UUID, execution: TripExecution
) -> ExecutionAnchor | None:
    """Resolve from execution facts to an adjacent current formal RouteLeg.

    A pending current activity after a completed predecessor means travel is
    *to* that current activity.  When already arrived/active, travel begins
    *from* that activity.  A brand-new execution has no predecessor, so its
    first persisted formal leg is the only honest anchor available today.
    """
    rows = list((await session.execute(
        select(Activity, ActivityExecution, DayPlan)
        .join(DayPlan, Activity.day_plan_id == DayPlan.id)
        .join(ActivityExecution, (ActivityExecution.activity_id == Activity.id) & (ActivityExecution.trip_execution_id == execution.id))
        .where(DayPlan.trip_id == trip_id)
        .order_by(DayPlan.position, Activity.position)
    )).tuples())
    if not rows or execution.current_activity_id is None:
        return None
    current_index = next((i for i, (activity, _, _) in enumerate(rows) if activity.id == execution.current_activity_id), None)
    if current_index is None:
        return None
    current_activity, current_execution, _ = rows[current_index]
    terminal = {"completed", "skipped"}
    route_rows = list((await session.scalars(
        select(RouteLeg).join(DayPlan, RouteLeg.day_plan_id == DayPlan.id)
        .where(DayPlan.trip_id == trip_id)
    )).all())
    by_pair = {(route.from_activity_id, route.to_activity_id): route for route in route_rows}

    def anchor_for(left: Activity, right: Activity) -> ExecutionAnchor | None:
        route = by_pair.get((left.id, right.id))
        return ExecutionAnchor(left.id, right.id, route.id) if route else None

    # Arrived / in-progress means the traveller is at current activity.
    if current_execution.status in {"arrived", "in_progress"}:
        next_row = next((row for row in rows[current_index + 1:] if row[1].status not in terminal), None)
        return anchor_for(current_activity, next_row[0]) if next_row else None

    # A pending current activity with a frozen predecessor is an incoming leg.
    predecessor = next((row for row in reversed(rows[:current_index]) if row[1].status in terminal), None)
    if current_execution.status == "pending" and predecessor is not None:
        return anchor_for(predecessor[0], current_activity)

    # Initial state: select the first actual formal leg leaving current. This
    # intentionally does not invent an accommodation -> first activity route.
    next_row = next((row for row in rows[current_index + 1:] if row[1].status not in terminal), None)
    return anchor_for(current_activity, next_row[0]) if next_row else None
