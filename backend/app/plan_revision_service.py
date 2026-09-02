import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Activity,
    DayPlan,
    PlaceCandidate,
    PlanningRun,
    PlanRevision,
    RouteLeg,
    SourceRecord,
    Trip,
)
from app.planning_run_repository import (
    InvalidPlanningRunStateError,
    PlanRevisionNotFoundError,
    StalePlanningRunError,
)
from app.repository import get_trip_preferences
from app.schemas import (
    CandidatePlanSnapshot,
    PlanValidationIssue,
    PlanValidationResult,
)


class InvalidPlanRevisionError(Exception):
    def __init__(self, result: PlanValidationResult):
        self.result = result
        super().__init__("candidate plan failed deterministic validation")


async def validate_candidate_plan(
    session: AsyncSession,
    trip_id: uuid.UUID,
    snapshot: CandidatePlanSnapshot,
) -> PlanValidationResult:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise PlanRevisionNotFoundError
    preferences = await get_trip_preferences(session, trip_id)
    days = list((await session.scalars(select(DayPlan).where(DayPlan.trip_id == trip_id))).all())
    day_by_date = {day.date: day for day in days}
    existing = list(
        (
            await session.scalars(
                select(Activity).join(DayPlan).where(DayPlan.trip_id == trip_id)
            )
        ).all()
    )
    existing_by_id = {item.id: item for item in existing}
    protected = {
        item.id: item
        for item in existing
        if item.schedule_locked or item.status in {"active", "completed"}
    }
    requested_place_ids = {item.place_candidate_id for item in snapshot.activities}
    place_rows = list(
        (
            await session.scalars(
                select(PlaceCandidate).where(
                    PlaceCandidate.trip_id == trip_id,
                    PlaceCandidate.id.in_(requested_place_ids or {uuid.uuid4()}),
                )
            )
        ).all()
    )
    places_by_id = {place.id: place for place in place_rows}
    requested_sources = {source_id for item in snapshot.activities for source_id in item.source_ids}
    valid_sources = set(
        (
            await session.scalars(
                select(SourceRecord.id).where(
                    SourceRecord.trip_id == trip_id,
                    SourceRecord.id.in_(requested_sources or {uuid.uuid4()}),
                )
            )
        ).all()
    )
    errors: list[PlanValidationIssue] = []
    intervals: dict = defaultdict(list)
    route_nodes: dict = defaultdict(list)
    daily_cost: dict = defaultdict(int)

    for activity in snapshot.activities:
        if activity.day_date not in day_by_date:
            errors.append(PlanValidationIssue(code="date_outside_trip", message="候选活动日期不属于该旅行", candidate_id=activity.candidate_id))
            continue
        place = places_by_id.get(activity.place_candidate_id)
        if place is None:
            errors.append(PlanValidationIssue(code="unknown_place", message="候选地点不属于该旅行", candidate_id=activity.candidate_id))
        elif activity.estimated_cost_fen != place.estimated_cost_fen:
            errors.append(PlanValidationIssue(code="place_cost_mismatch", message="候选费用必须使用后端保存的地点预计费用", candidate_id=activity.candidate_id))
        elif place.source_record_id not in activity.source_ids:
            errors.append(PlanValidationIssue(code="missing_place_source", message="候选活动必须保留地点来源", candidate_id=activity.candidate_id))
        if any(source_id not in valid_sources for source_id in activity.source_ids):
            errors.append(PlanValidationIssue(code="unknown_source", message="候选来源不属于该旅行", candidate_id=activity.candidate_id))
        if activity.replaces_activity_id is not None and activity.replaces_activity_id not in existing_by_id:
            errors.append(PlanValidationIssue(code="unknown_replacement", message="被替换活动不属于该旅行", candidate_id=activity.candidate_id))
        if activity.replaces_activity_id in protected:
            original = protected[activity.replaces_activity_id]
            original_day = next(day for day in days if day.id == original.day_plan_id)
            unchanged = (
                activity.day_date == original_day.date
                and activity.place_candidate_id == original.place_candidate_id
                and activity.planned_start_time == original.scheduled_time
                and activity.duration_minutes == original.duration_minutes
                and activity.estimated_cost_fen == original.estimated_cost_fen
            )
            if not unchanged:
                errors.append(PlanValidationIssue(code="protected_activity_changed", message="已完成、进行中或锁定活动不能被调整", candidate_id=activity.candidate_id))
        start = activity.planned_start_time.hour * 60 + activity.planned_start_time.minute
        end = start + activity.duration_minutes
        window_start = preferences.daily_start_time.hour * 60 + preferences.daily_start_time.minute
        window_end = preferences.daily_end_time.hour * 60 + preferences.daily_end_time.minute
        if start < window_start or end > window_end:
            errors.append(PlanValidationIssue(code="outside_daily_window", message="候选活动超出每日可用时间窗", candidate_id=activity.candidate_id))
        intervals[activity.day_date].append((start, end, activity.candidate_id))
        route_nodes[activity.day_date].append(
            (start, end, activity.candidate_id, activity.transport_mode_to_here)
        )
        daily_cost[activity.day_date] += activity.estimated_cost_fen
    represented_protected = {item.replaces_activity_id for item in snapshot.activities}
    final_place_ids = [item.place_candidate_id for item in snapshot.activities]
    for item_id, item in protected.items():
        if item_id in represented_protected:
            continue
        final_place_ids.append(item.place_candidate_id)
        day = next(day for day in days if day.id == item.day_plan_id)
        start = item.scheduled_time.hour * 60 + item.scheduled_time.minute
        intervals[day.date].append((start, start + item.duration_minutes, f"protected:{item.id}"))
        route_nodes[day.date].append(
            (
                start,
                start + item.duration_minutes,
                f"activity:{item.id}",
                day.route_mode,
            )
        )
        if item.status != "skipped":
            daily_cost[day.date] += item.estimated_cost_fen

    if len(final_place_ids) != len(set(final_place_ids)):
        errors.append(PlanValidationIssue(code="duplicate_place", message="同一旅行不能重复安排同一地点"))

    for day_date, items in intervals.items():
        ordered = sorted(items)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[0] < previous[1]:
                errors.append(PlanValidationIssue(code="time_overlap", message=f"{day_date} 存在活动时间重叠", candidate_id=current[2]))
    actual_routes: dict = defaultdict(list)
    for leg in snapshot.route_legs:
        actual_routes[leg.day_date].append(leg)
    for day_date in set(route_nodes) | set(actual_routes):
        ordered_nodes = sorted(route_nodes.get(day_date, []))
        expected_pairs = list(zip(ordered_nodes, ordered_nodes[1:], strict=False))
        ordered_legs = sorted(actual_routes.get(day_date, []), key=lambda leg: leg.position)
        if len(ordered_legs) != len(expected_pairs):
            errors.append(
                PlanValidationIssue(
                    code="candidate_route_set_mismatch",
                    message=f"{day_date} 的候选路线证据不完整",
                )
            )
            continue
        for position, ((origin, destination), leg) in enumerate(
            zip(expected_pairs, ordered_legs, strict=True)
        ):
            if not (
                leg.position == position
                and leg.from_activity_ref == origin[2]
                and leg.to_activity_ref == destination[2]
                and leg.mode == destination[3]
            ):
                errors.append(
                    PlanValidationIssue(
                        code="candidate_route_structure_mismatch",
                        message=f"{day_date} 的候选路线顺序与活动顺序不一致",
                        candidate_id=destination[2],
                    )
                )
                continue
            if destination[0] < origin[1] + leg.duration_minutes:
                required_start = origin[1] + leg.duration_minutes
                errors.append(
                    PlanValidationIssue(
                        code="route_travel_time_conflict",
                        message=(
                            f"{day_date} 的后续活动最早应在 "
                            f"{required_start // 60:02d}:{required_start % 60:02d} 开始"
                        ),
                        candidate_id=destination[2],
                        details={
                            "from_candidate_id": origin[2],
                            "to_candidate_id": destination[2],
                            "route_duration_minutes": leg.duration_minutes,
                            "previous_activity_end_minute": origin[1],
                            "required_start_minute": required_start,
                            "actual_start_minute": destination[0],
                        },
                    )
                )

    for day_date, cost in daily_cost.items():
        if cost > trip.daily_budget_fen:
            errors.append(PlanValidationIssue(code="daily_budget_exceeded", message=f"{day_date} 的预计费用超过每日预算"))
    if sum(daily_cost.values()) > trip.total_budget_fen:
        errors.append(PlanValidationIssue(code="total_budget_exceeded", message="候选计划预计费用超过总预算"))
    return PlanValidationResult(valid=not errors, errors=errors, warnings=[])


