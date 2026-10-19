import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Activity,
    ActivityExecution,
    DayPlan,
    PlaceCandidate,
    TravelEvent,
    TripExecution,
    Trip,
)
from app.repository import get_trip
from app.schemas import (
    DynamicReplanRequest,
    ActivityExecutionResponse,
    TravelEventResponse,
    TripExecutionActionRequest,
    TripExecutionResponse,
    TripExecutionStart,
    ExtendStayRequest,
    ExtendStayResponse,
    LeaveEarlyRequest,
    LeaveEarlyResponse,
)


class TripExecutionNotFoundError(Exception):
    pass


class InvalidTripExecutionStateError(Exception):
    pass


async def total_extension_minutes(session: AsyncSession, activity_execution_id: uuid.UUID) -> int:
    """Return only valid persisted user choices; malformed historical JSON is ignored."""
    events = (await session.scalars(select(TravelEvent).where(
        TravelEvent.activity_execution_id == activity_execution_id,
        TravelEvent.event_type == "user_extend_stay",
    ))).all()
    total = 0
    for event in events:
        value = event.details.get("extension_minutes") if isinstance(event.details, dict) else None
        if isinstance(value, int) and value > 0:
            total += value
    return total


def projected_activity_end(item: ActivityExecution, planned_duration_minutes: int, total_extension: int) -> datetime | None:
    return item.actual_started_at + timedelta(minutes=planned_duration_minutes + total_extension) if item.actual_started_at else None


async def _locked_experience_context(session: AsyncSession, activity_execution_id: uuid.UUID):
    from app.formal_write import lock_trip
    trip_id = await session.scalar(select(TripExecution.trip_id).join(ActivityExecution, ActivityExecution.trip_execution_id == TripExecution.id).where(ActivityExecution.id == activity_execution_id))
    if trip_id is None:
        raise TripExecutionNotFoundError
    await lock_trip(session, trip_id)
    row = await session.execute(select(ActivityExecution, Activity, TripExecution, Trip)
        .join(Activity, ActivityExecution.activity_id == Activity.id)
        .join(TripExecution, ActivityExecution.trip_execution_id == TripExecution.id)
        .join(Trip, TripExecution.trip_id == Trip.id)
        .where(ActivityExecution.id == activity_execution_id).with_for_update())
    result = row.tuples().one_or_none()
    if result is None:
        raise TripExecutionNotFoundError
    return result


def _assert_expected_itinerary_version(trip: Trip, expected_version: int | None) -> None:
    if expected_version is not None and trip.version != expected_version:
        raise InvalidTripExecutionStateError("行程版本已变化，请刷新后重试")


def _same_extend_stay_event(
    event: TravelEvent, activity_execution_id: uuid.UUID, extension_minutes: int, reason: str | None
) -> bool:
    details = event.details if isinstance(event.details, dict) else {}
    return (
        event.event_type == "user_extend_stay"
        and event.activity_execution_id == activity_execution_id
        and details.get("extension_minutes") == extension_minutes
        and details.get("reason") == (reason or "")
    )


def _same_leave_early_event(event: TravelEvent, activity_execution_id: uuid.UUID, reason: str | None) -> bool:
    details = event.details if isinstance(event.details, dict) else {}
    return (
        event.event_type == "user_leave_early"
        and event.activity_execution_id == activity_execution_id
        and details.get("reason") == (reason or "")
    )


async def _existing_client_action(
    session: AsyncSession, execution_id: uuid.UUID, client_action_id: uuid.UUID
) -> TravelEvent | None:
    return await session.scalar(
        select(TravelEvent).where(
            TravelEvent.trip_execution_id == execution_id,
            TravelEvent.client_action_id == client_action_id,
        )
    )


