"""Fixture-only SQL evidence; only explicitly named isolated promotion_test DB."""
import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Activity, Base, PlaceCandidate, PlanRevision, PlanningRun, Trip, TripPreferences
from app.draft_promotion.contracts import ConfirmRequest, PreviewRequest, PromotionError
from app.draft_promotion.preparation import valid_hashes
from app.draft_promotion.repository import metadata, promotions
from app.draft_promotion.service import DraftPromotionService
from app.drafts.contracts import DraftCreate, DraftPlan
from app.drafts.repository import DraftRepository, metadata as draft_metadata
from app.place_content.contracts import Place, RouteResult
from app.plan_revision_service import accept_plan_revision
from app.planning_run_repository import InvalidPlanningRunStateError, reject_revision


class FixturePlaces:
    def __init__(self):
        now = datetime.now(UTC)
        self.items = [Place.model_validate({"ref": {"place_id": f"00000000-0000-4000-8000-{i + 2:012d}", "external_ref": {"provider_place_id": str(i)}},
            "name": f"测试地点{i}", "category": "attraction", "city": "杭州", "location": {"longitude": 120 + i / 1000, "latitude": 30},
            "source": {"source_url": f"https://fixture.invalid/{i}", "fetched_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat()}}) for i in range(2)]
        self.duration, self.fail = 600, False
        self.pause, self.release = None, None

    async def get_place(self, place_id, **kwargs):
        if self.fail:
            raise RuntimeError("SENSITIVE PROVIDER FAILURE")
        result = next(p for p in self.items if p.ref.place_id == place_id).model_copy(deep=True)
        result.source.fetched_at = datetime.now(UTC)
        return result

    async def query_route(self, query):
        if self.pause:
            self.pause.set()
            await self.release.wait()
        now = datetime.now(UTC)
        return RouteResult(origin=query.origin, destination=query.destination, mode=query.mode,
            distance_meters=600, duration_seconds=self.duration, path=[query.origin, query.destination],
            source={"source_url": "https://fixture.invalid/route", "fetched_at": now, "expires_at": now + timedelta(hours=1)})


@pytest.fixture
def stack():
    url = os.environ.get("PROMOTION_TEST_DATABASE_URL", "")
    if not url or not url.endswith("/promotion_test"):
        pytest.skip("requires explicit isolated promotion_test database")
    sync = create_engine(url, poolclass=NullPool)
    Base.metadata.create_all(sync)
    draft_metadata.create_all(sync)
    metadata.create_all(sync)
    sessions = async_sessionmaker(create_async_engine(url, poolclass=NullPool), expire_on_commit=False)
    repo, places, owner = DraftRepository(sync), FixturePlaces(), str(uuid4())
    service = DraftPromotionService(repo, sessions, places)
    draft = repo.create(owner, DraftCreate(city="杭州", day_count=1))
    def fill(current):
        current.plan = DraftPlan(days=[{"day_index": 1, "title": "测试一天", "items": [
            {"name": p.name, "place_id": p.ref.place_id, "identity_status": "provider_confirmed"} for p in places.items]}])
    draft = repo.mutate(owner, draft.id, draft.version, fill)
    yield service, repo, places, owner, draft, sessions, sync
    sync.dispose()


async def preview_confirm(stack, **overrides):
    service, _, _, owner, draft, *_ = stack
    plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version,
        start_date="2026-11-01", **overrides))
    request = ConfirmRequest(request_id=uuid4(), prepared_id=plan.id, prepared_hash=plan.prepared_hash,
        action="create_and_adopt", confirmation="创建并采用当前方案")
    return plan, request, await service.confirm(owner, request)


def test_preview_no_trip_exact_plan_adopt_idempotency_and_guards(stack):
    async def scenario():
        service, _, _, owner, _, sessions, _ = stack
        async with sessions() as session:
            before = await session.scalar(select(func.count()).select_from(Trip))
        plan, request, op = await preview_confirm(stack)
        assert not plan.coverage.blockers and valid_hashes(plan)
        assert all(a.cost_nature == "planning_estimate" and a.estimated_cost_fen == 10000 for a in plan.activities)
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Trip)) == before
        assert (await service.confirm(owner, request)).id == op.id
        with pytest.raises(PromotionError, match="idempotency_key_reused"):
            await service.confirm(owner, request.model_copy(update={"action": "create_only", "confirmation": "创建旅行"}))
        await service._t1(owner, op.id)
        await service._t2(owner, op.id)
        pending = await service.get(owner, op.id)
        assert pending.status == "awaiting_apply"
        async with sessions() as session:
            with pytest.raises(InvalidPlanningRunStateError):
                await accept_plan_revision(session, pending.target_revision_id)
        async with sessions() as session:
            with pytest.raises(InvalidPlanningRunStateError):
                await reject_revision(session, pending.target_revision_id)
        applied = await service.resume(owner, op.id)
        assert applied.status == "applied", applied.model_dump_json()
        assert applied.consumed_at and applied.target_trip_id == pending.target_trip_id
        assert (await service.resume(owner, op.id)).target_revision_id == applied.target_revision_id
        assert (await service.cancel(owner, op.id)).status == "applied"
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Trip)) == before + 1
            assert (await session.get(Trip, applied.target_trip_id)).version == 2
            revision = await session.get(PlanRevision, applied.target_revision_id)
            assert revision.status == "accepted"
            activities = list((await session.scalars(select(Activity).where(Activity.place_candidate_id.in_(
                [UUID(a["place_candidate_id"]) for a in revision.proposed_snapshot["activities"]])))).all())
            assert len(activities) == 2
            assert sorted(a.scheduled_time.isoformat() for a in activities) == ["09:00:00", "10:40:00"]
    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["before_t1", "after_t1", "after_t2"])
