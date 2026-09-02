import asyncio
import hashlib
import json
import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import Activity, DayPlan, PlaceCandidate, RouteCache, RouteLeg, Trip
from app.schemas import CitySuggestionResponse, LocationPoiResponse, PlaceSearchResultResponse


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


logger = logging.getLogger("roamsync.maps")

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


async def search_amap_cities(query: str) -> list[CitySuggestionResponse]:
    settings = get_settings()
    if not settings.amap_rest_key:
        raise _missing_key_error()
    params = urlencode(
        {
            "key": settings.amap_rest_key,
            "keywords": query,
            "subdistrict": 0,
            "extensions": "base",
        }
    )
    payload = await asyncio.to_thread(
        _get_json, f"https://restapi.amap.com/v3/config/district?{params}"
    )
    if payload.get("status") != "1":
        raise _provider_response_error(payload, "高德城市查询失败")
    results: list[CitySuggestionResponse] = []
    for district in payload.get("districts", [])[:8]:
        center = str(district.get("center", "")).split(",")
        if len(center) != 2 or not district.get("adcode"):
            continue
        citycode = district.get("citycode")
        if isinstance(citycode, list):
            citycode = citycode[0] if citycode else ""
        results.append(
            CitySuggestionResponse(
                name=str(district.get("name") or query),
                adcode=str(district["adcode"]),
                citycode=str(citycode or ""),
                longitude=float(center[0]),
                latitude=float(center[1]),
            )
        )
    logger.info("amap city search success query_length=%s results=%s", len(query), len(results))
    return results


async def search_amap_location_pois(
    query: str,
    city: str,
    accommodation_only: bool = False,
) -> list[LocationPoiResponse]:
    settings = get_settings()
    if not settings.amap_rest_key:
        raise _missing_key_error()
    params: dict[str, object] = {
        "key": settings.amap_rest_key,
        "keywords": query,
        "city": city,
        "citylimit": "true",
        "offset": 12,
        "page": 1,
        "extensions": "all",
    }
    if accommodation_only:
        params["types"] = "100000|120000"
    payload = await asyncio.to_thread(
        _get_json, f"https://restapi.amap.com/v3/place/text?{urlencode(params)}"
    )
    if payload.get("status") != "1":
        raise _provider_response_error(payload, "高德地点搜索失败")
    results: list[LocationPoiResponse] = []
    for poi in payload.get("pois", []):
        location = str(poi.get("location", "")).split(",")
        if len(location) != 2 or not poi.get("id") or not poi.get("name"):
            continue
        biz_ext = poi.get("biz_ext")
        rating_raw = biz_ext.get("rating") if isinstance(biz_ext, dict) else None
        try:
            rating = float(rating_raw) if rating_raw not in (None, "") else None
        except (TypeError, ValueError):
            rating = None
        results.append(
            LocationPoiResponse(
                poi_id=str(poi["id"]),
                name=str(poi["name"]),
                address=str(poi.get("address") or ""),
                district=str(poi.get("adname") or poi.get("business_area") or ""),
                longitude=float(location[0]),
                latitude=float(location[1]),
                type_name=str(poi.get("type") or ""),
                rating=rating,
            )
        )
    logger.info(
        "amap location poi search success category=%s query_length=%s results=%s",
        "accommodation" if accommodation_only else "all",
        len(query),
        len(results),
    )
    return results


def _get_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=8) as response:  # noqa: S310 - fixed AMap host
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise MapProviderError(
            "高德服务连接超时或暂时不可用，请稍后重试",
            code="map_network_error",
        ) from exc


