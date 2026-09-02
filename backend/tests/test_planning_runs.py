import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import CandidatePlanSnapshot


def _create_trip(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/trips",
        json={
            "title": "Nanchang intelligent planning",
            "destination": "南昌市",
            "start_date": "2026-10-01",
            "end_date": "2026-10-02",
            "total_budget_fen": 80000,
            "daily_budget_fen": 40000,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_planning_run_captures_the_formal_trip_version() -> None:
    with TestClient(app) as client:
        trip = _create_trip(client)
        created = client.post(
            f"/api/v1/trips/{trip['id']}/planning-runs",
            json={"run_type": "initial_plan", "user_request": "  历史、美食，步行适量  "},
        )
        assert created.status_code == 201
        run = created.json()
        assert run["status"] == "queued"
        assert run["base_trip_version"] == trip["version"]
        assert run["user_request"] == "历史、美食，步行适量"

        fetched = client.get(f"/api/v1/planning-runs/{run['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["trip_id"] == trip["id"]

        not_ready = client.get(f"/api/v1/planning-runs/{run['id']}/revision")
        assert not_ready.status_code == 404
        assert not_ready.json()["detail"] == "planning revision not ready"


def test_planning_run_not_found_and_request_validation() -> None:
    with TestClient(app) as client:
        missing_id = uuid.uuid4()
        assert client.post(
            f"/api/v1/trips/{missing_id}/planning-runs", json={}
        ).status_code == 404
        assert client.get(f"/api/v1/planning-runs/{missing_id}").status_code == 404
        trip = _create_trip(client)
        invalid = client.post(
            f"/api/v1/trips/{trip['id']}/planning-runs",
            json={"run_type": "unknown"},
        )
        assert invalid.status_code == 422


def test_candidate_plan_requires_unique_structured_activities() -> None:
    place_id = uuid.uuid4()
    activity = {
        "candidate_id": "candidate-1",
        "day_date": "2026-10-01",
        "place_candidate_id": str(place_id),
        "planned_start_time": "09:00:00",
        "duration_minutes": 90,
        "estimated_cost_fen": 5000,
        "transport_mode_to_here": "transit",
        "source_ids": [],
    }
    with pytest.raises(ValidationError):
        CandidatePlanSnapshot.model_validate({"activities": [activity, activity]})

    parsed = CandidatePlanSnapshot.model_validate({"activities": [activity]})
    assert parsed.activities[0].estimated_cost_fen == 5000
