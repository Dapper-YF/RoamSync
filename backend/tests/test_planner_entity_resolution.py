import json
import uuid
from datetime import date
import pytest
from pydantic import ValidationError
from app.openai_planner import build_planner_input
from app.planner_entity_resolution import (PlannerEntityBindings, SemanticPlannerOutput,
    InvalidPlannerReference, resolve_planner_activity_references, parse_semantic_planner_output)
from tests.test_openai_planner import _state


def fixture():
    state, _, _ = _state()
    formal = state["planning_context"]["days"][0]["activities"][0]
    formal.update(status="planned", schedule_locked=False)
    raw, allowed, dates = build_planner_input(state, max_candidates=40)
    return state, formal, raw, PlannerEntityBindings(raw, allowed), dates


def selection(**kwargs):
    return {"source": "existing", "activity_ref": "activity_1", "day_date": "2026-11-01",
            "planned_start_time": "11:00", "duration_minutes": 90,
            "transport_mode_to_here": "transit", "reason": "留出停留与休息时间", **kwargs}


@pytest.mark.parametrize("start,duration", [("09:00",60), ("11:00",60), ("09:00",30), ("09:00",90)])
def test_preserve_move_shorten_extend_keeps_formal_identity(start,duration):
    _, formal, _, bindings, dates = fixture()
    draft=SemanticPlannerOutput(activities=[selection(planned_start_time=start,duration_minutes=duration)], explanation="调整节奏")
    item=resolve_planner_activity_references(draft,bindings,dates).activities[0]
    assert str(item.replaces_activity_id)==formal["id"]
    assert str(item.place_candidate_id)==formal["place_id"]
    assert str(item.source_ids[0])==formal["source"]["id"]
    assert item.estimated_cost_fen==formal["estimated_cost_fen"]


def test_new_candidate_exact_binding():
    state, _, _, bindings, dates = fixture()
    state["planning_context"]["candidates"].append({**state["planning_context"]["candidates"][0], "id": str(uuid.uuid4()), "name":"新候选2"})
    raw,allowed,dates=build_planner_input(state,max_candidates=40)
    bindings=PlannerEntityBindings(raw,allowed)
    data=selection(source="candidate",candidate_ref="candidate_2")
    data.pop("activity_ref")
    draft=SemanticPlannerOutput(activities=[data],explanation="新增体验")
    item=resolve_planner_activity_references(draft,bindings,dates).activities[0]
    assert item.place_candidate_id==bindings.candidates["candidate_2"].id
    assert item.replaces_activity_id is None


@pytest.mark.parametrize("source,ref",[("existing","activity_99"),("existing","candidate_1"),("candidate","candidate_99"),("candidate","activity_1")])
def test_unknown_and_cross_domain_refs_rejected(source,ref):
    _,_,_,bindings,dates=fixture()
    data=selection(source=source)
    if source=="candidate":
        data.pop("activity_ref"); data["candidate_ref"]=ref
    else:
        data["activity_ref"]=ref
    draft=SemanticPlannerOutput(activities=[data],explanation="")
    with pytest.raises(InvalidPlannerReference):
        resolve_planner_activity_references(draft,bindings,dates)


@pytest.mark.parametrize("data",[selection(candidate_ref="candidate_1"),selection(source="candidate",candidate_ref="candidate_1")])
def test_cross_domain_fields_rejected_by_schema(data):
    with pytest.raises(ValidationError):
        SemanticPlannerOutput(activities=[data],explanation="")


def test_wire_schema_prompt_have_same_refs_and_no_uuid_contract():
    state,_,raw,bindings,dates=fixture()
    wire=bindings.prompt(raw); schema=bindings.schema(dates)
    assert wire["allowed_activity_refs"]==schema["$defs"]["ExistingActivityDecision"]["properties"]["activity_ref"]["enum"]
    assert wire["allowed_candidate_refs"]==schema["$defs"]["NewActivityDecision"]["properties"]["candidate_ref"]["enum"]
    text=json.dumps([wire,schema])
    for day in state["planning_context"]["days"]:
        for item in day["activities"]:
            assert item["id"] not in text and item["place_id"] not in text
    assert "place_candidate_id" not in text
    assert "decision_ledger" not in schema["properties"]
    assert "coordinates" not in json.dumps(schema)


