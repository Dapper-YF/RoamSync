import asyncio
import json
from datetime import date
from unittest.mock import patch

import pytest

from app.config import Settings
from app.external_facts import ExternalFactError, fetch_open_meteo, search_tavily


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_open_meteo_adapter_builds_bounded_weather_request() -> None:
    settings = Settings.model_validate({"app_env": "test"})
    payload = {"hourly": {"time": ["2026-09-07T10:00"], "temperature_2m": [26.0]}}
    with patch("app.external_facts.urlopen", return_value=_Response(payload)) as mocked:
        result = asyncio.run(
            fetch_open_meteo(
                settings,
                latitude=30.27,
                longitude=120.15,
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 8),
                timezone="Asia/Shanghai",
            )
        )
    assert result.provider == "open_meteo"
    assert result.payload == payload
    request_url = mocked.call_args.args[0].full_url
    assert "precipitation_probability" in request_url
    assert "start_date=2026-09-07" in request_url
    assert "end_date=2026-09-08" in request_url


def test_tavily_requires_configuration_without_exposing_key() -> None:
    settings = Settings.model_validate({"tavily_api_key": ""})
    with pytest.raises(ExternalFactError, match="not configured"):
        asyncio.run(search_tavily(settings, query="杭州近期开放时间"))


def test_project_scoped_search_key_takes_precedence_over_old_process_key():
    settings = Settings(tavily_api_key="expired-process-key", roamsync_tavily_api_key="current-project-key")
    assert settings.search_api_key == "current-project-key"


def test_tavily_uses_bearer_authentication_and_keeps_key_out_of_body():
    with patch("app.external_facts.urlopen", return_value=_Response({"results": []})) as mocked:
        asyncio.run(search_tavily(Settings(tavily_api_key="private-test-key"), query="大理热门景点"))
    request = mocked.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer private-test-key"
    assert b"private-test-key" not in request.data


def test_search_authentication_error_is_actionable_and_does_not_expose_key():
    from urllib.error import HTTPError
    with patch("app.external_facts.urlopen", side_effect=HTTPError("https://api.tavily.com/search", 401, "Unauthorized", {}, None)):
        with pytest.raises(ExternalFactError, match="search_authentication_failed") as error:
            asyncio.run(search_tavily(Settings(tavily_api_key="private-test-key"), query="大理热门景点"))
    assert "private-test-key" not in str(error.value)


def test_search_recovers_once_from_a_transient_connection_failure():
    from urllib.error import URLError
    with patch("app.external_facts.urlopen", side_effect=[URLError("connection interrupted"), _Response({"results": [{"title": "景区介绍"}]})]) as mocked:
        fact = asyncio.run(search_tavily(Settings(tavily_api_key="test-key"), query="大理景点"))
    assert mocked.call_count == 2
    assert fact.payload["results"][0]["title"] == "景区介绍"


def test_search_uses_its_own_configured_proxy_and_timeout():
    from unittest.mock import Mock
    opener = Mock()
    opener.open.return_value = _Response({"results": []})
    with patch("app.external_facts.build_opener", return_value=opener) as build, patch("app.external_facts.urlopen") as direct:
        asyncio.run(search_tavily(Settings(tavily_api_key="test", tavily_proxy_url="http://proxy.example:8080", search_timeout_seconds=25), query="大理景点"))
    assert build.call_args.args[0].proxies["https"] == "http://proxy.example:8080"
    assert opener.open.call_args.kwargs["timeout"] == 25
    direct.assert_not_called()
