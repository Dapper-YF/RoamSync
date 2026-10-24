"""V2 adoption uses existing materialization and Accept in one transaction.

Durable authorization is independent. No formal object is committed until every
guard and the published conversation binding have passed. V1 resumes stay V1.
"""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import AssistantSession
from app.conversation_candidate.presentation import candidate_presentation, presentation_digest
from app.conversation_candidate.binding import row_conditions_hash
from .contracts import Operation, PromotionError
from .guard import locked_draft
from .preparation import digest, refresh_equivalent
from .repository import get_operation, get_prepared, promotions


async def published_session(session, owner, plan, session_id, presentation_hash, *, publication_id=None):
    row = await session.scalar(select(AssistantSession).where(AssistantSession.id == session_id)
        .with_for_update().execution_options(populate_existing=True))
    action = row.pending_action if row is not None else None
    view = (action or {}).get("presentation") or {}
    if (not action or action.get("kind") != "itinerary_candidate_v2" or action.get("owner_id") != owner
        or not action.get("topic_id") or not action.get("id")
        or (publication_id is not None and action["id"] != publication_id)
        or action.get("conditions_hash") != row_conditions_hash(row, action["topic_id"])
        or view.get("stage") != "ready" or view.get("protocol_version") != 2
        or view.get("prepared_id") != str(plan.id) or view.get("prepared_hash") != plan.prepared_hash
        or view.get("draft_id") != str(plan.draft_id) or view.get("draft_version") != plan.draft_version
        or view.get("presentation_hash") != presentation_hash
        or presentation_digest(view) != presentation_hash
        or candidate_presentation(plan)["presentation_hash"] != presentation_hash):
        raise PromotionError("candidate_publication_changed", "这份候选已更新或已撤回，请查看当前安排后再保存。")
    return row, action


async def confirm_atomic(service, owner, request, *, session_id, presentation_hash):
    session_id = UUID(str(session_id))
    request_hash = digest({"request": request.model_dump(mode="json"), "session_id": str(session_id),
        "presentation_hash": presentation_hash, "execution_mode": "atomic_candidate_v2"})
    try:
        async with service.sessions() as session, session.begin():
            existing = (await session.execute(select(promotions).where(promotions.c.owner_id == owner,
                promotions.c.request_id == str(request.request_id)).with_for_update())).mappings().first()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise PromotionError("idempotency_key_reused", "保存编号不能用于另一份候选。")
                return Operation.model_validate(existing["snapshot"])
            plan = await get_prepared(session, owner, request.prepared_id)
            if plan.schema_version != 2 or request.action != "create_and_adopt":
                raise PromotionError("candidate_protocol_required", "请从当前候选的保存入口操作，不能采用创建元数据。")
            service._check_plan(plan, request)
            await locked_draft(session, owner, plan.draft_id, plan.draft_version)
            row, action = await published_session(session, owner, plan, session_id, presentation_hash)
            previous = (await session.execute(select(promotions.c.snapshot).where(promotions.c.owner_id == owner,
                promotions.c.snapshot["prepared_id"].as_string() == str(plan.id)))).first()
            if previous:
                operation = Operation.model_validate(previous[0])
                binding = operation.publication_binding or {}
                if (operation.execution_mode != "atomic_candidate_v2" or binding.get("session_id") != str(session_id)
                    or binding.get("presentation_hash") != presentation_hash or binding.get("publication_id") != action["id"]):
                    raise PromotionError("prepared_already_authorized", "这份候选已有不同保存操作，请恢复原操作。")
                return operation
            now = datetime.now(UTC)
            operation = Operation(protocol_version=2, execution_mode="atomic_candidate_v2",
                publication_binding={"session_id": str(session_id), "topic_id": action["topic_id"],
                    "publication_id": action["id"], "presentation_hash": presentation_hash, "request_id": str(request.request_id)},
                id=uuid4(), draft_id=plan.draft_id, draft_version=plan.draft_version,
                prepared_id=plan.id, prepared_hash=plan.prepared_hash, content_hash=plan.content_hash,
                evidence_hash=plan.evidence_hash, allowed_action="create_and_adopt", status="requested",
                stage="authorized", authorized_at=now, expires_at=plan.expires_at, updated_at=now)
            await session.execute(promotions.insert().values(id=str(operation.id), owner_id=owner,
                request_id=str(request.request_id), request_hash=request_hash, version=1,
                snapshot=operation.model_dump(mode="json"), confirmation_keys={}))
            return operation
    except IntegrityError:
        async with service.sessions() as session:
            row = (await session.execute(select(promotions).where(promotions.c.owner_id == owner,
                promotions.c.request_id == str(request.request_id)))).mappings().first()
            if row is None or row["request_hash"] != request_hash:
                raise PromotionError("idempotency_key_reused", "保存编号已使用，请恢复原操作。") from None
            return Operation.model_validate(row["snapshot"])


async def resume_atomic(service, owner, operation_id):
    async with service.sessions() as session:
        operation, _ = await get_operation(session, owner, operation_id)
        if operation.execution_mode != "atomic_candidate_v2" or operation.protocol_version != 2:
            raise PromotionError("candidate_protocol_required", "保存协议不匹配，请恢复原操作。")
        if operation.status in {"applied", "created", "cancelled", "needs_review"}:
            return operation
        plan = await get_prepared(session, owner, operation.prepared_id)
    # Provider calls cannot hold either conversation or business transactions.
    equivalence, error = await refresh_equivalent(plan, service.places)
    if error:
        return await service._failure(owner, operation_id, error, review=True)
    try:
        async with service.sessions() as session, session.begin():
            operation, _ = await get_operation(session, owner, operation_id, lock=True)
            if not service._active(operation):
                return operation
            # New rows are private to this transaction. Existing units preserve
            # the original Validator/Accept; their wrappers remain for V1.
            await service._t1_unit(session, owner, operation_id, check_draft=False)
            await service._t2_unit(session, owner, operation_id, check_draft=False)
            current, _ = await get_operation(session, owner, operation_id)
            if current.status != "awaiting_apply":
                raise PromotionError("candidate_validation_failed", "这份安排没有通过最终检查，尚未保存。")
            applied = await service._apply_unit(session, owner, operation_id, equivalence)
            binding = applied.publication_binding or {}
            row, action = await published_session(session, owner, plan, UUID(binding["session_id"]),
                binding["presentation_hash"], publication_id=binding["publication_id"])
            if action["topic_id"] != binding.get("topic_id"):
                raise PromotionError("candidate_topic_changed", "对话主题已变化，原候选未保存。")
            row.trip_id, row.latest_run_id, row.pending_action = applied.target_trip_id, applied.target_run_id, None
            context = next((turn["context"] for turn in reversed(row.messages)
                if turn.get("context", {}).get("topic_id") == binding["topic_id"]), {"topic_id": binding["topic_id"]})
            row.messages = [*row.messages, {"id": binding.get("request_id", str(applied.id)), "user": "保存当前候选",
                "assistant": f"已经保存「{plan.title}」。你可以在我的安排查看完整日程，也可以继续让我修改。",
                "candidate": {**action["presentation"], "stage": "saved", "trip_id": str(applied.target_trip_id), "operation_id": str(applied.id)},
                "trip_id": str(applied.target_trip_id), "context": context}]
            row.applied_actions = {**(row.applied_actions or {}), str(applied.id): str(applied.target_trip_id)}
            return applied
    except PromotionError as exc:
        return await service._failure(owner, operation_id, exc.message, review=True)
    except Exception:
        return await service._failure(owner, operation_id, "这次保存未完成，正式行程没有新增。请重试当前候选。", review=False)