async def extend_stay(session: AsyncSession, activity_execution_id: uuid.UUID, payload: ExtendStayRequest) -> ExtendStayResponse:
    item, activity, execution, trip = await _locked_experience_context(session, activity_execution_id)
    _assert_expected_itinerary_version(trip, payload.expected_itinerary_version)
    replay = await _existing_client_action(session, execution.id, payload.client_action_id)
    if replay:
        if not _same_extend_stay_event(replay, item.id, payload.extension_minutes, payload.reason):
            raise InvalidTripExecutionStateError("client_action_id 已用于不同操作")
        total = await total_extension_minutes(session, item.id)
        return ExtendStayResponse(activity_execution_id=item.id, status=item.status, extension_minutes=payload.extension_minutes,
            total_extension_minutes=total, projected_end_at=projected_activity_end(item, activity.duration_minutes, total), replayed=True, server_timestamp=datetime.now(UTC))
    if execution.status != "in_progress" or execution.current_activity_id != activity.id or item.status not in {"arrived", "in_progress"}:
        raise InvalidTripExecutionStateError("只有当前已到达或正在体验的活动可以延长停留")
    event = TravelEvent(trip_execution_id=execution.id, activity_execution_id=item.id, client_action_id=payload.client_action_id,
        event_type="user_extend_stay", occurred_at=datetime.now(UTC), details={"extension_minutes": payload.extension_minutes, "source": "user", "reason": payload.reason or ""})
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError:
        replay = await _existing_client_action(session, execution.id, payload.client_action_id)
        if replay is None or not _same_extend_stay_event(replay, item.id, payload.extension_minutes, payload.reason):
            raise InvalidTripExecutionStateError("client_action_id 已用于不同操作")
        total = await total_extension_minutes(session, item.id)
        return ExtendStayResponse(activity_execution_id=item.id, status=item.status, extension_minutes=payload.extension_minutes,
            total_extension_minutes=total, projected_end_at=projected_activity_end(item, activity.duration_minutes, total), replayed=True, server_timestamp=datetime.now(UTC))
    total = await total_extension_minutes(session, item.id)
    projected_end = projected_activity_end(item, activity.duration_minutes, total)
    status = item.status
    await session.commit()
    return ExtendStayResponse(activity_execution_id=activity_execution_id, status=status, extension_minutes=payload.extension_minutes,
        total_extension_minutes=total, projected_end_at=projected_end, server_timestamp=datetime.now(UTC))


async def leave_early(session: AsyncSession, activity_execution_id: uuid.UUID, payload: LeaveEarlyRequest) -> LeaveEarlyResponse:
    item, activity, execution, trip = await _locked_experience_context(session, activity_execution_id)
    _assert_expected_itinerary_version(trip, payload.expected_itinerary_version)
    replay = await _existing_client_action(session, execution.id, payload.client_action_id)
    if replay:
        if not _same_leave_early_event(replay, item.id, payload.reason):
            raise InvalidTripExecutionStateError("client_action_id 已用于不同操作")
        return _leave_early_response(item, True)
    if execution.status != "in_progress" or execution.current_activity_id != activity.id or item.status != "in_progress" or item.actual_started_at is None:
        raise InvalidTripExecutionStateError("提前离开只适用于正在体验的当前活动；未开始活动请跳过")
    now = datetime.now(UTC)
    _apply_activity_action(item, activity, "complete", now, None)
    event = TravelEvent(trip_execution_id=execution.id, activity_execution_id=item.id, client_action_id=payload.client_action_id,
        event_type="user_leave_early", occurred_at=now, details={"source": "user", "reason": payload.reason or ""})
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError:
        replay = await _existing_client_action(session, execution.id, payload.client_action_id)
        if replay is None or not _same_leave_early_event(replay, item.id, payload.reason):
            raise InvalidTripExecutionStateError("client_action_id 已用于不同操作")
        await session.refresh(item)
        return _leave_early_response(item, True)
    await _advance_current_activity(session, execution)
    response = _leave_early_response(item, False)
    await session.commit()
    return response


