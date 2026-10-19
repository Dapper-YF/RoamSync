"""Stage C contract: unknown remains unknown; one Trip owns the decisions."""
import asyncio
from datetime import time
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.database import Activity, PlanRevision, Trip, TripArrangementItem
from app.main import app
from test_formal_write_protection import sample, current, pending_revision


async def create_item(c, x, version, **fields):
    return await c.post(f"/api/v1/trips/{x.trip_id}/arrangement-items", json={
        "id": str(uuid4()), "expected_version": version, "source_ref": "synthetic-explicit-user",
        **fields})


def test_nanjing_mixed_arrangement_roundtrip_without_fake_times(sample):
    async def scenario():
        async with sample.sessions() as s, s.begin():
            fixed = await s.get(Activity, sample.activities[0].id)
            fixed.day_plan_id, fixed.scheduled_time, fixed.schedule_locked = sample.days[1].id, time(14), True
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            a = await create_item(c, sample, 1, kind="selected", label="南京博物院", place_id=str(sample.places[2].id))
            assert a.status_code == 201, a.text
            b = await create_item(c, sample, 2, kind="optional", label="玄武湖", place_id=str(sample.places[3].id))
            assert b.status_code == 201, b.text
            window = await create_item(c, sample, 3, kind="free_window", label="自由活动", day_date="2026-11-07", start="15:00", end="16:00")
            assert window.status_code == 201, window.text
            state = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()
            assert state["version"] == 4 and len(state["items"]) == 3
            selected = next(i for i in state["items"] if i["id"] == a.json()["id"])
            assert selected["start"] is None and selected["end"] is None and selected["activity_id"] is None
            assert selected["source_ref"] == "synthetic-explicit-user"
            fixed = next(a for a in state["days"][1]["activities"] if a["id"] == str(sample.activities[0].id))
            assert fixed["scheduled_time"] == "14:00:00" and fixed["schedule_locked"] is True
            assert len((await current(sample))["activities"]) == 2
    asyncio.run(scenario())


def test_accept_revalidates_reserved_window(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await create_item(c, sample, 1, kind="free_window", label="留白", day_date="2026-11-07", start="15:00", end="16:00")).status_code == 201
            rid = await pending_revision(sample)
            async with sample.sessions() as s, s.begin():
                revision = await s.get(PlanRevision, rid)
                data = dict(revision.proposed_snapshot)
                data["activities"] = [dict(i) for i in data["activities"]]
                data["activities"][1]["planned_start_time"] = "15:30:00"
                revision.proposed_snapshot = data
            before = await current(sample)
            response = await c.post(f"/api/v1/plan-revisions/{rid}/accept")
            assert response.status_code == 422, response.text
            assert "arrangement_free_window_conflict" in {e["code"] for e in response.json()["detail"]["errors"]}
            assert await current(sample) == before
    asyncio.run(scenario())


def test_concurrent_choice_writes_do_not_lose_a_success(sample):
    from test_formal_write_protection import wait_for_blocked
    async def scenario():
        async with sample.sessions() as blocker:
            await blocker.scalar(select(Trip).where(Trip.id == sample.trip_id).with_for_update())
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
                tasks = [asyncio.create_task(create_item(c, sample, 1, kind="selected", label=label)) for label in ("博物院", "玄武湖")]
                await wait_for_blocked(sample, 2)
                await blocker.rollback()
                responses = await asyncio.wait_for(asyncio.gather(*tasks), 6)
                assert sorted(r.status_code for r in responses) == [201, 409]
                rows = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()
                assert rows["version"] == 2 and len(rows["items"]) == 1
    asyncio.run(scenario())


