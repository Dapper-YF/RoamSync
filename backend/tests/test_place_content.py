import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.pool import StaticPool

from app.map_transport import MapProviderError
from app.place_content.contracts import GeoPoint, RouteQuery, SearchQuery
from app.place_content.provider import AMapContentProvider, normalize_poi, stable_place_id
from app.place_content.repository import ContentRepository, favorites, metadata
from app.place_content.routes import create_router
from app.place_content.service import PlaceContentService


POI = {"id": "B000TEST01", "name": "测试餐厅", "location": "120.15,30.25", "cityname": "杭州市", "typecode": "050100", "address": "测试路1号", "biz_ext": {"rating": [], "cost": "88"}, "photos": [{"url": "https://example.com/photo.jpg"}]}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def system():
    calls = []
    state = {"failure": None, "pois": [POI]}

    async def request(url):
        calls.append(url)
        if state["failure"]:
            raise state["failure"]
        if "/direction/" in url:
            return {"status": "1", "route": {"paths": [{"distance": "1234", "cost": {"duration": "567"}, "steps": [{"polyline": "120.15,30.25;120.16,30.26"}]}]}}
        return {"status": "1", "count": str(len(state["pois"])), "pois": state["pois"]}

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    repository = ContentRepository(engine)
    service = PlaceContentService(AMapContentProvider("fixture-only", request), repository)

    def owner(authorization: str | None = Header(default=None)):
        if authorization not in ("Bearer alice", "Bearer bob"):
            raise HTTPException(401)
        return authorization.removeprefix("Bearer ")

    app = FastAPI()
    app.include_router(create_router(service, owner))
    with TestClient(app) as client:
        yield client, service, repository, calls, state
    engine.dispose()


@pytest.mark.parametrize("rating", [None, "", [], {}, "NaN", "Infinity", "-1", "0", "6", "bad"])
def test_unknown_rating_never_becomes_zero(rating):
    place = normalize_poi({**POI, "biz_ext": {"rating": rating}})
    assert place.rating is None and place.rating_status == "unknown"


def test_provider_facts_do_not_invent_quotes_or_images():
    food = normalize_poi(POI)
    assert food.price.amount == 88 and food.price.unit == "per_person_reference"
    assert food.price.verified_live_quote is False
    assert food.images == [] and food.image_status == "withheld_pending_license"
    hotel = normalize_poi({**POI, "typecode": "100100", "biz_ext": {"cost": "999", "rating": "4.5"}})
    assert hotel.price is None and hotel.rating == 4.5
    assert hotel.source.provider_updated_at is None


def test_stable_provider_identity_is_not_name_based():
    a = normalize_poi(POI)
    b = normalize_poi({**POI, "name": "改名"})
    c = normalize_poi({**POI, "id": "B000OTHER"})
    assert a.ref == b.ref and a.ref.place_id != c.ref.place_id


def test_provider_alias_is_metadata_and_never_changes_place_identity():
    canonical = normalize_poi({**POI, "id": "B000ALIAS", "name": "正式名称", "alias": "旧称;提供商原文"})
    renamed = normalize_poi({**POI, "id": "B000ALIAS", "name": "更新名称", "alias": ["旧称;提供商原文", "  另一个称呼  "]})
    same_alias_other_place = normalize_poi({**POI, "id": "B000OTHER", "name": "另一地点", "alias": "旧称;提供商原文"})

    assert canonical.aliases == ["旧称;提供商原文"]  # provider punctuation is preserved intact
    assert renamed.aliases == ["旧称;提供商原文", "另一个称呼"]
    assert canonical.ref.place_id == renamed.ref.place_id
    assert canonical.ref.place_id != same_alias_other_place.ref.place_id


