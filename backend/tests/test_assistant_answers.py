import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from app.database import PlanningRun, PlanRevision, Trip, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.planning_graph import AnswerGeneration, build_planning_graph
from app.planning_graph_runtime import invoke_compiled_graph


@pytest.mark.parametrize("message", [
    "现在的旅行行程是怎样的，你建议我怎么走这一趟？",
    "为什么这样规划行程？", "路线合理吗？", "预算花在哪里？", "第二天有什么建议？",
    "你推荐怎么调整行程？", "当前行程会不会太赶？", "有什么好吃的？", "你好",
])
def test_questions_cannot_create_runs_even_with_replan_and_page_selection(message):
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        response = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={
            "run_type": "replan", "user_request": message, "selected_day_id": day["id"],
            "selected_activity_id": day["activities"][0]["id"],
        })
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["route"] == "companion"


def test_arbitrary_text_is_never_defaulted_to_replanning():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={"run_type": "replan", "user_request": "xyz123"})
        assert response.status_code == 422
        assert response.json()["detail"]["route"] == "reject"


def test_historical_read_only_run_remains_executable_without_formal_change():
    class AnswerOnlyProvider:
        async def generate(self, state):
            raise AssertionError("a question must never invoke itinerary generation")

        async def answer(self, state):
            assert state["planning_context"]["days"][0]["activities"]
            return AnswerGeneration("第一天从西湖断桥开始。保留午间休息，可以减少连续游览的疲劳。", "test", "answer-only", 8)

    async def execute(run_id):
        async with session_factory() as session:
            run = await session.get(PlanningRun, uuid.UUID(run_id))
            graph = build_planning_graph(InMemorySaver(), AnswerOnlyProvider())
            result = await invoke_compiled_graph(graph, run)
            assert result.pending_interrupt is None
        async with session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(PlanRevision).where(PlanRevision.planning_run_id == uuid.UUID(run_id))) == 0

    async def historical_run():
        # Simulate a pre-Phase-0 queued record, bypassing the new creation guard.
        async with session_factory() as session:
            trip = await session.get(Trip, DEMO_TRIP_ID)
            run = PlanningRun(trip_id=DEMO_TRIP_ID, run_type="replan", status="queued",
                base_trip_version=trip.version,
                user_request="现在的旅行行程是怎样的，你建议我怎么走这一趟？")
            session.add(run)
            await session.commit()
            return {"id": str(run.id)}

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        before = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        trip_before = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        run = asyncio.run(historical_run())
        asyncio.run(execute(run["id"]))
        persisted = client.get(f"/api/v1/planning-runs/{run['id']}").json()
        assert persisted["status"] == "answered"
        assert "午间休息" in persisted["response_text"]
        assert persisted["pending_interrupt"] is None
        assert client.get(f"/api/v1/planning-runs/{run['id']}/revision").status_code == 404
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json() == before
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json() == trip_before


@pytest.mark.parametrize("message", ["请重新规划行程", "解释一下，并帮我调整第二天的行程", "我希望这次旅行可以丰富一些"])
def test_explicit_changes_still_produce_previews(message):
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={"run_type": "replan", "user_request": message})
        assert response.status_code == 201
        assert response.json()["intent_resolution"]["policy_decision"]["route"] == "plan_preview"
