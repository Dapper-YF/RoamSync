"""C vertical slice; API tests require a disposable DB, never production."""
import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.assistant_context import ContextEnvelope, check_action_target, restore_context
from app.assistant_places import PlaceView, load_places
from app.assistant_routes import get_place_port
from app.companion_contracts import CompanionDraft, SuggestionDraft
from app.companion_provider import ModelCompanionProvider
from app.main import app
from app.planning_errors import PlannerProviderError


NANJING = uuid.UUID("7b552ad4-6c80-469e-afcf-efce617c59f4")
NEARBY = uuid.UUID("2a7a9d42-8ad7-4ca4-b6bc-c06f080c6132")


class Places:
    def __init__(self):
        self.searches = []
        self.places = [PlaceView(place_id=place_id, name=name, city="南京市", category="food",
            longitude=118.79, latitude=32.06, source="fixture://b-contract", retrieved_at="2026-10-15T00:00:00Z")
            for place_id, name in [(NANJING, "南京讨论餐厅"), (NEARBY, "南京附近餐厅")]]

    async def get_place(self, place_id):
        return next((p for p in self.places if p.place_id == place_id), None)

    async def search(self, **kwargs):
        self.searches.append(kwargs)
        return self.places[1:]


@pytest.fixture
def api(monkeypatch):
    port, contexts = Places(), []

    async def generate(self, context, need):
        contexts.append(context)
        return CompanionDraft(response_text="可以结合口味偏好比较这两家；营业与价格尚未确认。", suggestions=[
            SuggestionDraft(title="南京附近餐厅", summary="可作为附近用餐的讨论选项。"),
            SuggestionDraft(title="模型随口提到的店", summary="没有真实地点身份。")])

    monkeypatch.setattr(ModelCompanionProvider, "generate", generate)
    app.dependency_overrides[get_place_port] = lambda: port
    try:
        with TestClient(app) as client:
            client.post("/api/v1/demo/reset")
            current = client.post("/api/v1/assistant/sessions", json={}).json()
            client.post(f"/api/v1/assistant/sessions/{current['id']}/reset")
            try:
                yield client, port, contexts
            finally:
                current = client.post("/api/v1/assistant/sessions", json={}).json()
                client.post(f"/api/v1/assistant/sessions/{current['id']}/reset")
    finally:
        app.dependency_overrides.pop(get_place_port, None)


def send(client, session, message, context, *, message_id=None, stream=False):
    return client.post(f"/api/v1/assistant/sessions/{session}/messages" + ("/stream" if stream else ""),
        json={"message": message, "message_id": message_id or str(uuid.uuid4()), "context": context})


def test_topic_restore_city_switch_and_no_authority_inheritance():
    message_id, trip = uuid.uuid4(), uuid.uuid4()
    old = ContextEnvelope(topic_id="hotel", browsing_city="苏州", requirements={"budget_fen": 50000},
        action_target={"trip_id": trip, "expected_version": 1, "operation": "plan_trip", "authorization_message_id": message_id})
    history = [{"context": old.model_dump(mode="json"), "user": "苏州预算500元"}]
    resumed, visible = restore_context(ContextEnvelope(topic_id="hotel", surface="map"), history)
    assert resumed.requirements.budget_fen == 50000 and resumed.action_target is None
    assert len(visible) == 1
    switched, visible = restore_context(ContextEnvelope(topic_id="hotel", browsing_city="南京"), history)
    assert switched.requirements is None and not visible
    history.append({"context": switched.model_dump(mode="json"), "user": "南京酒店"})
    again, visible = restore_context(ContextEnvelope(topic_id="hotel"), history)
    assert len(visible) == 1 and again.requirements is None
    other, visible = restore_context(ContextEnvelope(topic_id="food"), history)
    assert not visible and other.requirements is None
    cleared, _ = restore_context(ContextEnvelope(topic_id="hotel", requirements=None), history)
    assert cleared.requirements is None


def test_old_or_corrupt_context_is_not_imported_and_explicit_budget_is_kept():
    from app.assistant_context import capture_requirements
    envelope, history = restore_context(ContextEnvelope(topic_id="food"), [
        {"user": "历史预算一万元", "context": None},
        {"user": "旧版本", "context": {"topic_id": "food", "version": "unsupported"}}])
    assert not history and envelope.requirements is None
    envelope = capture_requirements(ContextEnvelope(topic_id="food"), "我们3个人，预算250元")
    assert envelope.requirements.budget_fen == 25000 and envelope.requirements.party_size == 3
    assert capture_requirements(envelope, "苏州旅行预算3000元吗？").requirements.budget_fen == 25000


