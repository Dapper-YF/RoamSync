"""Actual PostgreSQL/API regression evidence. No external map/model requests."""
import asyncio
import os
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url

from app.database import Activity, DayPlan, PlaceCandidate, PlanningRun, PlanRevision, RouteLeg, SourceRecord, Trip, TripPreferences, session_factory
from app.main import app
from app.plan_revision_service import validate_candidate_plan
from app.planning_run_repository import save_plan_revision
from app.repository import create_trip
from app.schemas import CandidateActivity, CandidatePlanSnapshot, TripCreate


@pytest.fixture
def sample(monkeypatch):
    url = os.environ.get("DATABASE_URL", "")
    assert make_url(url).database == "roamsync_test_write_protection"
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    previous_bind = session_factory.kw["bind"]
    session_factory.configure(bind=engine)
    async def route(*_args):
        return SimpleNamespace(distance_meters=600, duration_minutes=10, provider="write-test-fixture", is_estimated=False, path=[], alternatives=[])
    monkeypatch.setattr("app.maps_service.resolve_route_result", route)
    monkeypatch.setattr("app.candidate_route_service.resolve_route_result", route)
    async def setup():
        async with sessions() as s, s.begin():
            trip = await create_trip(s, TripCreate(title="formal write isolation test", destination="南京市",
                start_date=date(2026, 11, 7), end_date=date(2026, 11, 8)), commit=False)
            days = list((await s.scalars(select(DayPlan).where(DayPlan.trip_id == trip.id).order_by(DayPlan.position))).all())
            places = []
            for n in range(4):
                source = SourceRecord(trip_id=trip.id, title="synthetic fixture", url="https://fixture.invalid/write", provider="fixture", queried_at=datetime.now(UTC), confidence="low")
                s.add(source)
                await s.flush()
                place = PlaceCandidate(trip_id=trip.id, source_record_id=source.id, slug=str(uuid4()), name=f"测试地点{n}",
                    category="sight", neighborhood="fixture", description="synthetic only", longitude=118.8, latitude=32.05,
                    suggested_duration_minutes=30, estimated_cost_fen=0, rating=0, tags=[])
                s.add(place)
                await s.flush()
                places.append(place)
            activities = [Activity(day_plan_id=days[0].id, place_candidate_id=places[n].id,
                scheduled_time=time(9 + n * 2), duration_minutes=30, estimated_cost_fen=0, status="planned", position=n) for n in range(2)]
            s.add_all(activities)
            await s.flush()
            return SimpleNamespace(trip_id=trip.id, days=days, places=places, activities=activities, sessions=sessions)
    value = asyncio.run(setup())
    yield value
    session_factory.configure(bind=previous_bind)
    asyncio.run(engine.dispose())


async def current(x):
    async with x.sessions() as s:
        trip = await s.get(Trip, x.trip_id)
        rows = list((await s.scalars(select(Activity).join(DayPlan).where(DayPlan.trip_id == trip.id).order_by(Activity.id))).all())
        routes = list((await s.scalars(select(RouteLeg).join(DayPlan).where(DayPlan.trip_id == trip.id).order_by(RouteLeg.id))).all())
        return {"version": trip.version, "routes": [(str(r.id), str(r.day_plan_id), str(r.from_activity_id), str(r.to_activity_id), r.duration_minutes) for r in routes], "activities": [
            {"id": str(a.id), "day_id": str(a.day_plan_id), "place_id": str(a.place_candidate_id),
             "version": a.version, "position": a.position, "start": str(a.scheduled_time), "duration": a.duration_minutes,
             "note": a.note, "name": a.custom_name} for a in rows]}