def test_malformed_json_and_semantic_values_never_repaired():
    _,_,_,bindings,dates=fixture()
    with pytest.raises(json.JSONDecodeError):
        parse_semantic_planner_output('{"activities":[],}',bindings)
    draft,_,_=parse_semantic_planner_output(json.dumps({"activities":[selection(activity_ref="activity_99")],"explanation":""}),bindings)
    with pytest.raises(InvalidPlannerReference):
        resolve_planner_activity_references(draft,bindings,dates)


def test_memory_is_bounded_without_changing_stored_facts():
    _,_,raw,bindings,_=fixture()
    raw["previous_user_feedback"]=[{"source_revision_id":str(uuid.uuid4()),"rejection_reason_code":"too_rushed","rejection_reason_text":"多留休息时间","previous_candidate_summary":{"activity_count":5,"changed_activity_ids":[str(uuid.uuid4()) for _ in range(100)]},"full_history":"unused"}]
    wire=bindings.prompt(raw)
    memory=wire["previous_user_feedback"][0]
    assert memory["rejection_reason_text"]=="多留休息时间"
    assert len(memory["previous_candidate_summary"]["changed_activity_refs"])==10
    assert "full_history" not in memory
    assert len(raw["previous_user_feedback"][0]["previous_candidate_summary"]["changed_activity_ids"])==100


@pytest.mark.parametrize("ledger", ["invalid", [{"decision_type":"invented"}]])
def test_invalid_optional_shadow_ledger_does_not_block_candidate(ledger):
    _,_,_,bindings,dates=fixture()
    draft,parsed,errors=parse_semantic_planner_output(json.dumps({"activities":[selection()],"explanation":"调整节奏","decision_ledger":ledger}),bindings)
    assert parsed is None and errors==["decision_ledger_output_invalid"]
    result=resolve_planner_activity_references(draft,bindings,dates,ledger=parsed,errors=errors)
    assert len(result.activities)==1 and result.provenance_parse_errors==errors


def test_correction_context_uses_the_same_existing_and_new_identity_domains():
    state,formal,_,_,dates=fixture()
    place_id=state["planning_context"]["candidates"][0]["id"]
    def prior(place, key):
        return {"candidate_id":key,"day_date":"2026-11-01","place_candidate_id":place,"planned_start_time":"10:00","duration_minutes":60,"transport_mode_to_here":"transit","reason":"调整节奏"}
    state["proposed_snapshot"]={"activities":[prior(formal["place_id"],"prior-existing"),prior(place_id,"prior-new")],"route_legs":[{"day_date":"2026-11-01","from_activity_ref":"prior-existing","to_activity_ref":"prior-new","mode":"transit","duration_minutes":30,"distance_meters":3000}]}
    state["validation_result"]={"errors":[{"code":"route_travel_time_conflict","message":"预留交通时间"}]}
    raw,allowed,dates=build_planner_input(state,max_candidates=40)
    wire=PlannerEntityBindings(raw,allowed).prompt(raw)
    previous=wire["previous_plan"]
    assert previous["activities"][0]["source"]=="existing" and previous["activities"][0]["activity_ref"]=="activity_1"
    assert previous["activities"][1]["source"]=="candidate" and previous["activities"][1]["candidate_ref"]=="candidate_1"
    assert previous["route_legs"][0]["from_activity_ref"]=="activity_1"
    assert previous["route_legs"][0]["to_activity_ref"]=="candidate_1"
    assert "candidate_id" not in json.dumps(previous)
    assert formal["place_id"] not in json.dumps(previous)
