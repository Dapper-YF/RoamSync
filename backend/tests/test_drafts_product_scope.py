"""Product draft contract against a real isolated SQL repository (no model/network)."""
import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.drafts.contracts import DraftCreate, DraftPlan, RunRequest
from app.drafts.repository import DraftRepository, metadata
from app.drafts.routes import create_router
from app.drafts.service import DraftService


class WholePlanGenerator:
    source = "fixture"

    async def generate(self, draft, requirements):
        # Deliberately edits ALL days, even when only one is authorized.
        return DraftPlan(days=[{"day_index": i, "title": requirements or f"原始第{i}天",
            "items": [{"name": f"地点{i}", "note": requirements or f"原始建议{i}"}]}
            for i in range(1, draft.day_count + 1)])


@pytest.fixture
def stack():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine)
    repo = DraftRepository(engine)
    service = DraftService(repo, WholePlanGenerator())
    app = FastAPI()
    app.include_router(create_router(service, lambda: "owner"))
    yield TestClient(app), repo, service, engine
    engine.dispose()


def generated(stack):
    client = stack[0]
    draft = client.post("/api/v1/drafts", json={"city": "成都", "day_count": 3}).json()
    path = f'/api/v1/drafts/{draft["id"]}'
    return path, client.post(path + "/runs", json={"expected_version": 1, "request_id": str(uuid4())}).json()


def test_scoped_run_preserves_complete_protected_days_and_persists_scope(stack):
    client, repo, _, engine = stack
    path, before = generated(stack)
    def establish_reference(current):
        current.plan.days[0].items[0].place_id = uuid4()
        current.plan.days[0].items[0].identity_status = "provider_confirmed"
        current.plan.days[0].items[0].note = "必须完整保留的原说明"
    before = repo.mutate("owner", before["id"], before["version"], establish_reference).model_dump(mode="json")
    request = {"expected_version": before["version"], "request_id": str(uuid4()),
               "requirements": "第二天调整", "target_day_indices": [2]}
    response = client.post(path + "/runs", json=request)
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["plan"]["days"][0] == before["plan"]["days"][0]
    assert after["plan"]["days"][2] == before["plan"]["days"][2]
    assert after["plan"]["days"][1] != before["plan"]["days"][1]
    assert after["runs"][-1]["target_day_indices"] == [2]
    assert client.get(path).json() == after
    assert client.post(path + "/runs", json=request).json() == after
    conflict = client.post(path + "/runs", json={**request, "target_day_indices": [1]})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_key_reused"
    assert inspect(engine).get_table_names() == ["v2_travel_drafts"]
    assert len(repo.list("owner")) == 1
    assert repo.list("other") == []


@pytest.mark.parametrize("scope", [[0], [15], [2, 2], [1.5], [True], ["2"], [4]])
def test_invalid_scope_rejected_without_write(stack, scope):
    client = stack[0]
    path, before = generated(stack)
    response = client.post(path + "/runs", json={"expected_version": before["version"],
        "request_id": str(uuid4()), "target_day_indices": scope})
    assert response.status_code == 422
    assert client.get(path).json() == before


def test_scope_without_previous_plan_rejected_and_empty_scope_backward_compatible(stack):
    client = stack[0]
    draft = client.post("/api/v1/drafts", json={"city": "北京"}).json()
    path = f'/api/v1/drafts/{draft["id"]}'
    payload = {"expected_version": 1, "request_id": str(uuid4()), "target_day_indices": [1]}
    response = client.post(path + "/runs", json=payload)
    assert response.status_code == 422
    assert client.get(path).json() == draft
    assert client.post(path + "/runs", json={**payload, "target_day_indices": []}).status_code == 200


