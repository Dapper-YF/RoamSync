"""Real PostgreSQL/API proof: forecast conversation cannot change formal state."""
import asyncio, uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.database import session_factory
from app.demo_seed import DEMO_TRIP_ID
from test_companion_facts import tool_fixture

async def formal_snapshot():
    async with session_factory() as db:
        # Entire rows, not only counts/versions; conversation persistence excluded deliberately.
        names=['trips','day_plans','activities','planning_runs','plan_revisions','trip_executions','navigation_sessions']
        return {n:(await db.execute(text(f'SELECT row_to_json(t)::text FROM "{n}" t ORDER BY row_to_json(t)::text'))).scalars().all() for n in names}

def test_real_api_forecast_with_existing_trip_is_formally_readonly():
    fact,_=tool_fixture()
    with TestClient(app) as client, patch('app.assistant_service.get_default_fact_tool',return_value=fact):
        assert client.post('/api/v1/demo/reset').status_code==200
        sid=client.post('/api/v1/assistant/sessions',json={'trip_id':str(DEMO_TRIP_ID)}).json()['id']
        before=asyncio.run(formal_snapshot())
        for message in ['杭州明天下午天气怎么样？','西湖有什么历史，明天下午天气呢？','杭州现在多少度？','杭州昨天下午下雨了吗？']:
            res=client.post(f'/api/v1/assistant/sessions/{sid}/messages',json={'message':message,'message_id':str(uuid.uuid4())})
            assert res.status_code==200,res.text
            result=res.json()['messages'][-1]['companion_result']
            assert result['planning_handoff'] is None and res.json()['messages'][-1]['run_id'] is None
        assert before==asyncio.run(formal_snapshot())

def test_real_api_opening_with_existing_trip_is_formally_readonly():
    from test_opening_hours import hours_tool
    fact,_,_=hours_tool()
    with TestClient(app) as client, patch('app.assistant_service.get_default_fact_tool',return_value=fact):
        assert client.post('/api/v1/demo/reset').status_code==200
        sid=client.post('/api/v1/assistant/sessions',json={'trip_id':str(DEMO_TRIP_ID)}).json()['id']
        before=asyncio.run(formal_snapshot())
        for message in ['南京博物院明天几点开门？','浙江省博物馆之江馆区10月8日开馆吗？','南京博物院现在开着吗？','西湖几点关门？','南京博物院明天几点开门，南京明天下午天气如何？']:
            response=client.post(f'/api/v1/assistant/sessions/{sid}/messages',json={'message':message,'message_id':str(uuid.uuid4())})
            assert response.status_code==200,response.text
            row=response.json()['messages'][-1]
            assert row['run_id'] is None and row['companion_result']['planning_handoff'] is None
            assert not row['goal_routing']['mutation_requested']
        assert before==asyncio.run(formal_snapshot())
