import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.companion_facts import CompanionFactAdapter, opening_text
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal
from app.travel_facts.opening_hours import reviewed_schedule
from app.travel_facts.models import OpeningHoursValue, TimeScope, FactBundle
from app.travel_facts.resolution import resolve_bundle
from evals.companion_phase2.run import Reader
from test_companion_facts import NoModel, tool_fixture

NOW=datetime(2026,10,1,10,tzinfo=UTC)
def payload(provider):
    name='nanjing' if provider=='nanjing_museum' else 'zhejiang'
    return json.loads((Path(__file__).parent/'fixtures/opening_hours'/f'{name}.json').read_text(encoding='utf-8-sig'))

def hours_tool(mode='success'):
    calls=[]
    async def gateway(provider):
        calls.append(provider)
        if mode=='failure': raise TimeoutError()
        data=payload(provider)
        if mode=='malformed': return {}
        return data
    forecast,weather_calls=tool_fixture()
    tool=CompanionFactAdapter(geocoder=forecast.places.providers[0].gateway,weather_gateway=forecast.weather_gateway,opening_gateway=gateway,clock=lambda:NOW)
    return tool,calls,weather_calls

@pytest.mark.parametrize('text,closed',[('南京博物院明天几点开门？',False),('浙江省博物馆之江馆区明天开放时间？',False),('浙江省博物馆之江馆区10月8日开馆吗？',True),('南京博物院周一开馆吗？',False)])
def test_official_target_day_native(text,closed):
    async def run():
        tool,calls,weather=hours_tool(); plan=await tool.plan_opening_hours(text,[])
        result=(await tool.resolve_facts(plan.requirements))[0]
        assert result.usable_as_current and result.value.closed_all_day==closed
        assert not weather and len(calls)==1
        assert result.value.local_date==str(plan.requirements[0].time_scope.start.date())
        assert result.value.timezone=='Asia/Shanghai'
        if not closed: assert result.value.intervals[0].end.hour==20
        assert result.selected_evidence[0].metadata['last_updated']==('unknown' if '南京' in text else '2026-09-21T14:39:08')
        assert '不能证明此刻' in opening_text(plan,[result])
    asyncio.run(run())

@pytest.mark.parametrize('text,clarify',[('博物馆明天几点开门？',True),('西湖几点关门？',True),('浙江省博物馆明天几点开门？',True),('灵隐寺明天几点开门？',False),('南京博物院现在开着吗？',False),('南京博物院明天后天开门吗？',True),('南京博物院2月30日开门吗？',True)])
def test_entity_and_date_gate_before_network(text,clarify):
    async def run():
        tool,calls,weather=hours_tool(); plan=await tool.plan_opening_hours(text,[])
        assert plan.message and plan.clarification==clarify and not plan.requirements
        assert not calls and not weather
    asyncio.run(run())

@pytest.mark.parametrize('mode',['failure','malformed'])
def test_failure_never_guesses(mode):
    async def run():
        tool,_,_=hours_tool(mode);plan=await tool.plan_opening_hours('南京博物院明天几点开门？',[])
        result=await tool.resolve_facts(plan.requirements)
        assert not result[0].usable_as_current and '不能确认' in opening_text(plan,result)
    asyncio.run(run())

def test_outside_notice_and_changed_notice_fail_closed():
    data=payload('nanjing_museum')
    assert reviewed_schedule('nanjing_museum',data,datetime(2026,10,9).date()) is None
    data['data']['list'].append({'id':2,'time':'2026-10-01','title':'临时闭馆公告'})
    assert reviewed_schedule('nanjing_museum',data,datetime(2026,10,2).date()) is None

def test_named_campus_does_not_receive_gushan_hours():
    schedule=reviewed_schedule('zhejiang_museum',payload('zhejiang_museum'),datetime(2026,10,2).date())
    assert schedule['close']=='20:00' and schedule['admission']=='19:30'

def test_intervals_closed_and_unknown_contract():
    a=TimeScope(start=NOW,end=NOW+timedelta(hours=1));b=TimeScope(start=NOW+timedelta(hours=3),end=NOW+timedelta(hours=4))
    assert len(OpeningHoursValue(intervals=(a,b)).intervals)==2
    assert OpeningHoursValue(closed_all_day=True).closed_all_day
    assert OpeningHoursValue(unknown=True).unknown
    with pytest.raises(ValueError): OpeningHoursValue(intervals=(b,a))
    with pytest.raises(ValueError): OpeningHoursValue(closed_all_day=True,intervals=(a,))

