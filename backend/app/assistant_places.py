"""Read-only Place port. B owns lookup/identity/provider; C binds verified results."""
import uuid
from typing import Literal, Protocol

from pydantic import Field

from app.assistant_context import ContextEnvelope, ContextModel
from app.place_content.contracts import Image


class PlaceView(ContextModel):
    place_id: uuid.UUID
    name: str = Field(min_length=1, max_length=240)
    city: str = Field(min_length=1, max_length=120)
    category: str | None = None
    address: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    reference_cost_yuan: float | None = Field(default=None, ge=0)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    coordinate_system: str = "gcj02"
    source: str
    retrieved_at: str
    expires_at: str | None = None
    external_ref: dict | None = None
    images: list[Image] = Field(default_factory=list)
    opening_hours_reference: str | None = None
    provider_tags: list[str] = Field(default_factory=list)
    # No unverified price/hours/reviews/availability enter this initial port.
    missing_facts: list[str] = Field(default_factory=lambda: ["实时价格", "当前营业状态", "评论", "酒店可用性"])


class PlaceReadPort(Protocol):
    async def get_place(self, place_id: uuid.UUID) -> PlaceView | None: ...
    async def search(self, *, query: str, city: str | None, near: PlaceView | None, limit: int) -> list[PlaceView]: ...


class PlaceAdviceSelection(ContextModel):
    """A model selects discussion options; it cannot invent Place attributes."""
    approach: Literal["discuss", "nearby", "compare", "insufficient_information"]
    selected_place_names: list[str] = Field(default_factory=list, max_length=8)


def route_summary(route):
    value = route["result"]
    return f"路线服务给出的{'步行' if value['mode'] == 'walk' else '驾车'}估计为{value['distance_meters']}米、{value['duration_seconds']}秒；这是供应商估计时间，不是实时到达保证。"


