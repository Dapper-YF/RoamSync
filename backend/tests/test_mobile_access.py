from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.integration_runtime import install_content
from app.mobile_access import DeviceSessions


def test_pairing_one_use_expiry_and_revoke():
    clock = [1000.0]
    store = DeviceSessions("server-owner", lambda: clock[0])
    code = store.issue()["pairing_code"]
    result = store.exchange(code)
    bearer = "Bearer " + result["access_token"]
    assert store.authenticate(bearer) == "server-owner"
    with pytest.raises(HTTPException): store.exchange(code)
    store.revoke(bearer)
    assert store.authenticate(bearer) is None
    expired = store.issue()["pairing_code"]
    clock[0] += 121
    with pytest.raises(HTTPException): store.exchange(expired)
    token = store.exchange(store.issue()["pairing_code"])["access_token"]
    clock[0] += 3601
    assert store.authenticate("Bearer " + token) is None


def test_mobile_pairing_routes_keep_trusted_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("ROAMSYNC_INTEGRATION_TOKEN", "test-server-secret")
    monkeypatch.setenv("ROAMSYNC_INTEGRATION_OWNER", "server-owner")
    app = FastAPI()
    install_content(app, SimpleNamespace(database_url=f"sqlite:///{tmp_path / 'mobile.db'}", amap_rest_key=""))
    @app.get("/api/v1/identity")
    def identity(): return {"not_owner_from_client":True}
    with TestClient(app) as client:
        assert client.post("/api/v1/device-pairing").status_code == 401
        code = client.post("/api/v1/device-pairing", headers={"X-RoamSync-Access":"test-server-secret"}).json()["pairing_code"]
        result = client.post("/api/v1/device-sessions", json={"pairing_code":code})
        assert result.status_code == 200
        headers = {"Authorization":"Bearer " + result.json()["access_token"]}
        assert client.get("/api/v1/identity", headers=headers).status_code == 200
        assert client.post("/api/v1/device-pairing", headers=headers).status_code == 403
        assert client.post("/api/v1/device-sessions", json={"pairing_code":code}).status_code == 401
        assert client.get("/api/v1/identity", headers={**headers,"Origin":"https://untrusted.example"}).status_code == 403
        assert client.delete("/api/v1/device-sessions/current", headers=headers).status_code == 204
        assert client.get("/api/v1/identity", headers=headers).status_code == 401
    app.state.content_engine.dispose()