def test_cancel_retains_created_trip_and_never_applies(stack, stage):
    async def scenario():
        service, _, _, owner, _, sessions, _ = stack
        _, _, op = await preview_confirm(stack)
        if stage != "before_t1":
            await service._t1(owner, op.id)
        if stage == "after_t2":
            await service._t2(owner, op.id)
        cancelled = await service.cancel(owner, op.id)
        assert cancelled.status == "cancelled" and not cancelled.consumed_at
        assert (cancelled.target_trip_id is None) == (stage == "before_t1")
        assert (await service.resume(owner, op.id)).target_trip_id == cancelled.target_trip_id
        if cancelled.target_trip_id:
            async with sessions() as session:
                assert (await session.get(Trip, cancelled.target_trip_id)).version == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["create_and_adopt", "create_only"])
def test_material_change_requires_review_and_reuses_trip(stack, action):
    async def scenario():
        service, _, places, owner, draft, _, _ = stack
        _, _, op = await preview_confirm(stack)
        await service._t1(owner, op.id)
        places.duration = 1200
        changed = await service.resume(owner, op.id)
        assert changed.status == "needs_review" and not changed.consumed_at
        plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version,
            start_date="2026-11-01", operation_id=op.id))
        assert plan.activities[1].planned_start_time.isoformat() == "10:50:00"
        reauth = ConfirmRequest(request_id=uuid4(), prepared_id=plan.id, prepared_hash=plan.prepared_hash,
            action=action, confirmation="创建旅行" if action == "create_only" else "创建并采用当前方案")
        await service.review(owner, op.id, reauth)
        applied = await service.resume(owner, op.id)
        assert applied.status == ("created" if action == "create_only" else "applied"), applied.model_dump_json()
        assert applied.target_trip_id == changed.target_trip_id
        assert (await service.review(owner, op.id, reauth)).status == applied.status
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["draft", "trip", "candidate", "formal_place", "expiry", "provider_failure", "preferences", "run_cancelled"])
def test_fail_closed_on_changed_binding(stack, change):
    async def scenario():
        service, repo, places, owner, draft, sessions, _ = stack
        _, _, op = await preview_confirm(stack)
        await service._t1(owner, op.id)
        await service._t2(owner, op.id)
        pending = await service.get(owner, op.id)
        if change == "draft":
            repo.mutate(owner, draft.id, draft.version, lambda d: setattr(d, "saved", True))
        if change == "provider_failure":
            places.fail = True
        async with sessions() as session, session.begin():
            if change == "trip":
                (await session.get(Trip, pending.target_trip_id)).version += 1
            if change == "candidate":
                revision = await session.get(PlanRevision, pending.target_revision_id)
                value = {**revision.proposed_snapshot, "activities": [dict(a) for a in revision.proposed_snapshot["activities"]]}
                value["activities"][0]["duration_minutes"] += 1
                revision.proposed_snapshot = value
            if change == "formal_place":
                revision = await session.get(PlanRevision, pending.target_revision_id)
                place = await session.get(PlaceCandidate, UUID(revision.proposed_snapshot["activities"][0]["place_candidate_id"]))
                place.estimated_cost_fen += 1
            if change == "preferences":
                prefs = await session.get(TripPreferences, pending.target_trip_id)
                prefs.version += 1
            if change == "run_cancelled":
                (await session.get(PlanningRun, pending.target_run_id)).status = "cancelled"
            if change == "expiry":
                row = (await session.execute(select(promotions).where(promotions.c.id == str(op.id)))).mappings().one()
                value = {**row["snapshot"], "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
                await session.execute(update(promotions).where(promotions.c.id == str(op.id)).values(snapshot=value))
        failed = await service.resume(owner, op.id)
        assert failed.status == "needs_review", failed.model_dump_json()
        assert not failed.consumed_at and failed.target_trip_id == pending.target_trip_id
        assert "SENSITIVE" not in (failed.error or "")
    asyncio.run(scenario())


def test_unknown_place_blocks_adopt_but_explicit_create_only_available(stack):
    async def scenario():
        service, repo, _, owner, draft, _, _ = stack
        def unknown(d):
            d.plan.days[0].items[0].place_id = None
            d.plan.days[0].items[0].identity_status = "unknown"
        draft = repo.mutate(owner, draft.id, draft.version, unknown)
        plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version, start_date="2026-11-01"))
        assert plan.coverage.blockers and len(plan.activities) == 2
        request = ConfirmRequest(request_id=uuid4(), prepared_id=plan.id, prepared_hash=plan.prepared_hash,
            action="create_and_adopt", confirmation="创建并采用当前方案")
        with pytest.raises(PromotionError, match="preview_blocked"):
            await service.confirm(owner, request)
        op = await service.confirm(owner, request.model_copy(update={"action": "create_only", "confirmation": "创建旅行"}))
        result = await service.resume(owner, op.id)
        assert result.status == "created" and result.target_trip_id and not result.target_run_id
    asyncio.run(scenario())


