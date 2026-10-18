import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from app.companion_facts import CompanionFactAdapter, time_window, forecast_text
from app.companion_runtime import CompanionRuntime
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.travel_goal_router import route_travel_goal
from app.travel_facts.models import FactBundle, ResolvedFact
from evals.companion_phase2.run import Reader, CountingTool

NOW=datetime(2026,9,30,8,tzinfo=UTC)
class NoModel:
    async def generate(self,*args): raise AssertionError("No model may fill weather gaps")

def tool_fixture(mode="success"):
    async def geocode(name):
        if mode=="location_failed": raise TimeoutError()
        city,admin=("杭州","浙江省") if name=="杭州" else ("南京","江苏省")
        item=dict(id=1 if city=="杭州" else 2,name=city,admin1=admin,country_code="CN",feature_code="PPLA",timezone="Asia/Shanghai",latitude=30.2,longitude=120.1)
        return {"results":[item,item] if mode=="ambiguous_provider" else [item]}
    calls=[]
    async def weather(subject,scope,now):
        calls.append(scope)
        if mode=="timeout": raise TimeoutError()
        if mode=="5xx": raise RuntimeError("private provider URL must not escape")
        start=datetime.combine(scope.start.astimezone(UTC).date(),datetime.min.time(),tzinfo=UTC)
        payload={"timezone":"UTC","hourly_units":{"temperature_2m":"°C","precipitation_probability":"%","weather_code":"wmo code"},
            "hourly":{"time":[(start+timedelta(hours=i)).isoformat() for i in range(24)],"temperature_2m":[20+i/10 for i in range(24)],"precipitation_probability":[30]*24,"weather_code":[3]*24}}
        if mode=="malformed": payload["hourly"]["temperature_2m"]=[None]*24
        if mode=="empty": payload["hourly"]["time"]=[]
        queried=now-timedelta(hours=1) if mode=="stale" else now
        return SimpleNamespace(provider="open_meteo",latitude=subject.location.latitude,longitude=subject.location.longitude,payload=payload,queried_at=queried.isoformat())
    tool=CompanionFactAdapter(geocoder=geocode,weather_gateway=weather,clock=lambda:NOW)
    return tool,calls

@pytest.mark.parametrize("text,hours",[("杭州明天下午天气怎么样？",6),("杭州明天会下雨吗？",24),("10月2日下午南京天气如何？",6),("南京后天上午天气如何？",6),("杭州明天晚上天气？",6),("杭州今天晚上天气？",6)])
def test_future_forecast_typed_natural_and_readonly(text,hours):
    async def run():
        fact,calls=tool_fixture();knowledge=CountingTool(await build_reviewed_knowledge_tool());goal=route_travel_goal(text)
        assert goal.target_runtime=="companion" and not goal.mutation_requested
        result=await CompanionRuntime(Reader(),NoModel(),knowledge,fact).run(session_id="forecast",turn_id="1",message=text,goal=goal,messages=[])
        assert len(result.information_need.fact_requirements)==hours
        assert len(result.resolved_facts)==hours and all(r.usable_as_current for r in result.resolved_facts)
        assert not knowledge.calls and not result.planning_handoff
        assert "预计气温" in result.response_text and "Open-Meteo" not in result.response_text
        assert all(r.selected_evidence and r.selected_evidence[0].retrieved_at for r in result.resolved_facts)
        assert result.status=="completed" and len(calls)<=2
        assert all(r.requirement.time_scope.start.utcoffset()==timedelta(hours=8) for r in result.resolved_facts)
    asyncio.run(run())

@pytest.mark.parametrize("mode",["timeout","5xx","malformed","empty","location_failed","stale","ambiguous_provider"])
def test_provider_failure_never_guesses(mode):
    async def run():
        fact,calls=tool_fixture(mode)
        result=await CompanionRuntime(Reader(),NoModel(),fact_tool=fact).run(session_id="forecast",turn_id=mode,message="杭州明天下午天气怎么样？",goal=route_travel_goal("杭州明天下午天气怎么样？"),messages=[])
        assert "没有拿到可靠" in result.response_text and "预计气温" not in result.response_text
        assert result.status=="needs_information" and not result.suggestions
        assert not any(r.usable_as_current for r in result.resolved_facts)
        assert "private" not in result.response_text and len(calls)<=1
    asyncio.run(run())