def test_equal_authority_conflict_and_exception_overrides_lower_rank():
    async def run():
        tool,_,_=hours_tool();plan=await tool.plan_opening_hours('南京博物院明天几点开門？',[])
        # Direct planner call intentionally exercises exact typed identity.
        result=(await tool.resolve_facts(plan.requirements))[0];fact=result.selected_fact;evidence=result.selected_evidence[0]
        other_e=evidence.model_copy(update={'id':'other','source_reference':'https://official.example/other'})
        other_f=fact.model_copy(update={'id':'other','value':OpeningHoursValue(closed_all_day=True,local_date=fact.value.local_date,timezone='Asia/Shanghai',schedule_semantics='temporary_closure'),'evidence_refs':('other',)})
        bundle=FactBundle(facts=(fact,other_f),evidence=(evidence,other_e))
        conflict=resolve_bundle(plan.requirements[0],bundle,tool.freshness,tool.authority,now=NOW)
        assert conflict.resolution_status=='conflicting' and not conflict.usable_as_current
        from app.travel_facts.policies import AuthorityRule
        other_e=other_e.model_copy(update={'source_type':'official_schedule'})
        tool.authority.rules[(fact.fact_type,evidence.provider,'official_notice')]=AuthorityRule(level='authoritative',rank=90)
        tool.authority.rules[(fact.fact_type,evidence.provider,'official_schedule')]=AuthorityRule(level='authoritative',rank=100)
        closed=resolve_bundle(plan.requirements[0],FactBundle(facts=(fact,other_f),evidence=(evidence,other_e)),tool.freshness,tool.authority,now=NOW)
        assert closed.value.closed_all_day
    asyncio.run(run())

@pytest.mark.parametrize('text',["南京博物院明天几点开门？","浙江省博物馆之江馆区10月8日开馆吗？","西湖几点关门？","南京博物院现在开着吗？","南京博物院10月20日开放吗？","南京博物院明天几点开门，南京明天下午天气如何？"])
def test_real_companion_typed_server_answer(text):
    async def run():
        tool,hours,weather=hours_tool();goal=route_travel_goal(text)
        assert goal.target_runtime=='companion' and not goal.mutation_requested
        result=await CompanionRuntime(Reader(),NoModel(),fact_tool=tool).run(session_id='hours',turn_id='1',message=text,goal=goal,messages=[])
        assert not result.planning_handoff
        assert '预算' not in result.response_text and 'FactRequirement' not in result.response_text
        if '天气' not in text: assert not weather
        if '明天几点开门' in text: assert '20:00' in result.response_text
    asyncio.run(run())

def test_context_and_freshness_no_cross_turn_reuse():
    async def run():
        tool,calls,_=hours_tool()
        plan=await tool.plan_opening_hours('明天几点开门？',[{'user':'南京博物院怎么样？'}])
        assert plan.requirements[0].subject.ref=='amap:B001907TGR'
        first=(await tool.resolve_facts(plan.requirements))[0]
        await tool.resolve_facts(plan.requirements)
        assert len(calls)==2
        assert tool.freshness.classify(first.selected_fact,first.requirement,{e.id:e for e in first.evidence},now=NOW+timedelta(seconds=31))=='stale'
    asyncio.run(run())

def test_unknown_or_wrong_native_target_day_never_resolves():
    async def run():
        tool,_,_=hours_tool(); plan=await tool.plan_opening_hours('南京博物院明天几点开门？',[])
        result=(await tool.resolve_facts(plan.requirements))[0]
        fact=result.selected_fact;evidence=result.selected_evidence
        for value in [OpeningHoursValue(unknown=True),OpeningHoursValue(closed_all_day=True,local_date='2026-10-03',timezone='Asia/Shanghai')]:
            rejected=resolve_bundle(plan.requirements[0],FactBundle(facts=(fact.model_copy(update={'value':value}),),evidence=evidence),tool.freshness,tool.authority,now=NOW)
            assert not rejected.usable_as_current
        later=await tool.plan_opening_hours('南京博物院2027年国庆第二天几点开门？',[])
        assert later.requirements[0].time_scope.start.year==2027
    asyncio.run(run())

def test_explicit_other_venue_cannot_inherit_prior_hours():
    async def run():
        tool,calls,_=hours_tool();previous=[{'user':'南京博物院怎么样？'}]
        for message in ['南京市博物馆明天几点开门？','玄武湖明天几点开门？','这个南京市博物馆明天几点开门？']:
            plan=await tool.plan_opening_hours(message,previous)
            assert plan.clarification and not plan.requirements
        generic=await tool.plan_opening_hours('博物馆明天几点开门？',previous)
        assert generic.requirements[0].subject.ref=='amap:B001907TGR'
        shifted=await tool.plan_opening_hours('明天几点开门？',[*previous,{'user':'南京市博物馆怎么样？'}])
        assert not shifted.requirements and shifted.clarification and not calls
        landscape=await tool.plan_opening_hours('明天几点开门？',[*previous,{'user':'玄武湖怎么样？'}])
        assert not landscape.requirements and landscape.clarification
    asyncio.run(run())
