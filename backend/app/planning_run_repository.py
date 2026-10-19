import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidate_route_service import enrich_candidate_routes
from app.database import CandidateRouteLeg, PlanningRun, PlanRevision, TripDisruptionEvent
from app.repository import get_trip
from app.travel_goal_router import route_travel_goal
from app.requirements import valid_records
from app.repository import get_trip_preferences
from app.planning_intent_service import (
    SemanticIntentProvider,
    UnsupportedPlanningIntentError,
    resolve_planning_intent,
)
from app.schemas import (
    CandidatePlanSnapshot,
    PlanningIntentParseRequest,
    PlanningRunCreate,
)


class PlanningRunNotFoundError(Exception):
    pass


class PlanRevisionNotFoundError(Exception):
    pass


class InvalidPlanningRunStateError(Exception):
    pass


class StalePlanningRunError(Exception):
    pass


class RecoveryPlanningConflictError(Exception):
    """A live recovery run already owns this unresolved disruption."""
    pass


async def create_planning_run(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: PlanningRunCreate,
    *,
    semantic_provider: SemanticIntentProvider | None = None,
    commit: bool = True,
    trigger_type: str | None = None,
    trigger_key: str | None = None,
    trigger_snapshot: dict | None = None,
    trigger_fingerprint: str | None = None,
) -> PlanningRun:
    await get_trip(session, trip_id)
    from app.formal_write import lock_trip
    trip = await lock_trip(session, trip_id)
    disruption = None
    if payload.disruption_event_id is not None:
        if payload.run_type != "replan":
            raise RecoveryPlanningConflictError("a disruption can only trigger a replan")
        disruption = await session.scalar(
            select(TripDisruptionEvent).where(TripDisruptionEvent.id == payload.disruption_event_id).with_for_update()
        )
        if disruption is None or disruption.trip_id != trip_id or disruption.status != "active":
            raise RecoveryPlanningConflictError("disruption is not an active fact for this trip")
        if disruption.itinerary_version != trip.version:
            raise StalePlanningRunError("disruption belongs to an older itinerary")
    # Explicit API selection does not authorize turning a question into a run.
    # Persisted disruption/experience facts retain their deterministic authority.
    if disruption is None and trigger_type is None:
        goal = route_travel_goal(payload.user_request)
        if goal.target_runtime == "execution" or (goal.target_runtime == "companion" and goal.confidence >= 0.9):
            raise UnsupportedPlanningIntentError(
                goal.target_runtime,
                "这条请求不需要生成规划任务。旅行问答请使用旅行助手；停留和离开操作请使用活动执行卡片。",
            )
    resolution = await resolve_planning_intent(
        session,
        trip_id,
        PlanningIntentParseRequest(
            message=payload.user_request,
            entry_point=payload.entry_point,
            selected_day_id=payload.selected_day_id,
            selected_activity_id=payload.selected_activity_id,
        ),
        semantic_provider=semantic_provider,
        default_planning_intent=(
            "create_plan" if payload.run_type == "initial_plan" else "replan_trip"
        ),
    )
    route = resolution.policy_decision.route if resolution.policy_decision else None
    if route == "answer" and disruption is None and trigger_type is None:
        raise UnsupportedPlanningIntentError("companion", "旅行问答请使用旅行助手，不需要生成规划任务。")
    # The structured disruption, rather than incidental natural-language
    # wording, authorizes the recovery planning route.  The graph will still
    # resolve and persist an intent before model invocation.
    if route not in {"plan_preview", "clarify", "answer"} and disruption is None and trigger_type is None:
        raise UnsupportedPlanningIntentError(
            route or "reject",
            "我还不确定你希望我完成什么。可以问现有行程、路线或预算，也可以明确说明要修改哪部分；订票和删除整趟旅行请使用相应服务或页面。",
        )
    automatic_trigger_type = trigger_type or ("navigation_disruption" if disruption else None)
    preferences = await get_trip_preferences(session, trip_id)
    trigger_snapshot = {**(trigger_snapshot or {}), "effective_requirements":
        valid_records(getattr(preferences, "requirement_records", []))}
    run = PlanningRun(
        trip_id=trip_id,
        run_type=payload.run_type,
        status="queued",
        user_request=payload.user_request,
        entry_point=payload.entry_point,
        selected_day_id=payload.selected_day_id,
        selected_activity_id=payload.selected_activity_id,
        intent_resolution=resolution.model_dump(mode="json"),
        base_trip_version=trip.version,
        disruption_event_id=disruption.id if disruption else None,
        trigger_type=automatic_trigger_type,
        trigger_key=trigger_key,
        trigger_snapshot=trigger_snapshot,
        trigger_fingerprint=trigger_fingerprint,
    )
    session.add(run)
    try:
        if commit:
            await session.commit()
        else:
            await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if payload.disruption_event_id is not None or trigger_key is not None:
            raise RecoveryPlanningConflictError("an active recovery run already exists") from exc
        raise
    await session.refresh(run)
    return run


async def get_planning_run(session: AsyncSession, run_id: uuid.UUID) -> PlanningRun:
    run = await session.get(PlanningRun, run_id)
    if run is None:
        raise PlanningRunNotFoundError
    return run


