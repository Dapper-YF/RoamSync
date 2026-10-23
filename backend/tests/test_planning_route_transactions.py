"""Candidate route evidence must not retain a planning transaction."""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app import maps_service
from app.database import PlaceCandidate, PlanningRun, PlanRevision, Trip, TripPreferences
from app.schemas import CandidateActivity, CandidatePlanSnapshot
from app.planning_run_repository import save_plan_revision, StalePlanningRunError, InvalidPlanningRunStateError
from test_formal_write_protection import sample

REAL_ROUTE_RESOLVER = maps_service.resolve_route_result


async def setup_run(x):
    async with x.sessions() as db:
        # Unique cache inputs so another test cannot bypass the provider probe.
        for index, place in enumerate(x.places):
            row = await db.get(PlaceCandidate, place.id)
            row.longitude = 118 + (place.id.int % 900000) / 1000000
            row.latitude = 32 + index / 100
        run = PlanningRun(trip_id=x.trip_id, run_type="replan", status="validating",
            user_request="合成事务探针", base_trip_version=1)
        db.add(run)
        await db.commit()
        snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(
            candidate_id=f"probe-{i}", day_date=x.days[0].date,
            place_candidate_id=p.id, planned_start_time=a.scheduled_time,
            duration_minutes=a.duration_minutes, estimated_cost_fen=0,
            transport_mode_to_here="walk", replaces_activity_id=a.id,
        ) for i, (a, p) in enumerate(zip(x.activities, x.places))])
        return run.id, snapshot


def use_network_probe(monkeypatch, provider):
    # The baseline used its legacy cache resolver; the new boundary uses the
    # detached cache resolver. Both exercise the same real transport seam.
    monkeypatch.setattr("app.candidate_route_service.resolve_route_result", REAL_ROUTE_RESOLVER, raising=False)
    monkeypatch.setattr("app.candidate_route_service.resolve_detached_route_result", maps_service.resolve_detached_route_result)
    monkeypatch.setattr(maps_service, "get_settings", lambda: SimpleNamespace(
        amap_rest_key="synthetic-provider-key", allow_map_estimates=False, route_cache_ttl_seconds=3600))
    monkeypatch.setattr(maps_service, "_fetch_amap_route", provider)


async def save(db, rid, snapshot):
    return await save_plan_revision(db, rid, before_snapshot={}, proposed_snapshot=snapshot,
        reason="synthetic transaction probe", difference_summary={}, validation_result={}, source_ids=[])


def test_route_network_wait_has_no_business_lock_or_open_transaction(sample, monkeypatch):
    async def scenario():
        rid, snapshot = await setup_run(sample)
        async with sample.sessions() as caller:
            async def provider(*_args):
                async with sample.sessions() as probe:
                    await probe.scalar(select(Trip).where(Trip.id == sample.trip_id).with_for_update(nowait=True))
                    await probe.scalar(select(PlanningRun).where(PlanningRun.id == rid).with_for_update(nowait=True))
                    assert await probe.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                        "AND pid <> pg_backend_pid() AND state = 'idle in transaction'")) == 0
                assert not caller.in_transaction()
                return 600, 10, "synthetic-map", False, [[118, 32], [118.1, 32.1]], []
            use_network_probe(monkeypatch, provider)
            revision = await save(caller, rid, snapshot)
            assert len(revision.proposed_snapshot["route_legs"]) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("changed", ["itinerary", "preferences", "cancel"])
