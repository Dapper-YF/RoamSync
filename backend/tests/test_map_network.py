import io
from urllib.error import HTTPError

import pytest

from app import maps_service


def test_map_read_retries_one_transient_timeout(monkeypatch):
    calls = []

    def respond(url, *, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError()
        return io.BytesIO(b'{"status":"1"}')

    monkeypatch.setattr(maps_service, "urlopen", respond)
    assert maps_service._get_json("https://restapi.amap.com/test")["status"] == "1"
    assert len(calls) == 2


def test_map_quota_response_is_not_retried(monkeypatch):
    calls = []

    def reject(url, *, timeout):
        calls.append(url)
        raise HTTPError(url, 429, "quota", {}, None)

    monkeypatch.setattr(maps_service, "urlopen", reject)
    with pytest.raises(maps_service.MapProviderError):
        maps_service._get_json("https://restapi.amap.com/test")
    assert len(calls) == 1


def test_map_qps_limit_backs_off_once_and_recovers(monkeypatch):
    from unittest.mock import Mock
    calls = Mock(side_effect=[io.BytesIO(b'{"status":"0","info":"CUQPS_HAS_EXCEEDED_THE_LIMIT"}'), io.BytesIO(b'{"status":"1"}')])
    sleep = Mock()
    monkeypatch.setattr(maps_service, "urlopen", calls)
    monkeypatch.setattr(maps_service.clock_time, "sleep", sleep)
    assert maps_service._get_json("https://restapi.amap.com/test")["status"] == "1"
    assert calls.call_count == 2
    sleep.assert_called_once_with(1.1)


def test_map_qps_limit_exhaustion_has_a_specific_error():
    error = maps_service._provider_response_error({"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT"}, "失败")
    assert error.code == "map_rate_limited" and error.status_code == 429


def test_cached_estimate_requires_explicit_estimate_permission():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    now = datetime.now(UTC)
    cached = SimpleNamespace(expires_at=now + timedelta(hours=1), is_estimated=True, path=[])
    assert not maps_service.usable_route_cache(cached, now,
        SimpleNamespace(amap_rest_key="", allow_map_estimates=False))
    assert maps_service.usable_route_cache(cached, now,
        SimpleNamespace(amap_rest_key="", allow_map_estimates=True))
    assert not maps_service.usable_route_cache(cached, now,
        SimpleNamespace(amap_rest_key="real-key", allow_map_estimates=True))