async def accept_plan_revision(
    session: AsyncSession, revision_id: uuid.UUID
) -> PlanRevision:
    revision = await session.scalar(
        select(PlanRevision).where(PlanRevision.id == revision_id).with_for_update()
    )
    if revision is None:
        raise PlanRevisionNotFoundError
    if revision.status == "accepted":
        return revision
    if revision.status != "pending":
        raise InvalidPlanningRunStateError
    run = await session.scalar(
        select(PlanningRun).where(PlanningRun.id == revision.planning_run_id).with_for_update()
    )
    trip = await session.scalar(select(Trip).where(Trip.id == revision.trip_id).with_for_update())
    if run is None or trip is None:
        raise PlanRevisionNotFoundError
    if trip.version != run.base_trip_version:
        raise StalePlanningRunError
    snapshot = CandidatePlanSnapshot.model_validate(revision.proposed_snapshot)
    result = await validate_candidate_plan(session, trip.id, snapshot)
    revision.validation_result = result.model_dump(mode="json")
    if not result.valid:
        await session.rollback()
        raise InvalidPlanRevisionError(result)

    days = list((await session.scalars(select(DayPlan).where(DayPlan.trip_id == trip.id))).all())
    day_by_date = {day.date: day for day in days}
    existing = list((await session.scalars(select(Activity).join(DayPlan).where(DayPlan.trip_id == trip.id))).all())
    existing_by_id = {item.id: item for item in existing}
    protected_ids = {item.id for item in existing if item.schedule_locked or item.status in {"active", "completed"}}
    replaced_ids = {item.replaces_activity_id for item in snapshot.activities if item.replaces_activity_id}

    await session.execute(delete(RouteLeg).where(RouteLeg.day_plan_id.in_([day.id for day in days])))
    for temporary_index, item in enumerate(existing):
        if item.id not in protected_ids and item.id not in replaced_ids:
            await session.delete(item)
        else:
            item.position = 10_000 + temporary_index
    await session.flush()

    activities_by_day: dict = defaultdict(list)
    activities_by_ref: dict[str, Activity] = {}
    for item in existing:
        if item.id in protected_ids and item.id not in replaced_ids:
            day = next(day for day in days if day.id == item.day_plan_id)
            activities_by_day[day.date].append(item)
            activities_by_ref[f"activity:{item.id}"] = item
    for candidate_index, candidate in enumerate(snapshot.activities):
        activity = existing_by_id.get(candidate.replaces_activity_id) if candidate.replaces_activity_id else None
        if activity is None:
            activity = Activity(
                day_plan_id=day_by_date[candidate.day_date].id,
                place_candidate_id=candidate.place_candidate_id,
                scheduled_time=candidate.planned_start_time,
                duration_minutes=candidate.duration_minutes,
                estimated_cost_fen=candidate.estimated_cost_fen,
                status="planned",
                position=20_000 + candidate_index,
                schedule_locked=candidate.locked,
                note=candidate.reason or None,
            )
            session.add(activity)
        elif activity.id not in protected_ids:
            activity.day_plan_id = day_by_date[candidate.day_date].id
            activity.place_candidate_id = candidate.place_candidate_id
            activity.scheduled_time = candidate.planned_start_time
            activity.duration_minutes = candidate.duration_minutes
            activity.estimated_cost_fen = candidate.estimated_cost_fen
            activity.status = "planned"
            activity.schedule_locked = candidate.locked
            activity.version += 1
        activities_by_day[candidate.day_date].append(activity)
        activities_by_ref[candidate.candidate_id] = activity
    await session.flush()
    for day_date, activities in activities_by_day.items():
        for position, activity in enumerate(sorted(activities, key=lambda value: value.scheduled_time)):
            activity.position = position
    await session.flush()
    for leg in snapshot.route_legs:
        session.add(
            RouteLeg(
                day_plan_id=day_by_date[leg.day_date].id,
                from_activity_id=activities_by_ref[leg.from_activity_ref].id,
                to_activity_id=activities_by_ref[leg.to_activity_ref].id,
                position=leg.position,
                mode=leg.mode,
                distance_meters=leg.distance_meters,
                duration_minutes=leg.duration_minutes,
                provider=leg.provider,
                is_estimated=leg.is_estimated,
                path=[list(point) for point in leg.path],
                alternatives=[item.model_dump(mode="json") for item in leg.alternatives],
                calculated_at=leg.calculated_at,
            )
        )

    decided_at = datetime.now(UTC)
    trip.version += 1
    revision.status = "accepted"
    revision.decided_at = decided_at
    run.status = "accepted"
    run.completed_at = decided_at
    await session.commit()
    await session.refresh(revision)
    return revision