async def pending_revision(x):
    async with x.sessions() as s:
        trip = await s.get(Trip, x.trip_id)
        run = PlanningRun(trip_id=trip.id, run_type="replan", status="validating", user_request="保留现有安排", base_trip_version=trip.version)
        s.add(run)
        await s.flush()
        snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id=f"activity:{a.id}",
            day_date=x.days[0].date, place_candidate_id=a.place_candidate_id, planned_start_time=a.scheduled_time,
            duration_minutes=a.duration_minutes, estimated_cost_fen=0, transport_mode_to_here="walk",
            replaces_activity_id=a.id, source_ids=[x.places[n].source_record_id]) for n, a in enumerate(x.activities)])
        revision = await save_plan_revision(s, run.id, before_snapshot={}, proposed_snapshot=snapshot,
            reason="stale-write regression", difference_summary={}, validation_result={"valid": True, "errors": [], "warnings": []},
            source_ids=[], enrich_routes=True)
        return revision.id


def test_manual_add_api_invalidates_pending_revision(sample):
    async def scenario():
        rid = await pending_revision(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            added = await client.post(f"/api/v1/day-plans/{sample.days[0].id}/activities", json={"place_id": str(sample.places[2].id)})
            assert added.status_code == 201, added.text
            after_edit = await current(sample)
            response = await client.post(f"/api/v1/plan-revisions/{rid}/accept")
            after_accept = await current(sample)
            assert response.status_code == 409, {
                "accept_status": response.status_code, "added_id": added.json()["id"],
                "added_survives": added.json()["id"] in {a["id"] for a in after_accept["activities"]},
                "version_after_edit": after_edit["version"], "body": response.text,
            }
            assert after_accept == after_edit
    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["delete", "move", "order", "route", "update"])
def test_other_manual_writes_stale_old_candidates(sample, operation):
    async def scenario():
        rid = await pending_revision(sample)
        before = await current(sample)
        first, second = sample.activities
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            if operation == "delete":
                response = await c.delete(f"/api/v1/activities/{second.id}")
            elif operation == "move":
                response = await c.post(f"/api/v1/activities/{second.id}/move", json={"version": second.version, "target_day_plan_id": str(sample.days[1].id), "target_position": 0})
            elif operation == "order":
                response = await c.put(f"/api/v1/day-plans/{sample.days[0].id}/activity-order", json={"activity_ids": [str(second.id), str(first.id)]})
            elif operation == "route":
                response = await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"})
            else:
                response = await c.put(f"/api/v1/activities/{first.id}", json={"version": first.version, "duration_minutes": 45})
            assert response.status_code in {200, 204}, response.text
            edited = await current(sample)
            assert edited["version"] == before["version"] + 1
            accepted = await c.post(f"/api/v1/plan-revisions/{rid}/accept")
            assert accepted.status_code == 409, accepted.text
            assert await current(sample) == edited
    asyncio.run(scenario())


def test_read_and_noop_do_not_advance_formal_version(sample):
    async def scenario():
        before = await current(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.get(f"/api/v1/trips/{sample.trip_id}/days")).status_code == 200
            response = await c.put(f"/api/v1/activities/{sample.activities[0].id}", json={"version": sample.activities[0].version, "note": None})
            assert response.status_code == 200, response.text
        assert (await current(sample))["version"] == before["version"]
    asyncio.run(scenario())


async def wait_for_blocked(x, count=1):
    for _ in range(150):
        async with x.sessions() as s:
            blocked = await s.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND cardinality(pg_blocking_pids(pid)) > 0"))
        if blocked >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} actual PostgreSQL lock waiters")


