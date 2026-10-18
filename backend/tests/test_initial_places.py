import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import session_factory
from app.initial_places_service import prepare_initial_candidates
from app.main import app
from app.planner_repository import get_candidates, get_day_plans
from app.planning_errors import PlannerConstraintsUnsatisfiedError
from app.schemas import PlaceSearchResultResponse


def test_research_saves_sources_without_scheduling_and_is_idempotent():
    with TestClient(app) as client:
        response = client.post('/api/v1/trips', json={
            'title': 'Initial research test', 'destination': '杭州市',
            'start_date': '2026-11-01', 'end_date': '2026-11-02',
            'total_budget_fen': 200000, 'daily_budget_fen': 100000,
        })
        assert response.status_code == 201
        trip_id = uuid.UUID(response.json()['id'])
        item = PlaceSearchResultResponse(provider_place_id='test-poi', name='测试公园',
            category='nature', longitude=120.1, latitude=30.2,
            suggested_duration_minutes=60, estimated_cost_fen=0,
            source_url='https://www.amap.com/search?id=test-poi')
        search = AsyncMock(return_value=[item, item])

        async def scenario():
            async with session_factory() as session:
                await prepare_initial_candidates(session, trip_id, search=search)
                calls = search.await_count
                await prepare_initial_candidates(session, trip_id, search=search)
                assert search.await_count == calls
                candidates = await get_candidates(session, trip_id)
                assert len(candidates) == 1
                assert candidates[0].source.url == item.source_url
                assert not any(day.activities for day in await get_day_plans(session, trip_id))
        asyncio.run(scenario())


def test_empty_search_does_not_report_a_ready_plan():
    with TestClient(app) as client:
        response = client.post('/api/v1/trips', json={
            'title': 'Empty research test', 'destination': '杭州市',
            'start_date': '2026-11-01', 'end_date': '2026-11-02',
            'total_budget_fen': 200000, 'daily_budget_fen': 100000,
        })
        trip_id = uuid.UUID(response.json()['id'])
        async def scenario():
            async with session_factory() as session:
                with pytest.raises(PlannerConstraintsUnsatisfiedError, match='initial_places_unavailable'):
                    await prepare_initial_candidates(session, trip_id, search=AsyncMock(return_value=[]))
        asyncio.run(scenario())


def test_default_runtime_prepares_real_provider_candidates_before_model(monkeypatch):
    import app.planning_graph_runtime as runtime
    from app.planning_graph import DraftGeneration
    from app.schemas import CandidatePlanSnapshot, CandidateActivity
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from app.config import get_settings

    poi = PlaceSearchResultResponse(provider_place_id="D_RUNTIME_POI", name="测试公园",
        category="nature", longitude=120.1, latitude=30.2, suggested_duration_minutes=60,
        estimated_cost_fen=0, source_url="https://www.amap.com/search?id=D_RUNTIME_POI")
    async def prepare(session, trip_id):
        await prepare_initial_candidates(session, trip_id, search=AsyncMock(return_value=[poi]))
    resolver = AsyncMock(side_effect=prepare)
    class ModelFixture:
        async def generate(self, state):
            context = state["planning_context"]
            place = context["candidates"][0]
            return DraftGeneration(snapshot=CandidatePlanSnapshot(activities=[CandidateActivity(
                candidate_id="D-runtime-1", day_date=context["days"][0]["date"],
                place_candidate_id=place["id"], planned_start_time="10:00:00",
                duration_minutes=60, estimated_cost_fen=0, transport_mode_to_here="walk",
                source_ids=[place["source"]["id"]])]), provider="fixture", model="runtime-wiring-test", token_usage=0)
    monkeypatch.setattr(runtime, "research_destination", AsyncMock(return_value={"status":"not_required", "places":{}}))
    monkeypatch.setattr(runtime, "prepare_initial_candidates", resolver)
    monkeypatch.setattr(runtime, "OpenAIResponsesPlanner", lambda _: ModelFixture())
    async def setup():
        async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
            await saver.setup()
    asyncio.run(setup())
    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={"title":"Runtime initial resolver regression", "destination":"杭州",
            "start_date":"2026-11-01", "end_date":"2026-11-01", "total_budget_fen":200000, "daily_budget_fen":200000}).json()
        run = client.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={"run_type":"initial_plan", "user_request":"生成完整行程"}).json()
        asyncio.run(runtime.execute_planning_run(uuid.UUID(run["id"])))
        result = client.get(f"/api/v1/planning-runs/{run['id']}").json()
        assert result["status"] == "awaiting_confirmation", (result.get("error_code"), result.get("error_message"), result.get("pending_interrupt"))
        resolver.assert_awaited_once()
        assert client.get(f"/api/v1/planning-runs/{run['id']}/revision").status_code == 200
