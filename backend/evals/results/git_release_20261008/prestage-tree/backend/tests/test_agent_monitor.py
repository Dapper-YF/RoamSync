"""Monitor fixtures are test data, never replay/demo records."""
import asyncio
import json
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent_monitor import build_trace
from app.agent_observation import clean, observed, record
from app.database import PlanningRun, Trip, session_factory
from app.main import app
from app.planning_progress import active_run, report_progress


def fixture(status="queued", **changes):
    now = datetime.now(UTC)
    trip = Trip(id=uuid.uuid4(), title="Monitor fixture", version=3)
    fields = dict(id=uuid.uuid4(), trip_id=trip.id, status=status, run_type="replan", user_request="轻松一点", entry_point="trip_planner",
                  base_trip_version=3, created_at=now, started_at=None, completed_at=None, progress=None,
                  intent_resolution=None, model_name=None, model_provider=None, selected_activity_id=None,
                  error_code=None, error_message=None, error_details=None, trigger_snapshot=None, pending_interrupt=None)
    fields.update(changes)
    return PlanningRun(**fields), trip


def stage(trace, name):
    return next(item for item in trace["stages"] if item["id"] == name)


def event(sequence, stage_name, status, data=None, call_id="tool", duration=None):
    return {"sequence": sequence, "stage": stage_name, "status": status, "at": datetime.now(UTC).isoformat(),
            "data": data or {}, "call_id": call_id, "duration_ms": duration}


def test_missing_legacy_stages_and_latency_are_not_fabricated():
    run, trip = fixture("failed", error_code="unknown_failure")
    trace = build_trace(run, trip)
    assert stage(trace, "message")["status"] == "completed"
    assert stage(trace, "planner")["status"] == "unavailable"
    assert all(item["duration_ms"] is None for item in trace["stages"])
    assert trace["tools"] == []


def test_only_recorded_research_decision_can_skip_stages():
    run, trip = fixture("awaiting_confirmation", progress={"events": [event(1, "research_decision", "completed", {"destination_research_required": False})]})
    trace = build_trace(run, trip)
    assert stage(trace, "research")["status"] == "skipped"
    assert stage(trace, "poi")["status"] == "skipped"
    assert stage(trace, "planner")["status"] == "unavailable"
    assert stage(trace, "user_decision")["status"] == "running"


def test_answer_path_skips_planning_without_creating_fake_tools():
    run, trip = fixture("answered", intent_resolution={"policy_decision": {"route": "answer"}})
    trace = build_trace(run, trip)
    for name in ("planner", "route", "validator", "revision"):
        assert stage(trace, name)["status"] == "skipped"
    assert not trace["tools"]


def test_event_order_and_real_call_attempts_are_stable():
    run, trip = fixture("planning", progress={"events": [event(4, "planner", "completed", duration=18, call_id="b"), event(1, "planner", "running", call_id="a"), event(3, "planner", "running", call_id="b"), event(2, "planner", "failed", {"error_code": "parse"}, duration=12, call_id="a")]})
    trace = build_trace(run, trip)
    assert [item["sequence"] for item in trace["events"]] == [1, 2, 3, 4]
    assert [item["status"] for item in trace["tools"]] == ["failed", "completed"]
    assert [item["duration_ms"] for item in trace["tools"]] == [12, 18]
    assert stage(trace, "planner")["attempts"] == 2


def test_route_failure_is_not_relabelled_as_outer_validator_failure():
    run, trip = fixture("failed", error_code="planner_map_unavailable", progress={"events": [event(1, "route", "failed", {"error_code": "map_route_unavailable"}), event(2, "validator", "failed")]})
    trace = build_trace(run, trip)
    assert trace["error"]["stage"] == "route"
    assert stage(trace, "route")["status"] == "failed"


def test_invalid_validation_does_not_claim_other_checks_passed():
    run, trip = fixture("failed", error_code="planner_constraints_unsatisfied")
    trace = build_trace(run, trip, checkpoint={"validation_result": {"valid": False, "errors": [{"code": "route_travel_time_conflict", "details": {"available_minutes": 50, "required_minutes": 77}}]}})
    checks = stage(trace, "validator")["data"]["checks"]
    assert next(item for item in checks if item["label"] == "Route Feasibility")["status"] == "FAIL"
    assert next(item for item in checks if item["label"] == "Time Windows")["status"] == "unavailable"
    assert stage(trace, "validator")["status"] == "failed"


def test_checkpoint_projects_real_goal_and_context_without_current_state():
    run, trip = fixture("failed")
    checkpoint = {"planning_goals": {"soft_goals": {"requested_pace": "relaxed"}},
                  "planning_context": {"trip": {"version": 3}, "days": [], "preferences": {"pace": "relaxed"}, "candidates": []},
                  "hidden_prompt": "do not export"}
    trace = build_trace(run, trip, checkpoint=checkpoint, checkpoint_available=True)
    assert stage(trace, "goal")["data"]["soft_goals"]["requested_pace"] == "relaxed"
    assert stage(trace, "context")["data"]["available_count"] > 0
    assert "hidden_prompt" not in json.dumps(trace)
    assert stage(trace, "planner")["status"] == "unavailable"


