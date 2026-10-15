"""Conversational summaries retain source scope and requested detail."""
import asyncio
import re

import pytest

from app.companion_facts import forecast_text
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal
from evals.companion_phase2.run import Reader
from test_companion_facts import NoModel, tool_fixture


async def forecast(probability=90, request="杭州明天下午天气怎么样？"):
    tool, _ = tool_fixture()
    original = tool.weather_gateway

    async def weather(*args):
        result = await original(*args)
        result.payload["hourly"]["precipitation_probability"] = (
            probability if isinstance(probability, list) else [probability] * 24)
        return result

    tool.weather_gateway = weather
    plan = await tool.plan_forecast(request, None, [])
    assert plan.requirements, plan.message
    return tool, plan, await tool.resolve_facts(plan.requirements)


@pytest.mark.parametrize("probability,phrase", [(90, "下雨的可能性较大"), (45, "有可能下雨"), (5, "下雨的可能性较低")])
def test_default_answers_the_question_without_dumping_hourly_rows(probability, phrase):
    async def run():
        tool, _, _ = await forecast(probability)
        question = "杭州明天下午天气怎么样？"
        result = await CompanionRuntime(Reader(), NoModel(), fact_tool=tool).run(
            session_id="presentation", turn_id="1", message=question,
            goal=route_travel_goal(question), messages=[])
        text = result.response_text
        assert text.startswith("杭州明天下午" + phrase)
        assert len(text) < 220 and "Open-Meteo" not in text and "获取" not in text
        assert "预计气温" in text and all(r.selected_evidence for r in result.resolved_facts)
        assert "通过15分钟" not in text and "Asia/Shanghai" not in text
        assert not re.search(r"\d{2}:\d{2}–\d{2}:\d{2}：预计气温", text)
        assert len(result.resolved_facts) == 6 and result.grounding_status == "verified_forecast"
    asyncio.run(run())


def test_explicit_hourly_request_preserves_every_verified_hour():
    async def run():
        request = "杭州明天下午逐小时天气"
        _, plan, results = await forecast(request=request)
        text = forecast_text(plan, results, request)
        assert "逐小时预报" in text
        assert len(re.findall(r"\d{2}:\d{2}–\d{2}:\d{2}：预计气温", text)) == len(results)
        assert "12:00–13:00" in text and "17:00–18:00" in text
    asyncio.run(run())


def test_temperature_question_is_answered_first_without_extra_rain_advice():
    async def run():
        request = "杭州明天下午气温多少度？"
        _, plan, results = await forecast(request=request)
        text = forecast_text(plan, results, request)
        assert text.startswith("杭州明天下午预计气温约")
        assert "伞" not in text and "降水概率" not in text
    asyncio.run(run())


def test_missing_hour_does_not_become_a_continuous_verified_rain_window():
    async def run():
        _, plan, results = await forecast()
        text = forecast_text(plan, [results[0], *results[2:]], "杭州明天下午天气？")
        assert "部分时段" in text and "缺失时段暂时无法判断" in text
        assert "12:00–13:00、14:00–18:00" in text and "12:00–18:00" not in text
    asyncio.run(run())


def test_single_high_hour_is_not_reported_as_all_day_probability_or_heavy_rain():
    async def run():
        probabilities = [5] * 24
        probabilities[4] = 90  # 12:00 local time in the selected afternoon.
        _, plan, results = await forecast(probabilities)
        text = forecast_text(plan, results, "杭州明天下午降雨概率多少？")
        assert "12:00–13:00" in text and "各小时降水概率为5%–90%" in text
        assert "全天降雨概率" not in text and "大雨" not in text and "暴雨" not in text
    asyncio.run(run())


def test_unusable_forecast_cannot_generate_a_weather_summary():
    async def run():
        _, plan, results = await forecast()
        unusable = [r.model_copy(update={"resolution_status": "stale", "usable_as_current": False}) for r in results]
        text = forecast_text(plan, unusable, "杭州明天会下雨吗？")
        assert "没有拿到可靠" in text and "下雨的可能性较大" not in text
    asyncio.run(run())