def test_route_estimate_uses_read_tool_and_never_model():
    from app.companion_runtime import CompanionRuntime
    from app.travel_goal_router import route_travel_goal
    class Reader:
        async def load(self, context, need):
            return context
    class NoModel:
        async def generate(self, *args):
            raise AssertionError("route facts must be rendered by server")
    message = "从这家到那家多久能到？"
    result = asyncio.run(CompanionRuntime(Reader(), NoModel()).run(session_id="route", turn_id="route-1",
        message=message, goal=route_travel_goal(message), messages=[], assistant_context={"browsing_city": "南京"},
        read_tool_context={"route": {"status": "available", "result": {
            "mode": "walk", "distance_meters": 1234, "duration_seconds": 567}}}))
    assert "1234米、567秒" in result.response_text
    assert "供应商估计" in result.response_text


@pytest.mark.parametrize("mismatch", ["version", "trip", "message", "operation"])
def test_action_target_rejects_mismatch(mismatch):
    trip, message_id = uuid.uuid4(), uuid.uuid4()
    context = ContextEnvelope(action_target={"trip_id": trip, "expected_version": 3,
        "operation": "plan_trip", "authorization_message_id": message_id})
    args = dict(session_trip_id=trip, message_id=message_id, trip_version=3, operation="plan_trip")
    args[{"version": "trip_version", "trip": "session_trip_id", "message": "message_id", "operation": "operation"}[mismatch]] = (
        4 if mismatch == "version" else "reschedule_trip" if mismatch == "operation" else uuid.uuid4())
    with pytest.raises(ValueError):
        check_action_target(context, **args)
    check_action_target(context, session_trip_id=trip, message_id=message_id, trip_version=3, operation="plan_trip")


def test_unresolved_here_does_not_search_physical_location():
    port = Places()
    context = ContextEnvelope(browsing_city="南京", discussing_place_id=uuid.uuid4(),
        physical_location={"city": "杭州", "longitude": 120.1, "latitude": 30.2, "coordinate_system": "gcj02"})
    focus, places, gaps = asyncio.run(load_places(port, context, "这里附近还有呢"))
    assert focus is None and not places and gaps and not port.searches


def test_no_trip_place_roundtrip_replay_and_resume(api):
    client, port, contexts = api
    session = client.post("/api/v1/assistant/sessions", json={}).json()
    mid = str(uuid.uuid4())
    response = send(client, session["id"], "这家值得去吗", {"topic_id": "food", "surface": "place",
        "browsing_city": "南京", "discussing_place_id": str(NANJING)}, message_id=mid)
    assert response.status_code == 200
    turn = response.json()["messages"][-1]
    assert response.json()["trip_id"] is None and response.json()["latest_run_id"] is None
    assert turn["place_cards"][0]["place"]["place_id"] == str(NANJING)
    assert "尚未确认" in turn["assistant"]
    assert contexts[-1].current_destination == "南京"
    again = send(client, session["id"], "ignored stale retry", {"topic_id": "wrong"}, message_id=mid).json()
    assert len(again["messages"]) == 1 and len(contexts) == 1
    nearby = send(client, session["id"], "附近还有呢", {"topic_id": "food", "surface": "assistant"}).json()
    last = nearby["messages"][-1]
    assert port.searches[-1]["near"].place_id == NANJING
    assert port.searches[-1]["city"] == "南京市"
    suggestions = last["companion_result"]["suggestions"]
    assert suggestions[0]["place_ref"]["place_id"] == str(NEARBY)
    assert suggestions[1]["place_ref"] is None
    assert last["place_cards"][1]["detail_path"] == f"/places/{NEARBY}"
    restored = client.post("/api/v1/assistant/sessions", json={"session_id": session["id"]}).json()
    assert restored["id"] == session["id"] and len(restored["messages"]) == 2
    assert len(contexts[-1].recent_turns) == 1


def test_three_cities_read_only_and_formal_guard(api):
    client, _, contexts = api
    trip = client.get("/api/v1/trips").json()[0]
    trip = client.put(f"/api/v1/trips/{trip['id']}", json={"version": trip["version"], "destination": "苏州", "total_budget_fen": 300000, "daily_budget_fen": 100000}).json()
    session = client.post("/api/v1/assistant/sessions", json={}).json()
    response = send(client, session["id"], "这家南京餐厅适合加入我下周的苏州旅行吗？", {
        "topic_id": "comparison", "browsing_city": "南京", "read_trip_id": trip["id"],
        "discussing_place_id": str(NANJING), "requirements": {"budget_fen": 20000},
        "physical_location": {"city": "杭州", "longitude": 120.1, "latitude": 30.2, "coordinate_system": "gcj02"}})
    assert response.status_code == 200
    saved = response.json()
    assert saved["trip_id"] is None and saved["latest_run_id"] is None
    context = contexts[-1]
    assert context.current_destination == "南京" and context.saved_trip_preferences is None
    assert context.assistant_context["physical_location"]["city"] == "杭州"
    assert context.assistant_context["requirements"]["budget_fen"] == 20000
    assert context.trip_summary["id"] == trip["id"]
    assert context.trip_summary["destination"] == "苏州"
    assert "300000" not in context.model_dump_json()
    blocked = send(client, session["id"], "请把这家加入旅行", {"topic_id": "comparison", "read_trip_id": trip["id"]}).json()
    assert blocked["messages"][-1]["action_status"] == "authorization_required"
    assert blocked["latest_run_id"] is None and blocked["pending_action"] is None
    after = client.get(f"/api/v1/trips/{trip['id']}").json()
    assert after["version"] == trip["version"]


