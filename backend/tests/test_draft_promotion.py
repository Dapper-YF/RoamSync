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


async def atomic_preview(stack, *, lunch=False):
    """Synthetic itinerary; real PG transaction/Accept proof, not model quality."""
    from app.conversation_candidate.presentation import candidate_presentation
    from app.conversation_candidate.binding import conditions_hash
    from app.assistant_context import ContextEnvelope
    from app.database import AssistantSession
    service, repo, places, owner, draft, sessions, _ = stack
    def fill(current):
        current.schema_version = 2
        items = [
            {"item_ref": f"visit-{n}", "kind": "visit", "name": p.name,
             "place_id": str(p.ref.place_id), "provider_place_id": p.ref.external_ref.provider_place_id,
             "identity_status": "provider_confirmed", "duration_minutes": 90,
             "duration_source": "planning_allocation"} for n, p in enumerate(places.items)]
        if lunch:
            items.insert(1, {"item_ref": "lunch", "kind": "meal", "name": "午餐休息",
                "start_time": "12:00", "end_time": "13:00", "source_quote": "中午留一小时吃饭"})
        current.plan = DraftPlan.model_validate({"schema_version": 2, "schedule_constraints": {
            "start_date": "2026-11-01", "daily_start_time": "09:00", "daily_end_time": "18:00",
            "transport_mode": "walk"}, "days": [{"day_index": 1, "title": "真实状态测试", "items": items}]})
    draft = repo.mutate(owner, draft.id, draft.version, fill)
    plan = await service.preview(owner, draft.id, PreviewRequest(expected_version=draft.version, start_date="2026-11-01"))
    presentation = candidate_presentation(plan)
    session_id = uuid4()
    async with sessions() as session, session.begin():
        session.add(AssistantSession(id=session_id, messages=[], applied_actions={}, pending_action={
            "id": str(uuid4()), "kind": "itinerary_candidate_v2", "owner_id": owner,
            "conditions_hash": conditions_hash(ContextEnvelope(topic_id="atomic-test")),
            "topic_id": "atomic-test", "presentation": presentation}))
    request = ConfirmRequest(request_id=uuid4(), prepared_id=plan.id, prepared_hash=plan.prepared_hash,
        action="create_and_adopt", confirmation="创建并采用当前方案")
    return plan, presentation, session_id, request


def test_atomic_candidate_accepts_exact_published_plan_without_shell_trip(stack):
    async def scenario():
        from app.database import AssistantSession
        service, _, _, owner, _, sessions, _ = stack
        plan, presentation, session_id, request = await atomic_preview(stack)
        async with sessions() as session:
            before = await session.scalar(select(func.count()).select_from(Trip))
        operation = await service.confirm_atomic(owner, request, session_id=session_id,
            presentation_hash=presentation["presentation_hash"])
        assert operation.execution_mode == "atomic_candidate_v2" and operation.target_trip_id is None
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Trip)) == before
        result = await service.resume(owner, operation.id)
        assert result.status == "applied", result.model_dump_json()
        assert (await service.resume(owner, operation.id)).target_trip_id == result.target_trip_id
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Trip)) == before + 1
            assert (await session.get(AssistantSession, session_id)).trip_id == result.target_trip_id
            assert (await session.get(PlanRevision, result.target_revision_id)).status == "accepted"
    asyncio.run(scenario())


def test_atomic_candidate_validation_failure_rolls_back_all_formal_writes(stack, monkeypatch):
    async def scenario():
        from app.database import AssistantSession, DayPlan, RouteLeg, SourceRecord, TripArrangementItem
        from app.schemas import PlanValidationResult, PlanValidationIssue
        import app.draft_promotion.service as module
        service, _, _, owner, _, sessions, _ = stack
        _, presentation, session_id, request = await atomic_preview(stack)
        tables = (Trip, DayPlan, Activity, PlaceCandidate, SourceRecord, TripPreferences, RouteLeg, PlanningRun, PlanRevision, TripArrangementItem)
        async def counts():
            async with sessions() as session:
                return [await session.scalar(select(func.count()).select_from(table)) for table in tables]
        before = await counts()
        operation = await service.confirm_atomic(owner, request, session_id=session_id,
            presentation_hash=presentation["presentation_hash"])
        async def reject(*args, **kwargs):
            return PlanValidationResult(valid=False, errors=[PlanValidationIssue(code="fixture_failure", message="explicit failure injection")], warnings=[])
        monkeypatch.setattr(module, "validate_candidate_plan", reject)
        result = await service.resume(owner, operation.id)
        assert result.status == "needs_review" and result.target_trip_id is None
        assert await counts() == before
        async with sessions() as session:
            assert (await session.get(AssistantSession, session_id)).trip_id is None
    asyncio.run(scenario())


