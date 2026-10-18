import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app.place_content.contracts import SearchResponse
from app.place_content.provider import normalize_poi
from app.travel_preferences.contracts import DiscoveryQuery, TravelPreferences
from app.travel_preferences.routes import create_router
from app.travel_preferences.service import PreferenceService, metadata

class Content:
    def __init__(self):
        self.calls = []
    async def search(self, query):
        self.calls.append(query)
        def poi(id, name, rating=None, cost=None):
            return normalize_poi({"id":id,"name":name,"location":"120.15,30.25","typecode":"050000","biz_ext":{"rating":rating,"cost":cost}})
        items = [poi("ONE", "Tea", "4.8", "40"), poi("TWO", "Tea", "3", "200"), poi("THREE", "Unknown")]
        return SearchResponse(items=items, page=1, page_size=25, status="ok")

@pytest.fixture
def system():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread":False})
    metadata.create_all(engine)
    content = Content()
    service = PreferenceService(engine, content)
    yield service, content, engine
    engine.dispose()

def test_preferences_persist_owner_isolation(system):
    service, content, engine = system
    pref = TravelPreferences(preferred_categories=["food"], interests=["Tea", "Tea", " "])
    service.save("alice", pref)
    assert PreferenceService(engine, content).get("alice").interests == ["Tea"]
    assert service.get("bob").interests == []
    service.save("alice", TravelPreferences())
    assert service.get("alice").preferred_categories == []

def test_discovery_identity_filter_reasons_and_coordinates(system):
    service, content, _ = system
    service.save("alice", TravelPreferences(preferred_categories=["food"], interests=["Tea"]))
    query = DiscoveryQuery(city="Hangzhou", category="food", min_rating=4, max_food_price_yuan=100,
        center={"longitude":120.1,"latitude":30.2,"coordinate_system":"GCJ02"})
    result = asyncio.run(service.discover("alice", query))
    assert len(result.items) == 2  # unknown retained explicitly
    assert result.preference_applied
    assert "Tea" in str(result.items[0].reasons)
    assert content.calls[0].center == query.center
    strict = asyncio.run(service.discover("alice", query.model_copy(update={"include_unknown":False})))
    assert len(strict.items) == 1
    all_items = asyncio.run(service.discover("alice", DiscoveryQuery(city="Hangzhou")))
    assert len(all_items.items) == 3  # repeated canonical UUIDs collapse across categories
    assert len([item for item in all_items.items if item.place.name == "Tea"]) == 2  # same name stays distinct
    assert not asyncio.run(service.discover("alice", DiscoveryQuery(city="Hangzhou", use_preferences=False))).preference_applied

def test_nearby_discovery_uses_selected_center_and_preserves_distinct_same_name_places(system):
    service, _, engine = system
    center = {"longitude":120.15,"latitude":30.25,"coordinate_system":"GCJ02"}
    places = [
        normalize_poi({"id":"NEAR","name":"Tea","location":"120.1501,30.25","typecode":"050000"}),
        normalize_poi({"id":"MID","name":"Tea","location":"120.151,30.25","typecode":"050000"}),
        normalize_poi({"id":"FAR","name":"Inn","location":"120.153,30.25","typecode":"100000"}),
    ]

    class NearbyContent:
        def __init__(self): self.calls = []
        async def search(self, query):
            self.calls.append(query)
            return SearchResponse(items=places, page=1, page_size=25, status="ok")

    nearby_content = NearbyContent()
    nearby_service = PreferenceService(engine, nearby_content)
    result = asyncio.run(nearby_service.discover("alice", DiscoveryQuery(city="Hangzhou", center=center)))

    assert [item.place.ref.place_id for item in result.items] == [place.ref.place_id for place in places]
    assert len(nearby_content.calls) == 3  # repeated canonical UUIDs collapse across category batches
    assert all(any("距所选GCJ02位置直线约" in reason for reason in item.reasons) for item in result.items)
    assert result.items[0].reasons[-1] == "距所选GCJ02位置直线约10米"
    assert [item.place.name for item in result.items[:2]] == ["Tea", "Tea"]  # names never merge distinct UUIDs

def test_provider_alias_matches_explicit_interest_without_alias_based_merging(system):
    service, _, engine = system
    places = [
        normalize_poi({"id":"SCENIC-AREA","name":"杭州西湖风景名胜区-风篁岭","alias":"风篁岭","location":"120.15,30.25","typecode":"110000"}),
        normalize_poi({"id":"SCENIC-ENTRANCE","name":"风篁岭入口","alias":"风篁岭","location":"120.151,30.25","typecode":"110000"}),
    ]

    class AliasContent:
        async def search(self, query):
            return SearchResponse(items=places, page=1, page_size=25, status="ok")

    service.save("alice", TravelPreferences(interests=["风篁岭"]))
    alias_service = PreferenceService(engine, AliasContent())
    result = asyncio.run(alias_service.discover("alice", DiscoveryQuery(city="杭州", category="attraction")))

    assert len(result.items) == 2
    assert len({item.place.ref.place_id for item in result.items}) == 2
    assert all(any("地点别名" in reason and "风篁岭" in reason for reason in item.reasons) for item in result.items)

def test_routes_reject_owner_injection_and_missing_boundary(system):
    service, _, _ = system
    app = FastAPI(); app.include_router(create_router(service))
    with TestClient(app) as client:
        assert client.get("/api/v1/me/travel-preferences").status_code == 503
    app = FastAPI(); app.include_router(create_router(service, lambda: "trusted-owner"))
    with TestClient(app) as client:
        assert client.put("/api/v1/me/travel-preferences", json={"owner_id":"victim"}).status_code == 422
        assert client.put("/api/v1/me/travel-preferences", json={"interests":["Tea"]}).status_code == 200
        assert service.get("trusted-owner").interests == ["Tea"]
        assert service.get("victim").interests == []
        assert client.post("/api/v1/places/discover", json={"city":"Hangzhou","center":{"longitude":120,"latitude":30,"coordinate_system":"WGS84"}}).status_code == 422