def render_place_advice(selection: PlaceAdviceSelection, context):
    from app.companion_contracts import CompanionDraft, SuggestionDraft
    catalog = [PlaceView.model_validate(p) for p in context.place_context]
    envelope = context.assistant_context or {}
    focus = next((p for p in catalog if str(p.place_id) == envelope.get("discussing_place_id")), None)
    categories = {"food": "餐饮", "lodging": "住宿", "attraction": "景点", "other": "地点"}
    selected = [p for p in catalog if p.name in selection.selected_place_names]
    selected = [p for p in selected if sum(other.name == p.name for other in catalog) == 1]
    paragraphs = []
    if focus:
        paragraphs.append(f"你正在讨论的是{focus.city}的「{focus.name}」，地点资料将它归为{categories.get(focus.category, '地点')}。")
        direction = {"food": "口味、交通和用餐需求", "lodging": "住宿需求、交通和实际房源", "attraction": "兴趣、交通和可用游览时间"}.get(focus.category, "兴趣、交通和可用时间")
        paragraphs.append(f"可以先把它作为候选；是否值得专程前往，还需要结合你的{direction}判断。仅凭地点名称和分类，无法确认具体体验。")
    trip = context.trip_summary or {}
    city = focus.city if focus else envelope.get("browsing_city")
    if trip and city and trip.get("destination") and city.rstrip("市") != trip["destination"].rstrip("市"):
        paragraphs.append(f"当前地点范围是{city}，只读旅行的目的地是{trip['destination']}，两者不在同一城市。应先核实跨城交通和行程时间，不能直接判断顺路；本次讨论没有修改正式行程。")
    discussed = {str(p) for p in envelope.get("discussing_place_ids", [])}
    compared = [p for p in catalog if str(p.place_id) in discussed]
    discovery = envelope.get("discovery_context") or {}
    if compared:
        paragraphs.append("下面按你选中的真实地点比较；评分与餐饮消费是供应商参考信息，不代表实时体验或报价。")
        center = discovery.get("center") or {}
        for place in compared:
            facts = [f"评分{place.rating:g}/5" if place.rating is not None else "评分暂无",
                f"参考消费约{place.reference_cost_yuan:g}元/人" if place.reference_cost_yuan is not None else "参考消费暂无"]
            if place.address:
                facts.append("地址：" + place.address)
            if center.get("coordinate_system") == "gcj02" and place.longitude is not None and place.latitude is not None:
                from math import radians, sin, cos, asin, sqrt
                a, b = radians(place.latitude), radians(center["latitude"])
                delta = radians(place.longitude - center["longitude"])
                meters = 6371000 * 2 * asin(min(1, sqrt(sin((a-b)/2)**2 + cos(a)*cos(b)*sin(delta/2)**2)))
                facts.append(f"距所选中心直线约{meters:.0f}米（不是步行距离）")
            paragraphs.append(place.name + "：" + "；".join(facts) + "。")
        if discovery:
            paragraphs.append(f"本次搜索半径{discovery.get('radius_meters', 3000)}米；" +
                (f"最低参考评分{discovery['min_rating']:g}；" if discovery.get("min_rating") is not None else "") +
                (f"餐饮参考消费上限{discovery['max_food_price_yuan']:g}元；" if discovery.get("max_food_price_yuan") is not None else "") +
                ("信息未知的地点仍可能被保留。" if discovery.get("include_unknown", True) else "筛选条件缺失的地点不纳入结果。"))
        paragraphs.append("可以先从距离、类别和已知消费选择候选；缺少的营业、体验与价格信息不能据此推断。查询真实路线后再判断出发方式。")
    requirements = envelope.get("requirements") or {}
    if requirements.get("budget_fen") is not None:
        paragraphs.append(f"这次话题的预算为{requirements['budget_fen'] / 100:g}元；缺少可核实价格，暂不能判断是否符合预算。")
    route = context.read_tool_context.get("route", {})
    if route.get("status") == "available":
        paragraphs.append(route_summary(route))
    elif route:
        paragraphs.append("本次路线暂未取得可核实结果，不能据此判断交通耗时。")
    suggestions = [SuggestionDraft(title=p.name, summary=f"这是已获取的{p.city}{categories.get(p.category, '地点')}候选，具体体验仍需核实。",
        reasons=["来自本次地点查询；是否适合仍需结合你的需求判断。"])
        for p in selected]
    if selected:
        paragraphs.append("可打开详情继续比较：" + "、".join(p.name for p in selected) + "。")
    if selection.approach == "nearby" and not [p for p in selected if p != focus]:
        paragraphs.append("目前还没有可核实的其他周边推荐。")
    paragraphs.append("尚未确认这些地点的实时价格、当前营业状态、评论和酒店可用性。")
    return CompanionDraft(response_text="\n\n".join(paragraphs)[:3000], suggestions=suggestions,
        analysis_summary="结合当前地点的城市、分类与本话题要求比较；未获取的信息保留为待核实。")


class UnavailablePlaces:
    async def get_place(self, place_id):
        return None

    async def search(self, **kwargs):
        return []


