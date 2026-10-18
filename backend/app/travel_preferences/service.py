import asyncio
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from sqlalchemy import Column, DateTime, JSON, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.place_content.contracts import SearchQuery
from .contracts import DiscoveryItem, DiscoveryQuery, DiscoveryResponse, TravelPreferences

metadata = MetaData()
preferences = Table("v2_travel_preferences", metadata,
    Column("owner_id", String(200), primary_key=True),
    Column("payload", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False))

class PreferenceService:
    def __init__(self, engine, place_content_service):
        self.engine = engine
        self.content = place_content_service
        self.insert = {"sqlite": sqlite_insert, "postgresql": pg_insert}[engine.dialect.name]

    def get(self, owner: str) -> TravelPreferences:
        with self.engine.connect() as conn:
            payload = conn.execute(select(preferences.c.payload).where(preferences.c.owner_id == owner)).scalar_one_or_none()
        return TravelPreferences.model_validate(payload) if payload else TravelPreferences()

    def save(self, owner: str, value: TravelPreferences) -> TravelPreferences:
        stmt = self.insert(preferences).values(owner_id=owner, payload=value.model_dump(mode="json"), updated_at=datetime.now(UTC))
        stmt = stmt.on_conflict_do_update(index_elements=[preferences.c.owner_id], set_={"payload": stmt.excluded.payload, "updated_at": stmt.excluded.updated_at})
        with self.engine.begin() as conn:
            conn.execute(stmt)
        return value

    @staticmethod
    def _distance_meters(origin, destination) -> int:
        lat1, lat2 = radians(origin.latitude), radians(destination.latitude)
        dlat = lat2 - lat1
        dlon = radians(destination.longitude - origin.longitude)
        haversine = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return round(6_371_000 * 2 * asin(min(1.0, sqrt(haversine))))

    @staticmethod
    def _format_distance(meters: int) -> str:
        return f"{meters / 1000:.1f}公里" if meters >= 1000 else f"{meters}米"

    async def discover(self, owner: str, query: DiscoveryQuery) -> DiscoveryResponse:
        pref = await asyncio.to_thread(self.get, owner) if query.use_preferences else TravelPreferences()
        categories = [query.category] if query.category else list(dict.fromkeys([*pref.preferred_categories, "attraction", "food", "lodging"]))
        # Category lookup requests provider relevance ordering; no invented city landmarks.
        # Keep per-request batches ordered: avoids parallel SQLite snapshot writes and provider bursts.
        responses = [await self.content.search(SearchQuery(city=query.city, query=query.query,
            category=category, center=query.center, radius_meters=query.radius_meters, page_size=25)) for category in categories]
        unique = {}
        for index in range(max((len(response.items) for response in responses), default=0)):
            for response in responses:
                if index < len(response.items):
                    place = response.items[index]
                    unique.setdefault(str(place.ref.place_id), place)
        ranked = []
        for place in unique.values():
            if query.min_rating is not None and ((place.rating is None and not query.include_unknown) or (place.rating is not None and place.rating < query.min_rating)):
                continue
            if query.max_food_price_yuan is not None and place.category == "food":
                if (place.price is None and not query.include_unknown) or (place.price and place.price.amount > query.max_food_price_yuan):
                    continue
            fields = [("地点名称", place.name)]
            if place.provider_type:
                fields.append(("地点类别", place.provider_type))
            fields.extend(("地点别名", alias) for alias in place.aliases)
            matched = []
            for term in pref.interests:
                matched_fields = [label for label, value in fields if term.casefold() in value.casefold()]
                if matched_fields:
                    matched.append((term, matched_fields))
            reasons = []
            if place.category in pref.preferred_categories:
                reasons.append("符合你明确保存的类别偏好")
            reasons.extend(f"{'、'.join(labels)}匹配你明确保存的兴趣：{term}" for term, labels in matched)
            distance = self._distance_meters(query.center, place.location) if query.center else None
            if query.center:
                reasons.append(f"距所选GCJ02位置直线约{self._format_distance(distance or 0)}")
            if not reasons:
                reasons.append("来自所选城市的高德分类搜索" if not query.query else "来自当前关键词的高德搜索")
            preference_score = len(matched) * 2 + int(place.category in pref.preferred_categories)
            ranked.append((preference_score, distance, DiscoveryItem(place=place, reasons=reasons)))
        # Explicit preference matches lead; a selected center orders equal matches by straight-line distance.
        # Stable ties retain provider ordering, and canonical UUIDs remain the only deduplication key.
        if query.center:
            ranked.sort(key=lambda item: (-item[0], item[1] if item[1] is not None else float("inf")))
        else:
            ranked.sort(key=lambda item: -item[0])
        items = [item for _, _, item in ranked][:30]
        return DiscoveryResponse(items=items, status="ok" if items else "empty", preference_applied=bool(pref.interests or pref.preferred_categories))
