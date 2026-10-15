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
