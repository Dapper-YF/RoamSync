"""The formal Accept boundary invokes this before taking revision/run/trip locks."""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.database import PlanningRun, PlanRevision, Trip
from app.drafts.contracts import Draft
from app.drafts.repository import drafts
from .contracts import PromotionError
from .materialize import verify_formal_binding
from .repository import get_operation, get_prepared

_CAPABILITY = object()


async def locked_draft(session, owner, draft_id, expected_version):
    row = (await session.execute(select(drafts.c.snapshot).where(drafts.c.id == str(draft_id),
        drafts.c.owner_id == owner).with_for_update())).first()
    if row is None:
        raise PromotionError("draft_not_found", "草稿不存在。", 404)
    draft = Draft.model_validate(row[0])
    if draft.version != expected_version or draft.status != "active" or any(r.status == "running" for r in draft.runs):
        raise PromotionError("draft_changed", "草稿版本或状态已变化，请重新准备并确认。")
    return draft


async def authorize_accept(session, revision_id, *, commit=True):
    """No public request field can set this internal request-local capability.

    First unlocked lookups only discover provenance. Mutation locks are always
    operation -> revision -> run -> trip -> draft. Cancel also locks operation.
    """
    revision = await session.get(PlanRevision, revision_id)
    if revision is None:
        return
    run = await session.get(PlanningRun, revision.planning_run_id)
    if run is None or run.trigger_type != "draft_promotion":
        return
    if commit:
        from app.planning_run_repository import InvalidPlanningRunStateError
        raise InvalidPlanningRunStateError("Promotion采用必须与授权消费同事务提交")
    capability = session.info.get("draft_promotion_accept")
    promotion_id = (run.trigger_snapshot or {}).get("promotion_id")
    if (not isinstance(capability, tuple) or len(capability) != 3 or capability[0] is not _CAPABILITY
        or str(capability[2]) != promotion_id):
        from app.planning_run_repository import InvalidPlanningRunStateError
        raise InvalidPlanningRunStateError("Draft Promotion候选必须通过对应转换操作确认采用")
    owner = capability[1]
    operation, row = await get_operation(session, owner, UUID(promotion_id), lock=True)
    # populate_existing is essential after the unlocked provenance lookups.
    revision = await session.scalar(select(PlanRevision).where(PlanRevision.id == revision_id).with_for_update().execution_options(populate_existing=True))
    run = await session.scalar(select(PlanningRun).where(PlanningRun.id == revision.planning_run_id).with_for_update().execution_options(populate_existing=True))
    trip = await session.scalar(select(Trip).where(Trip.id == revision.trip_id).with_for_update().execution_options(populate_existing=True))
    now = datetime.now(UTC)
    if (operation.status != "awaiting_apply" or operation.allowed_action != "create_and_adopt"
        or operation.revoked_at or operation.consumed_at or operation.expires_at <= now):
        raise PromotionError("authorization_unavailable", "授权已过期、撤回或使用，请检查转换状态。")
    equivalence = operation.equivalence_check or {}
    if (not equivalence.get("equivalent") or equivalence.get("evidence_hash") != operation.evidence_hash
        or datetime.fromisoformat(equivalence["expires_at"]) <= now):
        raise PromotionError("evidence_expired", "证据复核已过期，请重新准备并确认。")
    await locked_draft(session, owner, operation.draft_id, operation.draft_version)
    plan = await get_prepared(session, owner, operation.prepared_id)
    await verify_formal_binding(session, plan, operation, revision, run, trip)
    # Keep the locked operation for the no-commit caller. Consumption follows
    # successful formal validation/apply and commits with those writes.
    session.info["draft_promotion_locked"] = (operation, row)