def test_manual_edit_save_restore_identity_and_conflicts(stack):
    client, repo, _, _ = stack
    path, draft = generated(stack)
    real_id = uuid4()
    def existing_reference(current):
        item = current.plan.days[0].items[0]
        item.place_id, item.identity_status = real_id, "provider_confirmed"
    draft = repo.mutate("owner", draft["id"], draft["version"], existing_reference).model_dump(mode="json")
    plan = draft["plan"]
    plan["days"][0]["items"][0]["note"] = "手动编辑建议"
    plan["days"][1]["items"][0].update(name="新地点", place_id=str(real_id), identity_status="provider_confirmed")
    plan["days"][2]["items"][0].update(place_id=str(uuid4()), identity_status="provider_confirmed")
    payload = {"expected_version": draft["version"], "title": "我的安排", "requirements": "慢慢走", "plan": plan}
    response = client.post(path + "/edit", json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["version"] == draft["version"] + 1 and saved["saved"]
    assert saved["title"] == "我的安排" and saved["requirements"] == "慢慢走"
    assert saved["plan"]["days"][0]["items"][0]["place_id"] == str(real_id)
    for day in saved["plan"]["days"][1:]:
        assert day["items"][0]["place_id"] is None
        assert day["items"][0]["identity_status"] == "unknown"
    assert client.get(path).json() == saved
    assert client.post(path + "/edit", json=payload).status_code == 409
    assert client.get(path).json() == saved
    invalid = {**payload, "expected_version": saved["version"], "plan": {"days": plan["days"][:2]}}
    assert client.post(path + "/edit", json=invalid).status_code == 422
    assert client.get(path).json() == saved


def test_manual_first_plan_and_running_cancelled_boundaries(stack):
    client, repo, service, _ = stack
    draft = client.post("/api/v1/drafts", json={"city": "成都", "day_count": 1}).json()
    path = f'/api/v1/drafts/{draft["id"]}'
    edit = {"expected_version": 1, "title": "手写安排", "requirements": "", "plan": {"days": [
        {"day_index": 1, "title": "自由一天", "items": [{"name": "新地点", "place_id": str(uuid4()), "identity_status": "provider_confirmed"}]}]}}
    response = client.post(path + "/edit", json=edit)
    assert response.status_code == 200
    draft = response.json()
    assert draft["plan"]["days"][0]["items"][0]["place_id"] is None
    current, _, _ = repo.begin_run("owner", draft["id"], RunRequest(expected_version=draft["version"], request_id=uuid4()), "fixture")
    assert client.post(path + "/edit", json={**edit, "expected_version": current.version}).status_code == 409
    cancelled = service.action("owner", current.id, current.version, "cancel")
    assert client.post(path + "/edit", json={**edit, "expected_version": cancelled.version}).status_code == 409


def test_cancelled_scoped_late_result_cannot_overwrite(stack):
    client, repo, service, _ = stack
    _, draft = generated(stack)
    before = draft["plan"]
    class Cancelling(WholePlanGenerator):
        async def generate(self, current, requirements):
            service.action("owner", current.id, current.version, "cancel-run")
            return await super().generate(current, requirements)
    service.generator = Cancelling()
    result = asyncio.run(service.run("owner", draft["id"], RunRequest(expected_version=draft["version"],
        request_id=uuid4(), requirements="不应采用", target_day_indices=[2])))
    assert result.plan.model_dump(mode="json") == before
    assert result.runs[-1].status == "cancelled"


def test_scoped_failure_and_stale_write_preserve_original(stack):
    client, _, service, _ = stack
    path, draft = generated(stack)
    class Failing:
        source = "fixture"
        calls = 0
        async def generate(self, *args):
            self.calls += 1
            raise RuntimeError("private provider failure")
    service.generator = Failing()
    request = {"expected_version": 1, "request_id": str(uuid4()), "target_day_indices": [2]}
    assert client.post(path + "/runs", json=request).status_code == 409
    assert service.generator.calls == 0
    response = client.post(path + "/runs", json={**request, "expected_version": draft["version"]})
    assert response.status_code == 200
    failed = response.json()
    assert failed["plan"] == draft["plan"]
    assert failed["runs"][-1]["status"] == "failed"
    assert "private provider failure" not in response.text


def test_scope_order_is_semantically_idempotent(stack):
    client = stack[0]
    path, draft = generated(stack)
    request = {"expected_version": draft["version"], "request_id": str(uuid4()), "target_day_indices": [3, 1]}
    result = client.post(path + "/runs", json=request).json()
    assert result["runs"][-1]["target_day_indices"] == [1, 3]
    assert client.post(path + "/runs", json={**request, "target_day_indices": [1, 3]}).json() == result


@pytest.mark.parametrize("version", [True, "1", 1.5])
def test_edit_version_must_be_integer(stack, version):
    client = stack[0]
    path, draft = generated(stack)
    response = client.post(path + "/edit", json={"expected_version": version, "title": "草稿", "requirements": "", "plan": draft["plan"]})
    assert response.status_code == 422
    assert client.get(path).json() == draft


def test_unplanned_draft_metadata_edit_does_not_require_generation_or_clear_existing_plan(stack):
    client = stack[0]
    before = client.post("/api/v1/drafts", json={"city": "成都"}).json()
    path = f'/api/v1/drafts/{before["id"]}'
    payload = {"expected_version": before["version"], "title": "我的成都", "requirements": "轻松慢游", "plan": None}
    response = client.post(path + "/edit", json=payload)
    assert response.status_code == 200
    saved = response.json()
    assert saved["saved"] and saved["plan"] is None and saved["requirements"] == "轻松慢游"
    assert client.get(path).json() == saved
    planned = client.post(path + "/runs", json={"expected_version": saved["version"], "request_id": str(uuid4())}).json()
    response = client.post(path + "/edit", json={**payload, "expected_version": planned["version"]})
    assert response.status_code == 422
    assert client.get(path).json() == planned


def test_search_selection_is_verified_server_side_before_manual_save(stack):
    from datetime import UTC,datetime,timedelta
    from app.place_content.contracts import Place
    client,repo,service,_=stack
    path,draft=generated(stack)
    ref=uuid4()
    place=Place.model_validate({"ref":{"place_id":str(ref),"external_ref":{"provider_place_id":"REAL_REF_FIXTURE"}},"name":"服务端核实地点","category":"attraction","city":"成都市","location":{"longitude":104,"latitude":30},"source":{"source_url":"fixture://trusted","fetched_at":datetime.now(UTC),"expires_at":datetime.now(UTC)+timedelta(hours=1)}})
    class Provider:
        async def get_place(self,place_id,**kwargs):
            assert place_id==ref and kwargs=={"allow_stale":False}
            return place
    service.generator.places_service=Provider()
    plan=draft["plan"]
    plan["days"][0]["items"][0].update(name=place.name,place_id=str(ref),identity_status="unknown")
    payload={"expected_version":draft["version"],"title":draft["title"],"requirements":"","plan":plan}
    saved=client.post(path+"/edit",json=payload)
    assert saved.status_code==200,saved.text
    assert saved.json()["plan"]["days"][0]["items"][0]["identity_status"]=="provider_confirmed"
    assert saved.json()["plan"]["days"][0]["items"][0]["place_id"]==str(ref)
    # Same reference with a forged new name cannot be silently certified.
    plan["days"][1]["items"][0].update(name="伪造改名",place_id=str(ref),identity_status="provider_confirmed")
    response=client.post(path+"/edit",json={**payload,"expected_version":saved.json()["version"]})
    assert response.status_code==422
    assert client.get(path).json()==saved.json()