async def search_amap_places(
    query: str,
    city: str,
    category: str | None = None,
) -> list[PlaceSearchResultResponse]:
    settings = get_settings()
    if not settings.amap_rest_key:
        if not settings.allow_map_estimates:
            raise _missing_key_error()
        return []
    params = urlencode(
        {
            "key": settings.amap_rest_key,
            "keywords": query,
            "city": city,
            "citylimit": "true",
            "offset": 12,
            "page": 1,
            "extensions": "all",
        }
    )
    payload = await asyncio.to_thread(
        _get_json, f"https://restapi.amap.com/v3/place/text?{params}"
    )
    if payload.get("status") != "1":
        raise _provider_response_error(payload, "高德地点搜索失败")

    results: list[PlaceSearchResultResponse] = []
    for poi in payload.get("pois", []):
        location = str(poi.get("location", "")).split(",")
        if len(location) != 2 or not poi.get("id") or not poi.get("name"):
            continue
        item_category = _category_for_type(str(poi.get("type", "")))
        if category is not None and item_category != category:
            continue
        photos = poi.get("photos") or []
        description = str(poi.get("address") or poi.get("type") or "高德地点搜索结果")
        tags = [part for part in str(poi.get("type", "")).split(";")[-2:] if part]
        if photos:
            tags.append("有图片")
        biz_ext = poi.get("biz_ext")
        rating_raw = biz_ext.get("rating") if isinstance(biz_ext, dict) else None
        try:
            rating = min(5.0, max(0.0, float(rating_raw or 0)))
        except (TypeError, ValueError):
            rating = 0.0
        results.append(
            PlaceSearchResultResponse(
                provider_place_id=str(poi["id"]),
                name=str(poi["name"]),
                category=item_category,
                neighborhood=str(poi.get("adname") or poi.get("business_area") or city),
                description=description[:500],
                longitude=float(location[0]),
                latitude=float(location[1]),
                suggested_duration_minutes=_duration_for_category(item_category),
                estimated_cost_fen=_cost_for_category(item_category),
                rating=rating,
                tags=tags or ["高德搜索"],
                source_url=f"https://www.amap.com/search?id={poi['id']}",
            )
        )
    logger.info("amap poi search success query_length=%s results=%s", len(query), len(results))
    return results


async def recalculate_day_route(
    session: AsyncSession,
    day_plan_id: uuid.UUID,
    mode: str = "walk",
) -> None:
    day = await session.get(DayPlan, day_plan_id)
    if day is not None:
        day.route_mode = mode
    rows = list(
        (
            await session.execute(
                select(Activity, PlaceCandidate)
                .join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
                .where(Activity.day_plan_id == day_plan_id)
                .order_by(Activity.position)
            )
        ).tuples()
    )
    await session.execute(delete(RouteLeg).where(RouteLeg.day_plan_id == day_plan_id))
    if not rows:
        return

    first_activity = rows[0][0]
    current = datetime.combine(datetime.today().date(), first_activity.scheduled_time)
    if current.hour < 7 or current.hour > 20:
        current = current.replace(hour=9, minute=0, second=0, microsecond=0)
    if not first_activity.schedule_locked:
        first_activity.scheduled_time = current.time()
    for position, ((from_activity, origin), (to_activity, destination)) in enumerate(
        zip(rows, rows[1:], strict=False)
    ):
        result = await resolve_route_result(session, origin, destination, mode)
        session.add(
            RouteLeg(
                day_plan_id=day_plan_id,
                from_activity_id=from_activity.id,
                to_activity_id=to_activity.id,
                position=position,
                mode=mode,
                distance_meters=result.distance_meters,
                duration_minutes=result.duration_minutes,
                provider=result.provider,
                is_estimated=result.is_estimated,
                path=result.path or [],
                alternatives=result.alternatives or [],
            )
        )
        suggested_start = current + timedelta(
            minutes=from_activity.duration_minutes + result.duration_minutes
        )
        if to_activity.schedule_locked:
            current = datetime.combine(datetime.today().date(), to_activity.scheduled_time)
        else:
            current = suggested_start
            to_activity.scheduled_time = current.time().replace(second=0, microsecond=0)


async def resolve_route_result(
    session: AsyncSession,
    origin: PlaceCandidate,
    destination: PlaceCandidate,
    mode: str,
) -> RouteCache:
    cache_key = hashlib.sha256(
        f"{float(origin.longitude):.5f},{float(origin.latitude):.5f}:"
        f"{float(destination.longitude):.5f},{float(destination.latitude):.5f}:{mode}".encode()
    ).hexdigest()
    cached = await session.get(RouteCache, cache_key)
    now = datetime.now(UTC)
    settings = get_settings()
    if (
        cached is not None
        and cached.expires_at > now
        and (cached.is_estimated or bool(cached.path))
        and (not cached.is_estimated or not settings.amap_rest_key)
    ):
        logger.info("amap route cache hit mode=%s", mode)
        return cached

    result = None
    if settings.amap_rest_key:
        try:
            trip = await session.get(Trip, origin.trip_id)
            result = await _fetch_amap_route(
                origin,
                destination,
                mode,
                trip.destination_citycode or trip.destination if trip else "",
            )
        except MapProviderError:
            if not settings.allow_map_estimates:
                raise
    elif not settings.allow_map_estimates:
        raise _missing_key_error()
    distance, duration, provider, estimated, path, alternatives = result or _estimated_route(
        origin, destination, mode
    )
    if cached is None:
        cached = RouteCache(cache_key=cache_key)
        session.add(cached)
    cached.mode = mode
    cached.distance_meters = distance
    cached.duration_minutes = duration
    cached.provider = provider
    cached.is_estimated = estimated
    cached.path = path
    cached.alternatives = alternatives
    cached.expires_at = now + timedelta(seconds=settings.route_cache_ttl_seconds)
    logger.info(
        "amap route resolved mode=%s provider=%s estimated=%s",
        mode,
        provider,
        estimated,
    )
    return cached


