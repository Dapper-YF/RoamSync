import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

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
    TripExecution,
    ActivityExecution,
    NavigationSession,
    TripDisruptionEvent,
)
from app.planning_run_repository import (
    InvalidPlanningRunStateError,
    PlanRevisionNotFoundError,
    StalePlanningRunError,
)
from app.repository import get_budget, get_trip_preferences
from app.schemas import (
    CandidatePlanSnapshot,
    PlanningIntentResolution,
    PlanValidationIssue,
    PlanValidationResult,
)
from app.navigation.session_service import supersede_navigation_sessions_for_itinerary
from app.trip_execution_service import projected_activity_end, total_extension_minutes


async def _execution_immutable_activity_ids(session: AsyncSession, trip_id: uuid.UUID) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Return frozen history and protected present facts for the formal trip."""
    execution = await session.scalar(select(TripExecution).where(TripExecution.trip_id == trip_id))
    if execution is None:
        return set(), set()
    rows = list((await session.scalars(select(ActivityExecution).where(ActivityExecution.trip_execution_id == execution.id))).all())
    frozen = {row.activity_id for row in rows if row.status in {"completed", "skipped"} or row.actual_ended_at is not None}
    protected = {row.activity_id for row in rows if row.status in {"arrived", "in_progress"} or row.actual_started_at is not None}
    if execution.current_activity_id:
        protected.add(execution.current_activity_id)
    navigation = await session.scalar(select(NavigationSession).where(
        NavigationSession.trip_execution_id == execution.id,
        NavigationSession.status.in_(("active", "rerouting")),
    ))
    if navigation:
        protected.add(navigation.to_activity_id)
    return frozen, protected - frozen


class InvalidPlanRevisionError(Exception):
    def __init__(self, result: PlanValidationResult):
        self.result = result
        super().__init__("candidate plan failed deterministic validation")


async def validate_candidate_plan(
    session: AsyncSession,
    trip_id: uuid.UUID,
    snapshot: CandidatePlanSnapshot,
    *,
    intent_resolution: PlanningIntentResolution | None = None,
    required_dates: set[date] | None = None,
    enforce_execution_invariants: bool = False,
) -> PlanValidationResult:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise PlanRevisionNotFoundError
    preferences = await get_trip_preferences(session, trip_id)
    actual_budget = await get_budget(session, trip_id)
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
    day_by_id = {day.id: day for day in days}
    frozen_execution, protected_execution = (await _execution_immutable_activity_ids(session, trip_id)) if enforce_execution_invariants else (set(), set())
    authoritative_boundary = None
    current_execution_activity_id = None
    if enforce_execution_invariants:
        execution = await session.scalar(select(TripExecution).where(TripExecution.trip_id == trip_id))
        if execution and execution.current_activity_id:
            current_execution_activity_id = execution.current_activity_id
            state = await session.scalar(select(ActivityExecution).where(
                ActivityExecution.trip_execution_id == execution.id,
                ActivityExecution.activity_id == current_execution_activity_id,
            ))
            current_formal = existing_by_id.get(current_execution_activity_id)
            if state and current_formal and state.status == "in_progress":
                authoritative_boundary = projected_activity_end(
                    state, current_formal.duration_minutes,
                    await total_extension_minutes(session, state.id),
                )
    protected = {
        item.id: item
        for item in existing
        if item.schedule_locked or item.status in {"active", "completed", "skipped"}
        or item.id in frozen_execution or item.id in protected_execution
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
    missing_dates = (required_dates or set()) - {item.day_date for item in snapshot.activities}
    if missing_dates:
        errors.append(PlanValidationIssue(
            code="missing_plan_days",
            message="以下日期尚未安排行程：" + "、".join(day.isoformat() for day in sorted(missing_dates)),
            details={"missing_dates": [day.isoformat() for day in sorted(missing_dates)]},
        ))
    intervals: dict = defaultdict(list)
    route_nodes: dict = defaultdict(list)
    daily_cost: dict = defaultdict(int)

    replacement_ids = [
        item.replaces_activity_id
        for item in snapshot.activities
        if item.replaces_activity_id is not None
    ]
    if len(replacement_ids) != len(set(replacement_ids)):
        errors.append(
            PlanValidationIssue(
                code="duplicate_activity_replacement",
                message="同一个现有活动不能在候选计划中被替换多次",
            )
        )
    candidate_by_replacement = {
        item.replaces_activity_id: item
        for item in snapshot.activities
        if item.replaces_activity_id is not None
    }
    for original in existing:
        if original.id in protected:
            # Protected activities are implicitly retained by the delta snapshot.
            continue
        candidate = candidate_by_replacement.get(original.id)
        same_place = candidate is not None and candidate.place_candidate_id == original.place_candidate_id
        if not same_place:
            if original.importance == "must_do":
                errors.append(PlanValidationIssue(
                    code="activity_must_do_removed",
                    message="必去活动不能从候选行程中移除或替换地点",
                    details={"activity_id": str(original.id)},
                ))
            elif not original.can_skip:
                errors.append(PlanValidationIssue(
                    code="activity_cannot_be_skipped",
                    message="不可跳过的活动不能从候选行程中移除或替换地点",
                    details={"activity_id": str(original.id)},
                ))
        elif original.minimum_duration_minutes is not None and candidate.duration_minutes < original.minimum_duration_minutes:
            errors.append(PlanValidationIssue(
                code="activity_minimum_duration_violated",
                message="候选停留时间低于活动的最短体验要求",
                candidate_id=candidate.candidate_id,
                details={
                    "activity_id": str(original.id),
                    "minimum_duration_minutes": original.minimum_duration_minutes,
                    "candidate_duration_minutes": candidate.duration_minutes,
                },
            ))
    grounded_intent = (
        intent_resolution.grounded_intent if intent_resolution is not None else None
    )
    operation_types = set(grounded_intent.operation_types) if grounded_intent else set()
    local_operations = {
        "replan_trip",
        "add_activity",
        "remove_activity",
        "replace_activity",
        "reorder_activities",
        "optimize_route",
        "adjust_budget",
        "weather_replan",
    }
    target_day_ids = set(grounded_intent.target_day_ids) if grounded_intent else set()
    target_activity_ids = (
        set(grounded_intent.target_activity_ids) if grounded_intent else set()
    )
    explicit_activity_scope = bool(
        target_activity_ids
        and operation_types & {"remove_activity", "replace_activity", "reorder_activities"}
    )
    scoped_day_dates = {
        day_by_id[day_id].date for day_id in target_day_ids if day_id in day_by_id
    }

    def candidate_matches_existing(candidate, original: Activity) -> bool:
        original_day = day_by_id[original.day_plan_id]
        return bool(
            candidate.day_date == original_day.date
            and candidate.place_candidate_id == original.place_candidate_id
            and candidate.planned_start_time == original.scheduled_time
            and candidate.duration_minutes == original.duration_minutes
            and candidate.estimated_cost_fen == original.estimated_cost_fen
        )

    if grounded_intent is not None and operation_types & local_operations:
        for original in existing:
            outside_scope = (
                explicit_activity_scope and original.id not in target_activity_ids
            ) or (
                not explicit_activity_scope
                and bool(scoped_day_dates)
                and day_by_id[original.day_plan_id].date not in scoped_day_dates
            )
            if not outside_scope or original.id in protected:
                continue
            candidate = candidate_by_replacement.get(original.id)
            if candidate is None:
                errors.append(
                    PlanValidationIssue(
                        code="intent_scope_activity_omitted",
                        message="候选计划删除了意图作用范围之外的活动",
                        details={"activity_id": str(original.id)},
                    )
                )
            elif not candidate_matches_existing(candidate, original):
                errors.append(
                    PlanValidationIssue(
                        code="intent_scope_activity_changed",
                        message="候选计划修改了意图作用范围之外的活动",
                        candidate_id=candidate.candidate_id,
                        details={"activity_id": str(original.id)},
                    )
                )
        if scoped_day_dates:
            for candidate in snapshot.activities:
                if (
                    candidate.replaces_activity_id is None
                    and candidate.day_date not in scoped_day_dates
                ):
                    errors.append(
                        PlanValidationIssue(
                            code="intent_scope_new_activity_outside_target",
                            message="候选计划在目标日期之外新增了活动",
                            candidate_id=candidate.candidate_id,
                        )
                    )

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
                errors.append(PlanValidationIssue(code="execution_activity_changed", message="已发生、进行中、导航目标或锁定活动不能被调整", candidate_id=activity.candidate_id,
                    details={"activity_id": str(activity.replaces_activity_id)}))
        start = activity.planned_start_time.hour * 60 + activity.planned_start_time.minute
        end = start + activity.duration_minutes
        if authoritative_boundary is not None and activity.replaces_activity_id != current_execution_activity_id:
            candidate_start = datetime.combine(activity.day_date, activity.planned_start_time, tzinfo=ZoneInfo(trip.timezone))
            if candidate_start < authoritative_boundary:
                errors.append(PlanValidationIssue(
                    code="execution_authoritative_boundary_conflict",
                    message="后续活动不能早于当前体验的真实结束边界开始",
                    candidate_id=activity.candidate_id,
                    details={"authoritative_boundary": authoritative_boundary.isoformat(), "candidate_start": candidate_start.isoformat()},
                ))
        window_start = preferences.daily_start_time.hour * 60 + preferences.daily_start_time.minute
        window_end = preferences.daily_end_time.hour * 60 + preferences.daily_end_time.minute
        if start < window_start or end > window_end:
            errors.append(PlanValidationIssue(
                code="outside_daily_window",
                message=f"{activity.day_date} 的{place.name if place else '活动'}安排在 {start // 60:02d}:{start % 60:02d}–{end // 60:02d}:{end % 60:02d}，超出每日 {window_start // 60:02d}:{window_start % 60:02d}–{window_end // 60:02d}:{window_end % 60:02d} 的可用时间",
                candidate_id=activity.candidate_id,
                details={"day_date": activity.day_date.isoformat(), "place_name": place.name if place else None,
                         "actual_start_minute": start, "actual_end_minute": end,
                         "window_start_minute": window_start, "window_end_minute": window_end,
                         "latest_start_minute": window_end - activity.duration_minutes},
            ))
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
        if item_id in target_activity_ids and "remove_activity" in operation_types:
            errors.append(PlanValidationIssue(
                code="execution_activity_changed",
                message="已发生、进行中、导航目标或锁定活动不能被删除",
                details={"activity_id": str(item_id)},
            ))
            continue
        # Candidate snapshots are deltas: absence means retention for a
        # protected fact.  There is no "delete by omission" operation here.
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

    if grounded_intent is not None and grounded_intent.constraints.requested_pace == "relaxed":
        original_counts: dict[date, int] = defaultdict(int)
        proposed_counts: dict[date, int] = defaultdict(int)
        for item in existing:
            if item.status != "skipped":
                original_counts[day_by_id[item.day_plan_id].date] += 1
        for item in snapshot.activities:
            proposed_counts[item.day_date] += 1
        for activity_id, item in protected.items():
            if activity_id not in candidate_by_replacement and item.status != "skipped":
                proposed_counts[day_by_id[item.day_plan_id].date] += 1
        for day_date, before_count in original_counts.items():
            if scoped_day_dates and day_date not in scoped_day_dates:
                continue
            after_count = proposed_counts[day_date]
            if after_count > before_count:
                errors.append(PlanValidationIssue(
                    code="relaxed_pace_increased_stops",
                    message=f"{day_date} 要求更轻松，但地点数量从 {before_count} 项增加到了 {after_count} 项。",
                    details={"day_date": day_date.isoformat(), "before_count": before_count, "proposed_count": after_count},
                ))

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

    planned_total = sum(daily_cost.values())
    for day_date, cost in daily_cost.items():
        if trip.daily_budget_fen is not None and cost > trip.daily_budget_fen:
            errors.append(PlanValidationIssue(code="daily_budget_exceeded", message=f"{day_date} 的预计费用超过每日预算"))
    if trip.total_budget_fen is not None and planned_total > trip.total_budget_fen:
        errors.append(
            PlanValidationIssue(
                code="total_budget_exceeded",
                message="候选计划预计费用超过总预算",
                details={
                    "planned_fen": planned_total,
                    "total_budget_fen": trip.total_budget_fen,
                    "overage_fen": planned_total - trip.total_budget_fen,
                },
            )
        )
    if trip.total_budget_fen is not None and actual_budget.total_spent_fen + planned_total > trip.total_budget_fen:
        errors.append(
            PlanValidationIssue(
                code="total_budget_with_actual_spend_exceeded",
                message="已发生消费与候选行程费用合计超过总预算",
                details={
                    "actual_spent_fen": actual_budget.total_spent_fen,
                    "planned_fen": planned_total,
                    "total_budget_fen": trip.total_budget_fen,
                    "overage_fen": actual_budget.total_spent_fen + planned_total - trip.total_budget_fen,
                },
            )
        )
    if grounded_intent is not None and grounded_intent.constraints.budget_must_not_increase:
        original_cost = sum(
            item.estimated_cost_fen for item in existing if item.status != "skipped"
        )
        proposed_cost = sum(daily_cost.values())
        if proposed_cost > original_cost:
            errors.append(
                PlanValidationIssue(
                    code="intent_budget_increase_forbidden",
                    message="用户要求预算不增加，但候选计划的预计费用更高",
                    details={
                        "original_cost_fen": original_cost,
                        "proposed_cost_fen": proposed_cost,
                    },
                )
            )
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
    if run.trigger_type == "experience_impact":
        from app.database import ActivityExecution
        from app.experience_replanning_service import _snapshot
        from app.activity_experience_impact import evaluate_activity_experience_time_impact
        trigger = run.trigger_snapshot or {}
        try:
            activity_execution_id = uuid.UUID(str(trigger["activity_execution_id"]))
        except (KeyError, ValueError):
            raise StalePlanningRunError
        activity_execution = await session.get(ActivityExecution, activity_execution_id)
        execution = await session.get(TripExecution, activity_execution.trip_execution_id) if activity_execution else None
        impact = (
            await evaluate_activity_experience_time_impact(session, execution.id, activity_execution.id)
            if activity_execution is not None and execution is not None else None
        )
        if activity_execution is None or execution is None or impact is None or (
            await _snapshot(session, execution, activity_execution, impact.model_dump(mode="json"))
        ).get("fingerprint") != trigger.get("fingerprint"):
            raise StalePlanningRunError
    snapshot = CandidatePlanSnapshot.model_validate(revision.proposed_snapshot)
    result = await validate_candidate_plan(
        session,
        trip.id,
        snapshot,
        required_dates={date.fromisoformat(value) for value in revision.difference_summary.get("required_day_dates", [])},
        intent_resolution=(
            PlanningIntentResolution.model_validate(run.intent_resolution)
            if run.intent_resolution is not None
            else None
        ),
        enforce_execution_invariants=run.disruption_event_id is not None or run.trigger_type == "experience_impact",
    )
    revision.validation_result = result.model_dump(mode="json")
    if not result.valid:
        await session.rollback()
        raise InvalidPlanRevisionError(result)

    days = list((await session.scalars(select(DayPlan).where(DayPlan.trip_id == trip.id))).all())
    day_by_date = {day.date: day for day in days}
    existing = list((await session.scalars(select(Activity).join(DayPlan).where(DayPlan.trip_id == trip.id))).all())
    existing_by_id = {item.id: item for item in existing}
    frozen_execution, protected_execution = (await _execution_immutable_activity_ids(session, trip.id)) if (run.disruption_event_id is not None or run.trigger_type == "experience_impact") else (set(), set())
    protected_ids = {item.id for item in existing if item.schedule_locked or item.status in {"active", "completed", "skipped"} or item.id in frozen_execution or item.id in protected_execution}
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
    # RouteLeg rows are recreated below/above as part of applying a candidate.
    # A live runtime projection must never keep accepting writes for the old
    # itinerary version after this transaction commits.
    await supersede_navigation_sessions_for_itinerary(session, trip.id, trip.version)
    trip.version += 1
    if run.trigger_type == "experience_impact":
        execution = await session.scalar(select(TripExecution).where(TripExecution.trip_id == trip.id).with_for_update())
        if execution is not None:
            execution.itinerary_version = trip.version
    revision.status = "accepted"
    revision.decided_at = decided_at
    run.status = "accepted"
    run.completed_at = decided_at
    if run.disruption_event_id is not None:
        disruption = await session.scalar(select(TripDisruptionEvent).where(
            TripDisruptionEvent.id == run.disruption_event_id
        ).with_for_update())
        # The event and the candidate are fenced by the same formal version.
        if disruption is None or disruption.status != "active" or disruption.itinerary_version != run.base_trip_version:
            await session.rollback()
            raise StalePlanningRunError
        disruption.status = "resolved"
        disruption.resolution_plan_revision_id = revision.id
        disruption.resolution_planning_run_id = run.id
    await session.commit()
    await session.refresh(revision)
    return revision
