import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, DayPlan, Expense, PlaceCandidate, RouteLeg, SourceRecord, Trip, TripPreferences
from app.formal_write import lock_trip
from app.schemas import (
    BudgetResponse,
    ExpenseCreate,
    TripCreate,
    TripDeletionPreviewResponse,
    TripPreferencesUpdate,
    TripUpdate,
)


class TripNotFoundError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class TripVersionConflictError(Exception):
    pass


class TripDateConflictError(Exception):
    pass


class TripPreferencesVersionConflictError(Exception):
    pass


async def create_trip(session: AsyncSession, payload: TripCreate, *, commit: bool = True) -> Trip:
    trip = Trip(**payload.model_dump())
    session.add(trip)
    await session.flush()
    session.add(TripPreferences(trip_id=trip.id))
    current = payload.start_date
    position = 0
    while current <= payload.end_date:
        session.add(
            DayPlan(
                trip_id=trip.id,
                date=current,
                label=f"第 {position + 1} 天",
                theme=f"探索{payload.destination or '目的地'}",
                position=position,
                route_mode="walk",
            )
        )
        current += timedelta(days=1)
        position += 1
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(trip)
    return trip


async def get_trip(session: AsyncSession, trip_id: uuid.UUID) -> Trip:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise TripNotFoundError
    return trip


async def list_trips(session: AsyncSession) -> list[Trip]:
    return list(
        (
            await session.scalars(
                select(Trip).order_by(Trip.start_date.desc(), Trip.created_at.desc())
            )
        ).all()
    )


async def update_trip(
    session: AsyncSession, trip_id: uuid.UUID, payload: TripUpdate
) -> Trip:
    await get_trip(session, trip_id)
    trip = await lock_trip(session, trip_id)
    if trip.version != payload.version:
        raise TripVersionConflictError
    values = payload.model_dump(
        exclude_unset=True,
        exclude={"version", "confirm_day_removal"},
    )
    if not any(getattr(trip, key) != value for key, value in values.items()):
        await session.commit()
        return trip
    if "total_budget_fen" in values and values["total_budget_fen"] is None:
        values["daily_budget_fen"] = None
    if "daily_budget_fen" in values and values["daily_budget_fen"] is None:
        values["total_budget_fen"] = None
    start_date = values.get("start_date", trip.start_date)
    end_date = values.get("end_date", trip.end_date)
    total_budget = values.get("total_budget_fen", trip.total_budget_fen)
    daily_budget = values.get("daily_budget_fen", trip.daily_budget_fen)
    if end_date < start_date or (daily_budget is not None and total_budget is not None and daily_budget > total_budget):
        raise ValueError("invalid trip dates or budget")

    days = list(
        (
            await session.scalars(
                select(DayPlan).where(DayPlan.trip_id == trip_id).order_by(DayPlan.position)
            )
        ).all()
    )
    wanted_dates = []
    current = start_date
    while current <= end_date:
        wanted_dates.append(current)
        current += timedelta(days=1)
    wanted = set(wanted_dates)
    removed = [day for day in days if day.date not in wanted]
    if removed and not payload.confirm_day_removal:
        removed_ids = [day.id for day in removed]
        activity_count = await session.scalar(
            select(func.count(Activity.id)).where(Activity.day_plan_id.in_(removed_ids))
        )
        if int(activity_count or 0) > 0:
            raise TripDateConflictError

    for key, value in values.items():
        setattr(trip, key, value)
    by_date = {day.date: day for day in days}
    for day in days:
        day.position += 10_000
    await session.flush()
    for day in removed:
        await session.delete(day)
    for position, day_date in enumerate(wanted_dates):
        day = by_date.get(day_date)
        if day is None:
            day = DayPlan(
                trip_id=trip_id,
                date=day_date,
                label=f"第 {position + 1} 天",
                theme=f"探索{values.get('destination', trip.destination)}",
                position=position,
                route_mode="walk",
            )
            session.add(day)
        else:
            day.position = position
            day.label = f"第 {position + 1} 天"
    trip.version += 1
    await session.commit()
    await session.refresh(trip)
    return trip


