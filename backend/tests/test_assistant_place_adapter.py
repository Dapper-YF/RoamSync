"""Run at B/C integration with app.place_content installed (B owns it)."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("app.place_content")
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app.place_content.contracts import SearchQuery
from app.place_content.provider import AMapContentProvider
from app.place_content.repository import ContentRepository, metadata
from app.place_content.service import PlaceContentService
from app.assistant_context import ContextEnvelope, RouteReadRequest
from app.assistant_places import ContentServicePlaces, load_places, load_read_tools


def test_actual_b_service_search_detail_nearby_and_failure():
    calls, state = [], {"fail": False}

    async def request(url):
        calls.append(url)
        if state["fail"]:
            raise RuntimeError("fixture provider failure")
        if "/direction/" in url:
            return {"status": "1", "route": {"paths": [{"distance": "1234", "cost": {"duration": "567"}, "steps": [{"polyline": "118.79,32.06;118.80,32.07;118.79,32.06"}]}]}}
        return {"status": "1", "count": "1", "pois": [{"id": "B000TEST01", "name": "南京餐厅",
            "location": "118.79,32.06", "cityname": "南京市", "typecode": "050100", "address": "测试地址"}]}

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    try:
        service = PlaceContentService(AMapContentProvider("fixture-only", request), ContentRepository(engine))
        async def run():
            found = await service.search(SearchQuery(query="餐厅", city="南京"))
            place_id = found.items[0].ref.place_id
            adapter = ContentServicePlaces(service)
            focus, places, gaps = await load_places(adapter, ContextEnvelope(discussing_place_id=place_id), "附近还有呢")
            assert focus.place_id == place_id and focus.city == "南京市" and not gaps
            assert focus.coordinate_system == "gcj02" and focus.external_ref["provider"] == "amap"
            assert "实时价格" in focus.missing_facts
            assert any("around" in call and "118.79" in call for call in calls)
            assert any("types=050000" in call for call in calls)
            tools = await load_read_tools(adapter, ContextEnvelope(route_request=RouteReadRequest(
                origin_place_id=place_id, destination_place_id=place_id)))
            assert tools["route"]["status"] == "available"
            assert tools["route"]["result"]["duration_semantics"] == "provider_estimated_travel_time"
            assert tools["route"]["result"]["distance_meters"] == 1234
            state["fail"] = True
            focus, _, gaps = await load_places(adapter, ContextEnvelope(discussing_place_id=place_id), "这里值得去吗")
            assert focus is None and gaps
            with pytest.raises(Exception):
                await adapter.get_place(uuid.uuid4())
            expired = found.items[0].model_copy(update={"source": found.items[0].source.model_copy(update={
                "expires_at": datetime.now(UTC) - timedelta(seconds=1)})})
            with pytest.raises(ValueError):
                adapter.view(expired)
            with pytest.raises(ValueError):
                adapter.view(found.items[0].model_copy(update={"identity_status": "provider_id_invalid"}))
        asyncio.run(run())
    finally:
        engine.dispose()
