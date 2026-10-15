"""Run fixture-backed Stage 0 benchmark results without a paid model.

Live adapters should write the same artifact schema after executing a real
PlanningRun.  This command deliberately does not invoke or tune the planner.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from evals.travel_benchmark import BenchmarkTrace, load_scenarios, write_result


ROOT = Path(__file__).resolve().parent


def baseline_artifact(scenario_id: str) -> dict:
    # Explicit observations of current architectural capability, not synthetic
    # quality scores. They make CI reproducible while live-provider runs remain optional.
    common = {"validation": {"valid": True, "errors": []}, "candidate": {"activities": [], "explanation": ""},
              "tool_calls": [], "changed_activity_ids": [], "preserved_activity_ids": [],
              "explanation_claims": [], "explanation_evidence": []}
    if scenario_id == "ambiguous-relaxed": return {**common, "final_outcome": "plans_without_value_clarification"}
    if scenario_id == "reject-repeat-density": return {**common, "repeat_error": True, "final_outcome": "rejection_not_in_planner_context"}
    if scenario_id == "bad-but-valid-rush": return {**common, "bad_but_valid_detected": False, "final_outcome": "no_semantic_critic"}
    if scenario_id == "provider-failure": return {**common, "validation": {"valid": False, "errors": [{"code": "provider_unavailable"}]}, "final_outcome": "fails_closed"}
    return {**common, "final_outcome": "requires_live_provider_run"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, default=ROOT / "scenarios" / "travel_agent_v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "baseline-offline")
    args = parser.parse_args()
    for scenario in load_scenarios(args.scenarios):
        trace = BenchmarkTrace(scenario.id, run_id=f"offline:{scenario.id}")
        trace.record("fixture_baseline", "context", input_fact_refs=list(scenario.input.get("facts", [])), data={"mode": "offline"})
        artifact = baseline_artifact(scenario.id)
        trace.record("final_outcome", "decision", data={"outcome": artifact["final_outcome"]})
        write_result(args.output / f"{scenario.id}.json", scenario=scenario, artifact=artifact, trace=trace)


if __name__ == "__main__":
    main()
