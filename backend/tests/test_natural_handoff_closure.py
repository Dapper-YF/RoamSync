"""Original 2026-10-19 browser failure, not a simplified demonstration."""
import asyncio
from uuid import uuid4
from datetime import date, time

import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.database import Activity, PlaceCandidate, PlanningRun
from app.planning_intent_service import _ActivityEntity, _resolve_protected_activities
from test_formal_write_protection import sample

ORIGINAL = "请调整第二天的安排：南京博物院需要12:30以后才能开始。总统府不要动。希望还可以游览110分钟，但如果赶不上预约请缩短博物院，说明取舍。其他日期和留白保持不变，玄武湖保持已选但时间未定，这次不要把它排进具体时间。"
BAD_REWRITE = "请调整 2026-11-08（第二天）的安排：1) 南京博物院需要12:30以后才能开始；2) 总统府不要动；3) 其他日期和留白保持不变（11-07 15:00-16:00自由活动留白保留）；4) 玄武湖保持已选但时间未定。"


def test_original_browser_request_survives_router_rewrite(sample, monkeypatch):
    from app.assistant_service import AssistantRouter, ToolDecision
    async def decide(self, context):
        assert context['message'] == ORIGINAL
        return ToolDecision(tool='plan_trip', reply='准备调整', planning_request=BAD_REWRITE)
    monkeypatch.setattr(AssistantRouter, 'decide', decide)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            session = (await c.post('/api/v1/assistant/sessions', json={'trip_id': str(sample.trip_id)})).json()
            mid = str(uuid4())
            r = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={'message': ORIGINAL, 'message_id': mid,
                'context': {'version': 'assistant-context-v1', 'topic_id': 'natural-travel', 'surface': 'trip', 'prefer_flexible': True,
                    'read_trip_id': str(sample.trip_id), 'action_target': {'trip_id': str(sample.trip_id), 'expected_version': 1,
                        'operation': 'plan_trip', 'authorization_message_id': mid}}})
            assert r.status_code == 200, r.text
            async with sample.sessions() as db:
                run = await db.get(PlanningRun, r.json()['latest_run_id'])
                assert run.user_request == ORIGINAL
                assert run.intent_resolution['request']['intent']['source_text'] == ORIGINAL
            turn = r.json()['messages'][-1]
            assert turn['router_planning_request'] == BAD_REWRITE
    asyncio.run(scenario())


@pytest.mark.parametrize('fragment', ['）', ')', '”', '】', '1)', '（', '""', '…'])
def test_format_fragment_is_not_an_activity_identity(fragment):
    errors = []
    assert _resolve_protected_activities('保留' + fragment, [], None, errors) == []
    assert errors == []


def test_decorated_real_name_and_unknown_name_keep_grounding():
    entity = _ActivityEntity(uuid4(), uuid4(), date(2026, 11, 8), ('总统府',), 'sight', time(14), True)
    errors = []
    assert _resolve_protected_activities('保留“总统府”', [entity], None, errors) == [entity.id]
    assert errors == []
    assert _resolve_protected_activities('保留“不存在的宫殿”', [entity], None, errors) == []
    assert errors and '不存在的宫殿' in errors[0]


def test_free_interval_is_not_an_unknown_venue():
    errors = []
    assert _resolve_protected_activities('其他安排不变，留白保留。', [], None, errors) == []
    assert _resolve_protected_activities('保留留白', [], None, errors) == []
    assert errors == []


def test_original_request_grounds_scope_and_fixed_appointment(sample):
    from app.planning_intent_service import resolve_planning_intent
    from app.schemas import PlanningIntentParseRequest
    async def scenario():
        async with sample.sessions() as db:
            for n, (name, start) in enumerate([('南京博物院', time(10)), ('总统府', time(14))]):
                place = await db.get(PlaceCandidate, sample.places[n].id)
                place.name = name
                activity = await db.get(Activity, sample.activities[n].id)
                activity.day_plan_id = sample.days[1].id
                activity.scheduled_time = start
                activity.schedule_locked = n == 1
            await db.commit()
            result = await resolve_planning_intent(db, sample.trip_id, PlanningIntentParseRequest(message=ORIGINAL))
            assert not result.requires_clarification, result.clarification_questions
            assert result.request.intent.time_scope.day_number == 2
            assert result.request.intent.protected_activity_ids == [sample.activities[1].id]
    asyncio.run(scenario())