@pytest.mark.parametrize("text,clarify",[("杭州现在多少度？",False),("杭州昨天下午下雨了吗？",False),("西湖区明天天气？",True),("明天下午天气？",True),("杭州天气怎么样？",True),("杭州明天后天天气？",True)])
def test_current_past_and_ambiguity_are_not_guessed(text,clarify):
    async def run():
        fact,calls=tool_fixture()
        result=await CompanionRuntime(Reader(),NoModel(),fact_tool=fact).run(session_id="forecast",turn_id="gap",message=text,goal=route_travel_goal(text),messages=[])
        assert not result.resolved_facts and not calls
        assert result.status==("needs_clarification" if clarify else "needs_information")
        assert not any(s in result.response_text for s in ["预算","返程","FactRequirement","provider_prediction"])
    asyncio.run(run())

def test_context_location_and_mixed_failure_independence():
    async def run():
        fact,_=tool_fixture();plan=await fact.plan_forecast("明天下午天气怎么样？",None,[{"user":"我准备去南京。"}])
        assert "南京" in plan.location_label
        runtime=CompanionRuntime(Reader(),NoModel(),fact_tool=fact)
        text='南京明天下午天气怎么样？'
        first=await runtime.run(session_id='context',turn_id='1',message=text,goal=route_travel_goal(text),messages=[])
        second=await runtime.run(session_id='context',turn_id='2',message='后天上午天气呢？',goal=route_travel_goal('后天上午天气呢？'),messages=[{'id':'1','user':text,'companion_result':first.model_dump(mode='json')}])
        assert second.conversation_destination=='南京' and second.resolved_facts
        for mode in ["success","timeout"]:
            fact,_=tool_fixture(mode);knowledge=CountingTool(await build_reviewed_knowledge_tool())
            text="西湖有什么历史文化特色，明天下午天气怎么样？"
            result=await CompanionRuntime(Reader(),NoModel(),knowledge,fact).run(session_id="mixed",turn_id=mode,message=text,goal=route_travel_goal(text),messages=[])
            assert knowledge.calls and result.claims and "西湖" in result.response_text
            assert ("预计气温" in result.response_text)==(mode=="success")
            assert not result.planning_handoff
    asyncio.run(run())

def test_timezone_dayparts_and_invalid_date():
    local=datetime(2026,9,30,23,30,tzinfo=UTC)
    window,_,_=time_window("明天下午","Asia/Shanghai",local)
    assert window[0].isoformat()=="2026-10-02T12:00:00+08:00"
    assert time_window("2月30日下午","Asia/Shanghai",NOW)[2]
    assert time_window("10月20日下午","Asia/Shanghai",NOW)[0] is None

def test_conflicting_resolver_not_selected_by_companion():
    async def run():
        tool,_=tool_fixture();plan=await tool.plan_forecast("杭州明天下午天气？",None,[])
        rs=[ResolvedFact(requirement=q,resolution_status="conflicting",resolved_at=NOW) for q in plan.requirements]
        assert "存在冲突" in forecast_text(plan,rs) and "预计气温" not in forecast_text(plan,rs)
    asyncio.run(run())

def test_stale_cache_only_is_not_published_and_tight_boundary():
    async def run():
        tool,calls=tool_fixture();plan=await tool.plan_forecast("杭州明天下午天气？",None,[])
        await tool.resolve_facts(plan.requirements)
        tool.clock=lambda:NOW+timedelta(hours=1)
        async def failed(*args): raise TimeoutError()
        tool.weather_gateway=failed
        rs=await tool.resolve_facts(plan.requirements)
        assert all(r.resolution_status=="stale" and not r.usable_as_current for r in rs)
        assert "预计气温" not in forecast_text(plan,rs)
    asyncio.run(run())