async def duplicate_trip(session: AsyncSession, trip_id: uuid.UUID, *, commit: bool = True) -> Trip:
    source_trip = await get_trip(session, trip_id)
    duplicate = Trip(
        title=f"{source_trip.title}（副本）",
        destination=source_trip.destination,
        destination_adcode=source_trip.destination_adcode,
        destination_citycode=source_trip.destination_citycode,
        center_longitude=source_trip.center_longitude,
        center_latitude=source_trip.center_latitude,
        accommodation=source_trip.accommodation,
        accommodation_poi_id=source_trip.accommodation_poi_id,
        accommodation_address=source_trip.accommodation_address,
        accommodation_district=source_trip.accommodation_district,
        accommodation_longitude=source_trip.accommodation_longitude,
        accommodation_latitude=source_trip.accommodation_latitude,
        currency=source_trip.currency,
        timezone=source_trip.timezone,
        start_date=source_trip.start_date,
        end_date=source_trip.end_date,
        total_budget_fen=source_trip.total_budget_fen,
        daily_budget_fen=source_trip.daily_budget_fen,
    )
    session.add(duplicate)
    await session.flush()
    source_preferences = await session.get(TripPreferences, trip_id)
    if source_preferences is not None:
        session.add(
            TripPreferences(
                trip_id=duplicate.id,
                pace=source_preferences.pace,
                interest_categories=list(source_preferences.interest_categories),
                transport_modes=list(source_preferences.transport_modes),
                daily_start_time=source_preferences.daily_start_time,
                daily_end_time=source_preferences.daily_end_time,
                meal_preferences=source_preferences.meal_preferences,
                avoid_categories=list(source_preferences.avoid_categories),
                max_walking_minutes=source_preferences.max_walking_minutes,
                free_text_requirements=source_preferences.free_text_requirements,
            )
        )

    source_map: dict[uuid.UUID, SourceRecord] = {}
    for source in (
        await session.scalars(select(SourceRecord).where(SourceRecord.trip_id == trip_id))
    ).all():
        cloned = SourceRecord(
            trip_id=duplicate.id,
            title=source.title,
            url=source.url,
            provider=source.provider,
            queried_at=source.queried_at,
            confidence=source.confidence,
        )
        session.add(cloned)
        await session.flush()
        source_map[source.id] = cloned

    place_map: dict[uuid.UUID, PlaceCandidate] = {}
    for place in (
        await session.scalars(select(PlaceCandidate).where(PlaceCandidate.trip_id == trip_id))
    ).all():
        cloned = PlaceCandidate(
            trip_id=duplicate.id,
            source_record_id=source_map[place.source_record_id].id,
            slug=place.slug,
            name=place.name,
            category=place.category,
            neighborhood=place.neighborhood,
            description=place.description,
            longitude=place.longitude,
            latitude=place.latitude,
            suggested_duration_minutes=place.suggested_duration_minutes,
            estimated_cost_fen=place.estimated_cost_fen,
            rating=place.rating,
            tags=list(place.tags),
        )
        session.add(cloned)
        await session.flush()
        place_map[place.id] = cloned

    day_map: dict[uuid.UUID, DayPlan] = {}
    for day in (
        await session.scalars(select(DayPlan).where(DayPlan.trip_id == trip_id))
    ).all():
        cloned = DayPlan(
            trip_id=duplicate.id,
            date=day.date,
            label=day.label,
            theme=day.theme,
            position=day.position,
            route_mode=day.route_mode,
        )
        session.add(cloned)
        await session.flush()
        day_map[day.id] = cloned

    activity_map: dict[uuid.UUID, Activity] = {}
    for activity in (
        await session.scalars(
            select(Activity).join(DayPlan, Activity.day_plan_id == DayPlan.id).where(DayPlan.trip_id == trip_id)
        )
    ).all():
        cloned = Activity(
                day_plan_id=day_map[activity.day_plan_id].id,
                place_candidate_id=place_map[activity.place_candidate_id].id,
                scheduled_time=activity.scheduled_time,
                duration_minutes=activity.duration_minutes,
                importance=activity.importance,
                can_skip=activity.can_skip,
                minimum_duration_minutes=activity.minimum_duration_minutes,
                importance_source=activity.importance_source,
                can_skip_source=activity.can_skip_source,
                minimum_duration_source=activity.minimum_duration_source,
                estimated_cost_fen=activity.estimated_cost_fen,
                status=activity.status,
                position=activity.position,
                custom_name=activity.custom_name,
                schedule_locked=activity.schedule_locked,
                note=activity.note,
        )
        session.add(cloned)
        await session.flush()
        activity_map[activity.id] = cloned
    for leg in (
        await session.scalars(
            select(RouteLeg).join(DayPlan, RouteLeg.day_plan_id == DayPlan.id).where(DayPlan.trip_id == trip_id)
        )
    ).all():
        session.add(
            RouteLeg(
                day_plan_id=day_map[leg.day_plan_id].id,
                from_activity_id=activity_map[leg.from_activity_id].id,
                to_activity_id=activity_map[leg.to_activity_id].id,
                position=leg.position,
                mode=leg.mode,
                distance_meters=leg.distance_meters,
                duration_minutes=leg.duration_minutes,
                provider=leg.provider,
                is_estimated=leg.is_estimated,
                calculated_at=leg.calculated_at,
            )
        )
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(duplicate)
    return duplicate


async def archive_trip(session: AsyncSession, trip_id: uuid.UUID) -> Trip:
    await get_trip(session, trip_id)
    trip = await lock_trip(session, trip_id)
    if trip.archived_at is not None:
        await session.commit()
        return trip
    trip.archived_at = datetime.now(UTC)
    trip.version += 1
    await session.commit()
    await session.refresh(trip)
    return trip


