"""Provider-independent Stage 0 Travel Agent benchmark primitives.

This module intentionally evaluates an observed run.  It never changes a
planner prompt, selects tools, or writes an itinerary.  Production adapters
may populate the same artifact from a PlanningRun; CI uses fixtures.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


SCENARIO_KINDS = {
    "initial_planning", "ambiguous_request", "must_do_conflict", "recovery_delay",
    "user_reject", "preference_preservation", "budget_pressure", "provider_failure",
    "bad_but_valid",
}


@dataclass(frozen=True)
class Scenario:
    id: str
    kind: str
    title: str
    input: dict[str, Any]
    expected: dict[str, Any]
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_geographic_metadata: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Scenario":
        missing = {"id", "kind", "title", "input", "expected"} - set(value)
        if missing:
            raise ValueError(f"scenario missing fields: {sorted(missing)}")
        if value["kind"] not in SCENARIO_KINDS:
            raise ValueError(f"unsupported scenario kind: {value['kind']}")
        if not isinstance(value["input"], dict) or not isinstance(value["expected"], dict):
            raise ValueError("scenario input and expected must be objects")
        return cls(value["id"], value["kind"], value["title"], value["input"], value["expected"],
                   tuple(value.get("required_tools", ())), tuple(value.get("forbidden_tools", ())),
                   tuple(value.get("required_geographic_metadata", ())))


def geographic_precondition_failure(
    scenario: Scenario, metadata: dict[str, Any]
) -> dict[str, Any] | None:
    """Return a fixture classification when required route facts are absent.

    This is eval-only validation. It does not infer, repair, or write trip data.
    """
    missing = [field for field in scenario.required_geographic_metadata if not metadata.get(field)]
    if not missing:
        return None
    return {
        "classification": "fixture/data precondition failure",
        "missing_geographic_metadata": missing,
        "planner_metrics": "not_applicable",
    }


def load_scenarios(path: Path) -> list[Scenario]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("scenario fixture must be a JSON list")
    scenarios = [Scenario.from_dict(item) for item in data]
    ids = [item.id for item in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("scenario ids must be unique")
    return scenarios


@dataclass(frozen=True)
class TraceEvent:
    graph_step: str
    kind: Literal["graph", "context", "tool_call", "tool_result", "planner", "validation", "decision"]
    input_fact_refs: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int | None = None


@dataclass
class BenchmarkTrace:
    scenario_id: str
    run_id: str | None = None
    events: list[TraceEvent] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def record(self, graph_step: str, kind: str, *, input_fact_refs: list[str] | tuple[str, ...] = (),
               data: dict[str, Any] | None = None, elapsed_ms: int | None = None) -> None:
        # Deliberately structured and small: no prompt, full DB snapshot, or secrets.
        self.events.append(TraceEvent(graph_step, kind, tuple(input_fact_refs), data or {}, elapsed_ms))

    def finish(self) -> None:
        self.completed_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "travel-agent-trace-v1", "scenario_id": self.scenario_id,
            "run_id": self.run_id, "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "events": [asdict(event) for event in self.events],
        }


def _ids(items: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("replaces_activity_id") or item.get("activity_id")) for item in items
            if item.get("replaces_activity_id") or item.get("activity_id")}


def deterministic_metrics(scenario: Scenario, artifact: dict[str, Any]) -> dict[str, Any]:
    """Calculate only evidence-backed Stage 0 metrics from an observed artifact."""
    validation = artifact.get("validation", {})
    candidate = artifact.get("candidate", {})
    activities = candidate.get("activities", []) if isinstance(candidate, dict) else []
    expected = scenario.expected
    errors = validation.get("errors", []) if isinstance(validation, dict) else []
    called = set(artifact.get("tool_calls", []))
    preserved = set(artifact.get("preserved_activity_ids", [])) | _ids(activities)
    must_preserve = set(expected.get("must_preserve_activity_ids", []))
    avoid_categories = set(expected.get("avoid_categories", []))
    categories = {str(item.get("category")) for item in activities if item.get("category")}
    changed = set(artifact.get("changed_activity_ids", []))
    allowed_changes = set(expected.get("allowed_change_activity_ids", []))
    explanation = str(candidate.get("explanation", "")) if isinstance(candidate, dict) else ""
    claims = artifact.get("explanation_claims", [])
    evidence = set(artifact.get("explanation_evidence", []))
    expected_task = expected.get("expected_resolved_intent") or expected.get("expected_task_type")
    resolved_intent = artifact.get("resolved_intent")
    planner_reached = artifact.get("reachability", {}).get("planner", "reached") == "reached"
    return {
        "intent_routing_accuracy": (
            float(resolved_intent == expected_task) if expected_task and resolved_intent is not None else None
        ),
        "constraint_violation_rate": 0.0 if validation.get("valid") is True else 1.0,
        "goal_satisfaction": (1.0 if must_preserve.issubset(preserved) else 0.0) if (planner_reached or must_preserve) else None,
        "preference_preservation": 0.0 if categories & avoid_categories else 1.0,
        "unnecessary_change_rate": (len(changed - allowed_changes) / len(changed)) if changed else 0.0,
        "tool_precision": (len(called & set(scenario.required_tools)) / len(called)) if called else 1.0,
        "tool_recall": (len(called & set(scenario.required_tools)) / len(scenario.required_tools)) if scenario.required_tools else 1.0,
        "forbidden_tool_calls": sorted(called & set(scenario.forbidden_tools)),
        "explanation_faithfulness": (1.0 if explanation and set(claims).issubset(evidence) else (1.0 if not claims else 0.0)) if planner_reached else None,
        "repeat_error": bool(artifact.get("repeat_error", False)),
        "bad_but_valid_detected": bool(artifact.get("bad_but_valid_detected", False)),
        "validation_error_codes": [str(item.get("code")) for item in errors if isinstance(item, dict)],
    }


SEMANTIC_RUBRIC = {
    "relaxed_pace": "Does the proposal avoid implausibly short meals/visits and excessive consecutive stops?",
    "tradeoff_grounding": "Does it link each major compromise to a supplied fact, constraint, or explicit preference?",
    "uncertainty_honesty": "Does it avoid presenting unavailable provider facts as known?",
}


def semantic_review_packet(scenario: Scenario, artifact: dict[str, Any]) -> dict[str, Any]:
    """Stable LLM-or-human judge input; the caller owns model invocation."""
    return {"schema_version": "travel-agent-semantic-rubric-v1", "scenario": asdict(scenario),
            "artifact": artifact, "rubric": SEMANTIC_RUBRIC,
            "required_output": {"scores": {key: "0..2" for key in SEMANTIC_RUBRIC},
                                "evidence": "fact references and concise explanation", "verdict": "pass|fail|unknown"}}


def write_result(path: Path, *, scenario: Scenario, artifact: dict[str, Any], trace: BenchmarkTrace) -> None:
    trace.finish()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"scenario_id": scenario.id, "artifact": artifact,
                                "metrics": deterministic_metrics(scenario, artifact), "trace": trace.to_dict(),
                                "semantic_review": semantic_review_packet(scenario, artifact)},
                               ensure_ascii=False, indent=2), encoding="utf-8")
