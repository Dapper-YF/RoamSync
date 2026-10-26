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
            json={"run_type": "initial_plan", "user_request": "  帮我规划行程，历史、美食，步行适量  "},
        )
        assert created.status_code == 201
        run = created.json()
        assert run["status"] == "queued"
        assert run["base_trip_version"] == trip["version"]
        assert run["user_request"] == "帮我规划行程，历史、美食，步行适量"

        fetched = client.get(f"/api/v1/planning-runs/{run['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["trip_id"] == trip["id"]

        not_ready = client.get(f"/api/v1/planning-runs/{run['id']}/revision")
        assert not_ready.status_code == 404
        assert not_ready.json()["detail"] == "planning revision not ready"


def test_planning_run_persists_page_context_and_grounded_intent() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[1]
        created = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={
                "run_type": "replan",
                "user_request": "调整这一天，节奏轻松一点",
                "entry_point": "day_planner",
                "selected_day_id": day["id"],
            },
        )
        assert created.status_code == 201
        run = created.json()
        assert run["entry_point"] == "day_planner"
        assert run["selected_day_id"] == day["id"]
        assert run["intent_resolution"]["request"]["target_day_id"] == day["id"]
        assert run["intent_resolution"]["grounded_intent"]["target_day_ids"] == [
            day["id"]
        ]

        invalid = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={
                "user_request": "调整这一天",
                "entry_point": "day_planner",
                "selected_day_id": str(uuid.uuid4()),
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "selected_day_not_in_trip"


def test_planning_run_not_found_and_request_validation() -> None:
    with TestClient(app) as client:
        missing_id = uuid.uuid4()
        assert client.post(
            f"/api/v1/trips/{missing_id}/planning-runs",
            json={"user_request": "帮我规划行程"},
        ).status_code == 404
        assert client.get(f"/api/v1/planning-runs/{missing_id}").status_code == 404
        trip = _create_trip(client)
        invalid = client.post(
            f"/api/v1/trips/{trip['id']}/planning-runs",
            json={"run_type": "unknown", "user_request": "帮我规划行程"},
        )
        assert invalid.status_code == 422
        assert client.post(
            f"/api/v1/trips/{trip['id']}/planning-runs",
            json={"user_request": "   "},
        ).status_code == 422


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
            json={"run_type": "initial_plan", "user_request": "帮我规划一个最小行程"},
        ).json()
        demo_days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        execution = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        current_leg = demo_days[0]["route_legs"][0]
        navigation = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",
            json={
                "trip_execution_id": execution["id"],
                "from_activity_id": current_leg["from_activity_id"],
                "to_activity_id": current_leg["to_activity_id"],
            },
        )
        assert navigation.status_code == 201
        revision_id = _save_revision(run["id"], {
            "activities": [{
                "candidate_id": "new-stop",
                "day_date": demo_days[0]["date"],
                "place_candidate_id": candidates[0]["id"],
                "planned_start_time": "16:00:00",
                "duration_minutes": 60,
                "estimated_cost_fen": candidates[0]["estimated_cost_fen"],
                "transport_mode_to_here": "walk",
                "source_ids": [candidates[0]["source"]["id"]],
            }, {
                "candidate_id": "second-stop",
                "day_date": demo_days[0]["date"],
                "place_candidate_id": candidates[1]["id"],
                "planned_start_time": "20:00:00",
                "duration_minutes": 60,
                "estimated_cost_fen": candidates[1]["estimated_cost_fen"],
                "transport_mode_to_here": "walk",
                "source_ids": [candidates[1]["source"]["id"]],
            }],
        })
        revision = client.get(f"/api/v1/planning-runs/{run['id']}/revision")
        assert revision.status_code == 200
        # Ordinary Planning retains both current and navigation-target stops.
        protected_ids = {current_leg["from_activity_id"], current_leg["to_activity_id"]}
        protected_before = {a["id"]: a for a in demo_days[0]["activities"] if a["id"] in protected_ids}
        assert len(revision.json()["proposed_snapshot"]["route_legs"]) == 3
        assert _candidate_route_count(revision_id) == 3
        accepted = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert accepted.status_code == 200, accepted.json()
        assert accepted.json()["status"] == "accepted"
        assert client.get(
            f"/api/v1/navigation-sessions/{navigation.json()['id']}"
        ).json()["status"] == "superseded"
        updated_days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        assert sum(len(day["activities"]) for day in updated_days) == 4
        protected_after = {a["id"]: a for a in updated_days[0]["activities"] if a["id"] in protected_ids}
        assert protected_after.keys() == protected_before.keys()
        for activity_id, original in protected_before.items():
            for field in ("place_id", "scheduled_time", "duration_minutes", "estimated_cost_fen", "status", "schedule_locked"):
                assert protected_after[activity_id][field] == original[field]
        assert len(updated_days[0]["route_legs"]) == 3
        assert updated_days[0]["route_legs"][0]["provider"] == "RoamSync Estimate"
        assert client.post(f"/api/v1/plan-revisions/{revision_id}/accept").status_code == 200
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()["version"] == run["base_trip_version"] + 1


def test_accept_revision_rejects_insufficient_travel_time() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        candidates = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[:2]
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        run = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"user_request": "测试路线约束"},
        ).json()
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
        run = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"user_request": "测试预算约束"},
        ).json()
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


