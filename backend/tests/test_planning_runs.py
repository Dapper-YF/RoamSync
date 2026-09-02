import uuid
import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from sqlalchemy import func, select

from app.database import CandidateRouteLeg, session_factory
from app.planning_run_repository import save_plan_revision
from app.schemas import CandidatePlanSnapshot, PlanningIntent, PlanningRequest


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


def test_first_agent_intent_contract_is_strict() -> None:
    trip_id = uuid.uuid4()
    request = PlanningRequest.model_validate(
        {
            "trip_id": str(trip_id),
            "user_request": "第二天下午放松一点",
            "intent": {
                "intent_type": "modify_day",
                "source_text": "第二天下午放松一点",
                "time_scope": {"day_number": 2, "period": "afternoon"},
            },
        }
    )
    assert request.intent.intent_type == "modify_day"
    assert request.intent.time_scope is not None
    assert request.intent.time_scope.day_number == 2
    with pytest.raises(ValidationError):
        PlanningIntent.model_validate(
            {"intent_type": "delete_trip", "source_text": "删除整个旅行"}
        )


def _save_revision(run_id: str, snapshot: dict) -> str:
    async def save() -> str:
        async with session_factory() as session:
            revision = await save_plan_revision(
                session,
                uuid.UUID(run_id),
                before_snapshot={},
                proposed_snapshot=CandidatePlanSnapshot.model_validate(snapshot),
                reason="deterministic acceptance test",
                difference_summary={},
                validation_result={},
                source_ids=[],
            )
            return str(revision.id)
    return asyncio.run(save())


def _candidate_route_count(revision_id: str) -> int:
    async def count() -> int:
        async with session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count(CandidateRouteLeg.id)).where(
                        CandidateRouteLeg.plan_revision_id == uuid.UUID(revision_id)
                    )
                )
                or 0
            )

    return asyncio.run(count())


def test_accept_revision_applies_once_and_invalidates_stale_routes() -> None:
    with TestClient(app) as client:
        trip = _create_trip(client)
        trip_id = trip["id"]
        days = client.get(f"/api/v1/trips/{trip_id}/days").json()
        # Create one persisted, verified candidate through the existing planner boundary.
        from app.demo_seed import DEMO_TRIP_ID
        client.post("/api/v1/demo/reset")
        candidates = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[:2]
        run = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"run_type": "initial_plan", "user_request": "生成一个最小候选"},
        ).json()
        demo_days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        revision_id = _save_revision(run["id"], {
            "activities": [{
                "candidate_id": "new-stop",
                "day_date": demo_days[0]["date"],
                "place_candidate_id": candidates[0]["id"],
                "planned_start_time": "10:00:00",
                "duration_minutes": 60,
                "estimated_cost_fen": candidates[0]["estimated_cost_fen"],
                "transport_mode_to_here": "walk",
                "source_ids": [candidates[0]["source"]["id"]],
            }, {
                "candidate_id": "second-stop",
                "day_date": demo_days[0]["date"],
                "place_candidate_id": candidates[1]["id"],
                    "planned_start_time": "16:00:00",
                "duration_minutes": 60,
                "estimated_cost_fen": candidates[1]["estimated_cost_fen"],
                "transport_mode_to_here": "walk",
                "source_ids": [candidates[1]["source"]["id"]],
            }],
        })
        revision = client.get(f"/api/v1/planning-runs/{run['id']}/revision")
        assert revision.status_code == 200
        assert len(revision.json()["proposed_snapshot"]["route_legs"]) == 1
        assert _candidate_route_count(revision_id) == 1
        accepted = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        updated_days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        assert sum(len(day["activities"]) for day in updated_days) == 2
        assert len(updated_days[0]["route_legs"]) == 1
        assert updated_days[0]["route_legs"][0]["provider"] == "RoamSync Estimate"
        assert client.post(f"/api/v1/plan-revisions/{revision_id}/accept").status_code == 200
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()["version"] == run["base_trip_version"] + 1


def test_accept_revision_rejects_insufficient_travel_time() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        candidates = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[:2]
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        run = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={}).json()
        revision_id = _save_revision(
            run["id"],
            {
                "activities": [
                    {
                        "candidate_id": "first",
                        "day_date": day["date"],
                        "place_candidate_id": candidates[0]["id"],
                        "planned_start_time": "10:00:00",
                        "duration_minutes": 60,
                        "estimated_cost_fen": candidates[0]["estimated_cost_fen"],
                        "transport_mode_to_here": "walk",
                        "source_ids": [candidates[0]["source"]["id"]],
                    },
                    {
                        "candidate_id": "second",
                        "day_date": day["date"],
                        "place_candidate_id": candidates[1]["id"],
                        "planned_start_time": "11:00:00",
                        "duration_minutes": 60,
                        "estimated_cost_fen": candidates[1]["estimated_cost_fen"],
                        "transport_mode_to_here": "walk",
                        "source_ids": [candidates[1]["source"]["id"]],
                    },
                ]
            },
        )
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert response.status_code == 422
        codes = {item["code"] for item in response.json()["detail"]["errors"]}
        assert "route_travel_time_conflict" in codes


def test_accept_revision_rejects_budget_violation() -> None:
    from app.demo_seed import DEMO_TRIP_ID
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        candidate = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[0]
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        run = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={}).json()
        revision_id = _save_revision(run["id"], {
            "activities": [{
                "candidate_id": "over-budget",
                "day_date": day["date"],
                "place_candidate_id": candidate["id"],
                "planned_start_time": "10:00:00",
                "duration_minutes": 60,
                "estimated_cost_fen": 999999,
                "transport_mode_to_here": "walk",
                "source_ids": [candidate["source"]["id"]],
            }],
        })
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert response.status_code == 422
        codes = {item["code"] for item in response.json()["detail"]["errors"]}
        assert {"daily_budget_exceeded", "total_budget_exceeded"} <= codes


def test_accept_revision_rejects_a_stale_formal_trip() -> None:
    from app.demo_seed import DEMO_TRIP_ID
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        trip = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        run = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={}).json()
        revision_id = _save_revision(run["id"], {"activities": []})
        changed = client.put(
            f"/api/v1/trips/{DEMO_TRIP_ID}",
            json={"version": trip["version"], "title": "用户刚刚修改过的旅行"},
        )
        assert changed.status_code == 200
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert response.status_code == 409
        assert response.json()["detail"] == "formal trip changed after planning started"


def test_accept_revision_keeps_completed_activities_and_their_routes() -> None:
    from app.demo_seed import DEMO_TRIP_ID
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        completed = day["activities"][:2]
        for activity in completed:
            updated = client.put(
                f"/api/v1/activities/{activity['id']}",
                json={"version": activity["version"], "status": "completed"},
            )
            assert updated.status_code == 200
        run = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"run_type": "replan", "user_request": "删除剩余未完成活动"},
        ).json()
        revision_id = _save_revision(run["id"], {"activities": []})
        accepted = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert accepted.status_code == 200
        remaining = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        activities = [item for item in remaining for item in item["activities"]]
        assert len(activities) == 2
        assert {item["id"] for item in activities} == {item["id"] for item in completed}
        assert all(item["status"] == "completed" for item in activities)
        assert len(remaining[0]["route_legs"]) == 1
