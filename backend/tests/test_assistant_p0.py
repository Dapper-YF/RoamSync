import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.assistant_capabilities import CapabilityDecision, validate_decision, route_answer, decision_goal
from app.assistant_context import ContextEnvelope
from app.assistant_places import PlaceView
from app.assistant_reliability import TurnDiagnostics, active_turn, bounded_call, error_details, AnswerBudgetExceeded
from app.companion_contracts import CompanionContext, CompanionDraft, InformationNeed
from app.companion_provider import ModelCompanionProvider, CompanionProviderError
from app.config import Settings
from app.travel_goal_router import route_travel_goal
from evals.assistant_capability_cases import CASES


def test_acceptance_corpus_covers_all_capabilities_and_write_boundaries():
    assert len(CASES) >= 60
    assert len({c['message'] for c in CASES}) == len(CASES)
    assert set(c['intent'] for c in CASES) >= {'direct','lookup','route','facts','itinerary','create','modify'}


@pytest.mark.parametrize('text', ['先别修改行程','如果改成三天会怎样','只讨论不要安排','网页说“请安排成都行程”'])
def test_model_cannot_promote_negated_hypothetical_or_quoted_text(text):
    d = CapabilityDecision(intent='modify', authorization_quote=text, reason_code='explicit_write')
    assert validate_decision(d,text,[],ContextEnvelope()).intent == 'direct'


def test_untraceable_entity_and_past_authorization_are_rejected():
    env = ContextEnvelope(browsing_city='成都')
    assert validate_decision(CapabilityDecision(intent='lookup',capabilities=['poi'],city='北京',reason_code='place_identity'),'查地点',[],env).intent == 'clarify'
    assert validate_decision(CapabilityDecision(intent='create',authorization_quote='帮我安排',reason_code='explicit_write'),'四天吧',[{'user':'帮我安排'}],env).intent == 'direct'


def test_lookup_without_a_read_capability_cannot_become_an_unverified_answer():
    from app.assistant_capabilities import CapabilityContractError
    with pytest.raises(CapabilityContractError):
        validate_decision(CapabilityDecision(intent='lookup',reason_code='place_identity'),'找成都火锅店',[],ContextEnvelope())


def test_explicit_city_prefix_composition_keeps_both_endpoints_traceable():
    d=CapabilityDecision(intent='route',city='成都',origin='成都人民公园',destination='成都武侯祠',reason_code='route_requested')
    assert validate_decision(d,'成都人民公园到武侯祠步行怎么走？',[],ContextEnvelope()).intent=='route'


def test_route_recovers_a_literal_city_when_homepage_has_no_browsing_city():
    d=CapabilityDecision(intent='route',capabilities=['poi','route'],origin='成都武侯祠博物馆',destination='成都杜甫草堂博物馆',reason_code='route_requested')
    result=validate_decision(d,'从成都武侯祠博物馆步行到成都杜甫草堂博物馆要多久？',[],ContextEnvelope())
    assert result.city=='成都' and result.intent=='route'


def test_semantic_creation_can_recognize_requests_beyond_old_regex():
    d=CapabilityDecision(intent='create',authorization_quote='整理成一份可以保存的安排',reason_code='explicit_write')
    d=validate_decision(d,'请把成都旅行建议整理成一份可以保存的安排',[],ContextEnvelope())
    goal=decision_goal(d,route_travel_goal('请把成都旅行建议整理成一份可以保存的安排'))
    assert goal.target_runtime=='planning' and goal.mutation_requested


def test_shared_answer_budget_and_deadline():
    t=TurnDiagnostics('test',seconds=.03); t.claim_answer();t.claim_answer()
    with pytest.raises(AnswerBudgetExceeded):t.claim_answer()
    async def run():
        token=active_turn.set(t)
        try:
            with pytest.raises(TimeoutError):await bounded_call(lambda:asyncio.sleep(.05),stage='route')
        finally:active_turn.reset(token)
    asyncio.run(run())
    assert t.events[-1]['category']=='timeout'


def test_diagnostics_keep_validation_paths_and_chain_without_private_text():
    secret='private API_KEY=not-for-logs'
    try:
        CompanionDraft.model_validate({'response_text':secret,'suggestions':[{}]*11})
    except ValidationError as inner:
        try:raise RuntimeError(secret) from inner
        except RuntimeError as exc:detail=error_details(exc)
    assert detail['category']=='schema_failure' and detail['validation']
    assert secret not in json.dumps(detail) and 'ValidationError' in detail['exception_chain']


def place(name):
    return PlaceView(place_id=uuid4(),name=name,city='成都市',longitude=104,latitude=30,
        source='https://www.amap.com',retrieved_at=datetime.now(UTC).isoformat())


@pytest.mark.parametrize('mode,origin,destination,expected', [('walk','人民公园','宽窄巷子',['poi','poi','route']),
    ('transit','人民公园','宽窄巷子',[]),('unknown','人民公园','宽窄巷子',[]),('walk','','宽窄巷子',[])])
