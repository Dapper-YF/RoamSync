"""Protocol faults never grant new reads, changed targets or write authority."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import assistant_capabilities as selector
from app.assistant_context import ContextEnvelope
from app.assistant_reliability import TurnDiagnostics, active_turn


BASE = {"intent": "itinerary", "capabilities": ["itinerary"],
        "reason_code": "saved_state", "itinerary_purpose": "saved_values"}
SUMMARY = {"destination": "成都", "read_coverage": {"scope_kind": "activity", "trip_version": 3}}


def exercise(monkeypatch, outputs, *, raw=None, summary=SUMMARY, hook=None):
    calls, closed = [], []
    history = [{"user": "我选中了第三天的馆"}]
    env = ContextEnvelope(browsing_city="成都")
    async def close():
        closed.append(True)
    monkeypatch.setattr(selector, "build_model_client", lambda _: SimpleNamespace(close=close))
    async def generate(*args, **kwargs):
        calls.append(kwargs)
        if hook:
            await hook(len(calls), history, env)
        output = outputs[len(calls) - 1]
        if isinstance(output, BaseException):
            raise output
        if isinstance(output, SimpleNamespace):
            return output
        return SimpleNamespace(status="completed", output_text=output if isinstance(output, str) else json.dumps(output))
    monkeypatch.setattr(selector, "create_model_response", generate)
    turn = TurnDiagnostics("selection-recovery-test")
    async def run():
        token = active_turn.set(turn)
        try:
            return await selector.select_capabilities(SimpleNamespace(planner_model="test"),
                "选中的馆原来保存了多久？", history, env, deepcopy(summary))
        finally:
            active_turn.reset(token)
    return run, calls, closed, turn


def test_extra_root_field_recovers_only_after_explicit_second_strict_output(monkeypatch):
    run, calls, closed, turn = exercise(monkeypatch, [{**BASE, "trip": {"candidate": None}}, BASE])
    result = asyncio.run(run())
    assert result.intent == "itinerary" and result.itinerary_purpose == "saved_values"
    assert len(calls) == 2 and closed == [True]
    repair = [e for e in turn.events if e["stage"] == "selection_repair"]
    assert [e["status"] for e in repair] == ["running", "completed"]
    assert "candidate" not in json.dumps(repair)
    frozen = json.loads(calls[0]["input_text"])
    assert json.loads(calls[1]["input_text"])["original_request"] == frozen


def test_read_task_only_misplaced_parser_metadata_gets_one_visible_format_repair(monkeypatch):
    known={k:v for k,v in BASE.items() if k!='capabilities'}
    known['read_tasks']=[{'source_quote':'选中的馆原来保存了多久？',
        'capabilities':['itinerary'],'itinerary_purpose':'saved_values'}]
    raw={**known,'confidence':.98,'parser':'model','parser_version':'v1'}
    run,calls,closed,_=exercise(monkeypatch,[raw,known])
    assert asyncio.run(run()).itinerary_purpose=='saved_values'
    assert len(calls)==2 and closed==[True]
    assert json.loads(calls[1]['input_text'])['invalid_selection']==raw


@pytest.mark.parametrize('extra',[
    {'budget_limit':105}, {'confidence':'high'}, {'parser':'save_now'},
    {'parser_version':'v1','memory_updates':[{'field':'city','value':'成都','source_quote':'成都'}]},
])
def test_read_task_only_unknown_or_authority_metadata_is_not_repairable(monkeypatch,extra):
    raw={k:v for k,v in BASE.items() if k!='capabilities'}
    raw['read_tasks']=[{'source_quote':'选中的馆原来保存了多久？','capabilities':['itinerary']}]
    run,calls,_,_=exercise(monkeypatch,[{**raw,**extra}])
    with pytest.raises(ValidationError):
        asyncio.run(run())
    assert len(calls)==1


@pytest.mark.parametrize("change", [
    {"intent": "modify", "authorization_quote": "请修改"},
    {"capabilities": ["itinerary", "web"]},
    {"itinerary_purpose": "original_rationale"},
    {"query": "第一天"},
    {"memory_updates": []},  # Even adding a default member is disallowed.
    {"read_tasks": [{"source_quote": "选中的馆", "capabilities": ["itinerary"]}]},
])
def test_schema_valid_repair_cannot_change_or_add_scope_conditions_or_authority(monkeypatch, change):
    run, calls, closed, turn = exercise(monkeypatch, [{**BASE, "trip": {}}, {**BASE, **change}])
    with pytest.raises(selector.CapabilityContractError, match="selection_repair_changed_decision"):
        asyncio.run(run())
    assert len(calls) == 2 and closed == [True]
    assert [e for e in turn.events if e["stage"] == "selection_repair"][-1]["status"] == "failed"


@pytest.mark.parametrize("output,summary", [
    ({**BASE, "trip": {}}, None),
    ({**BASE, "trip": {}}, {**SUMMARY, "candidate": {"draft_id": "present"}}),
    ({**BASE, "trip": {}, "intent": "create"}, SUMMARY),
    ({**BASE, "trip": {}, "intent": "direct"}, SUMMARY),
    ({**BASE, "trip": {}, "memory_updates": [{"field": "city", "value": "成都", "source_quote": "成都"}]}, SUMMARY),
    ({**BASE, "read_tasks": [{"source_quote": "选中的馆", "extra": True}]}, SUMMARY),
    ({"intent": "itinerary", "trip": {}}, SUMMARY),
    ("{invalid JSON", SUMMARY),
    (SimpleNamespace(status="incomplete", output_text=json.dumps({**BASE, "trip": {}})), SUMMARY),
    (TimeoutError(), SUMMARY),
    (RuntimeError("provider refusal"), SUMMARY),
    (asyncio.CancelledError(), SUMMARY),
])
def test_ineligible_failures_never_retry_and_always_close(monkeypatch, output, summary):
    run, calls, closed, turn = exercise(monkeypatch, [output], summary=summary)
    with pytest.raises((ValueError, RuntimeError, TimeoutError, asyncio.CancelledError)):
        asyncio.run(run())
    assert len(calls) == 1 and closed == [True]
    assert not any(e["stage"] == "selection_repair" for e in turn.events)


def test_failed_second_output_is_not_ignored_or_retried_a_third_time(monkeypatch):
    run, calls, closed, _ = exercise(monkeypatch, [{**BASE, "trip": {}}, {**BASE, "trip": {}}])
    with pytest.raises(ValidationError):
        asyncio.run(run())
    assert len(calls) == 2 and closed == [True]


def test_policy_rejection_does_not_trigger_protocol_repair(monkeypatch):
    run, calls, closed, turn = exercise(monkeypatch, [BASE])
    def reject(*args):
        raise selector.CapabilityContractError("policy_rejected")
    monkeypatch.setattr(selector, "validate_decision", reject)
    with pytest.raises(selector.CapabilityContractError):
        asyncio.run(run())
    assert len(calls) == 1 and closed == [True]
    assert not any(e["stage"] == "selection_repair" for e in turn.events)


def test_context_is_frozen_before_first_call(monkeypatch):
    async def mutate(attempt, history, env):
        history[0]["user"] = "改查第一天"
        env.conversation_memory["untrusted_change"] = "南京"
    run, calls, _, _ = exercise(monkeypatch, [{**BASE, "trip": {}}, BASE], hook=mutate)
    asyncio.run(run())
    assert json.loads(calls[1]["input_text"])["original_request"] == json.loads(calls[0]["input_text"])
    assert json.loads(calls[1]["input_text"])["original_request"]["browsing_city"] == "成都"


def test_second_attempt_shares_the_remaining_turn_deadline(monkeypatch):
    async def slow(attempt, history, env):
        if attempt == 2:
            await asyncio.Event().wait()
    run, calls, closed, turn = exercise(monkeypatch, [{**BASE, "trip": {}}, BASE], hook=slow)
    turn.seconds = .5
    with pytest.raises(TimeoutError):
        asyncio.run(run())
    assert len(calls) == 2 and closed == [True]
    assert any(e["stage"] == "selection_repair" and e["status"] == "failed" for e in turn.events)


def test_selection_timeout_encloses_both_attempts_once_even_with_large_turn_budget(monkeypatch):
    async def slow(attempt, history, env):
        if attempt == 2:
            await asyncio.Event().wait()
    run, calls, closed, turn = exercise(monkeypatch, [{**BASE, "trip": {}}, BASE], hook=slow)
    original, limits = selector.bounded_call, []
    async def short_selection_budget(operation, *, stage, limit):
        limits.append((stage, limit))
        return await original(operation, stage=stage, limit=.5)
    monkeypatch.setattr(selector, "bounded_call", short_selection_budget)
    with pytest.raises(TimeoutError):
        asyncio.run(run())
    assert limits == [("selection", 30)] and turn.remaining() > 80
    assert len(calls) == 2 and closed == [True]