def test_crashes_rollback_t1_t2_mapping_and_retry_same_operation(stack, monkeypatch):
    async def scenario():
        service, _, _, owner, _, sessions, _ = stack
        _, _, op = await preview_confirm(stack)
        import app.draft_promotion.service as module
        original = module.save_operation
        async with sessions() as session:
            before_trips = await session.scalar(select(func.count()).select_from(Trip))
        async def fail_save(*args):
            raise RuntimeError("synthetic crash before commit")
        monkeypatch.setattr(module, "save_operation", fail_save)
        with pytest.raises(RuntimeError):
            await service._t1(owner, op.id)
        assert (await service.get(owner, op.id)).target_trip_id is None
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Trip)) == before_trips
        monkeypatch.setattr(module, "save_operation", original)
        await service._t1(owner, op.id)
        trip_id = (await service.get(owner, op.id)).target_trip_id
        monkeypatch.setattr(module, "save_operation", fail_save)
        with pytest.raises(RuntimeError):
            await service._t2(owner, op.id)
        assert (await service.get(owner, op.id)).target_revision_id is None
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(PlanningRun).where(PlanningRun.trip_id == trip_id)) == 0
        monkeypatch.setattr(module, "save_operation", original)
        result = await service.resume(owner, op.id)
        assert result.status == "applied" and result.target_trip_id == trip_id
    asyncio.run(scenario())


def test_cancel_wins_during_external_refresh(stack):
    async def scenario():
        service, _, places, owner, _, sessions, _ = stack
        _, _, op = await preview_confirm(stack)
        await service._t1(owner, op.id)
        await service._t2(owner, op.id)
        places.pause, places.release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(service.resume(owner, op.id))
        await places.pause.wait()
        cancelled = await service.cancel(owner, op.id)
        places.release.set()
        assert (await task).status == cancelled.status == "cancelled"
        async with sessions() as session:
            assert (await session.get(Trip, cancelled.target_trip_id)).version == 1
    asyncio.run(scenario())