@pytest.mark.parametrize("name", ["API_KEY", "Authorization", "system_prompt", "chain_of_thought", "reasoning_content", "headers", "password", "token", "key"])
def test_nested_sensitive_fields_never_leave_monitor(name):
    value = clean({"details": [{name: "sensitive", "safe": "kept"}]})
    assert "sensitive" not in json.dumps(value)
    assert value["details"][0]["safe"] == "kept"


def test_sensitive_strings_and_url_credentials_are_removed(monkeypatch):
    import app.config as config
    settings = config.get_settings().model_copy(update={"amap_rest_key": "configured-private-key"})
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    result = clean("configured-private-key Bearer SECRET https://user:pass@example.com/path?key=xyz <think>hidden internal</think>")
    for private in ("configured-private-key", "SECRET", "user:pass", "xyz", "hidden internal"):
        assert private not in result


def create(client, text="重新规划行程"):
    trip = client.post("/api/v1/trips", json={"title": "Monitor SQL fixture", "destination": "杭州", "start_date": "2026-11-01", "end_date": "2026-11-01"}).json()
    response = client.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={"run_type": "replan", "user_request": text})
    assert response.status_code == 201
    return trip, response.json()


def test_api_run_isolation_recent_filter_and_read_only(monkeypatch):
    import app.agent_monitor as monitor
    async def no_checkpoint(_): return {}, False
    monkeypatch.setattr(monitor, "checkpoint_state", no_checkpoint)
    with TestClient(app) as client:
        first_trip, first = create(client)
        second_trip, second = create(client, "调整行程节奏")
        before = client.get(f"/api/v1/trips/{first_trip['id']}").json()
        response = client.get(f"/api/v1/agent-monitor/runs/{first['id']}")
        assert response.status_code == 200
        assert response.json()["run"]["trip_id"] == first_trip["id"]
        assert second["id"] not in json.dumps(response.json())
        second_response = client.get(f"/api/v1/agent-monitor/runs/{second['id']}").json()
        assert second_response["run"]["trip_id"] == second_trip["id"]
        recent = client.get(f"/api/v1/agent-monitor/runs?trip_id={first_trip['id']}").json()
        assert [item["id"] for item in recent] == [first["id"]]
        assert client.get(f"/api/v1/trips/{first_trip['id']}").json() == before
        assert client.get(f"/api/v1/agent-monitor/runs/{uuid.uuid4()}").status_code == 404
        assert client.get("/api/v1/agent-monitor/runs?limit=101").status_code == 422


def test_atomic_event_append_retains_legacy_progress_and_isolates_runs():
    with TestClient(app) as client:
        _, first = create(client)
        _, second = create(client)
        async def exercise():
            run_id = uuid.UUID(first["id"])
            token = active_run.set(run_id)
            try:
                await asyncio.gather(*(record("search", "completed", data={"index": index}) for index in range(5)))
                await report_progress("planning", "真实进度")
                async with session_factory() as db:
                    run = await db.get(PlanningRun, run_id)
                    assert run.progress["stage"] == "planning"
                    assert [item["sequence"] for item in run.progress["events"]] == [1, 2, 3, 4, 5]
                    other = await db.get(PlanningRun, uuid.UUID(second["id"]))
                    assert other.progress is None
            finally:
                active_run.reset(token)
        asyncio.run(exercise())


def test_observer_failure_preserves_value_and_original_exception(monkeypatch):
    import app.agent_observation as observation
    def unavailable(): raise RuntimeError("observer DB unavailable")
    monkeypatch.setattr(observation, "session_factory", unavailable)
    async def exercise():
        token = active_run.set(uuid.uuid4())
        try:
            @observed("planner")
            async def success(): return "actual return"
            @observed("planner")
            async def failure(): raise ValueError("actual failure")
            assert await success() == "actual return"
            with pytest.raises(ValueError, match="actual failure"):
                await failure()
        finally:
            active_run.reset(token)
    asyncio.run(exercise())


def test_persisted_revision_and_decision_replay_after_new_session():
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from app.config import get_settings
    from app.planning_graph import DraftGeneration
    from app.planning_graph_runtime import execute_planning_run
    from app.schemas import CandidatePlanSnapshot
    class Provider:
        async def generate(self, state):
            return DraftGeneration(CandidatePlanSnapshot(activities=[]), "test", "monitor-fixture", 0)
    async def execute(run_id):
        async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
            await saver.setup()
        await execute_planning_run(uuid.UUID(run_id), provider=Provider())
    with TestClient(app) as client:
        trip, run = create(client)
        asyncio.run(execute(run["id"]))
        trace = client.get(f"/api/v1/agent-monitor/runs/{run['id']}").json()
        assert trace["run"]["status"] == "awaiting_confirmation"
        assert stage(trace, "context")["status"] == "completed"
        assert stage(trace, "validator")["data"]["validation"]["valid"] is True
        revision_id = stage(trace, "revision")["data"]["id"]
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/reject", json={"reason_code": "other", "reason_text": "Monitor test feedback"})
        assert response.status_code == 200
    with TestClient(app) as client:
        replay = client.get(f"/api/v1/agent-monitor/runs/{run['id']}").json()
        assert replay["run"]["status"] == "rejected"
        assert stage(replay, "user_decision")["data"]["feedback_persisted"] is True
        assert client.get(f"/api/v1/trips/{trip['id']}").json()["version"] == trip["version"]