def test_unconstrained_trip_does_not_emit_budget_validation_errors() -> None:
    from app.demo_seed import DEMO_TRIP_ID
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        trip = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        updated = client.put(f"/api/v1/trips/{DEMO_TRIP_ID}", json={
            "version": trip["version"], "total_budget_fen": None, "daily_budget_fen": None,
        })
        assert updated.status_code == 200
        assert updated.json()["total_budget_fen"] is None
        candidate = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[0]
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        run = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={"user_request": "测试无预算约束"}).json()
        revision_id = _save_revision(run["id"], {"activities": [{
            "candidate_id": "unconstrained-cost", "day_date": day["date"],
            "place_candidate_id": candidate["id"], "planned_start_time": "10:00:00",
            "duration_minutes": 60, "estimated_cost_fen": 999999,
            "transport_mode_to_here": "walk", "source_ids": [candidate["source"]["id"]],
        }]})
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert response.status_code == 422
        codes = {item["code"] for item in response.json()["detail"]["errors"]}
        assert not any("budget" in code for code in codes)


def test_accept_revision_accounts_for_actual_expenses() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        trip = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        candidate = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[0]
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        expense = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/expenses",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "amount_fen": trip["total_budget_fen"] + 1,
                "category": "other",
                "description": "已发生消费",
            },
        )
        assert expense.status_code == 201
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/budget").json()["total_spent_fen"] == trip["total_budget_fen"] + 1
        run = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"user_request": "测试实际消费预算约束"},
        ).json()
        revision_id = _save_revision(run["id"], {
            "activities": [{
                "candidate_id": "actual-spend-over-budget",
                "day_date": day["date"],
                "place_candidate_id": candidate["id"],
                "planned_start_time": "10:00:00",
                "duration_minutes": 60,
                "estimated_cost_fen": candidate["estimated_cost_fen"],
                "transport_mode_to_here": "walk",
                "source_ids": [candidate["source"]["id"]],
            }],
        })
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert response.status_code == 422
        errors = response.json()["detail"]["errors"]
        actual_error = next(item for item in errors if item["code"] == "total_budget_with_actual_spend_exceeded")
        assert actual_error["details"]["actual_spent_fen"] == trip["total_budget_fen"] + 1


def test_accept_revision_rejects_a_stale_formal_trip() -> None:
    from app.demo_seed import DEMO_TRIP_ID
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        trip = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        run = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"user_request": "重新规划行程以测试版本约束"},
        ).json()
        revision_id = _save_revision(run["id"], {"activities": []})
        changed = client.put(
            f"/api/v1/trips/{DEMO_TRIP_ID}",
            json={"version": trip["version"], "title": "用户刚刚修改过的旅行"},
        )
        assert changed.status_code == 200
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert response.status_code == 409
        assert response.json()["detail"] == "formal trip changed after planning started"


def test_accept_revision_rejects_a_candidate_stale_after_importance_edit() -> None:
    """Decision semantics must advance the same formal-version fence as a Trip edit."""
    from app.demo_seed import DEMO_TRIP_ID
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        activity = days[0]["activities"][0]
        run = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"run_type": "replan", "user_request": "调整今天的行程"},
        ).json()
        revision_id = _save_revision(run["id"], {"activities": []})
        edited = client.put(
            f"/api/v1/activities/{activity['id']}",
            json={"version": activity["version"], "importance": "must_do"},
        )
        assert edited.status_code == 200
        rejected = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert rejected.status_code == 409
        assert rejected.json()["detail"] == "formal trip changed after planning started"


def test_accept_revision_enforces_grounded_day_scope() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        run_response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={
                "run_type": "replan",
                "user_request": "调整第二天，节奏轻松一点",
                "entry_point": "day_planner",
                "selected_day_id": days[1]["id"],
            },
        )
        assert run_response.status_code == 201
        revision_id = _save_revision(run_response.json()["id"], {"activities": []})
        accepted = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert accepted.status_code == 422
        codes = {item["code"] for item in accepted.json()["detail"]["errors"]}
        assert "intent_scope_activity_omitted" in codes


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


def test_relaxed_replan_cannot_increase_the_number_of_stops() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        before = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        day = before[1]
        candidate = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[0]
        run = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={
            "run_type": "replan", "user_request": "只调整第二天，节奏更轻松，其他日期保持不变。",
        }).json()
        assert run["intent_resolution"]["grounded_intent"]["constraints"]["requested_pace"] == "relaxed"
        activities = [{
            "candidate_id": f"keep-{a['id']}", "day_date": d["date"],
            "place_candidate_id": a["place_id"], "planned_start_time": a["scheduled_time"],
            "duration_minutes": a["duration_minutes"], "estimated_cost_fen": a["estimated_cost_fen"],
            "transport_mode_to_here": d["route_mode"], "source_ids": [a["source"]["id"]],
            "replaces_activity_id": a["id"],
        } for d in before for a in d["activities"]]
        activities.append({
            "candidate_id": "extra-stop", "day_date": day["date"],
            "place_candidate_id": candidate["id"], "planned_start_time": "19:00",
            "duration_minutes": 60, "estimated_cost_fen": candidate["estimated_cost_fen"],
            "transport_mode_to_here": "walk", "source_ids": [candidate["source"]["id"]],
        })
        revision_id = _save_revision(run["id"], {"activities": activities})
        result = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert result.status_code == 422
        assert "relaxed_pace_increased_stops" in {item["code"] for item in result.json()["detail"]["errors"]}
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json() == before
