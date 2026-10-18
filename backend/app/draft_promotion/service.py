import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.database import PlanRevision, PlanningRun, Trip, TripPreferences
from app.requirements import promote_requirements
from app.drafts.repository import DraftError
from app.plan_revision_service import InvalidPlanRevisionError, accept_plan_revision, validate_candidate_plan
from app.planning_run_repository import InvalidPlanningRunStateError, StalePlanningRunError, save_plan_revision
from app.repository import create_trip
from app.schemas import TripCreate
from .contracts import Operation, PromotionError
from .guard import _CAPABILITY, locked_draft
from .materialize import add_places, snapshot_for
from .preparation import digest, prepare, refresh_equivalent, valid_hashes
from .repository import get_operation, get_prepared, prepared_plans, promotions, save_operation


class DraftPromotionService:
    """Awaited coordinator with durable T1/T2/T3 checkpoints and explicit retry.

    D injects the same DB async_sessionmaker as formal services. Network calls
    happen only outside transactions. No background Planner task is queued.
    """
    def __init__(self, draft_repository, async_session_factory, place_content_service):
        self.drafts = draft_repository
        self.sessions = async_session_factory
        self.places = place_content_service

    async def preview(self, owner, draft_id, request):
        try:
            draft = await asyncio.to_thread(self.drafts.get, owner, draft_id)
        except DraftError as exc:
            raise PromotionError(exc.code, "草稿不存在。", exc.status) from None
        if draft.version != request.expected_version or draft.status != "active" or any(r.status == "running" for r in draft.runs):
            raise PromotionError("draft_changed", "草稿已变化或仍在生成，请刷新后重新准备。")
        if request.operation_id:
            operation = await self.get(owner, request.operation_id)
            if operation.draft_id != draft_id or operation.status not in {"needs_review", "failed"} or operation.consumed_at or operation.revoked_at:
                raise PromotionError("review_unavailable", "此转换不能重新确认，请检查其状态。")
        plan = await prepare(draft, request, self.places)
        if len(plan.requirements) > 2000:
            plan.coverage.blockers.append("旅行要求超过正式偏好支持的2000字，请缩短要求后重新准备；不会截断采用。")
            from .preparation import bind_hashes
            bind_hashes(plan)
        if len(plan.activities) > 100:
            plan.coverage.blockers.append("活动超过正式候选上限100项，请减少草稿活动。")
            from .preparation import bind_hashes
            bind_hashes(plan)
        async with self.sessions() as session, session.begin():
            await locked_draft(session, owner, draft_id, draft.version)
            await session.execute(prepared_plans.insert().values(id=str(plan.id), owner_id=owner, snapshot=plan.model_dump(mode="json")))
        return plan

    async def get(self, owner, operation_id):
        async with self.sessions() as session:
            operation, _ = await get_operation(session, owner, operation_id)
            return operation

    async def list(self, owner, draft_id):
        # Verify the draft owner even when the result is empty.
        await asyncio.to_thread(self.drafts.get, owner, draft_id)
        async with self.sessions() as session:
            rows = (await session.execute(select(promotions.c.snapshot).where(promotions.c.owner_id == owner))).all()
        return sorted([op for row in rows if (op := Operation.model_validate(row[0])).draft_id == draft_id], key=lambda op: op.updated_at, reverse=True)

    @staticmethod
    def _check_plan(plan, request):
        if not valid_hashes(plan) or request.prepared_hash != plan.prepared_hash:
            raise PromotionError("prepared_hash_mismatch", "确认内容与显示方案不一致，请重新准备。")
        if plan.expires_at <= datetime.now(UTC):
            raise PromotionError("prepared_expired", "方案已过期，请重新准备并确认。")
        if request.action == "create_and_adopt" and plan.coverage.blockers:
            raise PromotionError("preview_blocked", "方案存在阻塞，请先处理预备方案中的提示。")

    async def confirm(self, owner, request):
        request_hash = digest(request.model_dump(mode="json"))
        try:
            async with self.sessions() as session, session.begin():
                existing = (await session.execute(select(promotions).where(promotions.c.owner_id == owner,
                    promotions.c.request_id == str(request.request_id)).with_for_update())).mappings().first()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise PromotionError("idempotency_key_reused", "同一操作编号不能提交不同内容。")
                    return Operation.model_validate(existing["snapshot"])
                plan = await get_prepared(session, owner, request.prepared_id)
                self._check_plan(plan, request)
                if plan.operation_id:
                    raise PromotionError("review_confirmation_required", "请在原转换操作中重新确认。")
                await locked_draft(session, owner, plan.draft_id, plan.draft_version)
                # A lost confirmation response must not authorize another Trip from
                # the same displayed prepared plan under a new browser request ID.
                # The existing draft lock serializes all competing confirmations.
                previous = (await session.execute(select(promotions.c.snapshot).where(
                    promotions.c.owner_id == owner,
                    promotions.c.snapshot["prepared_id"].as_string() == str(plan.id)))).first()
                if previous:
                    operation = Operation.model_validate(previous[0])
                    if operation.allowed_action != request.action:
                        raise PromotionError("prepared_already_authorized", "这份方案已确认过另一种操作，请恢复原确认进度，不能重复创建旅行。")
                    return operation
                now = datetime.now(UTC)
                operation = Operation(id=uuid4(), draft_id=plan.draft_id, draft_version=plan.draft_version,
                    prepared_id=plan.id, prepared_hash=plan.prepared_hash, content_hash=plan.content_hash,
                    evidence_hash=plan.evidence_hash, allowed_action=request.action, status="requested", stage="authorized",
                    authorized_at=now, expires_at=plan.expires_at, updated_at=now)
                await session.execute(promotions.insert().values(id=str(operation.id), owner_id=owner,
                    request_id=str(request.request_id), request_hash=request_hash, version=1,
                    snapshot=operation.model_dump(mode="json"), confirmation_keys={}))
                return operation
        except IntegrityError:
            # A concurrent same-key INSERT either committed one whole operation or none.
            async with self.sessions() as session:
                row = (await session.execute(select(promotions).where(promotions.c.owner_id == owner,
                    promotions.c.request_id == str(request.request_id)))).mappings().first()
                if row is None or row["request_hash"] != request_hash:
                    raise PromotionError("idempotency_key_reused", "操作编号已使用，请刷新转换状态。") from None
                return Operation.model_validate(row["snapshot"])

    async def review(self, owner, operation_id, request):
        request_hash = digest(request.model_dump(mode="json"))
        async with self.sessions() as session, session.begin():
            op, row = await get_operation(session, owner, operation_id, lock=True)
            keys = dict(row["confirmation_keys"])
            key = str(request.request_id)
            if key == row["request_id"]:
                raise PromotionError("idempotency_key_reused", "重新确认必须使用新的操作编号。")
            if key in keys:
                if keys[key] != request_hash:
                    raise PromotionError("idempotency_key_reused", "同一操作编号不能提交不同内容。")
                return op
            if op.status not in {"needs_review", "failed"} or op.revoked_at or op.consumed_at:
                raise PromotionError("review_unavailable", "当前转换不能重新确认。")
            plan = await get_prepared(session, owner, request.prepared_id)
            self._check_plan(plan, request)
            if plan.operation_id != op.id or plan.draft_id != op.draft_id:
                raise PromotionError("review_binding_mismatch", "新方案不属于当前转换。")
            await locked_draft(session, owner, plan.draft_id, plan.draft_version)
            if op.target_trip_id:
                trip = await session.scalar(select(Trip).where(Trip.id == op.target_trip_id).with_for_update())
                if (trip is None or trip.version != 1 or trip.archived_at or trip.start_date != plan.constraints.start_date
                    or trip.end_date != plan.end_date or trip.destination != plan.city):
                    raise PromotionError("review_trip_changed", "旅行日期或版本已变化，请进入已创建旅行处理。")
                # Re-confirmed budgets/windows may change; no itinerary was accepted yet.
                trip.total_budget_fen, trip.daily_budget_fen = plan.constraints.total_budget_fen, plan.constraints.daily_budget_fen
            if op.target_revision_id:
                revision = await session.get(PlanRevision, op.target_revision_id)
                run = await session.get(PlanningRun, op.target_run_id)
                if revision.status != "pending" or run.status != "awaiting_confirmation":
                    raise PromotionError("review_candidate_decided", "原候选已处理，请刷新。")
                revision.status, run.status = "superseded", "cancelled"
                # Old deterministic place/source records remain for historical provenance;
                # next materialization uses fresh IDs through its new preparation identity.
            op.prepared_id, op.prepared_hash = plan.id, plan.prepared_hash
            op.content_hash, op.evidence_hash = plan.content_hash, plan.evidence_hash
            op.draft_version, op.allowed_action = plan.draft_version, request.action
            op.target_run_id = op.target_revision_id = None
            op.status = "trip_created" if op.target_trip_id else "requested"
            if op.target_trip_id and request.action == "create_only":
                op.status, op.consumed_at = "created", datetime.now(UTC)
            op.stage, op.error, op.validation, op.equivalence_check = "reauthorized", None, None, None
            op.authorized_at = op.updated_at = datetime.now(UTC)
            op.expires_at = plan.expires_at
            keys[key] = request_hash
            await session.execute(update(promotions).where(promotions.c.id == str(op.id)).values(confirmation_keys=keys))
            await save_operation(session, op, row)
            return op

    async def cancel(self, owner, operation_id):
        async with self.sessions() as session, session.begin():
            op, row = await get_operation(session, owner, operation_id, lock=True)
            if op.consumed_at or op.status in {"applied", "created", "cancelled"}:
                return op
            op.revoked_at = op.updated_at = datetime.now(UTC)
            op.status, op.stage = "cancelled", "authorization_revoked"
            op.error = "已撤回采用授权；已经创建的旅行仍保留，可在旅行页查看或归档。" if op.target_trip_id else "已取消，未创建旅行。"
            await save_operation(session, op, row)
            return op

    @staticmethod
    def _active(op):
        if op.revoked_at or op.consumed_at or op.status in {"cancelled", "needs_review", "applied", "created"}:
            return False
        if op.expires_at <= datetime.now(UTC):
            raise PromotionError("authorization_expired", "授权已过期，请重新准备并确认。")
        return True

    async def _t1(self, owner, operation_id):
        async with self.sessions() as session, session.begin():
            op, row = await get_operation(session, owner, operation_id, lock=True)
            if not self._active(op) or op.target_trip_id:
                return
            plan = await get_prepared(session, owner, op.prepared_id)
            await locked_draft(session, owner, op.draft_id, op.draft_version)
            if not valid_hashes(plan) or plan.prepared_hash != op.prepared_hash:
                raise PromotionError("prepared_hash_mismatch", "方案指纹变化，请重新准备并确认。")
            trip = await create_trip(session, TripCreate(title=plan.title, destination=plan.city,
                start_date=plan.constraints.start_date, end_date=plan.end_date,
                total_budget_fen=plan.constraints.total_budget_fen, daily_budget_fen=plan.constraints.daily_budget_fen), commit=False)
            # Create-only also transfers approved user requirements. It does
            # not need a candidate or an artificial PlanningRun as memory.
            preferences = await session.get(TripPreferences, trip.id)
            preferences.requirement_records = promote_requirements(plan.requirement_records,
                draft_id=plan.draft_id, trip_id=trip.id, city=trip.destination, start_date=trip.start_date)
            preferences.free_text_requirements = plan.requirements
            op.target_trip_id = trip.id
            op.status, op.stage, op.error = "trip_created", "trip_committed", None
            if op.allowed_action == "create_only":
                op.status, op.stage, op.consumed_at = "created", "create_only_completed", datetime.now(UTC)
            op.updated_at = datetime.now(UTC)
            await save_operation(session, op, row)

    async def _t2(self, owner, operation_id):
        async with self.sessions() as session, session.begin():
            op, row = await get_operation(session, owner, operation_id, lock=True)
            if not self._active(op) or op.target_revision_id:
                return
            plan = await get_prepared(session, owner, op.prepared_id)
            await locked_draft(session, owner, op.draft_id, op.draft_version)
            trip = await session.scalar(select(Trip).where(Trip.id == op.target_trip_id).with_for_update())
            if trip is None or trip.version != 1 or trip.archived_at:
                raise PromotionError("trip_changed", "已创建旅行发生变化，请进入旅行页检查。")
            c = plan.constraints
            preferences = await session.scalar(select(TripPreferences).where(TripPreferences.trip_id == trip.id).with_for_update())
            if preferences is None or preferences.version != 1:
                raise PromotionError("constraints_changed", "已创建旅行的偏好已修改，请检查后重新确认。")
            preferences.daily_start_time, preferences.daily_end_time = c.daily_start_time, c.daily_end_time
            preferences.transport_modes, preferences.max_walking_minutes = [c.transport_mode], c.max_walking_minutes
            preferences.free_text_requirements = plan.requirements
            preferences.requirement_records = promote_requirements(plan.requirement_records,
                draft_id=plan.draft_id, trip_id=trip.id, city=trip.destination, start_date=trip.start_date)
            run = PlanningRun(id=uuid5(op.id, f"run:{plan.id}"), trip_id=trip.id, run_type="initial_plan",
                status="validating", user_request="创建并采用当前已确认草稿方案", base_trip_version=trip.version,
                trigger_type="draft_promotion", trigger_key=f"draft-promotion:{op.id}",
                trigger_fingerprint=op.content_hash, trigger_snapshot={"promotion_id": str(op.id),
                    "prepared_id": str(plan.id), "draft_id": str(plan.draft_id), "draft_version": plan.draft_version,
                    "effective_requirements": preferences.requirement_records})
            session.add(run)
            await add_places(session, plan, op)
            candidate = snapshot_for(plan, op)
            await session.flush()
            result = await validate_candidate_plan(session, trip.id, candidate,
                required_dates={a.day_date for a in plan.activities})
            revision = await save_plan_revision(session, run.id, before_snapshot={}, proposed_snapshot=candidate,
                reason="用户明确授权的Draft确定性正式化", difference_summary={"draft_promotion_id": str(op.id),
                    "required_day_dates": [(c.start_date.fromordinal(c.start_date.toordinal() + i)).isoformat()
                        for i in range((plan.end_date - c.start_date).days + 1)]},
                validation_result=result.model_dump(mode="json"), source_ids=[a.source_ids[0] for a in candidate.activities],
                enrich_routes=False, commit=False)
            op.target_run_id, op.target_revision_id = run.id, revision.id
            op.validation = result.model_dump(mode="json")
            op.status = "awaiting_apply" if result.valid else "needs_review"
            op.stage = "candidate_committed"
            op.error = None if result.valid else "正式校验发现阻塞，方案未采用。请检查问题并重新准备确认。"
            op.updated_at = datetime.now(UTC)
            await save_operation(session, op, row)

    async def _apply(self, owner, operation_id, equivalence):
        async with self.sessions() as session, session.begin():
            op, row = await get_operation(session, owner, operation_id, lock=True)
            if not self._active(op):
                return op
            op.equivalence_check = equivalence
            op.status, op.updated_at = "awaiting_apply", datetime.now(UTC)
            await save_operation(session, op, row)
            session.info["draft_promotion_accept"] = (_CAPABILITY, owner, op.id)
            revision = await accept_plan_revision(session, op.target_revision_id, commit=False)
            locked, locked_row = session.info["draft_promotion_locked"]
            if revision.status != "accepted":
                raise PromotionError("accept_incomplete", "采用尚未完成，可重试原转换。")
            locked.status, locked.stage = "applied", "formal_accept_committed"
            locked.consumed_at = locked.updated_at = datetime.now(UTC)
            locked.error = None
            await save_operation(session, locked, locked_row)
            return locked

    async def _failure(self, owner, operation_id, message, *, review):
        async with self.sessions() as session, session.begin():
            op, row = await get_operation(session, owner, operation_id, lock=True)
            if op.status in {"applied", "created", "cancelled"} or op.consumed_at or op.revoked_at:
                return op
            op.status, op.error = ("needs_review" if review else "failed"), message
            op.updated_at = datetime.now(UTC)
            await save_operation(session, op, row)
            return op

    async def resume(self, owner, operation_id):
        # Reconciliation is deliberately first: an accepted revision must never
        # cause a second Trip, new candidate, or new consumption.
        async with self.sessions() as session, session.begin():
            op, row = await get_operation(session, owner, operation_id, lock=True)
            if op.target_revision_id:
                revision = await session.scalar(select(PlanRevision).where(PlanRevision.id == op.target_revision_id).with_for_update())
                if revision and revision.status == "accepted":
                    if not op.consumed_at:
                        # Impossible through the guarded atomic boundary; fail closed on corrupt legacy state.
                        op.status, op.error = "needs_review", "候选已采用但授权消费记录缺失，需要核对；不会重复创建或采用。"
                    else:
                        op.status, op.stage = "applied", "accepted_reconciled"
                    op.updated_at = datetime.now(UTC)
                    await save_operation(session, op, row)
                    return op
            if op.status in {"applied", "created", "cancelled", "needs_review"}:
                return op
        try:
            await self._t1(owner, operation_id)
            operation = await self.get(owner, operation_id)
            if operation.allowed_action == "create_only" or operation.status in {"cancelled", "needs_review", "applied", "created"}:
                return operation
            await self._t2(owner, operation_id)
            operation = await self.get(owner, operation_id)
            if operation.status in {"cancelled", "needs_review", "applied", "created"}:
                return operation
            async with self.sessions() as session:
                plan = await get_prepared(session, owner, operation.prepared_id)
            equivalence, error = await refresh_equivalent(plan, self.places)
            if error:
                return await self._failure(owner, operation_id, error, review=True)
            return await self._apply(owner, operation_id, equivalence)
        except (PromotionError, InvalidPlanRevisionError, StalePlanningRunError, InvalidPlanningRunStateError) as exc:
            message = exc.message if isinstance(exc, PromotionError) else "正式版本或校验已变化，方案未采用；请检查后重新准备并确认。"
            return await self._failure(owner, operation_id, message, review=True)
        except Exception:
            # No provider exception/private prose/DB details are persisted or exposed.
            return await self._failure(owner, operation_id, "转换暂时失败。已创建的旅行会保留；请重试当前操作，不会重复建旅行。", review=False)
