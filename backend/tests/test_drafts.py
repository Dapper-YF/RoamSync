import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.drafts.contracts import DraftCreate, DraftPlan, RunRequest
from app.drafts.repository import DraftError, DraftRepository, metadata
from app.drafts.routes import create_router
from app.drafts.service import DraftService


class FixtureGenerator:
    source = "fixture"
    async def generate(self, draft, requirements):
        return DraftPlan(days=[{"day_index": n + 1, "title": requirements or "自由探索", "items": [
            {"name": "待核实的建议", "note": "活动建议，地点待确认"}]} for n in range(draft.day_count)])


@pytest.fixture
def stack():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine)  # Explicit test-only isolated database.
    repository = DraftRepository(engine)
    service = DraftService(repository, FixtureGenerator())
    app = FastAPI()
    app.include_router(create_router(service, lambda: "trusted-test-owner"))
    yield TestClient(app), repository, service, engine
    engine.dispose()


def test_create_generate_modify_save_cancel_restore_without_trip(stack):
    client, repo, _, engine = stack
    draft = client.post("/api/v1/drafts", json={"city": "杭州", "day_count": 3}).json()
    assert draft["version"] == 1 and draft["plan"] is None
    assert inspect(engine).get_table_names() == ["v2_travel_drafts"]
    for requirement in ["", "第二天轻松一点"]:
        response = client.post(f'/api/v1/drafts/{draft["id"]}/runs', json={
            "expected_version": draft["version"], "request_id": str(uuid4()), "requirements": requirement})
        assert response.status_code == 200, response.text
        draft = response.json()
        assert [day["day_index"] for day in draft["plan"]["days"]] == [1, 2, 3]
        assert draft["runs"][-1]["status"] == "completed"
        assert draft["runs"][-1]["source"] == "fixture"
    for action, status in [("save", "active"), ("cancel", "cancelled"), ("restore", "active")]:
        draft = client.post(f'/api/v1/drafts/{draft["id"]}/{action}', json={"expected_version": draft["version"]}).json()
        assert draft["status"] == status
    assert client.get(f'/api/v1/drafts/{draft["id"]}').json()["saved"] is True
    assert len(client.get("/api/v1/drafts").json()) == 1
    with pytest.raises(DraftError) as error:
        repo.get("another-owner", draft["id"])
    assert error.value.status == 404


def test_version_idempotency_and_body_owner_rejection(stack):
    client, _, _, _ = stack
    assert client.post("/api/v1/drafts", json={"city": "杭州", "owner_id": "other"}).status_code == 422
    draft = client.post("/api/v1/drafts", json={"city": "杭州"}).json()
    path = f'/api/v1/drafts/{draft["id"]}'
    request = {"expected_version": 1, "request_id": str(uuid4()), "requirements": "慢游"}
    first = client.post(path + "/runs", json=request).json()
    assert client.post(path + "/runs", json=request).json() == first
    assert client.post(path + "/runs", json={**request, "requirements": "different"}).status_code == 409
    assert client.post(path + "/save", json={"expected_version": 1}).status_code == 409


def test_model_failure_preserves_plan_and_allows_retry(stack, caplog):
    _, repo, service, _ = stack
    draft = repo.create("owner", DraftCreate(city="杭州"))
    draft = asyncio.run(service.run("owner", draft.id, RunRequest(expected_version=1, request_id=uuid4())))
    previous = draft.plan
    class Broken:
        source = "model"
        async def generate(self, *args):
            raise RuntimeError("SECRET MUST NOT LEAK")
    service.generator = Broken()
    draft = asyncio.run(service.run("owner", draft.id, RunRequest(expected_version=draft.version, request_id=uuid4())))
    assert draft.plan == previous and draft.runs[-1].status == "failed"
    assert "SECRET" not in draft.model_dump_json()
    assert "SECRET" not in caplog.text
    assert '"exception_type": "RuntimeError"' in caplog.text
    service.generator = FixtureGenerator()
    assert asyncio.run(service.run("owner", draft.id, RunRequest(expected_version=draft.version, request_id=uuid4()))).runs[-1].status == "completed"