async def load_places(port: PlaceReadPort, context: ContextEnvelope, message: str):
    places, limitations = [], []
    focus = None
    if context.discussing_place_id:
        try:
            focus = await port.get_place(context.discussing_place_id)
            if focus is not None:
                focus = PlaceView.model_validate(focus)
                if focus.place_id != context.discussing_place_id:
                    raise ValueError("unrelated Place result")
                places.append(focus)
        except Exception:
            focus = None
        if focus is None:
            limitations.append("当前地点未能通过服务端解析，请重新打开地点详情；不能确认它的位置或周边。")
    for place_id in dict.fromkeys(context.discussing_place_ids):
        if place_id in {p.place_id for p in places}:
            continue
        try:
            place = PlaceView.model_validate(await port.get_place(place_id))
            if place.place_id != place_id:
                raise ValueError("unrelated Place result")
            places.append(place)
        except Exception:
            limitations.append("一个已选地点暂时无法核实，未用其他地点替代。")
    # Explicit comparison selections are the exact user-owned set. A conversational
    # search must not substitute different provider results into that comparison.
    if context.discussing_place_ids:
        return focus, places, limitations
    # Questions about saved days/current progress use their server-read snapshot.
    # Generic words such as “有哪些活动” must not replace that snapshot with a POI search.
    if (context.read_draft_id or context.read_trip_id) and not focus:
        return focus, places, limitations
    import re
    nearby = bool(re.search(r"附近|周边|这里", message))
    search_requested = nearby or bool(re.search(r"推荐|有什么|有哪些|找.{0,8}(?:餐厅|酒店|景点)", message))
    # Unresolved 'here' must never fall back to GPS or an unrelated Trip.
    if search_requested and (focus or (context.browsing_city and not nearby)):
        try:
            found = await port.search(query=message, city=focus.city if focus else context.browsing_city,
                                      near=focus if nearby else None, limit=8)
            for item in found[:8]:
                place = PlaceView.model_validate(item)
                if place.place_id not in {p.place_id for p in places}:
                    places.append(place)
        except Exception:
            limitations.append("地点搜索暂不可用，尚未取得可核实的附近推荐。")
    if nearby and not focus:
        limitations.append("“这里附近”缺少可确认的讨论地点，请指定地点。")
    return focus, places, limitations


def place_cards(result, places: list[PlaceView], focus: PlaceView | None, discussed_ids=()):
    cards = []
    for place in places:
        matched = [s for s in result.suggestions if s.place_ref is not None and s.place_ref.place_id == place.place_id]
        if place == focus or matched or place.place_id in discussed_ids:
            cards.append({"place": place.model_dump(mode="json"), "role": "discussed" if place == focus or place.place_id in discussed_ids else "recommendation",
                          "suggestion_ids": [s.suggestion_id for s in matched],
                          "reason_kind": "assistant_advice_unverified", "detail_path": f"/places/{place.place_id}"})
    return cards


