import asyncio

import pytest

from app.assistant_context import ContextEnvelope
import app.assistant_capabilities as capabilities
from app.companion_contracts import CompanionDraft, InformationNeed
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal


def compound():
    return capabilities.CapabilityDecision.model_validate({
        "intent": "route", "capabilities": ["poi", "route"], "city": "扬州",
        "origin": "何园", "destination": "个园", "mode": "driving", "reason_code": "route_requested",
        "read_tasks": [
            {"source_quote": "查扬州何园到个园的驾车路线", "capabilities": ["poi", "route"],
             "city": "扬州", "origin": "何园", "destination": "个园", "mode": "driving"},
            {"source_quote": "另外查瘦西湖的地址", "capabilities": ["poi"],
             "city": "扬州", "names": ["瘦西湖"], "query": "瘦西湖"}]})


def test_separate_address_is_not_consumed_by_route_endpoint_lookup(monkeypatch):
    calls = []
    async def leaf(settings, decision, message, *args, **kwargs):
        calls.append((message, decision.origin, decision.names))
        return {"assistant": message, "place_cards": [], "read_tools": {"poi": {"names": decision.names}}}, "complete"
    monkeypatch.setattr(capabilities, "_answer_leaf", leaf)
    decision = compound()
    text = "查扬州何园到个园的驾车路线；另外查瘦西湖的地址"
    decision = capabilities.validate_decision(decision, text, [], ContextEnvelope())
    bundle, status = asyncio.run(capabilities.answer_with_capabilities(None, decision, text, [],
        ContextEnvelope(), None, None, None, "session", "turn", route_travel_goal(text)))
    assert len(calls) == 2
    assert ("另外查瘦西湖的地址", "", ["瘦西湖"]) in calls
    assert [item["source_quote"] for item in bundle["read_tools"]["tasks"]] == [t.source_quote for t in decision.read_tasks]


def test_task_source_and_argument_provenance_are_checked():
    text = "查扬州何园到个园的驾车路线；另外查瘦西湖的地址"
    for field, value in [("source_quote", "替用户去订票"), ("names", ["不存在的模型自拟地点"])]:
        decision = compound()
        decision.read_tasks[1] = decision.read_tasks[1].model_copy(update={field: value})
        result = capabilities.validate_decision(decision, text, [], ContextEnvelope())
        assert result.intent == "clarify"


@pytest.mark.parametrize("changes", [{"names":["何园"], "query":"何园"},
    {"names":[], "query":"豪华酒店", "category":"lodging"}])
def test_task_cannot_borrow_other_current_clause_or_invent_query(changes):
    decision = compound()
    decision.read_tasks[1] = decision.read_tasks[1].model_copy(update=changes)
    text = "查扬州何园到个园的驾车路线；另外查瘦西湖的地址"
    result = capabilities.validate_decision(decision, text, [], ContextEnvelope())
    assert result.intent == "clarify"


def test_hypothetical_fact_task_cannot_upgrade_direct_consultation():
    text = "只是假设景德镇下雨，聊聊如何取舍，不查天气"
    decision = capabilities.CapabilityDecision.model_validate({"intent":"direct", "reason_code":"stable_knowledge",
        "read_tasks":[{"source_quote":text,"capabilities":["facts"],"fact_kind":"weather"}]})
    result = capabilities.validate_decision(decision, text, [], ContextEnvelope())
    assert not result.capabilities and not result.read_tasks


def test_cropped_fact_quote_does_not_escape_hypothetical_parent_clause():
    text = "只是假设景德镇下雨，聊聊如何取舍，不查天气"
    decision = capabilities.CapabilityDecision.model_validate({"intent":"facts", "reason_code":"current_information",
        "read_tasks":[{"source_quote":"景德镇下雨","capabilities":["facts"],"fact_kind":"weather"}]})
    result = capabilities.validate_decision(decision, text, [], ContextEnvelope())
    assert result.intent == "clarify" and not result.capabilities


def test_read_failure_keeps_other_task_and_records_its_status(monkeypatch):
    async def leaf(settings, decision, message, *args, **kwargs):
        if decision.origin:
            raise TimeoutError("route unavailable")
        return {"assistant": "地址检索结果", "place_cards": [], "read_tools": {}}, "complete"
    monkeypatch.setattr(capabilities, "_answer_leaf", leaf)
    decision = compound()
    result, status = asyncio.run(capabilities.answer_with_capabilities(None, decision, "复合请求", [],
        ContextEnvelope(), None, None, None, "s", "t", route_travel_goal("复合请求")))
    assert status == "partial" and "地址检索结果" in result["assistant"]
    assert [t["status"] for t in result["read_tools"]["tasks"]] == ["failed", "complete"]


def test_approved_hypothetical_consultation_cannot_reopen_weather_lookup(monkeypatch):
    import app.companion_graph as graph
    def forbidden(*args):
        raise AssertionError("downstream reinterpreted approved task")
    monkeypatch.setattr(graph, "determine_information_need", forbidden)
    class Reader:
        async def load(self, context, need):
            assert not need.live_fact_required
            return context
    class Provider:
        async def generate(self, context, need):
            return CompanionDraft(response_text="如果下雨，可以先比较室内展览，再核实各馆开放情况。")
    need = InformationNeed(general_knowledge_allowed=True, knowledge_reasons=["approved_direct_consultation"])
    runtime = CompanionRuntime(Reader(), Provider(), approved_need=need)
    message = "只是假设景德镇下雨，聊聊如何取舍，不查天气"
    result = asyncio.run(runtime.run(session_id="s", turn_id="t", message=message,
        messages=[], goal=route_travel_goal(message).model_copy(update={"target_runtime": "companion"})))
    assert result.status == "completed"
    assert not result.forecast_plan