def _leave_early_response(item: ActivityExecution, replayed: bool) -> LeaveEarlyResponse:
    assert item.actual_started_at is not None and item.actual_ended_at is not None
    return LeaveEarlyResponse(activity_execution_id=item.id, status="completed", actual_started_at=item.actual_started_at,
        actual_ended_at=item.actual_ended_at, actual_dwell_minutes=max(0, int((item.actual_ended_at-item.actual_started_at).total_seconds() // 60)), replayed=replayed, server_timestamp=datetime.now(UTC))


async def request_dynamic_replan(
    session: AsyncSession, trip_id: uuid.UUID, payload: DynamicReplanRequest
):
    """Record a travel event and enqueue a confirmation-gated replan run."""
    # Preserve the existing missing-execution 404 before taking the new fence.
    if await session.scalar(select(TripExecution.id).where(TripExecution.trip_id == trip_id)) is None:
        raise TripExecutionNotFoundError
    from app.formal_write import lock_trip
    await lock_trip(session, trip_id)
    execution = await session.scalar(
        select(TripExecution)
        .where(TripExecution.trip_id == trip_id)
        .with_for_update()
    )
    if execution is None:
        raise TripExecutionNotFoundError
    if execution.status not in {"in_progress", "paused"}:
        raise InvalidTripExecutionStateError("只有进行中的旅行可以动态重规划")

    now = datetime.now(UTC)
    event = TravelEvent(
        trip_execution_id=execution.id,
        event_type=payload.trigger,
        occurred_at=now,
        details={"source": "dynamic_replan", "details": payload.details},
    )
    session.add(event)
    await session.flush()

    from app.planning_run_repository import create_planning_run
    from app.schemas import PlanningRunCreate

    trigger_labels = {
        "delay": "延误",
        "weather_change": "天气变化",
        "fatigue": "疲劳",
        "budget_change": "预算变化",
        "user_change": "用户临时调整",
    }
    run = await create_planning_run(
        session,
        trip_id,
        PlanningRunCreate(
            run_type="replan",
            user_request=(
                f"根据{trigger_labels[payload.trigger]}，仅重新规划当前及后续尚未完成的活动。"
                f"原因：{payload.details}"
            ),
            entry_point="trip_planner",
            selected_day_id=execution.current_day_plan_id,
        ),
    )
    return run, event.id


async def get_trip_execution(
    session: AsyncSession, trip_id: uuid.UUID
) -> TripExecutionResponse:
    trip = await get_trip(session, trip_id)
    execution = await session.scalar(
        select(TripExecution).where(TripExecution.trip_id == trip_id)
    )
    rows = await _activity_rows(session, trip_id, execution.id if execution else None)
    if execution is None:
        first_day = rows[0][2] if rows else None
        return _build_response(
            trip_id=trip_id,
            execution=None,
            rows=rows,
            events=[],
            current_date=first_day.date if first_day else trip.start_date,
            current_day_plan_id=first_day.id if first_day else None,
            current_activity_id=rows[0][1].id if rows else None,
        )
    events = list(
        (
            await session.scalars(
                select(TravelEvent)
                .where(TravelEvent.trip_execution_id == execution.id)
                .order_by(TravelEvent.occurred_at.desc())
                .limit(100)
            )
        ).all()
    )
    return _build_response(
        trip_id=trip_id,
        execution=execution,
        rows=rows,
        events=list(reversed(events)),
        current_date=execution.current_date,
        current_day_plan_id=execution.current_day_plan_id,
        current_activity_id=execution.current_activity_id,
    )


async def start_trip_execution(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: TripExecutionStart,
    *,
    commit: bool = True,
) -> TripExecutionResponse:
    await get_trip(session, trip_id)
    from app.formal_write import lock_trip
    trip = await lock_trip(session, trip_id)
    existing = await session.scalar(
        select(TripExecution).where(TripExecution.trip_id == trip_id).with_for_update()
    )
    if existing is not None:
        return await get_trip_execution(session, trip_id)
    days = list(
        (
            await session.scalars(
                select(DayPlan).where(DayPlan.trip_id == trip_id).order_by(DayPlan.position)
            )
        ).all()
    )
    if not days:
        raise InvalidTripExecutionStateError("旅行没有可执行的日程")
    selected_day = next((day for day in days if day.id == payload.day_plan_id), None)
    if payload.day_plan_id is not None and selected_day is None:
        raise InvalidTripExecutionStateError("指定日期不属于当前旅行")
    if selected_day is None:
        selected_day = next((day for day in days if day.date == datetime.now(UTC).date()), days[0])
    activities = list(
        (
            await session.scalars(
                select(Activity)
                .join(DayPlan, Activity.day_plan_id == DayPlan.id)
                .where(DayPlan.trip_id == trip_id)
                .order_by(DayPlan.position, Activity.position)
            )
        ).all()
    )
    selected_activities = [item for item in activities if item.day_plan_id == selected_day.id]
    if not selected_activities:
        raise InvalidTripExecutionStateError("所选日期没有可执行活动")
    now = datetime.now(UTC)
    execution = TripExecution(
        trip_id=trip.id,
        status="in_progress",
        itinerary_version=trip.version,
        current_date=selected_day.date,
        current_day_plan_id=selected_day.id,
        current_activity_id=selected_activities[0].id,
        actual_started_at=now,
    )
    session.add(execution)
    await session.flush()
    activity_executions = [
        ActivityExecution(trip_execution_id=execution.id, activity_id=item.id, status="pending")
        for item in activities
    ]
    session.add_all(activity_executions)
    session.add(
        TravelEvent(
            trip_execution_id=execution.id,
            event_type="trip_started",
            occurred_at=now,
            details={"start_day_plan_id": str(selected_day.id)},
        )
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    return await get_trip_execution(session, trip_id)


async def apply_trip_execution_action(
    session: AsyncSession,
    execution_id: uuid.UUID,
    payload: TripExecutionActionRequest,
) -> TripExecutionResponse:
    from app.formal_write import lock_trip
    trip_id = await session.scalar(select(TripExecution.trip_id).where(TripExecution.id == execution_id))
    if trip_id is None:
        raise TripExecutionNotFoundError
    await lock_trip(session, trip_id)
    execution = await session.scalar(
        select(TripExecution).where(TripExecution.id == execution_id).with_for_update()
    )
    if execution is None:
        raise TripExecutionNotFoundError
    now = datetime.now(UTC)
    if payload.action == "pause":
        if execution.status != "in_progress":
            raise InvalidTripExecutionStateError("只有进行中的旅行可以暂停")
        execution.status = "paused"
        execution.paused_at = now
        _record_event(session, execution.id, "paused", now)
    elif payload.action == "resume":
        if execution.status != "paused":
            raise InvalidTripExecutionStateError("旅行当前没有暂停")
        execution.status = "in_progress"
        execution.paused_at = None
        _record_event(session, execution.id, "resumed", now)
    elif payload.action == "finish":
        if execution.status not in {"in_progress", "paused"}:
            raise InvalidTripExecutionStateError("旅行已经结束")
        remaining = await session.scalar(
            select(ActivityExecution.id).where(
                ActivityExecution.trip_execution_id == execution.id,
                ActivityExecution.status.notin_(["completed", "skipped"]),
            ).limit(1)
        )
        if remaining is not None:
            raise InvalidTripExecutionStateError("仍有未完成活动，完成或跳过后才能结束旅行")
        execution.status = "completed"
        execution.actual_ended_at = now
        execution.paused_at = None
        execution.current_activity_id = None
        _record_event(session, execution.id, "trip_finished", now)
    else:
        if execution.status != "in_progress":
            raise InvalidTripExecutionStateError("旅行暂停或已结束，当前不能更新活动")
        activity_id = payload.activity_id or execution.current_activity_id
        if activity_id is None or activity_id != execution.current_activity_id:
            raise InvalidTripExecutionStateError("只能更新当前活动")
        row = await session.execute(
            select(ActivityExecution, Activity)
            .join(Activity, ActivityExecution.activity_id == Activity.id)
            .where(
                ActivityExecution.trip_execution_id == execution.id,
                ActivityExecution.activity_id == activity_id,
            )
            .with_for_update()
        )
        pair = row.tuples().one_or_none()
        if pair is None:
            raise InvalidTripExecutionStateError("活动不属于本次旅行执行")
        activity_execution, activity = pair
        event_type = _apply_activity_action(
            activity_execution, activity, payload.action, now, payload.delay_minutes
        )
        _record_event(
            session,
            execution.id,
            event_type,
            now,
            activity_execution.id,
            {"activity_id": str(activity.id), "delay_minutes": activity_execution.delay_minutes},
        )
        if payload.action in {"complete", "skip"}:
            await session.flush()
            await _advance_current_activity(session, execution)
    await session.commit()
    return await get_trip_execution(session, execution.trip_id)


def _apply_activity_action(
    activity_execution: ActivityExecution,
    activity: Activity,
    action: str,
    now: datetime,
    delay_minutes: int | None,
) -> str:
    if activity_execution.status in {"completed", "skipped"}:
        raise InvalidTripExecutionStateError("当前活动已经结束")
    if delay_minutes is not None:
        activity_execution.delay_minutes = delay_minutes
    if action == "arrive":
        if activity_execution.status != "pending":
            raise InvalidTripExecutionStateError("当前活动已记录到达")
        activity_execution.status = "arrived"
        activity_execution.actual_arrived_at = now
        return "arrived"
    if action == "start_activity":
        if activity_execution.status not in {"pending", "arrived"}:
            raise InvalidTripExecutionStateError("当前活动不能重复开始")
        activity_execution.status = "in_progress"
        activity_execution.actual_arrived_at = activity_execution.actual_arrived_at or now
        activity_execution.actual_started_at = now
        activity.status = "active"
        return "activity_started"
    if action == "complete":
        activity_execution.status = "completed"
        activity_execution.actual_arrived_at = activity_execution.actual_arrived_at or now
        activity_execution.actual_started_at = activity_execution.actual_started_at or now
        activity_execution.actual_ended_at = now
        activity.status = "completed"
        return "completed"
    if action == "skip":
        activity_execution.status = "skipped"
        activity_execution.actual_ended_at = now
        activity.status = "skipped"
        return "skipped"
    raise InvalidTripExecutionStateError("不支持的活动操作")


async def _advance_current_activity(session: AsyncSession, execution: TripExecution) -> None:
    row = await session.execute(
        select(ActivityExecution, Activity, DayPlan)
        .join(Activity, ActivityExecution.activity_id == Activity.id)
        .join(DayPlan, Activity.day_plan_id == DayPlan.id)
        .where(
            ActivityExecution.trip_execution_id == execution.id,
            ActivityExecution.status.notin_(["completed", "skipped"]),
        )
        .order_by(DayPlan.position, Activity.position)
        .limit(1)
    )
    next_item = row.tuples().one_or_none()
    if next_item is None:
        execution.current_activity_id = None
        return
    _, activity, day = next_item
    execution.current_activity_id = activity.id
    execution.current_day_plan_id = day.id
    execution.current_date = day.date


async def _activity_rows(
    session: AsyncSession, trip_id: uuid.UUID, execution_id: uuid.UUID | None
) -> list[tuple[ActivityExecution | None, Activity, DayPlan, PlaceCandidate]]:
    statement = (
        select(ActivityExecution, Activity, DayPlan, PlaceCandidate)
        .select_from(Activity)
        .join(DayPlan, Activity.day_plan_id == DayPlan.id)
        .join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
        .where(DayPlan.trip_id == trip_id)
        .order_by(DayPlan.position, Activity.position)
    )
    if execution_id is None:
        base_rows = list((await session.execute(statement.with_only_columns(Activity, DayPlan, PlaceCandidate))).tuples())
        return [(None, activity, day, place) for activity, day, place in base_rows]
    statement = statement.join(
        ActivityExecution,
        (ActivityExecution.activity_id == Activity.id)
        & (ActivityExecution.trip_execution_id == execution_id),
    )
    return list((await session.execute(statement)).tuples())


def _build_response(
    *,
    trip_id: uuid.UUID,
    execution: TripExecution | None,
    rows: list[tuple[ActivityExecution | None, Activity, DayPlan, PlaceCandidate]],
    events: list[TravelEvent],
    current_date,
    current_day_plan_id,
    current_activity_id,
) -> TripExecutionResponse:
    items = [
        ActivityExecutionResponse(
            id=activity_execution.id if activity_execution else None,
            activity_id=activity.id,
            day_plan_id=day.id,
            day_date=day.date,
            name=activity.custom_name or place.name,
            scheduled_time=activity.scheduled_time,
            estimated_cost_fen=activity.estimated_cost_fen,
            status=activity_execution.status if activity_execution else "pending",
            actual_arrived_at=activity_execution.actual_arrived_at if activity_execution else None,
            actual_started_at=activity_execution.actual_started_at if activity_execution else None,
            actual_ended_at=activity_execution.actual_ended_at if activity_execution else None,
            delay_minutes=activity_execution.delay_minutes if activity_execution else 0,
        )
        for activity_execution, activity, day, place in rows
    ]
    today_remaining = [
        item for item in items
        if item.day_date == current_date and item.status not in {"completed", "skipped"}
    ]
    current = next((item for item in items if item.activity_id == current_activity_id), None)
    event_activity_ids = {
        activity_execution.id: activity_execution.activity_id
        for activity_execution, _, _, _ in rows if activity_execution is not None
    }
    return TripExecutionResponse(
        id=execution.id if execution else None,
        trip_id=trip_id,
        status=execution.status if execution else "not_started",
        current_date=current_date,
        current_day_plan_id=current_day_plan_id,
        current_activity_id=current_activity_id,
        actual_started_at=execution.actual_started_at if execution else None,
        actual_ended_at=execution.actual_ended_at if execution else None,
        paused_at=execution.paused_at if execution else None,
        schedule_delay_minutes=current.delay_minutes if current else 0,
        remaining_activity_count=len(today_remaining),
        remaining_estimated_cost_fen=sum(item.estimated_cost_fen for item in today_remaining),
        activities=items,
        events=[
            TravelEventResponse(
                id=event.id,
                event_type=event.event_type,
                activity_id=event_activity_ids.get(event.activity_execution_id),
                occurred_at=event.occurred_at,
                details=event.details,
            )
            for event in events
        ],
    )


def _record_event(
    session: AsyncSession,
    execution_id: uuid.UUID,
    event_type: str,
    occurred_at: datetime,
    activity_execution_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> None:
    session.add(
        TravelEvent(
            trip_execution_id=execution_id,
            activity_execution_id=activity_execution_id,
            event_type=event_type,
            occurred_at=occurred_at,
            details=details or {},
        )
    )
