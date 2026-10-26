import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.database import Trip, session_factory
from app.demo_seed import DEMO_TRIP_ID, demo_uuid
from app.main import app
from app.schemas import ExtendStayRequest
from app.trip_execution_service import extend_stay


def test_trip_execution_progresses_and_persists() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        initial = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution")
        assert initial.status_code == 200
        assert initial.json()["status"] == "not_started"
        assert initial.json()["remaining_activity_count"] == 3

        started = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={"day_plan_id": str(demo_uuid("day", "day-1"))}
        )
        assert started.status_code == 200
        state = started.json()
        execution_id = state["id"]
        first_activity_id = state["current_activity_id"]

        arrived = client.post(
            f"/api/v1/trip-executions/{execution_id}/actions",
            json={"action": "arrive", "activity_id": first_activity_id, "delay_minutes": 12},
        )
        assert arrived.status_code == 200
        assert next(item for item in arrived.json()["activities"] if item["activity_id"] == first_activity_id)["status"] == "arrived"

        active = client.post(
            f"/api/v1/trip-executions/{execution_id}/actions",
            json={"action": "start_activity", "activity_id": first_activity_id},
        )
        assert active.status_code == 200
        completed = client.post(
            f"/api/v1/trip-executions/{execution_id}/actions",
            json={"action": "complete", "activity_id": first_activity_id},
        )
        assert completed.status_code == 200
        assert completed.json()["current_activity_id"] != first_activity_id
        assert completed.json()["remaining_activity_count"] == 2

        persisted = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution").json()
        assert persisted["current_activity_id"] == completed.json()["current_activity_id"]
        assert [item["event_type"] for item in persisted["events"]][:4] == [
            "trip_started", "arrived", "activity_started", "completed"
        ]


def test_trip_execution_pause_sequence_and_finish_guard() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        state = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        execution_id = state["id"]
        paused = client.post(
            f"/api/v1/trip-executions/{execution_id}/actions", json={"action": "pause"}
        )
        assert paused.json()["status"] == "paused"
        blocked = client.post(
            f"/api/v1/trip-executions/{execution_id}/actions",
            json={"action": "complete", "activity_id": state["current_activity_id"]},
        )
        assert blocked.status_code == 409
        resumed = client.post(
            f"/api/v1/trip-executions/{execution_id}/actions", json={"action": "resume"}
        )
        assert resumed.json()["status"] == "in_progress"
        assert client.post(
            f"/api/v1/trip-executions/{execution_id}/actions", json={"action": "finish"}
        ).status_code == 409


def test_trip_can_advance_across_days_and_finish() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        state = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        execution_id = state["id"]
        first_date = state["current_date"]
        while state["current_activity_id"] is not None:
            state = client.post(
                f"/api/v1/trip-executions/{execution_id}/actions",
                json={"action": "skip", "activity_id": state["current_activity_id"]},
            ).json()
        assert any(item["day_date"] != first_date for item in state["activities"])
        finished = client.post(
            f"/api/v1/trip-executions/{execution_id}/actions", json={"action": "finish"}
        )
        assert finished.status_code == 200
        assert finished.json()["status"] == "completed"
        assert finished.json()["events"][-1]["event_type"] == "trip_finished"


def test_planning_run_history_is_trip_scoped() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        created = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"run_type": "replan", "user_request": "调整第二天下午"},
        )
        assert created.status_code == 201
        history = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs")
        assert history.status_code == 200
        assert history.json()[0]["id"] == created.json()["id"]


def test_dynamic_replan_records_event_and_scopes_run_to_current_day() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        execution = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}
        ).json()
        response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/execution/replan",
            json={"trigger": "delay", "details": "当前活动延误 45 分钟"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["run"]["run_type"] == "replan"
        assert body["run"]["status"] == "queued"
        assert body["run"]["selected_day_id"] == execution["current_day_plan_id"]
        assert body["trigger_event_id"]
        persisted = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution").json()
        assert persisted["events"][-1]["event_type"] == "delay"
        assert persisted["events"][-1]["details"]["source"] == "dynamic_replan"


def test_extend_stay_is_idempotent_and_never_changes_planned_duration() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        execution = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        current = next(item for item in execution["activities"] if item["activity_id"] == execution["current_activity_id"])
        planned_duration = next(item for item in client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]["activities"] if item["id"] == current["activity_id"])["duration_minutes"]
        client.post(f"/api/v1/trip-executions/{execution['id']}/actions", json={"action": "start_activity", "activity_id": current["activity_id"]})
        trip = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        action_id = str(uuid.uuid4())
        first = client.post(f"/api/v1/activity-executions/{current['id']}/extend-stay", json={"client_action_id": action_id, "extension_minutes": 30})
        assert first.status_code == 200
        assert first.json()["total_extension_minutes"] == 30
        replay = client.post(f"/api/v1/activity-executions/{current['id']}/extend-stay", json={"client_action_id": action_id, "extension_minutes": 30})
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        assert client.post(f"/api/v1/activity-executions/{current['id']}/extend-stay", json={"client_action_id": action_id, "extension_minutes": 60}).status_code == 409
        after = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        assert next(item for item in after[0]["activities"] if item["id"] == current["activity_id"])["duration_minutes"] == planned_duration


