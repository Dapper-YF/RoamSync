"""Real PostgreSQL counterexamples: network work must not own business locks."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.database import PlanningRun, Trip, TripPreferences
import app.planning_intent_service as intent_service
import app.planning_run_repository as repository
from app.repository import create_trip
from app.schemas import (
    PlanningRunCreate, SemanticIntentDraft, SemanticIntentOperation, TripCreate,
)


@asynccontextmanager
async def database():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def new_trip(sessions):
    async with sessions() as db:
        trip = await create_trip(db, TripCreate(title="Synthetic transaction probe", destination="南京",
            start_date=date(2026, 11, 7), end_date=date(2026, 11, 7)))
        return trip.id


def force_semantic_fallback(monkeypatch):
    # Keep an explicitly authorized imperative; force the existing fallback so
    # this test exercises a real async provider independently of rule coverage.
    monkeypatch.setattr(intent_service, "_build_rule_semantic_draft", lambda *a, **k:
        SemanticIntentDraft(primary_intent="unsupported", confidence=.1,
            operations=[SemanticIntentOperation(operation="unsupported", raw_text="请帮我规划南京完整行程")],
            parser_version="synthetic-force-fallback"))


def planning_draft(message):
    return SemanticIntentDraft(primary_intent="create_plan", confidence=.95, parser="model",
        parser_version="synthetic-transaction-test", operations=[
            SemanticIntentOperation(operation="create_plan", raw_text=message)])


def test_semantic_network_work_releases_trip_and_caller_transaction(monkeypatch):
    force_semantic_fallback(monkeypatch)

    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            async with sessions() as caller:
                class Provider:
                    async def extract(self, message, context):
                        async with sessions() as other:
                            # NOWAIT makes the old bug a deterministic failure.
                            await other.scalar(select(Trip).where(Trip.id == tid).with_for_update(nowait=True))
                            assert await other.scalar(text("SELECT count(*) FROM pg_stat_activity "
                                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                                "AND state = 'idle in transaction'")) == 0
                        assert not caller.in_transaction(), "network stage retains the caller transaction"
                        return planning_draft(message)
                run = await repository.create_planning_run(caller, tid,
                    PlanningRunCreate(user_request="请帮我规划南京完整行程"), semantic_provider=Provider())
                assert run.status == "queued"
                assert run.base_trip_version == 1

    asyncio.run(scenario())


def test_atomic_new_trip_and_run_are_not_committed_by_repository():
    async def scenario():
        async with database() as sessions:
            async with sessions() as caller:
                trip = await create_trip(caller, TripCreate(title="atomic synthetic", destination="南京",
                    start_date=date(2026, 11, 7), end_date=date(2026, 11, 7)), commit=False)
                tid = trip.id
                # Also cover legacy preferences repair: it must not commit the
                # new Trip/receipt-like business data as a side effect.
                await caller.delete(await caller.get(TripPreferences, tid))
                await caller.flush()
                run = await repository.create_planning_run(caller, tid,
                    PlanningRunCreate(user_request="请帮我规划南京完整行程"), commit=False)
                rid = run.id
                assert run.status == "queued" and caller.in_transaction()
                async with sessions() as observer:
                    assert await observer.get(Trip, tid) is None
                    assert await observer.get(PlanningRun, run.id) is None
                await caller.rollback()
            async with sessions() as check:
                assert await check.get(Trip, tid) is None
                assert await check.get(PlanningRun, rid) is None
    asyncio.run(scenario())


def test_network_preparation_never_discards_a_flushed_caller_write():
    from app.planning_preparation import PlanningPreparationRequiredError
    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            async with sessions() as caller:
                trip = await caller.get(Trip, tid)
                trip.title = "Uncommitted caller decision"
                await caller.flush()
                assert not caller.dirty  # dirty alone cannot detect this case.
                class Provider:
                    async def extract(self, *_args):
                        pytest.fail("network provider ran inside caller transaction")
                with pytest.raises(PlanningPreparationRequiredError):
                    await repository.create_planning_run(caller, tid,
                        PlanningRunCreate(user_request="请帮我规划南京完整行程"), semantic_provider=Provider())
                assert caller.in_transaction()
                assert (await caller.get(Trip, tid)).title == "Uncommitted caller decision"
                await caller.rollback()
            async with sessions() as check:
                assert (await check.get(Trip, tid)).title == "Synthetic transaction probe"
    asyncio.run(scenario())


def test_prepared_intent_is_bound_to_original_request():
    from app.planning_preparation import prepare_planning_intent
    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            async with sessions() as caller:
                prepared = await prepare_planning_intent(caller, tid,
                    PlanningRunCreate(user_request="请帮我规划南京完整行程"))
                with pytest.raises(repository.StalePlanningRunError, match="does not match"):
                    await repository.create_planning_run(caller, tid,
                        PlanningRunCreate(user_request="请重新规划南京全部行程"), prepared_intent=prepared)
                assert not caller.in_transaction()
    asyncio.run(scenario())


def test_prepared_intent_is_not_rerouted_by_legacy_classifier(monkeypatch):
    from app.planning_preparation import prepare_planning_intent
    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            async with sessions() as caller:
                payload = PlanningRunCreate(user_request="请帮我规划南京完整行程")
                prepared = await prepare_planning_intent(caller, tid, payload)
                def forbidden(_message):
                    pytest.fail("legacy router reinterpreted a prepared semantic decision")
                monkeypatch.setattr(repository, "route_travel_goal", forbidden)
                run = await repository.create_planning_run(caller, tid, payload, prepared_intent=prepared)
                assert run.status == "queued"
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_provider_failure_or_cancel_leaves_no_business_lock(monkeypatch, failure):
    force_semantic_fallback(monkeypatch)
    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            async with sessions() as caller:
                class Provider:
                    async def extract(self, *_args):
                        raise failure("synthetic provider interruption")
                with pytest.raises(failure):
                    await repository.create_planning_run(caller, tid,
                        PlanningRunCreate(user_request="请帮我规划南京完整行程"), semantic_provider=Provider())
                assert not caller.in_transaction()
                async with sessions() as check:
                    await check.scalar(select(Trip).where(Trip.id == tid).with_for_update(nowait=True))
                    assert await check.scalar(select(func.count()).select_from(PlanningRun).where(PlanningRun.trip_id == tid)) == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("changed", ["itinerary", "preferences"])
def test_network_result_cannot_be_rebased_onto_changed_facts(monkeypatch, changed):
    force_semantic_fallback(monkeypatch)

    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            entered, release = asyncio.Event(), asyncio.Event()
            class Provider:
                async def extract(self, message, context):
                    entered.set()
                    await release.wait()
                    return planning_draft(message)
            async def work():
                async with sessions() as caller:
                    return await repository.create_planning_run(caller, tid,
                        PlanningRunCreate(user_request="请帮我规划南京完整行程"), semantic_provider=Provider())
            task = asyncio.create_task(work())
            try:
                await asyncio.wait_for(entered.wait(), 5)
                async with sessions() as editor:
                    trip = await editor.scalar(select(Trip).where(Trip.id == tid).with_for_update(nowait=True))
                    if changed == "itinerary":
                        trip.title = "A newer user decision"
                        trip.version += 1
                    else:
                        prefs = await editor.get(TripPreferences, tid)
                        prefs.free_text_requirements = "新要求：完全吃素"
                        prefs.version += 1
                    await editor.commit()
                release.set()
                with pytest.raises(repository.StalePlanningRunError):
                    await task
                async with sessions() as check:
                    assert await check.scalar(select(func.count()).select_from(PlanningRun).where(PlanningRun.trip_id == tid)) == 0
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