def test_complete_no_trip_api_flow(system):
    client, service, repo, calls, state = system
    result = client.get("/api/v1/places/search", params={"city": "杭州", "category": "food"})
    assert result.status_code == 200
    place = result.json()["items"][0]
    pid = place["ref"]["place_id"]
    assert place["rating"] is None and place["location"]["coordinate_system"] == "GCJ02"
    assert client.get(f"/api/v1/places/{pid}").json()["ref"]["place_id"] == pid
    headers = {"Authorization": "Bearer alice"}
    for _ in range(2):
        assert client.put(f"/api/v1/me/favorites/{pid}?owner_id=bob", headers=headers).status_code == 200
    assert client.get("/api/v1/me/favorites", headers=headers).json()[0]["place"]["ref"]["place_id"] == pid
    assert client.get("/api/v1/me/favorites", headers={"Authorization": "Bearer bob"}).json() == []
    assert client.get(f"/api/v1/me/favorites/{pid}", headers=headers).json()["is_favorite"] is True
    assert client.put(f"/api/v1/me/favorites/{pid}").status_code == 401
    with repo.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(favorites)) == 1
    route = client.post("/api/v1/routes/query", json={"origin": place["location"], "destination": {"longitude": 120.16, "latitude": 30.26}, "mode": "walk"})
    assert route.status_code == 200 and route.json()["duration_seconds"] == 567
    assert route.json()["navigation_available"] is False
    for _ in range(2):
        assert client.delete(f"/api/v1/me/favorites/{pid}", headers=headers).status_code == 204
    assert client.get("/api/v1/me/favorites", headers=headers).json() == []
    assert set(inspect(repo.engine).get_table_names()) == {"v2_content_places", "v2_content_favorites"}


def test_search_filters_and_nearby(system):
    client, _, _, calls, _ = system
    for category, code in [("food", "050000"), ("lodging", "100000"), ("attraction", "110000")]:
        assert client.get("/api/v1/places/search", params={"city": "杭州", "category": category}).status_code == 200
        assert parse_qs(urlparse(calls[-1]).query)["types"] == [code]
    assert client.get("/api/v1/places/search", params={"query": "西湖", "longitude": 120.1, "latitude": 30.2, "radius_meters": 2000}).status_code == 200
    assert "/place/around?" in calls[-1]
    assert parse_qs(urlparse(calls[-1]).query)["radius"] == ["2000"]


@pytest.mark.parametrize("params", [{}, {"query": "西湖"}, {"city": "杭州"}, {"city": "杭州", "category": "bogus"}, {"query": "西湖", "longitude": 120}, {"city": "杭州", "query": "西湖", "coordinate_system": "WGS84"}, {"query": "西湖", "longitude": "nan", "latitude": 30}])
def test_invalid_search_is_explicit(system, params):
    client, _, _, calls, _ = system
    assert client.get("/api/v1/places/search", params=params).status_code == 422
    assert not calls


def test_empty_failure_and_identity_downgrade(system):
    client, service, repo, calls, state = system
    pid = client.get("/api/v1/places/search?city=杭州&query=餐厅").json()["items"][0]["ref"]["place_id"]
    state["pois"] = []
    assert client.get("/api/v1/places/search?city=杭州&query=不存在").json()["status"] == "empty"
    missing = client.get(f"/api/v1/places/{pid}").json()
    assert missing["identity_status"] == "provider_id_invalid" and missing["source"]["freshness"] == "stale"
    headers = {"Authorization": "Bearer alice"}
    client.put(f"/api/v1/me/favorites/{pid}", headers=headers)
    saved = client.get("/api/v1/me/favorites", headers=headers).json()[0]["place"]
    assert saved["identity_status"] == "provider_id_invalid" and saved["source"]["freshness"] == "stale"
    from uuid import UUID
    with pytest.raises(MapProviderError) as invalid:
        run(service.get_place(UUID(pid), allow_stale=False))
    assert invalid.value.status_code == 410
    state["failure"] = MapProviderError("secret-url", code="map_quota_exceeded", status_code=429)
    assert client.get("/api/v1/places/search?city=杭州&query=餐厅").status_code == 429
    cached = client.get(f"/api/v1/places/{pid}")
    assert cached.json()["identity_status"] == "provider_unavailable" and "secret-url" not in cached.text
    with pytest.raises(MapProviderError):
        run(service.get_place(UUID(pid), allow_stale=False))
    assert client.get(f"/api/v1/places/{uuid4()}").status_code == 404


@pytest.mark.parametrize("payload", [[], {"status": "1", "pois": {}}, {"status": "1", "pois": [{"id": "X", "name": "坏坐标", "location": "nan,nan"}]}])
def test_malformed_provider_data_is_not_a_successful_empty(payload):
    async def request(url):
        return payload
    with pytest.raises(MapProviderError) as error:
        run(AMapContentProvider("fixture-only", request).search(SearchQuery(query="景点", city="杭州")))
    assert error.value.code == "map_invalid_response"


