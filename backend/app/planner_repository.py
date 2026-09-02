import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, DayPlan, PlaceCandidate, RouteLeg, SourceRecord
from app.maps_service import recalculate_day_route
from app.repository import get_trip
from app.schemas import (
    ActivityResponse,
    ActivityMoveResponse,
    ActivityMoveRequest,
    ActivityUpdate,
    DayPlanResponse,
    PlaceCandidateResponse,
    PlaceSearchResultResponse,
    PlanningBudgetDayResponse,
    PlanningBudgetResponse,
    RouteLegResponse,
    ScheduleConflictResponse,
    SourceRecordResponse,
)


class DayPlanNotFoundError(Exception):
    pass


class ActivityNotFoundError(Exception):
    pass


class ActivityVersionConflictError(Exception):
    pass


class PlaceCandidateNotFoundError(Exception):
    pass


class DuplicatePlaceError(Exception):
    pass


class InvalidActivityOrderError(Exception):
    pass


class InvalidActivityMoveError(Exception):
    pass


def _source_response(source: SourceRecord) -> SourceRecordResponse:
    return SourceRecordResponse(
        id=source.id,
        title=source.title,
        url=source.url,
        provider=source.provider,
        queried_at=source.queried_at,
        confidence=source.confidence,
    )


def _place_response(
    place: PlaceCandidate, source: SourceRecord
) -> PlaceCandidateResponse:
    return PlaceCandidateResponse(
        id=place.id,
        name=place.name,
        category=place.category,
        neighborhood=place.neighborhood,
        description=place.description,
        longitude=float(place.longitude),
        latitude=float(place.latitude),
        suggested_duration_minutes=place.suggested_duration_minutes,
        estimated_cost_fen=place.estimated_cost_fen,
        rating=float(place.rating),
        tags=list(place.tags),
        source=_source_response(source),
    )


def _activity_response(
    activity: Activity, place: PlaceCandidate, source: SourceRecord
) -> ActivityResponse:
    return ActivityResponse(
        id=activity.id,
        place_id=place.id,
        name=place.name,
        custom_name=activity.custom_name,
        display_name=activity.custom_name or place.name,
        category=place.category,
        neighborhood=place.neighborhood,
        longitude=float(place.longitude),
        latitude=float(place.latitude),
        scheduled_time=activity.scheduled_time,
        duration_minutes=activity.duration_minutes,
        estimated_cost_fen=activity.estimated_cost_fen,
        status=activity.status,
        position=activity.position,
        schedule_locked=activity.schedule_locked,
        version=activity.version,
        note=activity.note,
        updated_at=activity.updated_at,
        source=_source_response(source),
    )


async def _activity_rows(
    session: AsyncSession, day_plan_id: uuid.UUID
) -> list[tuple[Activity, PlaceCandidate, SourceRecord]]:
    result = await session.execute(
        select(Activity, PlaceCandidate, SourceRecord)
        .join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
        .join(SourceRecord, PlaceCandidate.source_record_id == SourceRecord.id)
        .where(Activity.day_plan_id == day_plan_id)
        .order_by(Activity.position)
    )
    return list(result.tuples())


async def _route_mode(session: AsyncSession, day_plan_id: uuid.UUID) -> str:
    return (await session.scalar(select(DayPlan.route_mode).where(DayPlan.id == day_plan_id))) or "walk"


async def _recalculate_schedule_from_saved_route(
    session: AsyncSession, day_plan_id: uuid.UUID
) -> None:
    activities = list(
        (
            await session.scalars(
                select(Activity)
                .where(Activity.day_plan_id == day_plan_id)
                .order_by(Activity.position)
            )
        ).all()
    )
    legs = list(
        (
            await session.scalars(
                select(RouteLeg)
                .where(RouteLeg.day_plan_id == day_plan_id)
                .order_by(RouteLeg.position)
            )
        ).all()
    )
    leg_minutes = {
        (leg.from_activity_id, leg.to_activity_id): leg.duration_minutes for leg in legs
    }
    for previous, current in zip(activities, activities[1:], strict=False):
        if current.schedule_locked:
            continue
        start = datetime.combine(datetime.today().date(), previous.scheduled_time)
        current.scheduled_time = (
            start
            + timedelta(
                minutes=previous.duration_minutes
                + leg_minutes.get((previous.id, current.id), 0)
            )
        ).time().replace(second=0, microsecond=0)