def test_concurrent_trip_metadata_updates_reject_stale_version(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            async with sample.sessions() as guard:
                await guard.scalar(select(Trip).where(Trip.id == sample.trip_id).with_for_update())
                tasks = [asyncio.create_task(c.put(f"/api/v1/trips/{sample.trip_id}", json={"version": 1, "title": title})) for title in ("title-a", "title-b")]
                await wait_for_blocked(sample, 2)
                await guard.rollback()
            responses = await asyncio.wait_for(asyncio.gather(*tasks), 8)
        assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
        assert (await current(sample))["version"] == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("first", ["edit", "accept"])
def test_concurrent_manual_add_and_accept_are_serialized(sample, monkeypatch, first):
    import app.planner_repository as planner
    import app.plan_revision_service as revisions
    async def scenario():
        rid = await pending_revision(sample)
        held, release = asyncio.Event(), asyncio.Event()
        target = planner.recalculate_day_route if first == "edit" else revisions.validate_candidate_plan
        async def pause(*args, **kwargs):
            held.set()
            await release.wait()
            return await target(*args, **kwargs)
        monkeypatch.setattr(planner if first == "edit" else revisions,
            "recalculate_day_route" if first == "edit" else "validate_candidate_plan", pause)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            def edit():
                return c.post(f"/api/v1/day-plans/{sample.days[0].id}/activities", json={"place_id": str(sample.places[2].id)})
            def accept():
                return c.post(f"/api/v1/plan-revisions/{rid}/accept")
            leader = asyncio.create_task(edit() if first == "edit" else accept())
            await asyncio.wait_for(held.wait(), 5)
            follower = asyncio.create_task(accept() if first == "edit" else edit())
            await wait_for_blocked(sample)
            release.set()
            a, b = await asyncio.wait_for(asyncio.gather(leader, follower), 8)
            assert a.status_code == (201 if first == "edit" else 200), a.text
            assert b.status_code == 409, b.text
        assert len((await current(sample))["activities"]) == (3 if first == "edit" else 2)
    asyncio.run(scenario())


def test_two_concurrent_activity_edits_cannot_lose_a_successful_write(sample, monkeypatch):
    import app.formal_write as protection
    original = protection.lock_trip
    async def scenario():
        held, release = asyncio.Event(), asyncio.Event()
        async def pause(*args, **kwargs):
            trip = await original(*args, **kwargs)
            if asyncio.current_task().get_name() == "leader-edit":
                held.set()
                await release.wait()
            return trip
        monkeypatch.setattr(protection, "lock_trip", pause)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            async def update(note):
                return await c.put(f"/api/v1/activities/{sample.activities[0].id}", json={"version": 1, "note": note})
            a = asyncio.create_task(update("first"), name="leader-edit")
            await asyncio.wait_for(held.wait(), 5)
            b = asyncio.create_task(update("second"))
            await wait_for_blocked(sample)
            release.set()
            results = await asyncio.wait_for(asyncio.gather(a, b), 8)
        assert [r.status_code for r in results] == [200, 409]
        row = next(a for a in (await current(sample))["activities"] if a["id"] == str(sample.activities[0].id))
        assert row["note"] == "first" and row["version"] == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["add", "delete", "move", "order", "route", "update"])
def test_failed_transaction_rolls_back_every_formal_change(sample, monkeypatch, operation):
    import app.planner_repository as planner
    target = planner._recalculate_schedule_from_saved_route if operation == "update" else planner.recalculate_day_route
    async def fail(*args, **kwargs):
        await target(*args, **kwargs)
        await args[0].flush()
        raise RuntimeError("synthetic route/transaction failure")
    monkeypatch.setattr(planner, "_recalculate_schedule_from_saved_route" if operation == "update" else "recalculate_day_route", fail)
    async def scenario():
        before = await current(sample)
        first, second = sample.activities
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
            if operation == "add":
                r = await c.post(f"/api/v1/day-plans/{sample.days[0].id}/activities", json={"place_id": str(sample.places[2].id)})
            elif operation == "delete":
                r = await c.delete(f"/api/v1/activities/{second.id}")
            elif operation == "move":
                r = await c.post(f"/api/v1/activities/{second.id}/move", json={"version": 1, "target_day_plan_id": str(sample.days[1].id), "target_position": 0})
            elif operation == "order":
                r = await c.put(f"/api/v1/day-plans/{sample.days[0].id}/activity-order", json={"activity_ids": [str(second.id), str(first.id)]})
            elif operation == "route":
                r = await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"})
            else:
                r = await c.put(f"/api/v1/activities/{first.id}", json={"version": 1, "duration_minutes": 45})
            assert r.status_code == 500
        assert await current(sample) == before
    asyncio.run(scenario())


