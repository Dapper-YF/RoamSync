import json
from pathlib import Path

from evals.travel_benchmark import BenchmarkTrace, Scenario, deterministic_metrics, geographic_precondition_failure, load_scenarios, semantic_review_packet, write_result


FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "scenarios" / "travel_agent_v1.json"


def test_stage_zero_scenarios_are_structured_unique_and_cover_required_kinds():
    scenarios = load_scenarios(FIXTURE)
    # Stage 0 keeps both the generic and exact-reference must-do baselines.
    # The fixture is intentionally expanded rather than replacing the former.
    assert len(scenarios) == 12
    assert {item.kind for item in scenarios} == {
        "initial_planning", "ambiguous_request", "must_do_conflict", "recovery_delay", "user_reject",
        "preference_preservation", "budget_pressure", "provider_failure", "bad_but_valid",
    }


def test_deterministic_metrics_preserve_hard_facts_and_identify_excess_change():
    scenario = Scenario.from_dict({"id": "recovery", "kind": "recovery_delay", "title": "x", "input": {},
                                    "expected": {"must_preserve_activity_ids": ["show"], "allowed_change_activity_ids": ["coffee"], "avoid_categories": ["shopping"]},
                                    "required_tools": ["route"]})
    result = deterministic_metrics(scenario, {"validation": {"valid": True, "errors": []}, "tool_calls": ["route", "poi"],
        "candidate": {"activities": [{"replaces_activity_id": "show", "category": "culture"}], "explanation": "依据预约保留演出"},
        "changed_activity_ids": ["coffee", "museum"], "explanation_claims": ["reservation"], "explanation_evidence": ["reservation"]})
    assert result["constraint_violation_rate"] == 0
    assert result["goal_satisfaction"] == 1
    assert result["unnecessary_change_rate"] == 0.5
    assert result["tool_precision"] == 0.5
    assert result["explanation_faithfulness"] == 1


def test_intent_routing_metric_marks_pre_planning_exit_without_planner_failure():
    scenario = Scenario.from_dict({"id": "routing", "kind": "initial_planning", "title": "x", "input": {},
                                    "expected": {"expected_task_type": "initial_plan"}})
    result = deterministic_metrics(scenario, {"resolved_intent": "adjust_budget", "reachability": {"planner": "not_reached"},
                                              "validation": {}, "candidate": {}, "tool_calls": []})
    assert result["intent_routing_accuracy"] == 0
    assert result["goal_satisfaction"] is None
    assert result["explanation_faithfulness"] is None


def test_route_fixture_geographic_preconditions_are_explicit_and_fail_before_planner_metrics():
    scenario = Scenario.from_dict({"id": "route", "kind": "must_do_conflict", "title": "x", "input": {}, "expected": {},
                                    "required_geographic_metadata": ["destination_city", "destination_citycode", "coordinate_system"]})
    assert geographic_precondition_failure(scenario, {"destination_city": "杭州市"}) == {
        "classification": "fixture/data precondition failure",
        "missing_geographic_metadata": ["destination_citycode", "coordinate_system"],
        "planner_metrics": "not_applicable",
    }
    assert geographic_precondition_failure(scenario, {"destination_city": "杭州市", "destination_citycode": "0571", "coordinate_system": "GCJ-02"}) is None


def test_trace_and_result_are_json_serializable_and_human_reviewable(tmp_path):
    scenario = Scenario.from_dict({"id": "x", "kind": "bad_but_valid", "title": "x", "input": {}, "expected": {}})
    trace = BenchmarkTrace("x", run_id="run-1")
    trace.record("plan", "planner", input_fact_refs=["trip", "preferences"], data={"candidate_count": 1})
    artifact = {"validation": {"valid": True, "errors": []}, "candidate": {"activities": [], "explanation": "x"}, "tool_calls": []}
    output = tmp_path / "x.json"
    write_result(output, scenario=scenario, artifact=artifact, trace=trace)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["trace"]["events"][0]["graph_step"] == "plan"
    assert saved["semantic_review"]["rubric"] == semantic_review_packet(scenario, artifact)["rubric"]
