"""The persisted activity contract, not the model prompt, is the safety boundary."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Activity, DayPlan, PlaceCandidate, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.plan_revision_service import validate_candidate_plan
from app.schemas import ActivityCreate, CandidateActivity, CandidatePlanSnapshot


def test_create_contract_enforces_must_do_non_skippable():
    place_id = uuid.uuid4()
    payload = ActivityCreate(place_id=place_id, importance="must_do")
    assert payload.can_skip is False
    with pytest.raises(ValueError, match="must_do activity cannot be skippable"):
        ActivityCreate(place_id=place_id, importance="must_do", can_skip=True)


def _reset(client: TestClient) -> dict:
    assert client.post("/api/v1/demo/reset").status_code == 200
    return client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]["activities"][0]


def test_activity_semantics_persist_with_explicit_provenance_and_invariant():
    with TestClient(app) as client:
        activity = _reset(client)
        assert activity["importance"] == "normal"
        assert activity["can_skip"] is True
        assert activity["minimum_duration_minutes"] is None
        assert activity["can_skip_source"] == "system_default"

        response = client.put(f"/api/v1/activities/{activity['id']}", json={
            "version": activity["version"], "importance": "must_do",
            "minimum_duration_minutes": 30,
        })
        assert response.status_code == 200, response.text
        persisted = response.json()
        assert persisted["importance"] == "must_do"
        assert persisted["can_skip"] is False
        assert persisted["minimum_duration_minutes"] == 30
        assert persisted["importance_source"] == "user_explicit"
        assert persisted["can_skip_source"] == "user_explicit"
        assert persisted["minimum_duration_source"] == "user_explicit"
        refreshed = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]["activities"][0]
        assert refreshed["minimum_duration_minutes"] == 30

        illegal = client.put(f"/api/v1/activities/{activity['id']}", json={
            "version": persisted["version"], "can_skip": True,
        })
        assert illegal.status_code == 422
        too_long = client.put(f"/api/v1/activities/{activity['id']}", json={
            "version": persisted["version"], "minimum_duration_minutes": persisted["duration_minutes"] + 1,
        })
        assert too_long.status_code == 422


@pytest.mark.parametrize("importance,can_skip,minimum,candidate_duration,expected", [
    ("must_do", False, None, None, "activity_must_do_removed"),
    ("normal", False, None, None, "activity_cannot_be_skipped"),
    ("normal", True, 60, 30, "activity_minimum_duration_violated"),
    ("normal", True, 30, 45, None),
])
def test_candidate_validator_enforces_semantics(importance, can_skip, minimum, candidate_duration, expected):
    with TestClient(app) as client:
        activity = _reset(client)
        update = client.put(f"/api/v1/activities/{activity['id']}", json={
            "version": activity["version"], "importance": importance,
            "can_skip": can_skip, "minimum_duration_minutes": minimum,
        })
        assert update.status_code == 200, update.text

        async def validate() -> list[str]:
            async with session_factory() as session:
                original = await session.get(Activity, uuid.UUID(activity["id"]))
                assert original is not None
                day = await session.get(DayPlan, original.day_plan_id)
                place = await session.get(PlaceCandidate, original.place_candidate_id)
                assert day is not None and place is not None
                candidates = [] if candidate_duration is None else [CandidateActivity(
                    candidate_id="same-place", day_date=day.date, place_candidate_id=place.id,
                    planned_start_time=original.scheduled_time, duration_minutes=candidate_duration,
                    estimated_cost_fen=original.estimated_cost_fen, transport_mode_to_here="walk",
                    source_ids=[place.source_record_id], replaces_activity_id=original.id,
                )]
                result = await validate_candidate_plan(session, DEMO_TRIP_ID, CandidatePlanSnapshot(activities=candidates))
                return [issue.code for issue in result.errors]

        codes = asyncio.run(validate())
        if expected:
            assert expected in codes
        else:
            assert not any(code.startswith("activity_") for code in codes)