def test_owner_isolation_explicit_phrase_and_preferences_before_t2(stack):
    async def scenario():
        service, _, _, owner, _, sessions, _ = stack
        _, request, op = await preview_confirm(stack)
        with pytest.raises(PromotionError) as error:
            await service.get("other", op.id)
        assert error.value.status == 404
        with pytest.raises(PromotionError):
            await service.confirm("other", request)
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfirmRequest(**{**request.model_dump(), "confirmation": "创建旅行"})
        await service._t1(owner, op.id)
        current = await service.get(owner, op.id)
        async with sessions() as session, session.begin():
            prefs = await session.get(TripPreferences, current.target_trip_id)
            prefs.version += 1
            prefs.free_text_requirements = "用户新要求，不可覆盖"
        result = await service.resume(owner, op.id)
        assert result.status == "needs_review"
        async with sessions() as session:
            assert (await session.get(TripPreferences, current.target_trip_id)).free_text_requirements == "用户新要求，不可覆盖"
    asyncio.run(scenario())


def test_t3_fault_rolls_back_accept_and_consumption_and_response_loss_reconciles(stack, monkeypatch):
    async def scenario():
        service, _, _, owner, _, sessions, _ = stack
        _, _, op = await preview_confirm(stack)
        await service._t1(owner, op.id)
        await service._t2(owner, op.id)
        pending = await service.get(owner, op.id)
        import app.draft_promotion.service as module
        original = module.save_operation
        async def fail_consumption(session, operation, row):
            if operation.status == "applied":
                raise RuntimeError("synthetic crash after formal apply before operation consumption")
            await original(session, operation, row)
        monkeypatch.setattr(module, "save_operation", fail_consumption)
        result = await service.resume(owner, op.id)
        assert result.status == "failed" and not result.consumed_at
        async with sessions() as session:
            assert (await session.get(Trip, pending.target_trip_id)).version == 1
            assert (await session.get(PlanRevision, pending.target_revision_id)).status == "pending"
            from app.database import DayPlan
            assert await session.scalar(select(func.count()).select_from(Activity).join(DayPlan).where(DayPlan.trip_id == pending.target_trip_id)) == 0
        monkeypatch.setattr(module, "save_operation", original)
        accepted = await service.resume(owner, op.id)
        assert accepted.status == "applied" and accepted.target_trip_id == pending.target_trip_id
        # Feedback state lost after an already committed guarded adoption: reconcile facts.
        async with sessions() as session, session.begin():
            row = (await session.execute(select(promotions).where(promotions.c.id == str(op.id)))).mappings().one()
            value = {**row["snapshot"], "status": "failed", "stage": "response_lost"}
            await session.execute(update(promotions).where(promotions.c.id == str(op.id)).values(snapshot=value))
        reconciled = await service.resume(owner, op.id)
        assert reconciled.status == "applied" and reconciled.stage == "accepted_reconciled"
        assert reconciled.consumed_at == accepted.consumed_at
    asyncio.run(scenario())


def test_concurrent_key_and_resume_only_one_trip_revision(stack):
    async def scenario():
        service, _, _, owner, _, sessions, _ = stack
        service, _, _, owner, draft, sessions, _ = stack
        plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version, start_date="2026-11-01"))
        request = ConfirmRequest(request_id=uuid4(), prepared_id=plan.id, prepared_hash=plan.prepared_hash,
            action="create_and_adopt", confirmation="创建并采用当前方案")
        repeated = await asyncio.gather(*(service.confirm(owner, request) for _ in range(3)))
        op = repeated[0]
        assert {result.id for result in repeated} == {op.id}
        results = await asyncio.gather(*(service.resume(owner, op.id) for _ in range(3)))
        assert {result.status for result in results} == {"applied"}
        assert len({result.target_trip_id for result in results}) == 1
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(PlanningRun).where(PlanningRun.trip_id == results[0].target_trip_id)) == 1
            assert await session.scalar(select(func.count()).select_from(PlanRevision).where(PlanRevision.trip_id == results[0].target_trip_id)) == 1
    asyncio.run(scenario())


def test_long_requirements_and_prepared_tamper_never_accepted(stack):
    async def scenario():
        service, repo, _, owner, draft, sessions, _ = stack
        draft = repo.mutate(owner, draft.id, draft.version, lambda d: setattr(d, "requirements", "长" * 2001))
        plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version, start_date="2026-11-01"))
        assert plan.requirements == "长" * 2001 and any("2000" in text for text in plan.coverage.blockers)
        request = ConfirmRequest(request_id=uuid4(), prepared_id=plan.id, prepared_hash=plan.prepared_hash,
            action="create_and_adopt", confirmation="创建并采用当前方案")
        with pytest.raises(PromotionError, match="preview_blocked"):
            await service.confirm(owner, request)
        from app.draft_promotion.repository import prepared_plans
        async with sessions() as session, session.begin():
            value = plan.model_dump(mode="json")
            value["activities"][0]["duration_minutes"] += 1
            await session.execute(update(prepared_plans).where(prepared_plans.c.id == str(plan.id)).values(snapshot=value))
        with pytest.raises(PromotionError, match="prepared_hash_mismatch"):
            await service.confirm(owner, request)
    asyncio.run(scenario())