def test_atomic_candidate_cancelled_publication_cannot_be_saved(stack):
    async def scenario():
        from app.database import AssistantSession
        service, _, _, owner, _, sessions, _ = stack
        _, presentation, session_id, request = await atomic_preview(stack)
        operation = await service.confirm_atomic(owner, request, session_id=session_id,
            presentation_hash=presentation["presentation_hash"])
        async with sessions() as session, session.begin():
            row = await session.get(AssistantSession, session_id)
            row.pending_action = None
        result = await service.resume(owner, operation.id)
        assert result.status == "needs_review" and result.target_trip_id is None
    asyncio.run(scenario())


def test_atomic_concurrent_authorization_and_resume_create_one_trip(stack):
    async def scenario():
        service, _, _, owner, _, sessions, _ = stack
        _, view, session_id, request = await atomic_preview(stack)
        async with sessions() as db:
            before = await db.scalar(select(func.count()).select_from(Trip))
        first, repeated = await asyncio.gather(*[
            service.confirm_atomic(owner, value, session_id=session_id, presentation_hash=view["presentation_hash"])
            for value in (request, request.model_copy(update={"request_id": uuid4()}))])
        assert first.id == repeated.id
        results = await asyncio.gather(service.resume(owner, first.id), service.resume(owner, repeated.id))
        assert all(result.status == "applied" for result in results)
        assert results[0].target_trip_id == results[1].target_trip_id
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Trip)) == before + 1
    asyncio.run(scenario())


def test_atomic_cancel_during_provider_refresh_commits_no_trip(stack):
    async def scenario():
        service, _, places, owner, _, sessions, _ = stack
        _, view, session_id, request = await atomic_preview(stack)
        op = await service.confirm_atomic(owner, request, session_id=session_id, presentation_hash=view["presentation_hash"])
        async with sessions() as db:
            before = await db.scalar(select(func.count()).select_from(Trip))
        places.pause, places.release = asyncio.Event(), asyncio.Event()
        running = asyncio.create_task(service.resume(owner, op.id))
        await asyncio.wait_for(places.pause.wait(), timeout=10)
        cancelled = await asyncio.wait_for(service.cancel(owner, op.id), timeout=3)
        assert cancelled.status == "cancelled"
        places.release.set()
        result = await running
        assert result.status == "cancelled" and result.target_trip_id is None
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Trip)) == before
    asyncio.run(scenario())


def test_atomic_candidate_lunch_is_formal_window_and_keeps_real_route(stack):
    async def scenario():
        from datetime import time
        from app.database import TripArrangementItem, RouteLeg, DayPlan
        service, _, _, owner, _, sessions, _ = stack
        plan, view, session_id, request = await atomic_preview(stack, lunch=True)
        op = await service.confirm_atomic(owner, request, session_id=session_id, presentation_hash=view["presentation_hash"])
        result = await service.resume(owner, op.id)
        assert result.status == "applied", result.model_dump_json()
        async with sessions() as session:
            windows = list((await session.scalars(select(TripArrangementItem).where(
                TripArrangementItem.trip_id == result.target_trip_id, TripArrangementItem.kind == "free_window"))).all())
            assert [(w.start_time, w.end_time, w.label) for w in windows] == [(time(12), time(13), "午餐休息")]
            activities = list((await session.scalars(select(Activity).join(DayPlan).where(
                DayPlan.trip_id == result.target_trip_id).order_by(Activity.position))).all())
            assert [a.scheduled_time for a in activities] == [time(9), time(13, 10)]
            routes = list((await session.scalars(select(RouteLeg).where(RouteLeg.from_activity_id == activities[0].id))).all())
            assert len(routes) == 1 and not routes[0].is_estimated
    asyncio.run(scenario())


def test_legacy_review_cannot_rebind_v2_preparation(stack):
    async def scenario():
        service, _, _, owner, *_ = stack
        _, _, legacy = await preview_confirm(stack)
        await service._failure(owner, legacy.id, "injected review", review=True)
        plan, _, _, request = await atomic_preview(stack)
        with pytest.raises(PromotionError) as error:
            await service.review(owner, legacy.id, request)
        assert error.value.code == "candidate_protocol_required"
        assert (await service.get(owner, legacy.id)).prepared_id != plan.id
    asyncio.run(scenario())