async def list_planning_runs(
    session: AsyncSession, trip_id: uuid.UUID, *, limit: int = 20
) -> list[PlanningRun]:
    await get_trip(session, trip_id)
    return list(
        (
            await session.scalars(
                select(PlanningRun)
                .where(PlanningRun.trip_id == trip_id)
                .order_by(PlanningRun.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def get_latest_revision(
    session: AsyncSession, run_id: uuid.UUID
) -> PlanRevision:
    await get_planning_run(session, run_id)
    revision = await session.scalar(
        select(PlanRevision)
        .where(PlanRevision.planning_run_id == run_id)
        .order_by(PlanRevision.revision_number.desc())
        .limit(1)
    )
    if revision is None:
        raise PlanRevisionNotFoundError
    return revision


async def save_plan_revision(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    before_snapshot: dict,
    proposed_snapshot: CandidatePlanSnapshot,
    reason: str,
    difference_summary: dict,
    validation_result: dict,
    source_ids: list[uuid.UUID],
    enrich_routes: bool = True,
    commit: bool = True,
) -> PlanRevision:
    run = await get_planning_run(session, run_id)
    from app.formal_write import lock_trip
    trip = await lock_trip(session, run.trip_id)
    run = await session.scalar(select(PlanningRun).where(PlanningRun.id == run_id).with_for_update().execution_options(populate_existing=True))
    if run.status not in {"queued", "researching", "planning", "validating"}:
        raise InvalidPlanningRunStateError
    if trip.version != run.base_trip_version:
        raise StalePlanningRunError
    if enrich_routes:
        proposed_snapshot = await enrich_candidate_routes(
            session, run.trip_id, proposed_snapshot,
            enforce_execution_invariants=bool(run.disruption_event_id or run.trigger_type == "experience_impact"),
        )

    previous = await session.scalar(
        select(PlanRevision)
        .where(
            PlanRevision.planning_run_id == run_id,
            PlanRevision.status == "pending",
        )
        .order_by(PlanRevision.revision_number.desc())
        .limit(1)
    )
    if previous is not None:
        previous.status = "superseded"
    next_number = int(
        await session.scalar(
            select(func.coalesce(func.max(PlanRevision.revision_number), 0)).where(
                PlanRevision.planning_run_id == run_id
            )
        )
        or 0
    ) + 1
    revision = PlanRevision(
        planning_run_id=run_id,
        trip_id=run.trip_id,
        revision_number=next_number,
        reason=reason.strip(),
        before_snapshot=before_snapshot,
        proposed_snapshot=proposed_snapshot.model_dump(mode="json"),
        difference_summary=difference_summary,
        validation_result=validation_result,
        source_ids=[str(source_id) for source_id in source_ids],
        status="pending",
    )
    session.add(revision)
    await session.flush()
    for leg in proposed_snapshot.route_legs:
        session.add(
            CandidateRouteLeg(
                plan_revision_id=revision.id,
                day_date=leg.day_date,
                from_activity_ref=leg.from_activity_ref,
                to_activity_ref=leg.to_activity_ref,
                position=leg.position,
                mode=leg.mode,
                distance_meters=leg.distance_meters,
                duration_minutes=leg.duration_minutes,
                provider=leg.provider,
                is_estimated=leg.is_estimated,
                path=leg.path,
                alternatives=[item.model_dump(mode="json") for item in leg.alternatives],
                calculated_at=leg.calculated_at,
            )
        )
    run.status = "awaiting_confirmation"
    if commit:
        await session.commit()
        await session.refresh(revision)
    else:
        await session.flush()
    return revision


async def reject_revision(
    session: AsyncSession, revision_id: uuid.UUID, *,
    reason_code: str | None = None, reason_text: str | None = None,
) -> PlanRevision:
    from app.formal_write import lock_trip
    trip_id = await session.scalar(select(PlanRevision.trip_id).where(PlanRevision.id == revision_id))
    if trip_id is None:
        raise PlanRevisionNotFoundError
    await lock_trip(session, trip_id)
    revision = await session.scalar(select(PlanRevision).where(PlanRevision.id == revision_id).with_for_update().execution_options(populate_existing=True))
    if revision is None:
        raise PlanRevisionNotFoundError
    if revision.status != "pending":
        raise InvalidPlanningRunStateError
    run = await get_planning_run(session, revision.planning_run_id)
    if run.trigger_type == "draft_promotion":
        # Promotion cancellation shares the operation lock with authorization
        # consumption. The legacy reject endpoint cannot overwrite accepted
        # facts after reading an earlier pending revision.
        raise InvalidPlanningRunStateError("请通过草稿转换操作撤回授权")
    revision.status = "rejected"
    revision.rejection_reason_code = reason_code
    revision.rejection_reason_text = reason_text
    revision.decided_at = datetime.now(UTC)
    run.status = "rejected"
    snapshot = dict(run.trigger_snapshot or {})
    snapshot["decision_memory_feedback"] = {
        "persisted": bool(reason_code or reason_text),
        "source_revision_id": str(revision.id),
        "reason_code": reason_code,
        "reason_text_present": bool(reason_text),
    }
    run.trigger_snapshot = snapshot
    run.pending_interrupt = None
    run.completed_at = revision.decided_at
    await session.commit()
    await session.refresh(revision)
    return revision
