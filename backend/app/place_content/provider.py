import asyncio
import math
import re
import json
from pathlib import Path
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode
from uuid import UUID, uuid5

from app.map_transport import MapProviderError, get_json, _missing_key_error, _provider_response_error
from .contracts import ExternalRef, GeoPoint, Place, PlaceRef, Price, RouteQuery, RouteResult, SearchQuery, SearchResponse, Source

# Public, immutable namespace; never derive identity from name or coordinates.
PLACE_NAMESPACE = UUID("0ae98ec6-5e5d-4696-9877-8656a8b74b15")
REVIEWED_ALIASES = json.loads(Path(__file__).with_name('reviewed_aliases.json').read_text(encoding='utf-8'))
TYPE_CODES = {"attraction": "110000", "food": "050000", "lodging": "100000"}


def stable_place_id(provider_id: str) -> UUID:
    return uuid5(PLACE_NAMESPACE, f"amap:poi:{provider_id}")


def text_value(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def alias_values(value: Any, canonical_name: str) -> list[str]:
    # AMap returns alias as either one provider string or an array. Preserve each
    # supplied value intact; punctuation is provider data, not a delimiter rule.
    candidates = value if isinstance(value, list) else [value]
    aliases = []
    seen = {canonical_name.casefold()}
    for candidate in candidates:
        alias = text_value(candidate)
        if not alias or len(alias) > 200 or alias.casefold() in seen:
            continue
        aliases.append(alias)
        seen.add(alias.casefold())
        if len(aliases) == 20:
            break
    return aliases


def number(value: Any) -> float | None:
    if isinstance(value, (list, dict, bool)) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_poi(poi: dict, fetched_at: datetime | None = None) -> Place | None:
    provider_id, name = text_value(poi.get("id")), text_value(poi.get("name"))
    if not provider_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", provider_id) or not name:
        return None
    try:
        longitude, latitude = str(poi.get("location", "")).split(",")
        point = GeoPoint(longitude=float(longitude), latitude=float(latitude))
    except (ValueError, TypeError):
        return None
    type_code = text_value(poi.get("typecode")) or ""
    provider_type = text_value(poi.get("type"))
    category = {"05": "food", "10": "lodging", "11": "attraction"}.get(type_code[:2], "other")
    if category == "other" and provider_type:
        category = next((c for c, word in [("food", "餐饮"), ("lodging", "住宿"), ("attraction", "风景名胜")] if word in provider_type), "other")
    biz = poi.get("business") if isinstance(poi.get("business"), dict) else (poi.get("biz_ext") if isinstance(poi.get("biz_ext"), dict) else {})
    rating = number(biz.get("rating"))
    # AMap's empty/zero sentinel is not a verified zero-star review.
    rating = rating if rating is not None and 0 < rating <= 5 else None
    cost = number(biz.get("cost"))
    # Hotel average consumption is NOT a room-night quote; do not project it.
    price = Price(amount=cost) if category == "food" and cost is not None and cost > 0 else None
    now = fetched_at or datetime.now(UTC)
    place = Place(
        ref=PlaceRef(place_id=stable_place_id(provider_id), external_ref=ExternalRef(provider_place_id=provider_id)),
        name=name, category=category, provider_type=provider_type, aliases=alias_values(poi.get("alias"), name),
        address=text_value(poi.get("address")), city=text_value(poi.get("cityname")), district=text_value(poi.get("adname")),
        location=point, rating=rating, rating_status="provided" if rating is not None else "unknown",
        opening_hours_reference=text_value(biz.get("opentime_week")) or text_value(biz.get("opentime_today")),
        provider_tags=[p.strip() for p in str(biz.get("tag") or "").split(",") if p.strip()][:12],
        price=price, price_status="provider_reference" if price else "unknown",
        image_status="withheld_pending_license" if isinstance(poi.get("photos"), list) and poi["photos"] else "missing",
        source=Source(source_url=f"https://www.amap.com/search?id={provider_id}", fetched_at=now, expires_at=now + timedelta(hours=1)),
    )
    for entry in REVIEWED_ALIASES:
        if (provider_id == entry['provider_place_id'] and name == entry['name'] and place.city == entry['city']
            and abs(point.longitude-entry['longitude']) < .002 and abs(point.latitude-entry['latitude']) < .002):
            place = place.model_copy(update={'aliases': list(dict.fromkeys([*place.aliases, *entry['aliases']]))[:20]})
    from .images import project_images
    return project_images(place)


class AMapContentProvider:
    def __init__(self, key: str, request: Callable[[str], Awaitable[dict]] | None = None):
        self.key = key
        self.request = request

    async def _request(self, path: str, params: dict) -> dict:
        if not self.key:
            raise _missing_key_error()
        url = f"https://restapi.amap.com/{path}?{urlencode({'key': self.key, **params})}"
        payload = await self.request(url) if self.request else await asyncio.to_thread(get_json, url)
        if not isinstance(payload, dict):
            raise MapProviderError("高德响应格式无效", code="map_invalid_response")
        if payload.get("status") != "1":
            raise _provider_response_error(payload, "高德内容查询失败")
        return payload

    async def search(self, query: SearchQuery) -> SearchResponse:
        params = {"keywords": query.query.strip(), "offset": query.page_size, "page": query.page, "extensions": "all"}
        if query.category:
            params["types"] = TYPE_CODES[query.category]
        if query.city:
            params.update(city=query.city, citylimit="true")
        path = "v3/place/text"
        if query.center:
            path = "v3/place/around"
            params.update(location=f"{query.center.longitude},{query.center.latitude}", radius=query.radius_meters, sortrule="distance")
        payload = await self._request(path, params)
        raw = payload.get("pois")
        if not isinstance(raw, list):
            raise MapProviderError("高德地点列表格式无效", code="map_invalid_response")
        items = [place for poi in raw if isinstance(poi, dict) and (place := normalize_poi(poi)) is not None]
        if raw and not items:
            raise MapProviderError("高德地点缺少可靠身份或坐标", code="map_invalid_response")
        count = number(payload.get("count"))
        return SearchResponse(items=items, total=int(count) if count is not None else None, page=query.page, page_size=query.page_size, status="ok" if items else "empty")

    async def detail(self, ref: PlaceRef) -> Place | None:
        payload = await self._request("v3/place/detail", {"id": ref.external_ref.provider_place_id, "extensions": "all"})
        raw = payload.get("pois")
        if not isinstance(raw, list):
            raise MapProviderError("高德详情格式无效", code="map_invalid_response")
        for poi in raw:
            if isinstance(poi, dict) and poi.get("id") == ref.external_ref.provider_place_id:
                place = normalize_poi(poi)
                if place is not None:
                    return place
        if raw:
            raise MapProviderError("高德详情身份或坐标不确定", code="place_identity_uncertain")
        return None

    async def route(self, query: RouteQuery) -> RouteResult:
        mode = "walking" if query.mode == "walk" else "driving"
        payload = await self._request(f"v5/direction/{mode}", {
            "origin": f"{query.origin.longitude},{query.origin.latitude}",
            "destination": f"{query.destination.longitude},{query.destination.latitude}",
            "show_fields": "cost,polyline",
        })
        route = payload.get("route")
        paths = route.get("paths") if isinstance(route, dict) else None
        if not isinstance(paths, list) or not paths:
            raise MapProviderError("高德未返回可用路线", code="map_route_unavailable", status_code=404)
        for path in paths:
            if not isinstance(path, dict):
                continue
            cost = path.get("cost") if isinstance(path.get("cost"), dict) else {}
            distance, duration = number(path.get("distance")), number(cost.get("duration", path.get("duration")))
            points = []
            try:
                for step in path.get("steps", []):
                    for pair in (step.get("polyline") or "").split(";"):
                        if not pair:
                            continue
                        lng, lat = pair.split(",")
                        point = GeoPoint(longitude=float(lng), latitude=float(lat))
                        if not points or points[-1] != point:
                            points.append(point)
            except (ValueError, TypeError, AttributeError):
                continue
            if distance is None or duration is None or len(points) < 2:
                continue
            now = datetime.now(UTC)
            return RouteResult(origin=query.origin, destination=query.destination, mode=query.mode,
                distance_meters=math.ceil(distance), duration_seconds=math.ceil(duration), path=points,
                source=Source(source_url="https://lbs.amap.com/api/webservice/guide/api/newroute", fetched_at=now, expires_at=now + timedelta(minutes=5)))
        raise MapProviderError("高德路线数据不完整", code="map_invalid_response")