def test_atomic_candidate_window_tamper_is_rejected_and_rolled_back(stack, monkeypatch):
    async def scenario():
        from datetime import time
        from app.database import TripArrangementItem
        service, _, _, owner, _, sessions, _ = stack
        _, view, session_id, request = await atomic_preview(stack, lunch=True)
        async with sessions() as session:
            before = await session.scalar(select(func.count()).select_from(Trip))
        original = service._apply_unit
        async def tamper(session, who, operation_id, equivalence):
            op, _ = await service_module_get_operation(session, who, operation_id)
            window = await session.scalar(select(TripArrangementItem).where(
                TripArrangementItem.trip_id == op.target_trip_id, TripArrangementItem.kind == "free_window"))
            window.end_time = time(12, 30)
            await session.flush()
            return await original(session, who, operation_id, equivalence)
        from app.draft_promotion.repository import get_operation as service_module_get_operation
        monkeypatch.setattr(service, "_apply_unit", tamper)
        op = await service.confirm_atomic(owner, request, session_id=session_id, presentation_hash=view["presentation_hash"])
        result = await service.resume(owner, op.id)
        assert result.status == "needs_review" and result.target_trip_id is None
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Trip)) == before
    asyncio.run(scenario())


def test_conversation_generate_modify_save_same_candidate_without_metadata_shell(stack):
    async def scenario():
        from types import SimpleNamespace
        from app.assistant_capabilities import CapabilityDecision
        from app.assistant_turn import semantic_turn
        from app.database import AssistantSession
        from app.drafts.contracts import DraftPlan
        service, repo, places, owner, _, sessions, _ = stack
        session_id = uuid4()
        async with sessions() as db, db.begin():
            db.add(AssistantSession(id=session_id, messages=[], applied_actions={}))
        plan = DraftPlan.model_validate({"schema_version": 2, "schedule_constraints": {
            "start_date": "2026-11-01", "daily_start_time": "09:00", "daily_end_time": "18:00", "transport_mode": "walk"},
            "days": [{"day_index": 1, "title": "测试一天", "items": [
                {"item_ref": f"visit-{i}", "name": place.name, "duration_minutes": 90,
                 "duration_source": "planning_allocation"} for i, place in enumerate(places.items)]}]})
        async def search(query):
            from app.place_content.contracts import SearchResponse
            assert query.category is None
            return SearchResponse(items=[p for p in places.items if p.name == query.query], page=1, page_size=12, status="ok")
        places.search = search
        port = SimpleNamespace(owner=owner, draft_repository=repo, service=places)
        command = {"action": "generate", "source_quote": "创建杭州2026-11-01的一日安排", "plan": plan.model_dump(mode="json")}
        decision = CapabilityDecision(intent="create", city="杭州", authorization_quote=command["source_quote"],
            reason_code="explicit_write", creation={"destination": "杭州", "start_date": "2026-11-01", "end_date": "2026-11-01"},
            candidate_command=command)
        async def selector(*args):
            return decision
        settings = SimpleNamespace(saved_intentions_enabled=False)
        message = "创建杭州2026-11-01的一日安排，09:00出发18:00前结束，步行，只去测试地点0和测试地点1，先看候选。"
        async with sessions() as db:
            before = await db.scalar(select(func.count()).select_from(Trip))
            await db.rollback()
            row, _, _ = await semantic_turn(db, session_id, message, uuid4(), {"topic_id": "chain"}, port, settings, selector)
            assert row.pending_action and row.pending_action.get("kind") == "itinerary_candidate_v2", row.messages
            view = row.pending_action["presentation"]
            assert view["stage"] == "ready" and row.trip_id is None, view
            assert await db.scalar(select(func.count()).select_from(Trip)) == before
            draft_id = view["draft_id"]
        decision = CapabilityDecision(intent="modify", reason_code="explicit_write", authorization_quote="测试地点0改成120分钟",
            candidate_command={"action": "modify", "source_quote": "测试地点0改成120分钟", "patches": [
                {"item_ref": "visit-0", "source_quote": "测试地点0改成120分钟", "duration_minutes": 120}]})
        async with sessions() as db:
            row, _, _ = await semantic_turn(db, session_id, "测试地点0改成120分钟", uuid4(), {"topic_id": "chain"}, port, settings, selector)
            view = row.pending_action["presentation"]
            assert view["draft_id"] == draft_id and view["stops"][0]["duration_minutes"] == 120, row.messages
            assert view["stops"][1]["duration_minutes"] == 90 and row.trip_id is None
            assert view['stage'] == 'needs_input' and view['stops'][1]['start_time'] == '10:40'
        # A local extension must not silently move its peer. Resolve the
        # conflict with a shorter edit, then adopt the newly displayed content.
        decision = CapabilityDecision(intent='modify', reason_code='explicit_write', authorization_quote='测试地点0改成60分钟',
            candidate_command={'action':'modify','source_quote':'测试地点0改成60分钟','patches':[
                {'item_ref':'visit-0','source_quote':'测试地点0改成60分钟','duration_minutes':60}]})
        async with sessions() as db:
            row, _, _ = await semantic_turn(db, session_id, '测试地点0改成60分钟', uuid4(), {'topic_id':'chain'}, port, settings, selector)
            view = row.pending_action['presentation']
            assert view['stage'] == 'ready' and view['stops'][1]['start_time'] == '10:40'
        decision = CapabilityDecision(intent="create", reason_code="explicit_write", authorization_quote="采用并保存这份安排",
            candidate_command={"action": "adopt", "source_quote": "采用并保存这份安排"})
        save_id = uuid4()
        async with sessions() as db:
            row, _, _ = await semantic_turn(db, session_id, "采用并保存这份安排", save_id, {"topic_id": "chain"}, port, settings, selector)
            assert row.trip_id is not None and row.pending_action is None, row.messages
            trip_id = row.trip_id
        async with sessions() as db:
            row, _, _ = await semantic_turn(db, session_id, "采用并保存这份安排", save_id, {"topic_id": "chain"}, port, settings, selector)
            assert row.trip_id == trip_id
            assert await db.scalar(select(func.count()).select_from(Trip)) == before + 1
    asyncio.run(scenario())


