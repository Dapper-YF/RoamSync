"""User-provided cities must survive extraction, validation and conversation."""
import asyncio
from datetime import UTC, datetime

import pytest

from app.companion_facts import CompanionFactAdapter
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal
from evals.companion_phase2.run import Reader
from test_companion_facts import NoModel, tool_fixture

NOW = datetime(2026, 10, 15, 0, tzinfo=UTC)


def city_tool(*, mode="success"):
    calls = []

    async def geocoder(query):
        calls.append(query)
        if mode == "failure":
            raise TimeoutError()
        if mode == "empty":
            return {"results": []}
        rows = [dict(id=10, name=query, admin1="江西", country_code="CN", feature_code="PPLA2",
                     timezone="Asia/Shanghai", latitude=28.68, longitude=115.85)]
        if mode == "ambiguous":
            rows += [dict(rows[0], id=11, admin1="江苏", latitude=31.3, longitude=120.6)]
        if mode == "fuzzy":
            rows[0]["name"] = query + "新区"
        if mode == "village":
            rows[0]["feature_code"] = "PPL"
        if mode == "foreign":
            rows[0]["country_code"] = "US"
        if mode == "missing_timezone":
            rows[0].pop("timezone")
        return {"results": rows}

    forecast, weather_calls = tool_fixture()
    tool = CompanionFactAdapter(geocoder=geocoder, weather_gateway=forecast.weather_gateway, clock=lambda: NOW)
    return tool, calls, weather_calls


@pytest.mark.parametrize("message,city", [
    ("南昌今天会下雨吗", "南昌"),
    ("帮我查一下南昌今天会不会下雨？", "南昌"),
    ("今天苏州天气怎么样？", "苏州"),
    ("请问北京市明天下午的天气？", "北京"),
    ("我在南昌，今天会下雨吗？", "南昌"),
    ("江西省南昌市今天会下雨吗？", "南昌"),
    ("呼和浩特明天天气？", "呼和浩特"),
    ("景德镇明天下午天气？", "景德镇"),
    ("芒市明天天气？", "芒市"),
    ("所以南昌今天会不会下雨啊", "南昌"),
    ("所以，南昌今天会不会下雨啊", "南昌"),
    ("那么南昌今天会不会下雨啊", "南昌"),
])
def test_arbitrary_explicit_city_reaches_verified_forecast(message, city):
    async def run():
        tool, calls, _ = city_tool()
        result = await CompanionRuntime(Reader(), NoModel(), fact_tool=tool).run(
            session_id="generic-city", turn_id="1", message=message,
            goal=route_travel_goal(message), messages=[])
        assert calls == [city]
        assert result.resolved_facts and all(row.usable_as_current for row in result.resolved_facts)
        assert "预计气温" in result.response_text and city in result.response_text
        assert "哪个城市" not in result.response_text and "目前支持杭州和南京" not in result.response_text
        assert not result.planning_handoff
    asyncio.run(run())


def test_new_explicit_city_wins_over_previous_destination():
    async def run():
        tool, calls, _ = city_tool()
        plan = await tool.plan_forecast("南昌今天会下雨吗", "南京", [{"user": "我准备去南京"}])
        assert calls == ["南昌"] and plan.requirements and "南昌" in plan.location_label
        tool, calls, _ = city_tool(mode="empty")
        plan = await tool.plan_forecast("不存在城今天会下雨吗", "南京", [{"user": "我准备去南京"}])
        assert calls == ["不存在城"] and not plan.requirements and not plan.clarification
        assert "不存在城" in plan.message and "哪个城市" not in plan.message
    asyncio.run(run())


def test_city_context_and_weather_followup_use_user_destination():
    async def run():
        tool, calls, _ = city_tool()
        plan = await tool.plan_forecast("明天下午天气呢？", None, [{"user": "我准备去南昌。"}])
        assert calls == ["南昌"] and plan.requirements
        runtime = CompanionRuntime(Reader(), NoModel(), fact_tool=tool)
        message = "南昌今天会下雨吗"
        first = await runtime.run(session_id="cities", turn_id="1", message=message,
                                  goal=route_travel_goal(message), messages=[])
        second = await runtime.run(session_id="cities", turn_id="2", message="明天下午天气呢？",
            goal=route_travel_goal("明天下午天气呢？"),
            messages=[{"id": "1", "user": message, "companion_result": first.model_dump(mode="json")}])
        assert second.conversation_destination == "南昌" and second.resolved_facts
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["failure", "empty", "fuzzy", "village", "foreign", "missing_timezone"])
def test_lookup_failure_keeps_supplied_city_without_weather_guesses(mode):
    async def run():
        tool, calls, weather_calls = city_tool(mode=mode)
        plan = await tool.plan_forecast("南昌今天会下雨吗", None, [])
        assert calls == ["南昌"] and not plan.requirements and not weather_calls
        assert not plan.clarification and "南昌" in plan.message and "哪个城市" not in plan.message
    asyncio.run(run())


def test_real_ambiguity_asks_province_and_qualified_city_resolves():
    async def run():
        tool, _, weather_calls = city_tool(mode="ambiguous")
        plan = await tool.plan_forecast("南昌今天天气？", None, [])
        assert plan.clarification and "江西" in plan.message and "江苏" in plan.message and not weather_calls
        plan = await tool.plan_forecast("江西省南昌市今天天气？", None, [])
        assert plan.requirements and not plan.clarification
    asyncio.run(run())


def test_missing_information_is_distinct_from_provider_failure():
    async def run():
        tool, calls, _ = city_tool()
        plan = await tool.plan_forecast("今天天气怎么样？", None, [])
        assert plan.clarification and "哪个城市" in plan.message and not calls
        plan = await tool.plan_forecast("南昌天气怎么样？", None, [])
        assert plan.clarification and "哪一天" in plan.message and not calls
        plan = await tool.plan_forecast("南昌今天天气，苏州明天天气", None, [])
        assert plan.clarification and "多个地点" in plan.message and not calls
    asyncio.run(run())