def test_weekday_appointment_is_grounded_and_ambiguity_is_preserved():
    fixed = _ActivityEntity(uuid4(), uuid4(), date(2026, 11, 8), ('总统府',), 'sight', time(14), True)
    errors = []
    assert _resolve_protected_activities('周日下午的预约不要动。', [fixed], None, errors) == [fixed.id]
    assert errors == []
    other = _ActivityEntity(uuid4(), fixed.day_id, fixed.day_date, ('另一预约',), 'sight', time(16), True)
    assert _resolve_protected_activities('周日下午的预约不要动。', [fixed, other], None, errors) == []
    assert errors and errors[0].startswith('activity_not_unique:')


@pytest.mark.parametrize('message', ['把第二天下午留空，第一天别动。', '第一天别动，只调整第二天下午。'])
def test_unchanged_day_is_a_scope_boundary_not_an_activity(message):
    from types import SimpleNamespace
    from app.planning_intent_service import _parse_time_scope
    days = [SimpleNamespace(date=date(2026, 11, 7)), SimpleNamespace(date=date(2026, 11, 8))]
    errors = []
    scope = _parse_time_scope(message, SimpleNamespace(start_date=days[0].date), days, errors, relative_date_base=None)
    assert scope.day_number == 2 and scope.period == 'afternoon'
    assert _resolve_protected_activities(message, [], None, errors) == []
    assert errors == []


def test_true_pronoun_ambiguity_is_not_suppressed():
    errors = []
    assert _resolve_protected_activities('它不要动', [], None, errors) == []
    assert errors == ['ambiguous_activity_reference:它']


def test_unbound_flexible_conversation_does_not_offer_unselected_old_trips(sample, monkeypatch):
    from app.assistant_service import AssistantRouter, ToolDecision
    async def decide(self, context):
        assert context['trips'] == []
        return ToolDecision(tool='reply', reply='可以讨论新的旅行')
    monkeypatch.setattr(AssistantRouter, 'decide', decide)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            session = (await c.post('/api/v1/assistant/sessions', json={})).json()
            try:
                r = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={
                    'message':'我决定去南京两天，请形成允许留白的旅行安排建议。','message_id':str(uuid4()),
                    'context':{'version':'assistant-context-v1','topic_id':'new-trip','prefer_flexible':True}})
                assert r.status_code == 200, r.text
                assert r.json()['trip_id'] is None
            finally:
                from app.database import AssistantSession
                async with sample.sessions() as db:
                    await db.delete(await db.get(AssistantSession, session['id']))
                    await db.commit()
    asyncio.run(scenario())


def test_wrong_choice_authorization_returns_422_without_mutation(sample):
    from test_flexible_arrangement import create_item
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test') as c:
            assert (await create_item(c, sample, 1, kind='selected', label='玄武湖')).status_code == 201
            before = (await c.get(f'/api/v1/trips/{sample.trip_id}/arrangement-items')).json()
            session = (await c.post('/api/v1/assistant/sessions', json={'trip_id':str(sample.trip_id)})).json()
            mid = str(uuid4())
            r = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={'message':'取消玄武湖','message_id':mid,
                'context':{'version':'assistant-context-v1','topic_id':'wrong-auth','prefer_flexible':True,'read_trip_id':str(sample.trip_id),
                    'action_target':{'trip_id':str(sample.trip_id),'expected_version':2,'operation':'plan_trip','authorization_message_id':mid}}})
            assert r.status_code == 422, r.text
            assert (await c.get(f'/api/v1/trips/{sample.trip_id}/arrangement-items')).json() == before
    asyncio.run(scenario())


def test_chat_optional_choice_cannot_mutate_saved_item_without_preview(sample):
    from test_flexible_arrangement import create_item
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            assert (await create_item(c, sample, 1, kind='selected', label='玄武湖')).status_code == 201
            session = (await c.post('/api/v1/assistant/sessions', json={'trip_id':str(sample.trip_id)})).json()
            mid = str(uuid4())
            response = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={'message':'玄武湖还是备选，不要排进去','message_id':mid,
                'context':{'version':'assistant-context-v1','topic_id':'optional','prefer_flexible':True,'read_trip_id':str(sample.trip_id),
                    'action_target':{'trip_id':str(sample.trip_id),'expected_version':2,'operation':'edit_arrangement','authorization_message_id':mid}}})
            assert response.status_code == 200, response.text
            assert response.json()['messages'][-1]['tool']=='arrangement_edit'
            assert response.json()['messages'][-1]['run_id'] is None
            state=(await c.get(f'/api/v1/trips/{sample.trip_id}/arrangement-items')).json()
            assert state['items'][0]['kind']=='selected' and state['items'][0]['activity_id'] is None
            assert state['version'] == 2
            assert '未改变' in response.json()['messages'][-1]['assistant']
    asyncio.run(scenario())