def test_activity_experience_read_model_and_leave_early_are_fact_based() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        execution = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        current = next(item for item in execution["activities"] if item["activity_id"] == execution["current_activity_id"])
        execution_id = execution["id"]

        assert client.post(
            f"/api/v1/trip-executions/{execution_id}/actions",
            json={"action": "arrive", "activity_id": current["activity_id"]},
        ).status_code == 200
        arrived_extension = client.post(
            f"/api/v1/activity-executions/{current['id']}/extend-stay",
            json={"client_action_id": str(uuid.uuid4()), "extension_minutes": 30, "reason": "想多看看"},
        )
        assert arrived_extension.status_code == 200
        assert arrived_extension.json()["projected_end_at"] is None

        assert client.post(
            f"/api/v1/trip-executions/{execution_id}/actions",
            json={"action": "start_activity", "activity_id": current["activity_id"]},
        ).status_code == 200
        active_extension = client.post(
            f"/api/v1/activity-executions/{current['id']}/extend-stay",
            json={"client_action_id": str(uuid.uuid4()), "extension_minutes": 15},
        )
        assert active_extension.status_code == 200
        assert active_extension.json()["total_extension_minutes"] == 45
        assert active_extension.json()["projected_end_at"] is not None

        progress = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution-progress")
        assert progress.status_code == 200
        experience = progress.json()["current_activity_experience"]
        assert experience["activity_execution_id"] == current["id"]
        assert experience["planned_duration_minutes"] > 0
        assert experience["actual_started_at"] is not None
        assert experience["actual_ended_at"] is None
        assert experience["total_extension_minutes"] == 45
        assert experience["projected_end_at"] is not None

        action_id = str(uuid.uuid4())
        left = client.post(
            f"/api/v1/activity-executions/{current['id']}/leave-early",
            json={"client_action_id": action_id, "reason": "今天想放慢节奏"},
        )
        assert left.status_code == 200
        assert left.json()["status"] == "completed"
        assert left.json()["actual_ended_at"] is not None
        replay = client.post(
            f"/api/v1/activity-executions/{current['id']}/leave-early",
            json={"client_action_id": action_id, "reason": "今天想放慢节奏"},
        )
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        persisted = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution").json()
        assert [event["event_type"] for event in persisted["events"]].count("user_leave_early") == 1


def test_activity_experience_rejects_invalid_state_and_stale_version() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        execution = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        current = next(item for item in execution["activities"] if item["activity_id"] == execution["current_activity_id"])
        extension_url = f"/api/v1/activity-executions/{current['id']}/extend-stay"
        assert client.post(extension_url, json={"client_action_id": str(uuid.uuid4()), "extension_minutes": 5}).status_code == 409
        assert client.post(
            f"/api/v1/trip-executions/{execution['id']}/actions",
            json={"action": "start_activity", "activity_id": current["activity_id"]},
        ).status_code == 200
        async def bump_formal_version() -> None:
            async with session_factory() as db:
                await db.execute(update(Trip).where(Trip.id == DEMO_TRIP_ID).values(version=Trip.version + 1))
                await db.commit()
        asyncio.run(bump_formal_version())
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution-progress").json()["experience_impact"]["impact_state"] == "unavailable"
        assert client.post(extension_url, json={
            "client_action_id": str(uuid.uuid4()), "extension_minutes": 5, "expected_itinerary_version": 999,
        }).status_code == 409
        assert client.post(
            f"/api/v1/trip-executions/{execution['id']}/actions",
            json={"action": "complete", "activity_id": current["activity_id"]},
        ).status_code == 200
        assert client.post(extension_url, json={"client_action_id": str(uuid.uuid4()), "extension_minutes": 5}).status_code == 409


def test_concurrent_extend_stay_replays_one_persisted_event() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        execution = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        current = next(item for item in execution["activities"] if item["activity_id"] == execution["current_activity_id"])
        assert client.post(
            f"/api/v1/trip-executions/{execution['id']}/actions",
            json={"action": "start_activity", "activity_id": current["activity_id"]},
        ).status_code == 200
        action_id = uuid.uuid4()

        async def once():
            async with session_factory() as db:
                return await extend_stay(
                    db,
                    uuid.UUID(current["id"]),
                    ExtendStayRequest(client_action_id=action_id, extension_minutes=20),
                )

        async def race():
            return await asyncio.gather(once(), once())

        first, second = asyncio.run(race())
        assert {first.replayed, second.replayed} == {False, True}
        assert first.total_extension_minutes == second.total_extension_minutes == 20