@pytest.mark.parametrize("message,kind", [
    ("保存当前候选会怎样？", "question"),
    ("出发日期改成2026-11-02", "date"),
    ("测试地点0改成120分钟，这次总预算不得超过100元", "compound"),
    ("改去南京，保存当前候选", "city_save"),
])
def test_conversation_rejects_inquiry_and_changed_conditions_without_partial_write(stack, monkeypatch, message, kind):
    async def scenario():
        from types import SimpleNamespace
        from app.assistant_capabilities import CapabilityDecision, failure_bundle
        from app.assistant_turn import semantic_turn
        service, repo, places, owner, _, sessions, _ = stack
        _, initial, session_id, _ = await atomic_preview(stack)
        if kind == "date":
            decision = CapabilityDecision(intent="direct", reason_code="stable_knowledge", response_purpose="conditions_only",
                memory_updates=[{"field": "start_date", "value": "2026-11-02", "source_quote": message}])
        elif kind == "compound":
            decision = CapabilityDecision(intent="modify", reason_code="explicit_write", authorization_quote="测试地点0改成120分钟",
                candidate_command={"action": "modify", "source_quote": "测试地点0改成120分钟", "patches": [
                    {"item_ref": "visit-0", "source_quote": "测试地点0改成120分钟", "duration_minutes": 120}]})
        else:
            quote = "保存当前候选"
            decision = CapabilityDecision(intent="create", city="南京" if kind == "city_save" else "", reason_code="explicit_write", authorization_quote=quote,
                candidate_command={"action": "adopt", "source_quote": quote})
        async def selector(*args):
            return decision
        async def answer(settings, selected, text, history, envelope, *args):
            return failure_bundle(envelope, "只解释保存流程，尚未执行。"), "complete"
        monkeypatch.setattr("app.assistant_turn.answer_with_capabilities", answer)
        port = SimpleNamespace(owner=owner, draft_repository=repo, service=places)
        async with sessions() as db:
            before = await db.scalar(select(func.count()).select_from(Trip))
            await db.rollback()
            row, _, _ = await semantic_turn(db, session_id, message, uuid4(), {"topic_id": "atomic-test"}, port,
                SimpleNamespace(saved_intentions_enabled=False), selector)
            assert row.trip_id is None, row.messages
            assert await db.scalar(select(func.count()).select_from(Trip)) == before
            current = repo.get(owner, UUID(initial["draft_id"]))
            assert current.version == initial["draft_version"]
            if kind in {"date", "compound"}:
                assert row.pending_action["presentation"]["stage"] == "stale", row.messages
            if kind == "city_save":
                assert row.pending_action is None, row.messages
    asyncio.run(scenario())


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