def test_retry_does_not_duplicate_add_or_accept(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            path = f"/api/v1/day-plans/{sample.days[0].id}/activities"
            payload = {"place_id": str(sample.places[2].id)}
            assert (await c.post(path, json=payload)).status_code == 201
            once = await current(sample)
            assert (await c.post(path, json=payload)).status_code == 409
            assert await current(sample) == once
        # Existing Accept replay uses the same revision identity, not a new run.
        rid = await pending_revision(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.post(f"/api/v1/plan-revisions/{rid}/accept")).status_code == 200
            once = await current(sample)
            assert (await c.post(f"/api/v1/plan-revisions/{rid}/accept")).status_code == 200
            assert await current(sample) == once
    asyncio.run(scenario())


def test_optional_trip_version_header_and_legacy_body_compatibility(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            path = f"/api/v1/day-plans/{sample.days[0].id}/activities"
            a = await c.post(path, json={"place_id": str(sample.places[2].id)}, headers={"X-Trip-Version": "1"})
            assert a.status_code == 201
            b = await c.post(path, json={"place_id": str(sample.places[3].id)}, headers={"X-Trip-Version": "1"})
            assert b.status_code == 409 and b.json()["detail"]["code"] == "trip_version_conflict"
            assert (await c.post(path, json={"place_id": str(sample.places[3].id)})).status_code == 201
    asyncio.run(scenario())


def test_indirect_schedule_changes_advance_other_activity_version(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"})).status_code == 200
            # Stage B preserves slack: use an actual overlap to exercise the
            # same indirect Activity-version fence instead of compacting a gap.
            r = await c.put(f"/api/v1/activities/{sample.activities[0].id}", json={"version": 1, "duration_minutes": 180})
            assert r.status_code == 200
            second = next(a for a in (await current(sample))["activities"] if a["id"] == str(sample.activities[1].id))
            assert second["start"] != "11:00:00" and second["version"] == 2
            stale = await c.put(f"/api/v1/activities/{sample.activities[1].id}", json={"version": 1, "scheduled_time": "11:00"})
            assert stale.status_code == 409
    asyncio.run(scenario())


def test_delete_selected_run_activity_cannot_deadlock_accept(sample, monkeypatch):
    import app.formal_write as protection
    original = protection.lock_trip
    async def scenario():
        rid = await pending_revision(sample)
        async with sample.sessions() as s, s.begin():
            rev = await s.get(PlanRevision, rid)
            run = await s.get(PlanningRun, rev.planning_run_id)
            run.selected_activity_id = sample.activities[1].id
        held, release = asyncio.Event(), asyncio.Event()
        async def pause(*args, **kwargs):
            trip = await original(*args, **kwargs)
            if asyncio.current_task().get_name() == "delete-first":
                held.set()
                await release.wait()
            return trip
        monkeypatch.setattr(protection, "lock_trip", pause)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            deletion = asyncio.create_task(c.delete(f"/api/v1/activities/{sample.activities[1].id}"), name="delete-first")
            await asyncio.wait_for(held.wait(), 5)
            accepting = asyncio.create_task(c.post(f"/api/v1/plan-revisions/{rid}/accept"))
            await wait_for_blocked(sample)
            release.set()
            a, b = await asyncio.wait_for(asyncio.gather(deletion, accepting), 8)
            assert a.status_code == 204 and b.status_code == 409
    asyncio.run(scenario())


def test_accept_failure_rolls_back_revision_activities_routes_and_version(sample, monkeypatch):
    import app.plan_revision_service as service
    async def crash(*_args):
        raise RuntimeError("synthetic failure after candidate writes")
    async def scenario():
        rid = await pending_revision(sample)
        before = await current(sample)
        monkeypatch.setattr(service, "supersede_navigation_sessions_for_itinerary", crash)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
            assert (await c.post(f"/api/v1/plan-revisions/{rid}/accept")).status_code == 500
        assert await current(sample) == before
        async with sample.sessions() as s:
            assert (await s.get(PlanRevision, rid)).status == "pending"
    asyncio.run(scenario())


def test_requirement_version_remains_independent_and_accept_rechecks_it(sample):
    async def scenario():
        rid = await pending_revision(sample)
        before = await current(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            path = f"/api/v1/trips/{sample.trip_id}/preferences"
            pref = (await c.get(path)).json()
            allowed = {"version", "pace", "interest_categories", "transport_modes", "daily_start_time", "daily_end_time", "meal_preferences", "avoid_categories", "max_walking_minutes", "free_text_requirements"}
            payload = {k: v for k, v in pref.items() if k in allowed}
            payload["daily_end_time"] = "09:15:00"
            changed = await c.put(path, json=payload)
            assert changed.status_code == 200 and changed.json()["version"] == pref["version"] + 1
            assert (await current(sample))["version"] == before["version"]
            rejected = await c.post(f"/api/v1/plan-revisions/{rid}/accept")
            assert rejected.status_code == 422, rejected.text
        assert await current(sample) == before
    asyncio.run(scenario())


def test_repeated_route_recalculation_ignores_row_ids_and_timestamps(sample):
    async def scenario():
        path = f"/api/v1/day-plans/{sample.days[0].id}/route"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.post(path, json={"mode": "walk"})).status_code == 200
            once = await current(sample)
            assert (await c.post(path, json={"mode": "walk"})).status_code == 200
            twice = await current(sample)
        assert twice["version"] == once["version"]
        assert twice["activities"] == once["activities"]
    asyncio.run(scenario())


def test_two_concurrent_accepts_apply_only_once(sample):
    async def scenario():
        rid = await pending_revision(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            responses = await asyncio.wait_for(asyncio.gather(
                c.post(f"/api/v1/plan-revisions/{rid}/accept"), c.post(f"/api/v1/plan-revisions/{rid}/accept")), 8)
        assert [r.status_code for r in responses] == [200, 200]
        assert (await current(sample))["version"] == 2
    asyncio.run(scenario())


def test_concurrent_opposing_moves_have_no_deadlock_or_lost_success(sample):
    async def scenario():
        async with sample.sessions() as s, s.begin():
            a = await s.get(Activity, sample.activities[1].id)
            a.day_plan_id, a.position = sample.days[1].id, 0
        async with sample.sessions() as guard:
            await guard.scalar(select(Trip).where(Trip.id == sample.trip_id).with_for_update())
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
                tasks = [asyncio.create_task(c.post(f"/api/v1/activities/{a.id}/move", json={"version": 1,
                    "target_day_plan_id": str(sample.days[1-n].id), "target_position": 0})) for n, a in enumerate(sample.activities)]
                await wait_for_blocked(sample, 2)
                await guard.rollback()
                responses = await asyncio.wait_for(asyncio.gather(*tasks), 8)
        assert sorted(r.status_code for r in responses) == [200, 409]
        assert len((await current(sample))["activities"]) == 2
    asyncio.run(scenario())


def test_concurrent_requirement_updates_keep_independent_version(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            path = f"/api/v1/trips/{sample.trip_id}/preferences"
            original = (await c.get(path)).json()
            allowed = {"version", "pace", "interest_categories", "transport_modes", "daily_start_time", "daily_end_time", "meal_preferences", "avoid_categories", "max_walking_minutes", "free_text_requirements"}
            base = {k: v for k, v in original.items() if k in allowed}
            async with sample.sessions() as guard:
                await guard.scalar(select(TripPreferences).where(TripPreferences.trip_id == sample.trip_id).with_for_update())
                tasks = [asyncio.create_task(c.put(path, json={**base, "pace": pace})) for pace in ("relaxed", "intensive")]
                await wait_for_blocked(sample, 2)
                await guard.rollback()
            responses = await asyncio.wait_for(asyncio.gather(*tasks), 8)
            assert sorted(r.status_code for r in responses) == [200, 409]
            latest = (await c.get(path)).json()
        assert latest["version"] == original["version"] + 1
        assert (await current(sample))["version"] == 1
    asyncio.run(scenario())