def test_failed_choice_write_rolls_back_item_and_version(sample, monkeypatch):
    async def fail(*args):
        raise RuntimeError("synthetic failure after relation flush")
    monkeypatch.setattr("app.arrangement_service.validate_current_arrangement", fail)
    async def scenario():
        before = await current(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
            assert (await create_item(c, sample, 1, kind="selected", label="博物院")).status_code == 500
            assert (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()["items"] == []
        assert await current(sample) == before
    asyncio.run(scenario())


def test_manual_time_edit_cannot_enter_reserved_window(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await create_item(c, sample, 1, kind="free_window", label="留白", day_date="2026-11-07", start="15:00", end="16:00")).status_code == 201
            before = await current(sample)
            response = await c.put(f"/api/v1/activities/{sample.activities[1].id}", json={"version": 1, "scheduled_time": "15:30"})
            assert response.status_code == 422, response.text
            assert await current(sample) == before
    asyncio.run(scenario())


def test_blank_day_is_valid_only_with_explicit_day_coverage_permission(sample):
    from app.schemas import CandidatePlanSnapshot
    from app.plan_revision_service import validate_candidate_plan
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            # The second day has no Activity. Explicitly reserve it as free.
            assert (await create_item(c, sample, 1, kind="free_window", label="整天留空", day_date="2026-11-08", start="00:00", end="23:59")).status_code == 201
        async with sample.sessions() as s:
            empty = CandidatePlanSnapshot(activities=[])
            explicit = await validate_candidate_plan(s, sample.trip_id, empty, required_dates={sample.days[1].date})
            unspecified = await validate_candidate_plan(s, sample.trip_id, empty, required_dates={sample.days[0].date})
            assert "missing_plan_days" not in {e.code for e in explicit.errors}
            assert "missing_plan_days" in {e.code for e in unspecified.errors}
    asyncio.run(scenario())


def test_linked_item_cannot_be_omitted_by_current_version_candidate(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            added = await create_item(c, sample, 1, kind="selected", label="博物院", place_id=str(sample.places[2].id))
            iid = added.json()["id"]
            response = await c.post(f"/api/v1/trips/{sample.trip_id}/arrangement-items/{iid}/schedule", json={"expected_version": 2,
                "day_plan_id": str(sample.days[1].id), "scheduled_time": "14:00", "duration_minutes": 60})
            assert response.status_code == 200, response.text
            rid = await pending_revision(sample)
            before = await current(sample)
            rejected = await c.post(f"/api/v1/plan-revisions/{rid}/accept")
            assert rejected.status_code == 422, rejected.text
            assert "arrangement_decision_omitted" in {e["code"] for e in rejected.json()["detail"]["errors"]}
            assert await current(sample) == before
    asyncio.run(scenario())


def test_accept_can_bind_selected_item_atomically_and_replay(sample):
    from app.schemas import CandidateActivity
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            added = await create_item(c, sample, 1, kind="selected", label="博物院", place_id=str(sample.places[2].id))
            assert added.status_code == 201
            iid = added.json()["id"]
            rid = await pending_revision(sample)
            async with sample.sessions() as s, s.begin():
                rev = await s.get(PlanRevision, rid)
                data = dict(rev.proposed_snapshot)
                data["activities"] = [*data["activities"], CandidateActivity(candidate_id=f"arrangement:{iid}", day_date=sample.days[1].date,
                    place_candidate_id=sample.places[2].id, planned_start_time=time(14), duration_minutes=60,
                    estimated_cost_fen=0, transport_mode_to_here="walk", source_ids=[sample.places[2].source_record_id]).model_dump(mode="json")]
                rev.proposed_snapshot = data
            accepted = await c.post(f"/api/v1/plan-revisions/{rid}/accept")
            assert accepted.status_code == 200, accepted.text
            once = await current(sample)
            rows = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()["items"]
            item = next(i for i in rows if i["id"] == iid)
            assert item["activity_id"] in {a["id"] for a in once["activities"]}
            assert item["source_ref"] == added.json()["source_ref"]
            assert item["decision_ref"] == f"accept:{rid}"
            assert len(once["activities"]) == 3
            assert (await c.post(f"/api/v1/plan-revisions/{rid}/accept")).status_code == 200
            assert await current(sample) == once
    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", ["precision", "foreign_key"])
def test_database_rejects_invalid_precision_or_place_identity(sample, invalid):
    from sqlalchemy.exc import IntegrityError
    async def scenario():
        async with sample.sessions() as s:
            row = TripArrangementItem(trip_id=sample.trip_id, kind="selected", label="synthetic", identity_key="test-invalid",
                source_ref="synthetic", decision_ref="synthetic", place_id=uuid4() if invalid == "foreign_key" else None,
                start_time=time(9) if invalid == "precision" else None)
            s.add(row)
            with pytest.raises(IntegrityError):
                await s.flush()
            await s.rollback()
        assert (await current(sample))["version"] == 1
    asyncio.run(scenario())


def test_deleting_trip_with_place_choice_preserves_existing_cascade_contract(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
            added = await create_item(c, sample, 1, kind="selected", label="博物院", place_id=str(sample.places[2].id))
            assert added.status_code == 201
            removed = await c.delete(f"/api/v1/trips/{sample.trip_id}?confirm=true")
            assert removed.status_code == 204, removed.text
    asyncio.run(scenario())


@pytest.mark.parametrize("locked", [False, True])
def test_returning_scheduled_choice_to_optional_is_atomic_and_protects_fixed(sample, locked):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            added = await create_item(c, sample, 1, kind="selected", label="博物院", place_id=str(sample.places[2].id))
            iid = added.json()["id"]
            path = f"/api/v1/trips/{sample.trip_id}/arrangement-items/{iid}"
            assert (await c.post(path + "/schedule", json={"expected_version": 2, "day_plan_id": str(sample.days[1].id),
                "scheduled_time": "14:00", "duration_minutes": 60, "schedule_locked": locked})).status_code == 200
            before = await current(sample)
            response = await c.put(path, json={"expected_version": 3, "kind": "optional", "label": "博物院",
                "place_id": str(sample.places[2].id), "source_ref": "synthetic-new-decision"})
            assert response.status_code == (422 if locked else 200), response.text
            if locked:
                assert await current(sample) == before
            else:
                assert response.json()["activity_id"] is None and response.json()["kind"] == "optional"
                assert response.json()["source_ref"] == added.json()["source_ref"]
                assert response.json()["decision_ref"] == "synthetic-new-decision"
                assert len((await current(sample))["activities"]) == 2
    asyncio.run(scenario())


def test_duplicate_and_date_shift_preserve_choices_with_remapped_links(sample):
    from datetime import timedelta
    from app.formal_write import lock_trip
    from app.assistant_service import shift_trip_dates
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await create_item(c, sample, 1, kind="free_window", label="自由活动", day_date="2026-11-08", start="15:00", end="16:00")).status_code == 201
            assert (await create_item(c, sample, 2, kind="selected", label="博物院", place_id=str(sample.places[2].id))).status_code == 201
            copied = await c.post(f"/api/v1/trips/{sample.trip_id}/duplicate")
            assert copied.status_code == 201, copied.text
            tid = copied.json()["id"]
            original = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()
            clone = (await c.get(f"/api/v1/trips/{tid}/arrangement-items")).json()
            assert len(clone["items"]) == 2
            assert {i["id"] for i in clone["items"]}.isdisjoint(i["id"] for i in original["items"])
            clone_place = next(i["place_id"] for i in clone["items"] if i["kind"] == "selected")
            assert clone_place != str(sample.places[2].id)
            from uuid import UUID
            async with sample.sessions() as s, s.begin():
                trip = await lock_trip(s, UUID(tid))
                await shift_trip_dates(s, trip, trip.start_date + timedelta(days=7), trip.end_date + timedelta(days=7))
            shifted = (await c.get(f"/api/v1/trips/{tid}/arrangement-items")).json()
            assert next(i["day_date"] for i in shifted["items"] if i["kind"] == "free_window") == "2026-11-15"
            assert (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json() == original
    asyncio.run(scenario())


def test_live_trip_requires_coordination_for_new_precise_time(sample):
    from datetime import datetime, UTC
    from app.database import TripExecution
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            item = await create_item(c, sample, 1, kind="selected", label="博物院", place_id=str(sample.places[2].id))
            async with sample.sessions() as s, s.begin():
                s.add(TripExecution(trip_id=sample.trip_id, status="in_progress", itinerary_version=2,
                    current_date=sample.days[0].date, actual_started_at=datetime.now(UTC)))
            before = await current(sample)
            response = await c.post(f"/api/v1/trips/{sample.trip_id}/arrangement-items/{item.json()['id']}/schedule", json={
                "expected_version": 2, "day_plan_id": str(sample.days[1].id), "scheduled_time": "14:00", "duration_minutes": 60})
            assert response.status_code == 422, response.text
            assert await current(sample) == before
    asyncio.run(scenario())


def test_user_selected_provider_place_can_be_bound_with_explicit_times(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            item = await create_item(c, sample, 1, kind="selected", label="博物院")
            snapshot = {"provider": "amap", "provider_place_id": "synthetic-explicit-place", "name": "博物院", "category": "sight", "neighborhood": "synthetic", "longitude": 118.8, "latitude": 32.05,
                "suggested_duration_minutes": 99, "estimated_cost_fen": 0, "rating": 0, "tags": [], "source_url": "https://www.amap.com/search?id=synthetic-explicit-place"}
            response = await c.post(f"/api/v1/trips/{sample.trip_id}/arrangement-items/{item.json()['id']}/schedule", json={"expected_version": 2,
                "day_plan_id": str(sample.days[1].id), "place_snapshot": snapshot, "scheduled_time": "14:00", "duration_minutes": 60})
            assert response.status_code == 200, response.text
            state = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()
            added = next(a for d in state["days"] for a in d["activities"] if a["id"] == response.json()["activity_id"])
            assert added["duration_minutes"] == 60 and added["scheduled_time"] == "14:00:00"
            assert response.json()["source_ref"] == item.json()["source_ref"]
    asyncio.run(scenario())


def test_item_change_fences_old_candidate_and_old_page(sample):
    async def scenario():
        rid = await pending_revision(sample)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            added = await create_item(c, sample, 1, kind="selected", label="南京博物院")
            assert added.status_code == 201, added.text
            before = await current(sample)
            assert (await c.post(f"/api/v1/plan-revisions/{rid}/accept")).status_code == 409
            assert (await create_item(c, sample, 1, kind="optional", label="玄武湖")).status_code == 409
            assert await current(sample) == before
    asyncio.run(scenario())


def test_schedule_transfer_and_delete_retains_decision_identity(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            added = await create_item(c, sample, 1, kind="selected", label="南京博物院", place_id=str(sample.places[2].id))
            assert added.status_code == 201, added.text
            iid = added.json()["id"]
            path = f"/api/v1/trips/{sample.trip_id}/arrangement-items/{iid}/schedule"
            scheduled = await c.post(path, json={"expected_version": 2, "day_plan_id": str(sample.days[1].id), "scheduled_time": "14:00", "duration_minutes": 60})
            assert scheduled.status_code == 200, scheduled.text
            activity_id = scheduled.json()["activity_id"]
            assert scheduled.json()["id"] == iid and scheduled.json()["source_ref"] == added.json()["source_ref"]
            assert (await c.post(path, json={"expected_version": 2, "day_plan_id": str(sample.days[1].id), "scheduled_time": "14:00", "duration_minutes": 60})).status_code == 409
            assert len((await current(sample))["activities"]) == 3
            assert (await c.delete(f"/api/v1/activities/{activity_id}", headers={"X-Trip-Version": "3"})).status_code == 204
            items = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()["items"]
            previous = next(i for i in items if i["id"] == iid)
            assert previous["kind"] == "cancelled" and previous["activity_id"] is None
            assert previous["source_ref"] == added.json()["source_ref"]
    asyncio.run(scenario())


def test_free_window_rejects_overlapping_activity_and_rolls_back(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            added = await create_item(c, sample, 1, kind="free_window", label="留白", day_date="2026-11-08", start="13:00", end="16:00")
            assert added.status_code == 201, added.text
            choice = await create_item(c, sample, 2, kind="selected", label="南京博物院", place_id=str(sample.places[2].id))
            assert choice.status_code == 201
            before = await current(sample)
            response = await c.post(f"/api/v1/trips/{sample.trip_id}/arrangement-items/{choice.json()['id']}/schedule", json={
                "expected_version": 3, "day_plan_id": str(sample.days[1].id), "scheduled_time": "14:00", "duration_minutes": 60})
            assert response.status_code == 422, response.text
            assert await current(sample) == before
    asyncio.run(scenario())