async def get_trip_deletion_preview(
    session: AsyncSession, trip_id: uuid.UUID
) -> TripDeletionPreviewResponse:
    await get_trip(session, trip_id)
    day_ids = select(DayPlan.id).where(DayPlan.trip_id == trip_id)
    return TripDeletionPreviewResponse(
        trip_id=trip_id,
        day_plans=int(await session.scalar(select(func.count(DayPlan.id)).where(DayPlan.trip_id == trip_id)) or 0),
        activities=int(await session.scalar(select(func.count(Activity.id)).where(Activity.day_plan_id.in_(day_ids))) or 0),
        candidates=int(await session.scalar(select(func.count(PlaceCandidate.id)).where(PlaceCandidate.trip_id == trip_id)) or 0),
        expenses=int(await session.scalar(select(func.count(Expense.id)).where(Expense.trip_id == trip_id)) or 0),
    )


async def delete_trip(session: AsyncSession, trip_id: uuid.UUID) -> None:
    await get_trip(session, trip_id)
    # Assistant actions hold Session before Trip. Lock dependent sessions in
    # that order before cascading them, rather than invert the order on delete.
    from app.database import AssistantSession
    await session.scalars(select(AssistantSession).where(AssistantSession.trip_id == trip_id).order_by(AssistantSession.id).with_for_update())
    await lock_trip(session, trip_id)
    await session.execute(delete(Trip).where(Trip.id == trip_id))
    await session.commit()


async def get_trip_preferences(
    session: AsyncSession, trip_id: uuid.UUID
) -> TripPreferences:
    await get_trip(session, trip_id)
    preferences = await session.get(TripPreferences, trip_id)
    if preferences is None:
        # Defensive compatibility for databases imported without running migrations.
        preferences = TripPreferences(trip_id=trip_id)
        session.add(preferences)
        await session.commit()
        await session.refresh(preferences)
    return preferences


async def update_trip_preferences(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: TripPreferencesUpdate,
) -> TripPreferences:
    await get_trip(session, trip_id)
    await lock_trip(session, trip_id)
    preferences = await session.scalar(select(TripPreferences).where(TripPreferences.trip_id == trip_id).with_for_update().execution_options(populate_existing=True))
    if preferences is None:
        preferences = TripPreferences(trip_id=trip_id)
        session.add(preferences)
        await session.flush()
    if preferences.version != payload.version:
        raise TripPreferencesVersionConflictError
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(preferences, key, value)
    preferences.version += 1
    await session.commit()
    await session.refresh(preferences)
    return preferences


def _same_expense(existing: Expense, payload: ExpenseCreate) -> bool:
    if (
        existing.amount_fen != payload.amount_fen
        or existing.category != payload.category
        or existing.description != payload.description
    ):
        return False
    if payload.spent_at is None:
        return True
    return existing.spent_at.astimezone(UTC) == payload.spent_at.astimezone(UTC)


async def create_expense(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: ExpenseCreate,
) -> tuple[Expense, bool]:
    await get_trip(session, trip_id)
    existing = await session.scalar(
        select(Expense).where(
            Expense.trip_id == trip_id,
            Expense.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if not _same_expense(existing, payload):
            raise IdempotencyConflictError
        return existing, True

    expense = Expense(
        trip_id=trip_id,
        idempotency_key=payload.idempotency_key,
        amount_fen=payload.amount_fen,
        category=payload.category,
        description=payload.description,
        spent_at=payload.spent_at or datetime.now(UTC),
    )
    session.add(expense)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(Expense).where(
                Expense.trip_id == trip_id,
                Expense.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is None or not _same_expense(existing, payload):
            raise IdempotencyConflictError
        return existing, True
    await session.refresh(expense)
    return expense, False


async def get_budget(session: AsyncSession, trip_id: uuid.UUID) -> BudgetResponse:
    trip = await get_trip(session, trip_id)
    timezone = ZoneInfo(trip.timezone)
    now_local = datetime.now(timezone)
    local_date = now_local.date()
    day_start = datetime.combine(local_date, time.min, tzinfo=timezone).astimezone(UTC)
    day_end = datetime.combine(local_date, time.max, tzinfo=timezone).astimezone(UTC)

    total_spent = await session.scalar(
        select(func.coalesce(func.sum(Expense.amount_fen), 0)).where(
            Expense.trip_id == trip_id
        )
    )
    today_spent = await session.scalar(
        select(func.coalesce(func.sum(Expense.amount_fen), 0)).where(
            Expense.trip_id == trip_id,
            Expense.spent_at >= day_start,
            Expense.spent_at <= day_end,
        )
    )
    total_spent_fen = int(total_spent or 0)
    today_spent_fen = int(today_spent or 0)

    return BudgetResponse(
        trip_id=trip.id,
        currency=trip.currency,
        total_budget_fen=trip.total_budget_fen,
        total_spent_fen=total_spent_fen,
        total_remaining_fen=(trip.total_budget_fen - total_spent_fen) if trip.total_budget_fen is not None else None,
        daily_budget_fen=trip.daily_budget_fen,
        today_spent_fen=today_spent_fen,
        today_remaining_fen=(trip.daily_budget_fen - today_spent_fen) if trip.daily_budget_fen is not None else None,
        local_date=local_date,
    )
