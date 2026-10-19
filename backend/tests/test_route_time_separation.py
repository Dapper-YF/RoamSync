"""Stage B: map evidence must not authorize compacting an itinerary."""
import asyncio
from datetime import time

import httpx
from sqlalchemy import select

from app.database import Activity
from app.main import app
from test_formal_write_protection import sample, current


async def afternoon(x):
    async with x.sessions() as s, s.begin():
        first, second = [await s.get(Activity, a.id) for a in x.activities]
        first.scheduled_time, first.duration_minutes = time(14), 30
        second.scheduled_time = time(17)


def test_refresh_route_preserves_gap_and_activity_versions(sample):
    async def scenario():
        await afternoon(sample)
        before = await current(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"})
            assert response.status_code == 200, response.text
        assert (await current(sample))["activities"] == before["activities"]
    asyncio.run(scenario())


def test_duration_edit_using_saved_route_preserves_existing_gap(sample):
    async def scenario():
        # Populate the real persisted route first; then create the user's gap.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"})).status_code == 200
            await afternoon(sample)
            r = await c.put(f"/api/v1/activities/{sample.activities[0].id}", json={"version": 1, "duration_minutes": 45})
            assert r.status_code == 200, r.text
        row = next(a for a in (await current(sample))["activities"] if a["id"] == str(sample.activities[1].id))
        assert row["start"] == "17:00:00" and row["version"] == 1
    asyncio.run(scenario())


def test_get_route_does_not_save_formal_route_or_change_version(sample):
    async def scenario():
        await afternoon(sample)
        before = await current(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(f"/api/v1/day-plans/{sample.days[0].id}/route")
            assert response.status_code == 200 and len(response.json()["legs"]) == 1
        assert await current(sample) == before
    asyncio.run(scenario())


def test_explicit_route_time_adjustment_and_fixed_conflict_rollback(sample):
    async def scenario():
        await afternoon(sample)
        async with sample.sessions() as s, s.begin():
            (await s.get(Activity, sample.activities[0].id)).duration_minutes = 180
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            path = f"/api/v1/day-plans/{sample.days[0].id}/route"
            response = await c.post(path, json={"mode": "walk", "adjust_times": True})
            assert response.status_code == 200, response.text
            assert response.json()["activities"][1]["scheduled_time"] == "17:10:00"
            async with sample.sessions() as s, s.begin():
                second = await s.get(Activity, sample.activities[1].id)
                second.scheduled_time, second.schedule_locked = time(17), True
            before = await current(sample)
            conflict = await c.post(path, json={"mode": "walk", "adjust_times": True})
            assert conflict.status_code == 422, conflict.text
            assert await current(sample) == before
    asyncio.run(scenario())


def test_late_map_response_rejected_without_blocking_manual_edit(sample, monkeypatch):
    import app.maps_service as maps
    original = maps.resolve_route_result
    async def scenario():
        held, release = asyncio.Event(), asyncio.Event()
        async def pause(*args):
            held.set()
            await release.wait()
            return await original(*args)
        monkeypatch.setattr(maps, "resolve_route_result", pause)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            query = asyncio.create_task(c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"}))
            await asyncio.wait_for(held.wait(), 3)
            try:
                edited = await asyncio.wait_for(c.put(f"/api/v1/activities/{sample.activities[0].id}", json={"version": 1, "note": "用户新决定"}), 3)
                assert edited.status_code == 200, edited.text
                after = await current(sample)
            finally:
                release.set()
            assert (await asyncio.wait_for(query, 4)).status_code == 409
            assert await current(sample) == after
    asyncio.run(scenario())


def test_network_failure_does_not_modify_formal_state(sample, monkeypatch):
    from app.maps_service import MapProviderError
    async def fail(*args):
        raise MapProviderError("synthetic provider failure")
    monkeypatch.setattr("app.maps_service.resolve_route_result", fail)
    async def scenario():
        before = await current(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"})).status_code == 503
        assert await current(sample) == before
    asyncio.run(scenario())


def test_explicit_adjustment_cannot_exceed_available_day_window(sample):
    async def scenario():
        await afternoon(sample)
        async with sample.sessions() as s, s.begin():
            (await s.get(Activity, sample.activities[0].id)).duration_minutes = 400
        before = await current(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk", "adjust_times": True})
            assert response.status_code == 422, response.text
        assert await current(sample) == before
    asyncio.run(scenario())


def test_saved_route_edit_outside_day_returns_422_and_rolls_back(sample):
    async def scenario():
        await afternoon(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.post(f"/api/v1/day-plans/{sample.days[0].id}/route", json={"mode": "walk"})).status_code == 200
            before = await current(sample)
            response = await c.put(f"/api/v1/activities/{sample.activities[0].id}", json={"version": 1, "duration_minutes": 400})
            assert response.status_code == 422, response.text
            assert await current(sample) == before
    asyncio.run(scenario())