def test_api_topics_and_legacy_history_do_not_leak(api):
    client, _, contexts = api
    session = client.post("/api/v1/assistant/sessions", json={}).json()
    send(client, session["id"], "苏州预算500元", {"topic_id": "suzhou", "browsing_city": "苏州", "requirements": {"budget_fen": 50000}})
    send(client, session["id"], "南京酒店值得去吗", {"topic_id": "nanjing", "browsing_city": "南京"})
    assert not contexts[-1].recent_turns and not contexts[-1].relevant_user_preferences
    assert contexts[-1].assistant_context["requirements"] is None
    send(client, session["id"], "继续聊", {"topic_id": "suzhou"})
    assert len(contexts[-1].recent_turns) == 1
    assert contexts[-1].assistant_context["requirements"]["budget_fen"] == 50000


def test_provider_failure_keeps_resolved_place_and_stream_completes(api, monkeypatch):
    client, _, _ = api

    async def fail(*args):
        raise PlannerProviderError("planner_unavailable", "private provider details", retryable=True)

    monkeypatch.setattr(ModelCompanionProvider, "generate", fail)
    session = client.post("/api/v1/assistant/sessions", json={}).json()
    response = send(client, session["id"], "这家值得去吗", {"topic_id": "failure", "discussing_place_id": str(NANJING)}, stream=True)
    events = [json.loads(frame[6:]) for frame in response.text.strip().split("\n\n") if frame.startswith("data: ")]
    assert events[-1]["type"] == "done"
    last = events[-1]["session"]["messages"][-1]
    assert last["place_cards"][0]["place"]["place_id"] == str(NANJING)
    assert last["companion_result"]["status"] == "needs_information"
    assert "private" not in response.text


def test_formal_version_and_model_target_are_checked(api, monkeypatch):
    from app.assistant_service import AssistantRouter, ToolDecision
    client, _, _ = api
    trip = client.get("/api/v1/trips").json()[0]
    session = client.post("/api/v1/assistant/sessions", json={"trip_id": trip["id"]}).json()
    mid = str(uuid.uuid4())
    target = {"trip_id": trip["id"], "expected_version": trip["version"] + 1,
        "operation": "plan_trip", "authorization_message_id": mid}
    blocked = send(client, session["id"], "请调整行程", {"action_target": target}, message_id=mid).json()
    assert blocked["messages"][-1]["action_status"] == "authorization_required"
    async def wrong_trip(self, context):
        return ToolDecision(tool="plan_trip", source_trip_id=uuid.uuid4(), reply="收到。")
    monkeypatch.setattr(AssistantRouter, "decide", wrong_trip)
    mid = str(uuid.uuid4())
    target.update(expected_version=trip["version"], authorization_message_id=mid)
    blocked = send(client, session["id"], "请调整行程", {"action_target": target}, message_id=mid)
    assert blocked.status_code == 422


def test_place_model_can_only_select_server_catalog_and_stream_checked_text(monkeypatch):
    from types import SimpleNamespace
    from app import companion_provider
    from app.config import Settings
    from app.companion_contracts import CompanionContext, InformationNeed
    from app.assistant_stream import stream_sink
    from app.travel_goal_router import route_travel_goal
    places = Places().places
    context = CompanionContext(current_message="这家值得去吗", travel_goal=route_travel_goal("这家值得去吗"),
        assistant_context={"discussing_place_id": str(NANJING), "browsing_city": "南京"},
        place_context=[p.model_dump(mode="json") for p in places])
    class Client:
        async def close(self):
            pass
    async def complete(*args, **kwargs):
        schema = kwargs["text_format"]["schema"]
        assert set(schema["properties"]) == {"approach", "selected_place_names"}
        assert "on_content" not in kwargs
        return SimpleNamespace(status="completed", output_text=json.dumps({"approach": "discuss",
            "selected_place_names": ["南京附近餐厅", "不存在的豪华店"]}))
    monkeypatch.setattr(companion_provider, "get_settings", lambda: Settings(_env_file=None, planner_api_key="fixture", planner_model="fixture"))
    monkeypatch.setattr(companion_provider, "build_model_client", lambda settings: Client())
    monkeypatch.setattr(companion_provider, "create_model_response", complete)
    events = []
    token = stream_sink.set(events.append)
    try:
        draft = asyncio.run(ModelCompanionProvider().generate(context, InformationNeed(general_knowledge_allowed=True)))
    finally:
        stream_sink.reset(token)
    assert [s.title for s in draft.suggestions] == ["南京附近餐厅"]
    assert "不存在" not in draft.response_text and "豪华" not in draft.response_text
    assert "尚未确认" in draft.response_text
    assert events[-1] == {"type": "answer_delta", "delta": draft.response_text}
