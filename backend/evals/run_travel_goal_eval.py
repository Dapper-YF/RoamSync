"""Offline routing evaluation: python -m evals.run_travel_goal_eval --output PATH."""
import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.travel_goal_router import route_travel_goal
from evals.travel_goal_cases import TRAVEL_GOAL_CASES


def evaluate() -> dict:
    results = []
    for case in TRAVEL_GOAL_CASES:
        actual = route_travel_goal(case["text"], case.get("history"))
        results.append({"id": case["id"], "expected_runtime": case["runtime"],
            "expected_goal": case["goal"], "actual": actual.model_dump(mode="json")})
    counts = Counter(case["runtime"] for case in TRAVEL_GOAL_CASES)
    return {"measured_at": datetime.now(UTC).isoformat(), "mode": "offline_deterministic_rules",
        "provider_calls": 0, "case_count": len(results), "expected_runtime_counts": dict(counts),
        "runtime_correct": sum(r["actual"]["target_runtime"] == r["expected_runtime"] for r in results),
        "goal_correct": sum(r["actual"]["goal_type"] == r["expected_goal"] for r in results),
        "error_a_companion_to_planning": sum(r["expected_runtime"] == "companion" and r["actual"]["target_runtime"] == "planning" for r in results),
        "error_b_planning_to_companion": sum(r["expected_runtime"] == "planning" and r["actual"]["target_runtime"] == "companion" for r in results),
        "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False))
    raise SystemExit(0 if report["runtime_correct"] == report["goal_correct"] == report["case_count"] else 1)
