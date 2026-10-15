"""A noisy search phrase is not a city; model output still needs evidence."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from app.companion_facts import CompanionFactAdapter
from app.forecast_location_extraction import extract_forecast_city_mentions
from app.config import Settings
from test_forecast_city_resolution import city_tool, NOW


def bounded_tool(extracted):
    base, _, weather = city_tool()
    calls = []

    async def lookup(name):
        calls.append(name)
        if name == "南昌":
            return await base.places.providers[0].gateway(name)
        return {"results": []}

    extractor = AsyncMock(return_value=extracted)
    return CompanionFactAdapter(geocoder=lookup, weather_gateway=base.weather_gateway,
        clock=lambda: NOW, location_extractor=extractor), calls, weather, extractor


@pytest.mark.parametrize("message", ["所以南昌今天会不会下雨啊", "那么南昌今天会不会下雨啊", "所以，南昌今天会不会下雨啊"])
def test_screenshot_phrase_sends_only_city_to_location_service(message):
    async def run():
        tool, calls, _, extractor = bounded_tool([])
        plan = await tool.plan_forecast(message, "南京", [])
        assert calls == ["南昌"] and plan.requirements and plan.location_label.startswith("南昌")
        extractor.assert_not_awaited()
    asyncio.run(run())


def test_semantic_extraction_recovers_new_phrase_and_requires_second_provider_check():
    async def run():
        tool, calls, _, extractor = bounded_tool(["南昌"])
        question = "你觉得南昌今天会不会下雨啊"
        plan = await tool.plan_forecast(question, "南京", [])
        assert calls == ["你觉得南昌", "南昌"]
        extractor.assert_awaited_once_with(question)
        assert plan.requirements and plan.place_result.usable_as_current
        assert plan.place_result.requirement.subject.destination == "南昌"
    asyncio.run(run())


@pytest.mark.parametrize("extracted", [["广州"], ["不存在城"], [], None, {"city": "南昌"}])
def test_invalid_or_unverified_proposal_cannot_use_old_city_or_forecast(extracted):
    async def run():
        tool, calls, weather, extractor = bounded_tool(extracted)
        plan = await tool.plan_forecast("你觉得不存在城今天会不会下雨啊", "南京", [])
        assert not plan.requirements and not weather and "南京" not in calls
        assert extractor.await_count == 1
        assert "广州" not in calls
    asyncio.run(run())


def test_provider_outage_does_not_trigger_model_to_repair_city():
    async def run():
        tool, _, _, extractor = bounded_tool(["南昌"])
        tool.places.providers[0].gateway = AsyncMock(side_effect=TimeoutError())
        plan = await tool.plan_forecast("你觉得南昌今天天气？", None, [])
        assert not plan.requirements
        extractor.assert_not_awaited()
    asyncio.run(run())


@pytest.mark.parametrize("output,status,expected", [
    ('{"cities":["南昌"]}', "completed", ["南昌"]),
    ('{"cities":["广州"]}', "completed", []),
    ('{"cities":["南昌"],"weather":"晴"}', "completed", []),
    ('{"cities":["南昌"]}', "incomplete", []),
    ('not JSON', "completed", []),
])
def test_model_extraction_accepts_only_complete_schema_and_literal_user_span(output,status,expected):
    async def run():
        client = SimpleNamespace(close=AsyncMock())
        settings = Settings(_env_file=None, planner_api_key=SecretStr("synthetic"), planner_model="synthetic")
        with patch("app.config.get_settings",return_value=settings), \
             patch("app.model_client.build_model_client",return_value=client), \
             patch("app.model_client.create_model_response",new=AsyncMock(return_value=SimpleNamespace(status=status,output_text=output))) as create:
            assert await extract_forecast_city_mentions("你觉得南昌今天会不会下雨啊") == expected
            assert create.await_count == 1
        client.close.assert_awaited_once()
    asyncio.run(run())