def test_route_network_result_is_rejected_after_facts_change(sample, monkeypatch, changed):
    async def scenario():
        rid, snapshot = await setup_run(sample)
        entered, release = asyncio.Event(), asyncio.Event()
        async def provider(*_args):
            entered.set()
            await release.wait()
            return 600, 10, "synthetic-map", False, [[118, 32], [118.1, 32.1]], []
        use_network_probe(monkeypatch, provider)
        async def work():
            async with sample.sessions() as caller:
                return await save(caller, rid, snapshot)
        task = asyncio.create_task(work())
        try:
            await asyncio.wait_for(entered.wait(), 5)
            async with sample.sessions() as editor:
                trip = await editor.scalar(select(Trip).where(Trip.id == sample.trip_id).with_for_update(nowait=True))
                run = await editor.scalar(select(PlanningRun).where(PlanningRun.id == rid).with_for_update(nowait=True))
                if changed == "itinerary":
                    trip.version += 1
                elif changed == "preferences":
                    (await editor.get(TripPreferences, trip.id)).version += 1
                else:
                    run.status = "cancelled"
                await editor.commit()
            release.set()
            with pytest.raises(InvalidPlanningRunStateError if changed == "cancel" else StalePlanningRunError):
                await task
            async with sample.sessions() as check:
                assert await check.scalar(select(func.count()).select_from(PlanRevision).where(PlanRevision.planning_run_id == rid)) == 0
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_concurrent_saves_only_publish_one_pending_revision(sample):
    async def scenario():
        rid, snapshot = await setup_run(sample)
        async def work():
            async with sample.sessions() as db:
                return await save_plan_revision(db, rid, before_snapshot={}, proposed_snapshot=snapshot,
                    reason="concurrent synthetic", difference_summary={}, validation_result={}, source_ids=[], enrich_routes=False)
        results = await asyncio.gather(work(), work(), return_exceptions=True)
        assert sum(not isinstance(r, BaseException) for r in results) == 1
        assert sum(isinstance(r, InvalidPlanningRunStateError) for r in results) == 1
        async with sample.sessions() as check:
            rows = list((await check.scalars(select(PlanRevision).where(PlanRevision.planning_run_id == rid))).all())
            assert [(row.revision_number, row.status) for row in rows] == [(1, "pending")]
    asyncio.run(scenario())


def test_no_network_persist_rechecks_context_preferences(sample):
    async def scenario():
        rid, snapshot = await setup_run(sample)
        async with sample.sessions() as editor:
            (await editor.get(TripPreferences, sample.trip_id)).version += 1
            await editor.commit()
        async with sample.sessions() as db:
            with pytest.raises(StalePlanningRunError):
                await save_plan_revision(db, rid, before_snapshot={"preferences": {"version": 1}},
                    proposed_snapshot=snapshot, reason="stale deterministic persist", difference_summary={},
                    validation_result={}, source_ids=[], enrich_routes=False)
    asyncio.run(scenario())


def test_route_preparation_rejects_flushed_caller_writes(sample):
    from app.planning_preparation import PlanningPreparationRequiredError
    async def scenario():
        rid, snapshot = await setup_run(sample)
        async with sample.sessions() as db:
            trip = await db.get(Trip, sample.trip_id)
            trip.title = "Pending caller write"
            await db.flush()
            with pytest.raises(PlanningPreparationRequiredError):
                await save(db, rid, snapshot)
            assert db.in_transaction() and trip.title == "Pending caller write"
            await db.rollback()
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_route_provider_interruption_has_no_pending_revision_or_locks(sample, monkeypatch, failure):
    async def scenario():
        rid, snapshot = await setup_run(sample)
        async def provider(*_args):
            raise failure("synthetic network interruption")
        use_network_probe(monkeypatch, provider)
        async with sample.sessions() as db:
            with pytest.raises(failure):
                await save(db, rid, snapshot)
            assert not db.in_transaction()
        async with sample.sessions() as probe:
            await probe.scalar(select(Trip).where(Trip.id == sample.trip_id).with_for_update(nowait=True))
            await probe.scalar(select(PlanningRun).where(PlanningRun.id == rid).with_for_update(nowait=True))
            assert await probe.scalar(select(func.count()).select_from(PlanRevision).where(PlanRevision.planning_run_id == rid)) == 0
    asyncio.run(scenario())
