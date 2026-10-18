from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.integration_runtime import install_content
from app.place_content.provider import normalize_poi
from app.place_content.repository import metadata, favorites


def test_controlled_proxy_boundary_and_server_owned_favorites(tmp_path, monkeypatch):
    monkeypatch.setenv("ROAMSYNC_INTEGRATION_TOKEN", "server-only-test-credential")
    monkeypatch.setenv("ROAMSYNC_INTEGRATION_OWNER", "trusted-user")
    app = FastAPI()
    install_content(app, SimpleNamespace(database_url=f"sqlite:///{tmp_path / 'content.db'}", amap_rest_key=""))
    metadata.create_all(app.state.content_engine)
    place = normalize_poi({"id":"B_TEST_D", "name":"测试地点", "location":"120.15,30.25", "typecode":"110000", "cityname":"杭州市"})
    app.state.place_content_service.repository.save(place)
    pid = str(place.ref.place_id)
    headers = {"X-RoamSync-Access":"server-only-test-credential", "Origin":"http://127.0.0.1:3000"}
    with TestClient(app) as client:
        assert client.get("/api/v1/me/favorites").status_code == 401
        assert client.get("/api/v1/me/favorites", headers={**headers,"Origin":"https://other.example"}).status_code == 403
        assert client.get("/api/v1/me/favorites", headers={**headers,"Sec-Fetch-Site":"cross-site"}).status_code == 403
        assert client.put(f"/api/v1/me/favorites/{pid}?owner_id=attacker", headers=headers).status_code == 200
        with app.state.content_engine.connect() as conn:
            assert conn.execute(select(favorites.c.owner_id)).scalars().all() == ["trusted-user"]
        assert client.get(f"/api/v1/me/favorites/{pid}", headers=headers).json()["is_favorite"]
        assert client.delete(f"/api/v1/me/favorites/{pid}", headers=headers).status_code == 204
        assert not client.get(f"/api/v1/me/favorites/{pid}", headers=headers).json()["is_favorite"]
    app.state.content_engine.dispose()
