"""Shared AMap transport/errors without planner, model, or database imports."""
import json
import time as clock_time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

class MapProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "map_provider_unavailable",
        status_code: int = 503,
        provider_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.provider_code = provider_code



_QUOTA_CODES = {"10003", "10004", "10010", "10044", "10045"}
_CREDENTIAL_CODES = {"10001", "10002", "10005", "10007", "10008", "10009", "10012", "10019"}


def _missing_key_error() -> MapProviderError:
    return MapProviderError(
        "未配置高德 Web 服务 Key",
        code="map_not_configured",
    )


def _provider_response_error(payload: dict[str, Any], fallback: str) -> MapProviderError:
    provider_code = str(payload.get("infocode") or "") or None
    provider_message = str(payload.get("info") or fallback)
    if "QPS" in provider_message:
        return MapProviderError("高德查询频率暂时受限，请稍后重试", code="map_rate_limited", status_code=429, provider_code=provider_code)
    if provider_code in _QUOTA_CODES:
        return MapProviderError(
            "高德免费配额或并发额度已用尽，请稍后重试或检查控制台配额",
            code="map_quota_exceeded",
            status_code=429,
            provider_code=provider_code,
        )
    if provider_code in _CREDENTIAL_CODES:
        return MapProviderError(
            "高德 Web 服务 Key 无效或权限配置不正确",
            code="map_credentials_invalid",
            provider_code=provider_code,
        )
    return MapProviderError(
        provider_message,
        code="map_provider_rejected",
        provider_code=provider_code,
    )


def get_json(url: str, *, opener=urlopen, sleep=clock_time.sleep) -> dict[str, Any]:
    for attempt in range(2):
        try:
            with opener(url, timeout=12) as response:  # noqa: S310 - fixed AMap host
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise MapProviderError("高德响应格式无效", code="map_invalid_response")
            if attempt == 0 and payload.get("status") != "1" and "QPS" in str(payload.get("info", "")):
                sleep(1.1)
                continue
            return payload
        except HTTPError as exc:
            # Do not retry rejected requests or provider quotas.
            if attempt == 0 and exc.code >= 500:
                continue
            raise MapProviderError("高德服务暂时不可用，请稍后重试", code="map_network_error") from exc
        except (URLError, OSError) as exc:
            if attempt == 0:
                continue
            raise MapProviderError("高德服务连接超时或暂时不可用，请稍后重试", code="map_network_error") from exc
        except (ValueError, UnicodeError) as exc:
            raise MapProviderError("高德返回的数据暂时无法读取，请稍后重试", code="map_invalid_response") from exc
    raise AssertionError("map retry loop exited unexpectedly")


