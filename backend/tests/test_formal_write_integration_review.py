"""Integration-review counterexamples, real isolated PostgreSQL only."""
import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import delete, select, text

from app.database import DayPlan, Trip, TripPreferences
from app.main import app
from app.repository import create_trip
from app.schemas import TripCreate
from test_formal_write_protection import sample, current, pending_revision


def test_missing_dynamic_replan_preserves_not_found_status(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(f"/api/v1/trips/{uuid4()}/execution/replan", json={"trigger": "user_change", "details": "synthetic"})
            assert response.status_code == 404, response.text
    asyncio.run(scenario())


def test_accept_missing_preferences_does_not_release_parent_lock(sample, monkeypatch):
    import app.plan_revision_service as revisions
    original = revisions.validate_candidate_plan
    async def scenario():
        revision = await pending_revision(sample)
        async with sample.sessions() as s, s.begin():
            await s.execute(delete(TripPreferences).where(TripPreferences.trip_id == sample.trip_id))
        held, release = asyncio.Event(), asyncio.Event()
        async def pause(*args, **kwargs):
            result = await original(*args, **kwargs)
            held.set()
            await release.wait()
            return result
        monkeypatch.setattr(revisions, "validate_candidate_plan", pause)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            accepting = asyncio.create_task(c.post(f"/api/v1/plan-revisions/{revision}/accept"))
            await asyncio.wait_for(held.wait(), 5)
            editing = asyncio.create_task(c.post(f"/api/v1/day-plans/{sample.days[0].id}/activities",
                json={"place_id": str(sample.places[2].id)}))
            try:
                for _ in range(150):
                    async with sample.sessions() as s:
                        blocked = await s.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND cardinality(pg_blocking_pids(pid))>0"))
                    if blocked or editing.done():
                        break
                    await asyncio.sleep(.01)
                locked = bool(blocked) and not editing.done()
            finally:
                release.set()
            a, b = await asyncio.wait_for(asyncio.gather(accepting, editing), 8)
        assert locked and [a.status_code, b.status_code] == [200, 409], {
            "parent_lock_retained": locked, "accept": a.status_code, "edit": b.status_code,
            "final": await current(sample)}
    asyncio.run(scenario())


def test_accept_missing_preferences_creation_rolls_back_on_failure(sample, monkeypatch):
    async def crash(*_args):
        raise RuntimeError("synthetic failure after candidate writes")
    async def scenario():
        revision = await pending_revision(sample)
        async with sample.sessions() as s, s.begin():
            await s.execute(delete(TripPreferences).where(TripPreferences.trip_id == sample.trip_id))
        before = await current(sample)
        monkeypatch.setattr("app.plan_revision_service.supersede_navigation_sessions_for_itinerary", crash)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
            assert (await c.post(f"/api/v1/plan-revisions/{revision}/accept")).status_code == 500
        assert await current(sample) == before
        async with sample.sessions() as s:
            assert await s.get(TripPreferences, sample.trip_id) is None
    asyncio.run(scenario())


def test_explicit_null_budget_retains_existing_linked_clear_semantics(sample):
    async def scenario():
        async with sample.sessions() as s, s.begin():
            trip = await s.get(Trip, sample.trip_id)
            trip.total_budget_fen, trip.daily_budget_fen = None, 5000
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            response = await c.put(f"/api/v1/trips/{sample.trip_id}", json={"version": 1, "total_budget_fen": None})
            assert response.status_code == 200, response.text
            assert response.json()["daily_budget_fen"] is None
            assert response.json()["version"] == 2
    asyncio.run(scenario())


def test_invalid_cross_trip_move_rejects_without_locking_foreign_day(sample):
    async def scenario():
        async with sample.sessions() as s, s.begin():
            other = await create_trip(s, TripCreate(title="other synthetic trip", destination="南京市",
                start_date=sample.days[0].date, end_date=sample.days[1].date), commit=False)
            other_day = await s.scalar(select(DayPlan.id).where(DayPlan.trip_id == other.id))
        before = await current(sample)
        async with sample.sessions() as blocker:
            await blocker.scalar(select(DayPlan).where(DayPlan.id == other_day).with_for_update())
            async with sample.sessions() as writer:
                # Fail fast if the command even tries to lock another Trip's day.
                await writer.execute(text("SET LOCAL lock_timeout='300ms'"))
                from app.planner_repository import move_activity, InvalidActivityMoveError
                from app.schemas import ActivityMoveRequest
                try:
                    await move_activity(writer, sample.activities[0].id, ActivityMoveRequest(
                        version=1, target_day_plan_id=other_day, target_position=0))
                except InvalidActivityMoveError:
                    pass
                else:
                    raise AssertionError("cross-Trip move must retain its existing rejection")
        assert await current(sample) == before
    asyncio.run(scenario())