async def _day_response(session: AsyncSession, day: DayPlan) -> DayPlanResponse:
    rows = await _activity_rows(session, day.id)
    legs = list(
        (
            await session.scalars(
                select(RouteLeg)
                .where(RouteLeg.day_plan_id == day.id)
                .order_by(RouteLeg.position)
            )
        ).all()
    )
    conflicts = []
    for activity, _, _ in rows:
        finish = datetime.combine(day.date, activity.scheduled_time) + timedelta(
            minutes=activity.duration_minutes
        )
        if finish.hour >= 22 or finish.date() > day.date:
            conflicts.append(
                ScheduleConflictResponse(
                    activity_id=activity.id,
                    code="late_finish",
                    message=f"{activity.scheduled_time.strftime('%H:%M')} 开始的活动将在 22:00 后结束",
                )
            )
    return DayPlanResponse(
        id=day.id,
        trip_id=day.trip_id,
        date=day.date,
        label=day.label,
        theme=day.theme,
        position=day.position,
        route_mode=day.route_mode,
        activities=[_activity_response(*row) for row in rows],
        route_legs=[
            RouteLegResponse(
                id=leg.id,
                from_activity_id=leg.from_activity_id,
                to_activity_id=leg.to_activity_id,
                position=leg.position,
                mode=leg.mode,
                distance_meters=leg.distance_meters,
                duration_minutes=leg.duration_minutes,
                provider=leg.provider,
                is_estimated=leg.is_estimated,
            )
            for leg in legs
        ],
        conflicts=conflicts,
    )


async def get_day_plans(
    session: AsyncSession, trip_id: uuid.UUID
) -> list[DayPlanResponse]:
    await get_trip(session, trip_id)
    days = list(
        (
            await session.scalars(
                select(DayPlan)
                .where(DayPlan.trip_id == trip_id)
                .order_by(DayPlan.position)
            )
        ).all()
    )
    return [await _day_response(session, day) for day in days]


async def get_day_plan(session: AsyncSession, day_plan_id: uuid.UUID) -> DayPlanResponse:
    day = await session.get(DayPlan, day_plan_id)
    if day is None:
        raise DayPlanNotFoundError
    return await _day_response(session, day)


async def get_candidates(
    session: AsyncSession, trip_id: uuid.UUID
) -> list[PlaceCandidateResponse]:
    await get_trip(session, trip_id)
    used_ids = select(Activity.place_candidate_id).join(
        DayPlan, Activity.day_plan_id == DayPlan.id
    ).where(DayPlan.trip_id == trip_id)
    result = await session.execute(
        select(PlaceCandidate, SourceRecord)
        .join(SourceRecord, PlaceCandidate.source_record_id == SourceRecord.id)
        .where(
            PlaceCandidate.trip_id == trip_id,
            PlaceCandidate.id.not_in(used_ids),
        )
        .order_by(PlaceCandidate.name)
    )
    return [_place_response(place, source) for place, source in result.tuples()]


async def add_activity(
    session: AsyncSession,
    day_plan_id: uuid.UUID,
    place_id: uuid.UUID | None = None,
    place_snapshot: PlaceSearchResultResponse | None = None,
) -> ActivityResponse:
    day = await session.get(DayPlan, day_plan_id)
    if day is None:
        raise DayPlanNotFoundError
    place = await _resolve_place(session, day, place_id, place_snapshot)
    duplicate = await session.scalar(
        select(Activity.id)
        .join(DayPlan, Activity.day_plan_id == DayPlan.id)
        .where(
            DayPlan.trip_id == day.trip_id,
            Activity.place_candidate_id == place.id,
        )
    )
    if duplicate is not None:
        raise DuplicatePlaceError

    existing = list(
        (
            await session.scalars(
                select(Activity)
                .where(Activity.day_plan_id == day_plan_id)
                .order_by(Activity.position)
            )
        ).all()
    )
    route_mode = await _route_mode(session, day_plan_id)
    scheduled_time = _next_activity_time(existing)
    activity = Activity(
        day_plan_id=day_plan_id,
        place_candidate_id=place.id,
        scheduled_time=scheduled_time,
        duration_minutes=place.suggested_duration_minutes,
        estimated_cost_fen=place.estimated_cost_fen,
        status="planned",
        position=len(existing),
    )
    session.add(activity)
    await session.flush()
    await recalculate_day_route(session, day_plan_id, route_mode)
    await session.commit()
    await session.refresh(activity)
    source = await session.get(SourceRecord, place.source_record_id)
    if source is None:
        raise PlaceCandidateNotFoundError
    return _activity_response(activity, place, source)


