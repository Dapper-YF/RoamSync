"""Bounded external fact adapters used by future research/planning nodes.

Adapters return provider data only. They do not authorize writes or turn
unverified text into formal trip state.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen, build_opener, ProxyHandler

from app.config import Settings
from app.agent_observation import observed


class ExternalFactError(RuntimeError):
    pass


async def extract_tavily(settings: Settings, *, urls: list[str]) -> dict:
    """Read known public search URLs, never crawl or claim inaccessible pages."""
    if not settings.search_api_key:
        raise ExternalFactError("tavily provider is not configured")
    def request():
        req = Request(f"{settings.tavily_base_url.rstrip('/')}/extract",
            data=json.dumps({"urls": urls[:6], "extract_depth": "basic", "format": "text"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.search_api_key}"}, method="POST")
        try:
            transport = build_opener(ProxyHandler({"https": settings.tavily_proxy_url, "http": settings.tavily_proxy_url})).open if settings.tavily_proxy_url.strip() else urlopen
            with transport(req, timeout=settings.search_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ExternalFactError("extract_provider_unavailable") from exc
    return await asyncio.to_thread(request)


@dataclass(frozen=True)
class WeatherFact:
    provider: str
    queried_at: str
    latitude: float
    longitude: float
    payload: dict


@dataclass(frozen=True)
class SearchFact:
    provider: str
    queried_at: str
    query: str
    payload: dict


def _get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float) -> dict:
    request = Request(url, headers=headers or {}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ExternalFactError("external provider request failed") from exc


@observed("weather", provider="Open-Meteo", purpose="Travel-date weather", output_summary=lambda fact: {"queried_at": fact.queried_at, "hourly_sample_count": len(fact.payload.get("hourly", {}).get("time", []))})
async def fetch_open_meteo(
    settings: Settings, *, latitude: float, longitude: float, start_date: date, end_date: date, timezone: str
) -> WeatherFact:
    query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": timezone,
    })
    payload = await asyncio.to_thread(
        _get_json, f"{settings.weather_base_url}?{query}", timeout=settings.weather_timeout_seconds
    )
    from datetime import datetime, UTC
    return WeatherFact("open_meteo", datetime.now(UTC).isoformat(), latitude, longitude, payload)


@observed("search", provider="Tavily", purpose="Destination Research", input_summary=lambda args, kwargs: {"query": kwargs.get("query")},
          output_summary=lambda fact: {"query": fact.query, "sources": [{"title": item.get("title"), "url": item.get("url"), "content": item.get("content", "")[:800]} for item in fact.payload.get("results", [])], "source_count": len(fact.payload.get("results", []))})
async def search_tavily(settings: Settings, *, query: str, max_results: int = 5, include_images: bool = False, retry_attempts: int = 2) -> SearchFact:
    key = settings.search_api_key
    if not key:
        raise ExternalFactError("tavily provider is not configured")

    def request() -> dict:
        body = json.dumps({"query": query, "max_results": max_results,
            **({"include_images": True, "include_image_descriptions": True} if include_images else {})}).encode()
        req = Request(
            f"{settings.tavily_base_url.rstrip('/')}/search",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        try:
            transport = build_opener(ProxyHandler({"https": settings.tavily_proxy_url, "http": settings.tavily_proxy_url})).open if settings.tavily_proxy_url.strip() else urlopen
            with transport(req, timeout=settings.search_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise ExternalFactError("search_authentication_failed") from exc
            raise ExternalFactError("search_provider_unavailable") from exc
        except Exception as exc:
            raise ExternalFactError("search_provider_unavailable") from exc

    for attempt in range(max(1, min(2, retry_attempts))):
        try:
            payload = await asyncio.to_thread(request)
            break
        except ExternalFactError as exc:
            if attempt + 1 >= max(1, min(2, retry_attempts)) or str(exc) == "search_authentication_failed":
                raise
            await asyncio.sleep(0.5)
    from datetime import datetime, UTC
    return SearchFact("tavily", datetime.now(UTC).isoformat(), query, payload)