def test_successful_modification_requirements_preserved_and_expired_run_recovered(stack):
    async def scenario():
        service, repo, _, owner, draft, _, _ = stack
        from app.drafts.contracts import DraftRun
        now = datetime.now(UTC)
        def modify(d):
            d.requirements = "喜欢历史"
            d.runs = [DraftRun(id=uuid4(), request_id=uuid4(), status="completed", requirements="第二天轻松一点",
                source="fixture", created_at=now), DraftRun(id=uuid4(), request_id=uuid4(), status="running", requirements="未完成要求不采用",
                source="fixture", created_at=now - timedelta(minutes=10), lease_expires_at=now - timedelta(minutes=5))]
        draft = repo.mutate(owner, draft.id, draft.version, modify)
        assert repo.recover_interrupted(owner=owner, now=now) == 1
        draft = repo.get(owner, draft.id)
        assert draft.runs[1].status == "interrupted" and draft.plan is not None
        plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version, start_date="2026-11-01"))
        from app.requirements import project_requirements
        day1 = project_requirements(plan.requirement_records, draft_id=str(draft.id), city=draft.city, day_index=1)
        day2 = project_requirements(plan.requirement_records, draft_id=str(draft.id), city=draft.city, day_index=2)
        assert any(r["text"] == "喜欢历史" for r in day1)
        assert not any(r["key"] == "pace" for r in day1)
        assert any(r["key"] == "pace" and r["value"] == "relaxed" and r["scope"]["day_index"] == 2 for r in day2)
        assert "未完成" not in plan.requirements
    asyncio.run(scenario())


def test_golden_normalization_semantics_and_evidence(stack):
    async def scenario():
        import json
        from pathlib import Path
        from app.draft_promotion.preparation import bind_hashes, evidence_values, semantic_values, digest
        service, _, places, owner, draft, _, _ = stack
        plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version, start_date="2026-11-01"))
        plan.draft_id = UUID("00000000-0000-4000-8000-000000000001")
        fixture = json.loads((Path(__file__).parents[1] / "evals" / "fixtures" / "draft_promotion_golden_v1.json").read_text(encoding="utf-8"))
        assert semantic_values(plan) == fixture["semantic"]
        assert evidence_values(plan) == fixture["evidence"]
        assert digest(semantic_values(plan)) == fixture["content_hash"]
        assert digest(evidence_values(plan)) == fixture["evidence_hash"]
        # New IDs, prose and retrieval timestamps do not grant different semantics.
        plan.id, plan.title = uuid4(), "新的展示标题"
        plan.activities[0].note = "非语义说明变化"
        plan.activities[0].place.source.fetched_at += timedelta(minutes=1)
        plan.activities[0].place.source.expires_at += timedelta(minutes=1)
        plan.routes[0].route.source.fetched_at += timedelta(minutes=1)
        assert digest(semantic_values(plan)) == fixture["content_hash"]
        assert digest(evidence_values(plan)) == fixture["evidence_hash"]
        plan.activities[0].estimated_cost_fen += 1
        assert digest(semantic_values(plan)) != fixture["content_hash"]
        plan.routes[0].route.duration_seconds += 1
        assert digest(evidence_values(plan)) != fixture["evidence_hash"]
    asyncio.run(scenario())


def test_same_prepared_plan_cannot_create_duplicate_operation_with_different_request_id(stack):
    from app.draft_promotion.contracts import ConfirmRequest
    async def scenario():
        service,_,_,owner,_,_,_=stack
        plan,request,first=await preview_confirm(stack)
        retry=request.model_copy(update={"request_id":uuid4()})
        repeated=await service.confirm(owner,retry)
        assert repeated.id==first.id
        different=ConfirmRequest(request_id=uuid4(),prepared_id=plan.id,prepared_hash=plan.prepared_hash,action="create_only",confirmation="创建旅行")
        with pytest.raises(PromotionError) as error:
            await service.confirm(owner,different)
        assert error.value.code=="prepared_already_authorized"
        assert len(await service.list(owner,plan.draft_id))==1
    asyncio.run(scenario())