async def update_activity(
    session: AsyncSession,
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
) -> ActivityResponse:
    activity = await session.scalar(
        select(Activity).where(Activity.id == activity_id).with_for_update()
    )
    if activity is None:
        raise ActivityNotFoundError
    if activity.version != payload.version:
        raise ActivityVersionConflictError

    editable_fields = {
        "custom_name",
        "scheduled_time",
        "duration_minutes",
        "estimated_cost_fen",
        "status",
        "note",
        "schedule_locked",
    }
    changed_fields = payload.model_fields_set & editable_fields
    for field in changed_fields:
        setattr(activity, field, getattr(payload, field))
    activity.version += 1
    activity.updated_at = datetime.now(UTC)
    await session.flush()

    if changed_fields & {"scheduled_time", "duration_minutes", "schedule_locked"}:
        await _recalculate_schedule_from_saved_route(session, activity.day_plan_id)
        await session.flush()

    place = await session.get(PlaceCandidate, activity.place_candidate_id)
    if place is None:
        raise PlaceCandidateNotFoundError
    source = await session.get(SourceRecord, place.source_record_id)
    if source is None:
        raise PlaceCandidateNotFoundError
    await session.commit()
    await session.refresh(activity)
    return _activity_response(activity, place, source)


async def move_activity(
    session: AsyncSession,
    activity_id: uuid.UUID,
    payload: ActivityMoveRequest,
) -> ActivityMoveResponse:
    activity = await session.scalar(
        select(Activity).where(Activity.id == activity_id).with_for_update()
    )
    if activity is None:
        raise ActivityNotFoundError
    if activity.version != payload.version:
        raise ActivityVersionConflictError

    source_day = await session.scalar(
        select(DayPlan).where(DayPlan.id == activity.day_plan_id).with_for_update()
    )
    target_day = await session.scalar(
        select(DayPlan).where(DayPlan.id == payload.target_day_plan_id).with_for_update()
    )
    if source_day is None or target_day is None:
        raise DayPlanNotFoundError
    if source_day.trip_id != target_day.trip_id:
        raise InvalidActivityMoveError

    source_items = list(
        (
            await session.scalars(
                select(Activity)
                .where(Activity.day_plan_id == source_day.id)
                .order_by(Activity.position)
                .with_for_update()
            )
        ).all()
    )
    if source_day.id == target_day.id:
        target_items = [item for item in source_items if item.id != activity.id]
    else:
        target_items = list(
            (
                await session.scalars(
                    select(Activity)
                    .where(Activity.day_plan_id == target_day.id)
                    .order_by(Activity.position)
                    .with_for_update()
                )
            ).all()
        )
        if any(item.place_candidate_id == activity.place_candidate_id for item in target_items):
            raise DuplicatePlaceError

    if payload.target_position > len(target_items):
        raise InvalidActivityMoveError

    touched = source_items if source_day.id == target_day.id else source_items + target_items
    for item in touched:
        item.position += 10_000
    await session.flush()

    source_remaining = [item for item in source_items if item.id != activity.id]
    target_items.insert(payload.target_position, activity)
    if source_day.id != target_day.id:
        activity.day_plan_id = target_day.id
        for position, item in enumerate(source_remaining):
            item.position = position
    for position, item in enumerate(target_items):
        item.position = position
    activity.version += 1
    activity.updated_at = datetime.now(UTC)
    await session.flush()

    await recalculate_day_route(session, source_day.id, source_day.route_mode)
    if target_day.id != source_day.id:
        await recalculate_day_route(session, target_day.id, target_day.route_mode)
    await session.commit()
    return ActivityMoveResponse(
        activity_id=activity.id,
        source_day=await _day_response(session, source_day),
        target_day=await _day_response(session, target_day),
    )