def test_wrong_detail_identity_is_not_silently_rebound(system):
    client, _, _, _, state = system
    pid = client.get("/api/v1/places/search?city=杭州&query=餐厅").json()["items"][0]["ref"]["place_id"]
    state["pois"] = [{**POI, "id": "DIFFERENT"}]
    result = client.get(f"/api/v1/places/{pid}").json()
    assert result["ref"]["place_id"] == pid and result["identity_status"] == "uncertain"


def test_stale_favorite_projection(system):
    client, _, repo, _, _ = system
    place = normalize_poi(POI, fetched_at=datetime.now(UTC) - timedelta(days=1))
    repo.save(place)
    repo.favorite("alice", place.ref.place_id)
    saved = client.get("/api/v1/me/favorites", headers={"Authorization": "Bearer alice"}).json()[0]["place"]
    assert saved["source"]["freshness"] == "stale"


def test_missing_key_never_returns_fake_empty():
    with pytest.raises(MapProviderError, match="Key"):
        run(AMapContentProvider("").search(SearchQuery(query="西湖", city="杭州")))


@pytest.mark.parametrize("patch", [{"mode": "transit"}, {"origin": {"longitude": 120, "latitude": 30, "coordinate_system": "WGS84"}}, {"origin": {"longitude": 181, "latitude": 30}}])
def test_route_rejects_unsupported_modes_and_crs(system, patch):
    client, _, _, calls, _ = system
    payload = {"origin": {"longitude": 120, "latitude": 30}, "destination": {"longitude": 121, "latitude": 31}, **patch}
    assert client.post("/api/v1/routes/query", json=payload).status_code == 422
    assert calls == []


def test_persistence_survives_repository_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'isolated.db'}"
    engine = create_engine(url)
    metadata.create_all(engine)
    repo = ContentRepository(engine)
    place = normalize_poi({**POI, "alias": ["测试别名"]})
    repo.save(place)
    repo.favorite("alice", place.ref.place_id)
    saved_at = repo.list_favorites("alice")[0].saved_at
    engine.dispose()
    engine = create_engine(url)
    restarted = ContentRepository(engine)
    restarted.favorite("alice", place.ref.place_id)
    assert restarted.get(place.ref.place_id).ref == place.ref
    assert restarted.get(place.ref.place_id).aliases == ["测试别名"]
    assert restarted.list_favorites("alice")[0].saved_at == saved_at
    engine.dispose()


def test_owner_boundary_fails_closed(system):
    _, service, _, _, _ = system
    app = FastAPI()
    app.include_router(create_router(service))
    with TestClient(app) as client:
        assert client.get("/api/v1/me/favorites?owner_id=alice").status_code == 503


def test_empty_server_owner_fails_closed(system):
    _, service, _, _, _ = system
    app = FastAPI()
    app.include_router(create_router(service, lambda: " "))
    with TestClient(app) as client:
        assert client.get("/api/v1/me/favorites?owner_id=alice").status_code == 503


def test_versioned_golden_fixture_matches_dtos():
    import json
    from pathlib import Path
    from app.place_content.contracts import Favorite, FavoriteState, Place, RouteResult, SearchResponse
    fixture = json.loads((Path(__file__).parent / "fixtures/place_content_v1.json").read_text(encoding="utf-8"))
    assert fixture["version"] == "place-content-v1" and fixture["synthetic"] is True
    SearchResponse.model_validate(fixture["search_response"])
    SearchResponse.model_validate(fixture["empty_search"])
    legacy_place = Place.model_validate(fixture["lodging_detail"])
    assert legacy_place.aliases == []  # older place responses remain valid
    assert legacy_place.model_dump(mode="json")["aliases"] == []
    Place.model_validate(fixture["stale_detail"])
    FavoriteState.model_validate(fixture["favorite_state"])
    Favorite.model_validate(fixture["favorites"][0])
    RouteQuery.model_validate(fixture["route_request"])
    RouteResult.model_validate(fixture["route_response"])
