"""NavigationSession use cases and database compare-and-set boundaries."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import update, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Activity,
    DayPlan,
    NavigationDetectionState,
    NavigationSession,
    PlaceCandidate,
    RouteLeg,
    Trip,
    TripExecution,
)
from app.navigation.providers import (
    RoutingCoordinate,
    RoutingProvider,
    RoutingProviderError,
    RoutingRequest,
    RoutingResult,
)
from app.schemas import (
    NavigationCoordinate,
    NavigationLocationUpdate,
    NavigationSessionActionRequest,
    NavigationSessionCreate,
    NavigationSessionResponse,
)


LIVE_STATUSES = ("active", "rerouting")
TERMINAL_STATUSES = ("completed", "cancelled", "superseded")
COORDINATE_PRECISION = Decimal("0.000001")


class NavigationSessionError(Exception):
    pass


class NavigationSessionNotFoundError(NavigationSessionError):
    pass


class NavigationSessionConflictError(NavigationSessionError):
    pass


class NavigationSessionStateError(NavigationSessionError):
    pass


class StaleNavigationWriteError(NavigationSessionError):
    pass


@dataclass(frozen=True, slots=True)
class RouteRefreshToken:
    session_id: uuid.UUID
    itinerary_version: int
    route_revision: int
    request: RoutingRequest


def navigation_session_response(item: NavigationSession) -> NavigationSessionResponse:
    last_location = None
    if item.last_location_longitude is not None and item.last_location_latitude is not None:
        last_location = NavigationCoordinate(
            longitude=float(item.last_location_longitude), latitude=float(item.last_location_latitude)
        )
    return NavigationSessionResponse(
        id=item.id,
        trip_id=item.trip_id,
        trip_execution_id=item.trip_execution_id,
        from_activity_id=item.from_activity_id,
        to_activity_id=item.to_activity_id,
        formal_route_leg_id=item.formal_route_leg_id,
        itinerary_version=item.itinerary_version,
        travel_mode=item.travel_mode,
        coordinate_system=item.coordinate_system,
        origin=NavigationCoordinate(longitude=float(item.origin_longitude), latitude=float(item.origin_latitude)),
        destination=NavigationCoordinate(longitude=float(item.destination_longitude), latitude=float(item.destination_latitude)),
        planned_departure_at=item.planned_departure_at,
        planned_arrival_at=item.planned_arrival_at,
        current_eta=item.current_eta,
        remaining_distance_meters=item.remaining_distance_meters,
        current_duration_minutes=item.current_duration_minutes,
        progress_ratio=float(item.progress_ratio) if item.progress_ratio is not None else None,
        provider=item.provider,
        provider_metadata=item.provider_metadata,
        route_path=[tuple(point) for point in item.route_path],
        route_revision=item.route_revision,
        last_location_sequence=item.last_location_sequence,
        last_location=last_location,
        last_location_accuracy_meters=(
            float(item.last_location_accuracy_meters)
            if item.last_location_accuracy_meters is not None
            else None
        ),
        last_location_at=item.last_location_at,
        remaining_duration_seconds=item.remaining_duration_seconds,
        navigation_status=item.navigation_status,
        observation_source=item.observation_source,
        status=item.status,
        state_version=item.state_version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def create_navigation_session(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: NavigationSessionCreate,
    *,
    commit: bool = True,
) -> NavigationSession:
    """Create a live projection from a currently persisted formal RouteLeg."""
    trip = await session.scalar(select(Trip).where(Trip.id == trip_id).with_for_update())
    if trip is None:
        raise NavigationSessionNotFoundError("trip not found")
    execution = await session.scalar(
        select(TripExecution)
        .where(TripExecution.id == payload.trip_execution_id, TripExecution.trip_id == trip_id)
        .with_for_update()
    )
    if execution is None:
        raise NavigationSessionNotFoundError("trip execution not found")
    if execution.status != "in_progress":
        raise NavigationSessionStateError("只有进行中的旅行可以创建导航会话")

    route = await session.scalar(
        select(RouteLeg)
        .join(DayPlan, RouteLeg.day_plan_id == DayPlan.id)
        .where(
            RouteLeg.from_activity_id == payload.from_activity_id,
            RouteLeg.to_activity_id == payload.to_activity_id,
            DayPlan.trip_id == trip_id,
        )
        .with_for_update()
    )
    if route is None:
        raise NavigationSessionConflictError("指定活动不是当前正式行程中的相邻路线")
    origin = await _activity_place(session, payload.from_activity_id, trip_id)
    destination = await _activity_place(session, payload.to_activity_id, trip_id)
    if origin is None or destination is None:
        raise NavigationSessionConflictError("导航活动不属于当前旅行")
    from_activity, from_day, from_place = origin
    _, _, to_place = destination
    timezone = ZoneInfo(trip.timezone)
    departure = datetime.combine(from_day.date, from_activity.scheduled_time, tzinfo=timezone)
    departure += timedelta(minutes=from_activity.duration_minutes)
    arrival = departure + timedelta(minutes=route.duration_minutes)
    created = NavigationSession(
        trip_id=trip.id,
        trip_execution_id=execution.id,
        from_activity_id=from_activity.id,
        to_activity_id=payload.to_activity_id,
        formal_route_leg_id=route.id,
        itinerary_version=trip.version,
        travel_mode=route.mode,
        origin_longitude=from_place.longitude,
        origin_latitude=from_place.latitude,
        destination_longitude=to_place.longitude,
        destination_latitude=to_place.latitude,
        planned_departure_at=departure,
        planned_arrival_at=arrival,
        remaining_distance_meters=route.distance_meters,
        current_duration_minutes=route.duration_minutes,
        status="active",
    )
    session.add(created)
    if commit:
        try:
            await session.flush()
            session.add(
                NavigationDetectionState(
                    navigation_session_id=created.id,
                    itinerary_version=created.itinerary_version,
                )
            )
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise NavigationSessionConflictError("当前旅行执行已有有效导航会话") from exc
        await session.refresh(created)
    else:
        # The caller owns the transaction.  Do not rollback here: doing so
        # would accidentally discard its execution/start changes as well.
        await session.flush()
        session.add(
            NavigationDetectionState(
                navigation_session_id=created.id,
                itinerary_version=created.itinerary_version,
            )
        )
        await session.flush()
    return created


async def _activity_place(
    session: AsyncSession, activity_id: uuid.UUID, trip_id: uuid.UUID
) -> tuple[Activity, DayPlan, PlaceCandidate] | None:
    row = await session.execute(
        select(Activity, DayPlan, PlaceCandidate)
        .join(DayPlan, Activity.day_plan_id == DayPlan.id)
        .join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
        .where(Activity.id == activity_id, DayPlan.trip_id == trip_id)
    )
    return row.tuples().one_or_none()


async def get_navigation_session(session: AsyncSession, session_id: uuid.UUID) -> NavigationSession:
    item = await session.get(NavigationSession, session_id)
    if item is None:
        raise NavigationSessionNotFoundError("navigation session not found")
    return item


async def apply_location_update(
    session: AsyncSession, session_id: uuid.UUID, payload: NavigationLocationUpdate
) -> NavigationSession:
    """Persist only a newer client sequence through an atomic compare-and-set."""
    result = await session.execute(
        update(NavigationSession)
        .where(
            NavigationSession.id == session_id,
            NavigationSession.status.in_(LIVE_STATUSES),
            NavigationSession.itinerary_version == payload.itinerary_version,
            NavigationSession.last_location_sequence < payload.sequence,
        )
        .values(
            last_location_sequence=payload.sequence,
            last_location_longitude=_stored_coordinate(payload.location.longitude),
            last_location_latitude=_stored_coordinate(payload.location.latitude),
            last_location_at=payload.observed_at.astimezone(UTC),
            state_version=NavigationSession.state_version + 1,
        )
        .returning(NavigationSession.id)
    )
    if result.scalar_one_or_none() is None:
        await session.rollback()
        return await _resolve_location_write_miss(session, session_id, payload)
    await session.commit()
    return await get_navigation_session(session, session_id)


async def _resolve_location_write_miss(
    session: AsyncSession, session_id: uuid.UUID, payload: NavigationLocationUpdate
) -> NavigationSession:
    item = await get_navigation_session(session, session_id)
    if item.status in TERMINAL_STATUSES:
        raise NavigationSessionStateError(f"{item.status} 导航会话不能接收位置更新")
    if item.itinerary_version != payload.itinerary_version:
        raise StaleNavigationWriteError("位置更新对应的正式行程版本已过期")
    # Retrying an already-acknowledged delivery is safe.  A client sequence is
    # an idempotency key only when all material values match; a different point
    # reusing the sequence is a stale/conflicting write.
    if (
        item.last_location_sequence == payload.sequence
        and item.last_location_longitude == _stored_coordinate(payload.location.longitude)
        and item.last_location_latitude == _stored_coordinate(payload.location.latitude)
        and item.last_location_at is not None
        and item.last_location_at.astimezone(UTC) == payload.observed_at.astimezone(UTC)
    ):
        return item
    raise StaleNavigationWriteError("位置更新序号不是最新值")


def _stored_coordinate(value: float) -> Decimal:
    """Match PostgreSQL Numeric(9, 6) before comparing an idempotent replay."""
    return Decimal(str(value)).quantize(COORDINATE_PRECISION)


async def apply_navigation_session_action(
    session: AsyncSession, session_id: uuid.UUID, payload: NavigationSessionActionRequest
) -> NavigationSession:
    """Terminal transitions are explicit and cannot revive a closed session."""
    target_status = "completed" if payload.action == "complete" else "cancelled"
    updated = await session.execute(
        update(NavigationSession)
        .where(NavigationSession.id == session_id, NavigationSession.status.in_(LIVE_STATUSES))
        .values(status=target_status, state_version=NavigationSession.state_version + 1)
        .returning(NavigationSession.id)
    )
    if updated.scalar_one_or_none() is None:
        await session.rollback()
        item = await get_navigation_session(session, session_id)
        raise NavigationSessionStateError(f"{item.status} 导航会话不能执行 {payload.action}")
    await session.commit()
    return await get_navigation_session(session, session_id)


async def prepare_route_refresh(session: AsyncSession, session_id: uuid.UUID) -> RouteRefreshToken:
    """Fence an asynchronous provider call before awaiting external I/O."""
    item = await session.scalar(select(NavigationSession).where(NavigationSession.id == session_id).with_for_update())
    if item is None:
        raise NavigationSessionNotFoundError("navigation session not found")
    if item.status not in LIVE_STATUSES:
        raise NavigationSessionStateError(f"{item.status} 导航会话不能刷新路线")
    item.route_revision += 1
    item.state_version += 1
    item.status = "rerouting"
    origin = RoutingCoordinate(
        longitude=float(item.last_location_longitude if item.last_location_longitude is not None else item.origin_longitude),
        latitude=float(item.last_location_latitude if item.last_location_latitude is not None else item.origin_latitude),
    )
    request = RoutingRequest(
        origin=origin,
        destination=RoutingCoordinate(longitude=float(item.destination_longitude), latitude=float(item.destination_latitude)),
        travel_mode=item.travel_mode,
        departure_at=datetime.now(UTC),
        coordinate_system=item.coordinate_system,
    )
    token = RouteRefreshToken(item.id, item.itinerary_version, item.route_revision, request)
    await session.commit()
    return token


async def apply_route_result(
    session: AsyncSession, token: RouteRefreshToken, result: RoutingResult
) -> NavigationSession:
    """CAS a provider response so old route results can never win the race."""
    updated = await session.execute(
        update(NavigationSession)
        .where(
            NavigationSession.id == token.session_id,
            NavigationSession.status.in_(LIVE_STATUSES),
            NavigationSession.itinerary_version == token.itinerary_version,
            NavigationSession.route_revision == token.route_revision,
        )
        .values(
            status="active",
            current_eta=result.eta,
            remaining_distance_meters=result.distance_meters,
            current_duration_minutes=result.duration_minutes,
            provider=result.provider,
            provider_metadata=result.provider_metadata,
            route_path=[[point.longitude, point.latitude] for point in result.path],
            state_version=NavigationSession.state_version + 1,
        )
        .returning(NavigationSession.id)
    )
    if updated.scalar_one_or_none() is None:
        await session.rollback()
        raise StaleNavigationWriteError("路线响应已过期，未写入导航会话")
    await session.commit()
    return await get_navigation_session(session, token.session_id)


async def mark_route_failure(session: AsyncSession, token: RouteRefreshToken) -> None:
    """Restore active only if this still is the newest in-flight revision."""
    await session.execute(
        update(NavigationSession)
        .where(
            NavigationSession.id == token.session_id,
            NavigationSession.status == "rerouting",
            NavigationSession.itinerary_version == token.itinerary_version,
            NavigationSession.route_revision == token.route_revision,
        )
        .values(status="active", state_version=NavigationSession.state_version + 1)
    )
    await session.commit()


async def refresh_route(
    session_factory, session_id: uuid.UUID, provider: RoutingProvider
) -> NavigationSession:
    """Do not retain a database transaction while waiting for a provider."""
    async with session_factory() as session:
        token = await prepare_route_refresh(session, session_id)
    try:
        result = await provider.route(token.request)
    except RoutingProviderError:
        async with session_factory() as session:
            await mark_route_failure(session, token)
        raise
    async with session_factory() as session:
        return await apply_route_result(session, token, result)


async def supersede_navigation_sessions_for_itinerary(
    session: AsyncSession, trip_id: uuid.UUID, itinerary_version: int
) -> int:
    """Called in the same acceptance transaction before replaceable legs change."""
    result = await session.execute(
        update(NavigationSession)
        .where(
            NavigationSession.trip_id == trip_id,
            NavigationSession.itinerary_version == itinerary_version,
            NavigationSession.status.in_(LIVE_STATUSES),
        )
        .values(status="superseded", state_version=NavigationSession.state_version + 1)
    )
    return int(result.rowcount or 0)