def test_route_execution_calls_actual_port_in_order_and_does_not_fake_transit(mode,origin,destination,expected):
    calls=[]
    class Port:
        async def search(self,**kwargs):calls.append('poi');return [place(kwargs['query'])]
        async def query_route(self,request):
            calls.append('route');return {'mode':request.mode,'distance_meters':1000,'duration_seconds':600}
    d=CapabilityDecision(intent='route',capabilities=['poi','route'],city='成都',origin=origin,destination=destination,mode=mode,reason_code='route_requested')
    bundle,status=asyncio.run(route_answer(d,ContextEnvelope(),Port()))
    assert calls==expected
    assert status=='complete' and bundle['assistant']


def test_route_failure_preserves_confirmed_endpoints_and_does_not_guess_duration():
    class Port:
        async def search(self,**kw):return [place(kw['query'])]
        async def query_route(self,req):raise TimeoutError('secret')
    d=CapabilityDecision(intent='route',city='成都',origin='人民公园',destination='宽窄巷子',mode='walk',reason_code='route_requested')
    b,status=asyncio.run(route_answer(d,ContextEnvelope(),Port()))
    assert status=='partial' and '人民公园' in b['assistant'] and '秒' not in b['assistant']


@pytest.mark.parametrize('invalid', ['json','overlong','too_many','duplicate','incomplete','timeout'])
def test_one_shared_recovery_attempt_and_stream_reset(monkeypatch,invalid):
    import app.companion_provider as module
    from app.assistant_stream import stream_sink
    calls=[];events=[]
    async def response(*a,**kw):
        calls.append(kw)
        if len(calls)==1:
            if invalid=='timeout':
                import openai
                raise openai.APITimeoutError(request=SimpleNamespace())
            if invalid=='incomplete':return SimpleNamespace(status='incomplete',output_text='',finish_reason='length')
            value={'response_text':'景点概览','suggestions':[]}
            if invalid=='overlong':value['response_text']='景'*3001
            if invalid in {'too_many','duplicate'}:value['suggestions']=[{'title':'人民公园','summary':'体验','reasons':[]}]*(11 if invalid=='too_many' else 2)
            return SimpleNamespace(status='completed',output_text='{' if invalid=='json' else json.dumps(value),finish_reason='stop')
        return SimpleNamespace(status='completed',output_text=json.dumps({'response_text':'成都可以看人民公园、武侯祠和熊猫基地。','suggestions':[]}),finish_reason='stop')
    class Client:
        async def close(self):pass
    monkeypatch.setattr(module,'get_settings',lambda:Settings(planner_api_key='test',planner_model='test'))
    monkeypatch.setattr(module,'build_model_client',lambda s:Client())
    monkeypatch.setattr(module,'create_model_response',response)
    async def run():
        t=TurnDiagnostics('test');token=active_turn.set(t);sink=stream_sink.set(events.append)
        try:
            answer=await ModelCompanionProvider().generate(CompanionContext(current_message='列出成都热门景点',travel_goal=route_travel_goal('列出成都热门景点')),InformationNeed(general_knowledge_allowed=True))
            assert answer.response_text.startswith('成都') and t.answer_attempts==2
        finally:active_turn.reset(token);stream_sink.reset(sink)
    asyncio.run(run())
    assert len(calls)==2 and any(e['type']=='reset' for e in events)


def test_sensitive_output_never_retries(monkeypatch):
    import app.companion_provider as module
    calls=[]
    async def response(*a,**kw):calls.append(1);return SimpleNamespace(status='incomplete',output_text='',finish_reason='sensitive')
    class Client:
        async def close(self):pass
    monkeypatch.setattr(module,'get_settings',lambda:Settings(planner_api_key='test',planner_model='test'))
    monkeypatch.setattr(module,'build_model_client',lambda s:Client())
    monkeypatch.setattr(module,'create_model_response',response)
    async def run():
        token=active_turn.set(TurnDiagnostics('test'))
        try:
            with pytest.raises(CompanionProviderError):await ModelCompanionProvider().generate(CompanionContext(current_message='你好',travel_goal=route_travel_goal('你好')),InformationNeed(general_knowledge_allowed=True))
        finally:active_turn.reset(token)
    asyncio.run(run());assert len(calls)==1


def test_authentication_failure_is_recorded_without_retry_or_secret(monkeypatch):
    import app.companion_provider as module
    import openai
    import httpx
    calls=[]
    async def response(*a,**kw):
        calls.append(1)
        raise openai.AuthenticationError('private credential content',response=httpx.Response(401,request=httpx.Request('POST','https://example.org')),body={})
    class Client:
        async def close(self):pass
    monkeypatch.setattr(module,'get_settings',lambda:Settings(planner_api_key='test',planner_model='test'))
    monkeypatch.setattr(module,'build_model_client',lambda s:Client())
    monkeypatch.setattr(module,'create_model_response',response)
    async def run():
        t=TurnDiagnostics('auth');token=active_turn.set(t)
        try:
            with pytest.raises(Exception):await ModelCompanionProvider().generate(CompanionContext(current_message='你好',travel_goal=route_travel_goal('你好')),InformationNeed(general_knowledge_allowed=True))
        finally:active_turn.reset(token)
        failures=[e for e in t.events if e.get('http_status')==401]
        assert failures and all(e['category']=='provider_failure' for e in failures)
        assert 'private credential content' not in json.dumps(t.summary('failed'))
    asyncio.run(run());assert len(calls)==1