def test_incomplete_model_diagnostics_do_not_log_output(stack, monkeypatch, caplog):
    from app.drafts import service as module
    class Client:
        async def close(self):
            pass
    monkeypatch.setattr(module, "build_model_client", lambda _: Client())
    async def response(*args, **kwargs):
        return SimpleNamespace(status="incomplete", output_text="SECRET MODEL PAYLOAD",
            finish_reason="length", usage=SimpleNamespace(completion_tokens=6000))
    monkeypatch.setattr(module, "create_model_response", response)
    draft = stack[1].create("owner", DraftCreate(city="杭州"))
    with pytest.raises(ValueError, match="model_incomplete"):
        asyncio.run(module.ModelDraftGenerator(SimpleNamespace(planner_model="fixture")).generate(draft, ""))
    assert '"finish_reason": "length"' in caplog.text
    assert '"completion_tokens": 6000' in caplog.text
    assert "SECRET" not in caplog.text


def test_safe_validation_diagnostic_excludes_model_input():
    from app.drafts.service import _safe_failure
    with pytest.raises(ValueError) as error:
        DraftPlan.model_validate({"days": [{"day_index": "SECRET MODEL PAYLOAD"}]})
    diagnostic = _safe_failure(error.value)
    assert diagnostic["exception_type"] == "ValidationError"
    assert "int_parsing" in diagnostic["validation_types"]
    assert "SECRET" not in str(diagnostic)


def test_cancelled_inflight_result_cannot_overwrite_and_can_restore(stack):
    _, repo, service, _ = stack
    draft = repo.create("owner", DraftCreate(city="杭州"))
    class Cancelling(FixtureGenerator):
        async def generate(self, current, requirements):
            service.action("owner", current.id, current.version, "cancel")
            return await super().generate(current, requirements)
    service.generator = Cancelling()
    result = asyncio.run(service.run("owner", draft.id, RunRequest(expected_version=1, request_id=uuid4())))
    assert result.plan is None and result.status == "cancelled" and result.runs[0].status == "cancelled"
    assert service.action("owner", draft.id, result.version, "restore").status == "active"


def test_missing_owner_fails_closed(stack):
    app = FastAPI()
    app.include_router(create_router(stack[2]))
    assert TestClient(app).get("/api/v1/drafts").status_code == 503


def test_invalid_relative_day_indexes():
    with pytest.raises(ValueError):
        DraftPlan(days=[{"day_index": 2, "title": "bad", "items": []}])


def test_model_place_binding_requires_unique_fresh_real_identity(stack, monkeypatch):
    from app.drafts import service as module
    def place(name, *, expired=False, stale=False):
        return SimpleNamespace(name=name, ref=SimpleNamespace(place_id=uuid4()), identity_status="provider_identity",
            source=SimpleNamespace(freshness="stale" if stale else "fresh", expires_at=datetime.now(UTC) + timedelta(days=-1 if expired else 1)))
    unique = place("唯一真实地点")
    known = [unique, place("同名地点"), place("同名地点"), place("过期地点", expired=True), place("旧地点", stale=True)]
    class Places:
        async def search(self, query):
            return SimpleNamespace(items=known)
    class Client:
        async def close(self):
            pass
    monkeypatch.setattr(module, "build_model_client", lambda _: Client())
    async def response(*args, **kwargs):
        assert kwargs["reasoning_effort"] == "high"
        return SimpleNamespace(status="completed", output_text=DraftPlan(days=[{"day_index": 1, "title": "一天", "items": [
            {"name": name, "place_id": str(uuid4()), "identity_status": "provider_confirmed"}
            for name in ["唯一真实地点", "同名地点", "过期地点", "旧地点", "虚构地点"]]}]).model_dump_json())
    monkeypatch.setattr(module, "create_model_response", response)
    draft = stack[1].create("owner", DraftCreate(city="杭州", day_count=1))
    generator = module.ModelDraftGenerator(SimpleNamespace(planner_model="fixture", planner_reasoning_effort="high"), Places())
    plan = asyncio.run(generator.generate(draft, ""))
    assert plan.days[0].items[0].place_id == unique.ref.place_id
    assert all(item.place_id is None and item.identity_status == "unknown" for item in plan.days[0].items[1:])