class ContentServicePlaces:
    """Adapter to B's public DTO/service; no Provider implementation here."""
    def __init__(self, service, draft_repository=None, owner=None):
        self.service, self.draft_repository, self.owner = service, draft_repository, owner

    async def get_draft(self, draft_id):
        if self.draft_repository is None or not self.owner:
            raise ValueError("draft read boundary unavailable")
        import asyncio
        draft = await asyncio.to_thread(self.draft_repository.get, self.owner, draft_id)
        return {"id": str(draft.id), "version": draft.version, "title": draft.title,
            "city": draft.city, "requirements": draft.requirements, "saved": draft.saved,
            "status": draft.status, "day_count": draft.day_count,
            "days": [{"day_index": d.day_index, "title": d.title,
                "items": [{"name": i.name, "note": i.note[:200], "place_id": str(i.place_id) if i.place_id else None,
                    "identity_status": i.identity_status} for i in d.items[:8]]} for d in (draft.plan.days[:7] if draft.plan else [])],
            "scope": "server_saved_draft_readonly", "truncated": draft.day_count > 7 or bool(draft.plan and any(len(d.items)>8 for d in draft.plan.days))}

    @staticmethod
    def view(place):
        if place.identity_status != "provider_identity" or place.source.freshness != "fresh":
            raise ValueError("unverified Place identity")
        from datetime import UTC, datetime
        if place.source.expires_at <= datetime.now(UTC):
            raise ValueError("expired Place")
        return PlaceView(place_id=place.ref.place_id, name=place.name, city=place.city or place.district or "未知城市",
            category=place.category, address=place.address, rating=place.rating,
            reference_cost_yuan=place.price.amount if place.price and place.category == "food" else None,
            longitude=place.location.longitude, latitude=place.location.latitude,
            coordinate_system="gcj02", source=place.source.source_url, retrieved_at=place.source.fetched_at.isoformat(),
            expires_at=place.source.expires_at.isoformat(), external_ref=place.ref.external_ref.model_dump(mode="json"), images=place.images,
            opening_hours_reference=place.opening_hours_reference, provider_tags=place.provider_tags)

    async def research_search(self, *, query, city, near, limit, category):
        """V5 reference fields, same canonical identity/cache and no formal writes."""
        from app.place_content.provider import normalize_poi, TYPE_CODES
        import asyncio
        params = {"keywords": query, "region": city, "city_limit": "true", "page_size": limit,
            "show_fields": "business,photos"}
        if category == "food":
            params["types"] = TYPE_CODES[category]
        path = "v5/place/text"
        if near:
            path = "v5/place/around"
            params.update(location=f"{near.longitude},{near.latitude}", radius=3000, sortrule="distance")
        payload = await self.service.provider._request(path, params)
        found = []
        for raw in payload.get("pois", [])[:limit]:
            place = normalize_poi(raw)
            if place:
                await asyncio.to_thread(self.service.repository.save, place)
                found.append(self.view(place))
        return found

    async def get_place(self, place_id):
        return self.view(await self.service.get_place(place_id, allow_stale=False))

    async def search(self, *, query, city, near, limit):
        from app.place_content.contracts import GeoPoint, SearchQuery
        center = None
        if near:
            if near.coordinate_system != "gcj02" or near.longitude is None or near.latitude is None:
                raise ValueError("nearby search requires GCJ02 coordinates")
            center = GeoPoint(longitude=near.longitude, latitude=near.latitude)
        import re
        category = next((key for key, pattern in (("food", r"餐厅|吃|美食|餐馆"),
            ("lodging", r"酒店|住宿|住哪"), ("attraction", r"景点|景区|游览|值得去")) if re.search(pattern, query)), None)
        if near and category is None and near.category in {"food", "lodging", "attraction"}:
            category = near.category
        # Conversational follow-ups are not POI keyword queries. A category
        # and explicit city/center produce actual provider candidates.
        keywords = "" if category else query[:200]
        response = await self.service.search(SearchQuery(query=keywords, category=category, city=city, center=center, page_size=limit))
        items = []
        for place in response.items[:limit]:
            try:
                items.append(self.view(place))
            except ValueError:
                continue
        return items

    async def query_route(self, request):
        from app.place_content.contracts import GeoPoint, RouteQuery
        origin = await self.get_place(request.origin_place_id)
        destination = await self.get_place(request.destination_place_id)
        def point(place):
            return GeoPoint(longitude=place.longitude, latitude=place.latitude)
        query = RouteQuery(origin=point(origin), destination=point(destination), mode=request.mode)
        result = await self.service.query_route(query)
        if result.origin != query.origin or result.destination != query.destination or result.mode != query.mode:
            raise ValueError("unrelated route result")
        return result.model_dump(mode="json")


async def load_read_tools(port, context):
    tools = {}
    if context.route_request is not None:
        try:
            result = await port.query_route(context.route_request)
            tools["route"] = {"status": "available", "result": result}
        except Exception:
            tools["route"] = {"status": "unavailable"}
    if context.read_draft_id is not None:
        try:
            result = await port.get_draft(context.read_draft_id)
            tools["draft"] = {"status": "available", "result": result,
                "page_version_matches": context.read_draft_version is None or result["version"] == context.read_draft_version}
        except Exception:
            tools["draft"] = {"status": "unavailable"}
    return tools


def default_place_port(db=None):
    return UnavailablePlaces()


def request_place_port(request):
    service = getattr(request.app.state, "place_content_service", None)
    draft_service = getattr(request.app.state, "draft_service", None)
    owner = getattr(request.state, "authenticated_owner", None)
    return ContentServicePlaces(service, getattr(draft_service, "repository", None), owner) if service is not None else UnavailablePlaces()