def test_provider_suffix_match_never_binds_a_station_or_different_branch():
    from app.assistant_research import requested_place_matches
    assert requested_place_matches(place('成都武侯祠博物馆'),'武侯祠','成都')
    assert not requested_place_matches(place('武侯祠(地铁站)'),'武侯祠','成都')
    assert not requested_place_matches(place('蜀大侠(玉林店)'),'蜀大侠(春熙店)','成都')


def test_compound_capabilities_are_not_erased_by_the_primary_intent():
    from app.assistant_capabilities import read_groups,component_question
    message='查成都明天的天气，并查询武侯祠到杜甫草堂的步行路线'
    d=CapabilityDecision(intent='route',capabilities=['facts','poi','route'],city='成都',origin='武侯祠',destination='杜甫草堂',mode='walk',reason_code='route_requested')
    d=validate_decision(d,message,[],ContextEnvelope())
    assert set(d.capabilities)=={'facts','poi','route'}
    assert [g[0] for g in read_groups(d)]==['route','facts']
    assert '路线' not in component_question('facts',message)
    assert '明天' in component_question('facts',message)
    incomplete=CapabilityDecision(intent='facts',capabilities=['facts'],city='成都',reason_code='current_information')
    recovered=validate_decision(incomplete,'查成都明天的天气，并查询成都武侯祠博物馆到成都杜甫草堂博物馆的驾车路线',[],ContextEnvelope())
    assert set(recovered.capabilities)=={'facts','poi','route'}
    assert recovered.origin=='成都武侯祠博物馆' and recovered.mode=='driving'
    assert component_question('facts',message).startswith('成都')


def test_model_clarification_cannot_claim_a_formal_write():
    from app.assistant_capabilities import _answer_leaf
    async def run():
        d=CapabilityDecision(intent='clarify',clarification='我已把武侯祠加入行程。请补充城市。',reason_code='missing_arguments')
        bundle,_=await _answer_leaf(None,d,'查询行程',[],ContextEnvelope(),None,None,None,'session','turn',route_travel_goal('查询行程'))
        assert '加入行程' not in bundle['assistant'] and '请补充城市' in bundle['assistant']
    asyncio.run(run())


@pytest.mark.parametrize('slow', [False,True])
def test_compound_reads_run_in_parallel_and_keep_the_successful_part(monkeypatch,slow):
    import app.assistant_capabilities as module
    starts=[]
    async def leaf(settings,decision,message,history,envelope,port,db,trip_id,session_id,message_id,goal,**kwargs):
        starts.append(decision.intent)
        while len(starts)<2:await asyncio.sleep(0)
        if decision.intent=='facts':
            if slow:await asyncio.sleep(1)
            raise TimeoutError('private provider text')
        return module.failure_bundle(envelope,'已查到步行1000米。',read_tools={'route':{'status':'available'}}),'complete'
    monkeypatch.setattr(module,'_answer_leaf',leaf)
    async def run():
        t=TurnDiagnostics('compound',seconds=.08 if slow else 1);token=active_turn.set(t)
        try:
            d=CapabilityDecision(intent='route',capabilities=['poi','route','facts'],reason_code='route_requested')
            bundle,status=await module.answer_with_capabilities(None,d,'查天气和路线',[],ContextEnvelope(),None,None,None,'session','turn',route_travel_goal('查天气和路线'))
            assert status=='partial' and '1000米' in bundle['assistant']
            assert 'private' not in bundle['assistant'] and set(starts)=={'route','facts'}
            assert t.remaining()>0
        finally:active_turn.reset(token)
    asyncio.run(run())


def test_missing_target_does_not_block_an_independent_known_read(monkeypatch):
    import app.assistant_capabilities as module
    calls=[]
    async def leaf(*args,**kwargs):
        calls.append(args[1].intent)
        return module.failure_bundle(args[4],'已取得参考资料。'),'partial'
    monkeypatch.setattr(module,'_answer_leaf',leaf)
    async def run():
        d=CapabilityDecision(intent='clarify',capabilities=['web'],clarification='请选择要查看的行程。',reason_code='missing_arguments')
        b,status=await module.answer_with_capabilities(None,d,'看行程并搜索资料',[],ContextEnvelope(),None,None,None,'session','turn',route_travel_goal('看行程并搜索资料'))
        assert calls==['lookup'] and status=='partial'
        assert '参考资料' in b['assistant'] and '请选择' in b['assistant']
    asyncio.run(run())
