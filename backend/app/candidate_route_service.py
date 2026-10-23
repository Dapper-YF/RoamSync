import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import Activity, DayPlan, PlaceCandidate, Trip
from app.maps_service import resolve_detached_route_result, MapProviderError, RoutePlace
from app.planning_preparation import PlanningPreparationRequiredError
from app.schemas import CandidatePlanSnapshot, CandidateRouteLeg
from app.agent_observation import observed


@dataclass(frozen=True)
class _PlanNode:
    activity_ref: str
    day_date: date
    planned_start_time: time
    duration_minutes: int
    place: RoutePlace
    transport_mode_to_here: str


@observed("route", purpose="Route enrichment (includes persisted cache lookup)",
          output_summary=lambda result: {"route_legs": result.model_dump(mode="json")["route_legs"]})
async def enrich_candidate_routes(
    session: AsyncSession,
    trip_id: uuid.UUID,
    snapshot: CandidatePlanSnapshot,
    *,
    enforce_execution_invariants: bool = False,
) -> CandidatePlanSnapshot:
    """Resolve route evidence for the complete candidate plan.

    Locked, active, and completed formal activities that are not represented in
    the candidate snapshot remain part of the final plan, so they are included
    under stable ``activity:<uuid>`` references.
    """

    if session.in_transaction():
        raise PlanningPreparationRequiredError("prepare routes before opening the caller transaction")
    sessions = async_sessionmaker(session.bind, expire_on_commit=False)
    async with sessions() as reader:
        nodes_by_day = await _load_plan_nodes(reader, trip_id, snapshot, enforce_execution_invariants)
        trip = await reader.get(Trip, trip_id)
        city = trip.destination_citycode or trip.destination if trip else ""
    return await _resolve_nodes(sessions, snapshot, nodes_by_day, city)


async def _load_plan_nodes(session, trip_id, snapshot, enforce_execution_invariants):
    day_rows = list(
        (await session.scalars(select(DayPlan).where(DayPlan.trip_id == trip_id))).all()
    )
    days_by_date = {day.date: day for day in day_rows}
    represented_activity_ids = {
        item.replaces_activity_id
        for item in snapshot.activities
        if item.replaces_activity_id is not None
    }
    formal_rows = list(
        (
            await session.execute(
                select(Activity, DayPlan, PlaceCandidate)
                .join(DayPlan, Activity.day_plan_id == DayPlan.id)
                .join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
                .where(DayPlan.trip_id == trip_id)
            )
        ).tuples()
    )

    nodes_by_day: dict[date, list[_PlanNode]] = defaultdict(list)
    from app.navigation.execution_context import execution_invariants_required
    enforce_execution_invariants = await execution_invariants_required(session, trip_id, enforce_execution_invariants)
    execution_protected = set()
    if enforce_execution_invariants:
        from app.plan_revision_service import _execution_immutable_activity_ids
        frozen, protected = await _execution_immutable_activity_ids(session, trip_id)
        execution_protected = frozen | protected
    for activity, day, place in formal_rows:
        is_protected = activity.schedule_locked or activity.status in {"active", "completed"} or activity.id in execution_protected
        if not is_protected or activity.id in represented_activity_ids:
            continue
        nodes_by_day[day.date].append(
            _PlanNode(
                activity_ref=f"activity:{activity.id}",
                day_date=day.date,
                planned_start_time=activity.scheduled_time,
                duration_minutes=activity.duration_minutes,
                place=RoutePlace.from_place(place),
                transport_mode_to_here=day.route_mode,
            )
        )

    requested_place_ids = {item.place_candidate_id for item in snapshot.activities}
    places = list(
        (
            await session.scalars(
                select(PlaceCandidate).where(
                    PlaceCandidate.trip_id == trip_id,
                    PlaceCandidate.id.in_(requested_place_ids or {uuid.uuid4()}),
                )
            )
        ).all()
    )
    places_by_id = {place.id: place for place in places}
    for item in snapshot.activities:
        place = places_by_id.get(item.place_candidate_id)
        if place is None or item.day_date not in days_by_date:
            continue
        nodes_by_day[item.day_date].append(
            _PlanNode(
                activity_ref=item.candidate_id,
                day_date=item.day_date,
                planned_start_time=item.planned_start_time,
                duration_minutes=item.duration_minutes,
                place=RoutePlace.from_place(place),
                transport_mode_to_here=item.transport_mode_to_here,
            )
        )

    return nodes_by_day


async def _resolve_nodes(sessions, snapshot, nodes_by_day, city):
    route_legs: list[CandidateRouteLeg] = []
    for day_date, nodes in sorted(nodes_by_day.items()):
        ordered = sorted(nodes, key=lambda node: (node.planned_start_time, node.activity_ref))
        for position, (origin, destination) in enumerate(
            zip(ordered, ordered[1:], strict=False)
        ):
            try:
                result = await resolve_detached_route_result(
                    sessions, origin.place, destination.place, destination.transport_mode_to_here, city)
            except MapProviderError as exc:
                if exc.code != "map_route_unavailable":
                    raise
                mode = {"walk": "步行", "transit": "公共交通", "driving": "驾车"}[destination.transport_mode_to_here]
                error = MapProviderError(f"{day_date}：{origin.place.name} → {destination.place.name}，高德未返回可用的{mode}路线。需要更换可达地点或确认其他交通方式。", code=exc.code)
                error.route_details = {"day_date": str(day_date), "from_place": origin.place.name, "to_place": destination.place.name,
                    "from_activity_ref": origin.activity_ref, "to_activity_ref": destination.activity_ref, "mode": destination.transport_mode_to_here}
                raise error from exc
            route_legs.append(
                CandidateRouteLeg(
                    day_date=day_date,
                    from_activity_ref=origin.activity_ref,
                    to_activity_ref=destination.activity_ref,
                    position=position,
                    mode=destination.transport_mode_to_here,
                    distance_meters=result.distance_meters,
                    duration_minutes=result.duration_minutes,
                    provider=result.provider,
                    is_estimated=result.is_estimated,
                    path=result.path or [],
                    alternatives=result.alternatives or [],
                    calculated_at=datetime.now(UTC),
                )
            )
    return snapshot.model_copy(update={"route_legs": route_legs})