async def _resolve_place(
    session: AsyncSession,
    day: DayPlan,
    place_id: uuid.UUID | None,
    snapshot: PlaceSearchResultResponse | None,
) -> PlaceCandidate:
    if place_id is not None:
        place = await session.get(PlaceCandidate, place_id)
        if place is None or place.trip_id != day.trip_id:
            raise PlaceCandidateNotFoundError
        return place
    if snapshot is None:
        raise PlaceCandidateNotFoundError

    slug = f"{snapshot.provider}-{snapshot.provider_place_id}"
    existing = await session.scalar(
        select(PlaceCandidate).where(
            PlaceCandidate.trip_id == day.trip_id,
            PlaceCandidate.slug == slug,
        )
    )
    if existing is not None:
        return existing

    source = SourceRecord(
        trip_id=day.trip_id,
        title=f"高德地点搜索：{snapshot.name}",
        url=snapshot.source_url,
        provider="AMap POI",
        queried_at=datetime.now(UTC),
        confidence="high",
    )
    session.add(source)
    await session.flush()
    place = PlaceCandidate(
        trip_id=day.trip_id,
        source_record_id=source.id,
        slug=slug,
        name=snapshot.name,
        category=snapshot.category,
        neighborhood=snapshot.neighborhood,
        description=snapshot.description,
        longitude=Decimal(str(snapshot.longitude)),
        latitude=Decimal(str(snapshot.latitude)),
        suggested_duration_minutes=snapshot.suggested_duration_minutes,
        estimated_cost_fen=snapshot.estimated_cost_fen,
        rating=Decimal(str(snapshot.rating)),
        tags=snapshot.tags,
    )
    session.add(place)
    await session.flush()
    return place


def _next_activity_time(existing: list[Activity]) -> time:
    if not existing:
        return time(9, 0)
    last = existing[-1]
    start = datetime.combine(datetime.today().date(), last.scheduled_time)
    candidate = start + timedelta(minutes=last.duration_minutes + 30)
    if candidate.hour >= 22:
        return time(22, 0)
    return candidate.time().replace(second=0, microsecond=0)


async def reorder_activities(
    session: AsyncSession, day_plan_id: uuid.UUID, activity_ids: list[uuid.UUID]
) -> DayPlanResponse:
    day = await session.get(DayPlan, day_plan_id)
    if day is None:
        raise DayPlanNotFoundError
    if len(activity_ids) != len(set(activity_ids)):
        raise InvalidActivityOrderError
    activities = list(
        (
            await session.scalars(
                select(Activity).where(Activity.day_plan_id == day_plan_id)
            )
        ).all()
    )
    by_id = {activity.id: activity for activity in activities}
    if set(activity_ids) != set(by_id):
        raise InvalidActivityOrderError

    route_mode = await _route_mode(session, day_plan_id)
    for activity in activities:
        activity.position += 10_000
    await session.flush()
    for position, activity_id in enumerate(activity_ids):
        by_id[activity_id].position = position
    await session.flush()
    await recalculate_day_route(session, day_plan_id, route_mode)
    await session.commit()
    return await _day_response(session, day)


async def delete_activity(session: AsyncSession, activity_id: uuid.UUID) -> None:
    activity = await session.get(Activity, activity_id)
    if activity is None:
        raise ActivityNotFoundError
    day_plan_id = activity.day_plan_id
    route_mode = await _route_mode(session, day_plan_id)
    await session.delete(activity)
    await session.flush()
    remaining = list(
        (
            await session.scalars(
                select(Activity)
                .where(Activity.day_plan_id == day_plan_id)
                .order_by(Activity.position)
            )
        ).all()
    )
    for item in remaining:
        item.position += 10_000
    await session.flush()
    for position, item in enumerate(remaining):
        item.position = position
    await session.flush()
    await recalculate_day_route(session, day_plan_id, route_mode)
    await session.commit()


async def get_planning_budget(
    session: AsyncSession, trip_id: uuid.UUID
) -> PlanningBudgetResponse:
    trip = await get_trip(session, trip_id)
    days = list(
        (
            await session.scalars(
                select(DayPlan)
                .where(DayPlan.trip_id == trip_id)
                .order_by(DayPlan.position)
            )
        ).all()
    )
    day_responses: list[PlanningBudgetDayResponse] = []
    total_planned = 0
    for day in days:
        planned = sum(
            activity.estimated_cost_fen
            for activity, _, _ in await _activity_rows(session, day.id)
            if activity.status != "skipped"
        )
        total_planned += planned
        ratio = planned / trip.daily_budget_fen if trip.daily_budget_fen else 1.0
        status = "over" if ratio > 1 else "watch" if ratio >= 0.8 else "comfortable"
        day_responses.append(
            PlanningBudgetDayResponse(
                day_plan_id=day.id,
                date=day.date,
                planned_fen=planned,
                remaining_fen=trip.daily_budget_fen - planned,
                ratio=ratio,
                status=status,
            )
        )
    return PlanningBudgetResponse(
        trip_id=trip_id,
        total_planned_fen=total_planned,
        total_remaining_fen=trip.total_budget_fen - total_planned,
        days=day_responses,
    )