async def _fetch_amap_route(
    origin: PlaceCandidate, destination: PlaceCandidate, mode: str, city: str
) -> tuple[int, int, str, bool, list[list[float]], list[dict[str, Any]]]:
    settings = get_settings()
    path = {
        "walk": "walking",
        "driving": "driving",
        "transit": "transit/integrated",
    }[mode]
    params: dict[str, object] = {
        "key": settings.amap_rest_key,
        "origin": f"{origin.longitude},{origin.latitude}",
        "destination": f"{destination.longitude},{destination.latitude}",
        "show_fields": "cost,navi,polyline",
    }
    if mode == "transit":
        params.update(
            {"city1": city, "city2": city, "strategy": 0, "AlternativeRoute": 3}
        )
    elif mode == "walk":
        params["alternative_route"] = 3
    elif mode == "driving":
        params["strategy"] = 32
    payload = await asyncio.to_thread(
        _get_json,
        f"https://restapi.amap.com/v5/direction/{path}?{urlencode(params)}",
    )
    if payload.get("status") != "1":
        raise _provider_response_error(payload, "高德路线计算失败")
    route = payload.get("route") or {}
    paths = route.get("paths") or route.get("transits") or []
    if not paths:
        raise MapProviderError("高德未返回可用路线")
    candidates = [_parse_route_path(item, route) for item in paths]
    candidates = [candidate for candidate in candidates if candidate is not None]
    if not candidates:
        raise MapProviderError("高德路线数据不完整")
    candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
    distance, duration, geometry = candidates[0]
    alternatives = [
        {
            "distance_meters": item_distance,
            "duration_minutes": item_duration,
            "path": item_geometry,
        }
        for item_distance, item_duration, item_geometry in candidates[1:3]
    ]
    return distance, duration, "AMap Route 2.0", False, geometry, alternatives


def _parse_route_path(
    item: dict[str, Any], route: dict[str, Any]
) -> tuple[int, int, list[list[float]]] | None:
    cost = item.get("cost") if isinstance(item.get("cost"), dict) else {}
    distance = _positive_int(item.get("distance") or route.get("distance"))
    duration_seconds = _positive_int(item.get("duration") or cost.get("duration"))
    geometry = _collect_geometry(item)
    if distance <= 0 or duration_seconds <= 0 or len(geometry) < 2:
        return None
    return distance, max(1, math.ceil(duration_seconds / 60)), geometry


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _collect_geometry(value: Any) -> list[list[float]]:
    points: list[list[float]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            polyline = node.get("polyline")
            if isinstance(polyline, str):
                for pair in polyline.split(";"):
                    parts = pair.split(",")
                    if len(parts) != 2:
                        continue
                    try:
                        point = [float(parts[0]), float(parts[1])]
                    except ValueError:
                        continue
                    if not points or points[-1] != point:
                        points.append(point)
            for key, child in node.items():
                if key != "polyline":
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return points


def _estimated_route(
    origin: PlaceCandidate, destination: PlaceCandidate, mode: str
) -> tuple[int, int, str, bool, list[list[float]], list[dict[str, Any]]]:
    lat1, lat2 = map(math.radians, [float(origin.latitude), float(destination.latitude)])
    dlat = lat2 - lat1
    dlon = math.radians(float(destination.longitude) - float(origin.longitude))
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    straight = 6_371_000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    factor = {"walk": 1.25, "transit": 1.45, "driving": 1.35}[mode]
    speed = {"walk": 75, "transit": 350, "driving": 500}[mode]
    distance = max(100, round(straight * factor))
    return distance, max(2, math.ceil(distance / speed)), "RoamSync Estimate", True, [], []


def _category_for_type(value: str) -> str:
    if any(word in value for word in ("餐饮", "美食", "咖啡")):
        return "food"
    if any(word in value for word in ("购物", "商场")):
        return "shopping"
    if any(word in value for word in ("博物馆", "美术馆", "文化", "寺庙")):
        return "culture"
    if any(word in value for word in ("公园", "山", "湖", "自然")):
        return "nature"
    return "sight"


def _duration_for_category(category: str) -> int:
    return {"food": 75, "shopping": 90, "culture": 120, "nature": 120}.get(category, 90)


def _cost_for_category(category: str) -> int:
    return {"food": 8000, "shopping": 5000, "culture": 3000, "nature": 1000}.get(category, 3000)
