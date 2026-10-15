import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.config import get_settings
from app.database import Activity, DayPlan, Trip, session_factory
from app.demo_seed import DEMO_TRIP_ID, seed_demo_data
from app.openai_intent_parser import build_semantic_intent_provider
from app.planning_intent_service import resolve_planning_intent
from app.schemas import PlanningIntentParseRequest
from evals.intent_cases import INTENT_EVAL_CASES


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile), len(ordered) - 1)
    return ordered[index]


async def _fingerprint() -> dict[str, Any]:
    async with session_factory() as session:
        trip = await session.get(Trip, DEMO_TRIP_ID)
        activity_count = await session.scalar(
            select(func.count(Activity.id))
            .join(DayPlan)
            .where(DayPlan.trip_id == DEMO_TRIP_ID)
        )
        return {
            "trip_version": trip.version if trip is not None else None,
            "activity_count": int(activity_count or 0),
        }


async def run(use_model: bool) -> dict[str, Any]:
    async with session_factory() as session:
        await seed_demo_data(session, reset=False)
        days = list(
            (
                await session.scalars(
                    select(DayPlan)
                    .where(DayPlan.trip_id == DEMO_TRIP_ID)
                    .order_by(DayPlan.position)
                )
            ).all()
        )
        activity_rows = list(
            (
                await session.execute(
                    select(Activity, DayPlan)
                    .join(DayPlan, Activity.day_plan_id == DayPlan.id)
                    .where(DayPlan.trip_id == DEMO_TRIP_ID)
                    .order_by(DayPlan.position, Activity.position)
                )
            ).tuples()
        )
    activities_by_day: dict[int, list[Activity]] = {}
    for activity, day in activity_rows:
        activities_by_day.setdefault(day.position + 1, []).append(activity)
    provider = build_semantic_intent_provider(get_settings()) if use_model else None
    before = await _fingerprint()
    counters: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    latencies: list[float] = []

    for case in INTENT_EVAL_CASES:
        selected_activity_id = None
        selected_reference = case.get("selected_activity")
        if selected_reference:
            day_part, index_part = selected_reference.split(":", 1)
            selected_activity_id = activities_by_day[int(day_part.removeprefix("day"))][
                int(index_part)
            ].id
        started = time.perf_counter()
        async with session_factory() as session:
            result = await resolve_planning_intent(
                session,
                DEMO_TRIP_ID,
                PlanningIntentParseRequest(
                    message=case["text"],
                    entry_point=("activity_editor" if selected_activity_id else "trip_planner"),
                    selected_activity_id=selected_activity_id,
                ),
                semantic_provider=provider,
            )
        latencies.append((time.perf_counter() - started) * 1000)
        assert result.semantic_draft is not None
        assert result.grounded_intent is not None
        assert result.policy_decision is not None
        counters["cases"] += 1
        counters[f"parser:{result.semantic_draft.parser}"] += 1
        mismatches: list[str] = []

        expected_primary = case["expected_primary"]
        if expected_primary != "mixed":
            counters["primary_scored"] += 1
            if result.semantic_draft.primary_intent == expected_primary:
                counters["primary_correct"] += 1
            else:
                mismatches.append("primary")

        expected_operations = set(case["expected_operations"])
        if expected_operations:
            counters["operations_scored"] += 1
            actual_operations = set(result.grounded_intent.operation_types)
            if actual_operations == expected_operations:
                counters["operations_correct"] += 1
            else:
                mismatches.append("operations")

        if case["expected_route"] != "mixed":
            counters["route_scored"] += 1
            if result.policy_decision.route == case["expected_route"]:
                counters["route_correct"] += 1
            else:
                mismatches.append("route")

        expected_clarify = case["should_clarify"]
        if case["expected_route"] == "mixed":
            pass
        elif expected_clarify:
            counters["clarify_positive"] += 1
            if result.requires_clarification:
                counters["clarify_true_positive"] += 1
            else:
                mismatches.append("missed_clarification")
        else:
            counters["clarify_negative"] += 1
            if result.requires_clarification:
                counters["clarify_false_positive"] += 1
                mismatches.append("false_clarification")

        expected_day = case["target_day_number"]
        if expected_day is not None:
            counters["day_scored"] += 1
            expected_day_id = days[expected_day - 1].id
            if expected_day_id in result.grounded_intent.target_day_ids:
                counters["day_correct"] += 1
            else:
                mismatches.append("target_day")

        if "grounding" in case["tags"]:
            counters["grounding_scored"] += 1
            if "unknown_place" in case["tags"]:
                grounded_ok = bool(result.grounded_intent.unresolved_place_mentions)
            else:
                grounded_ok = not (
                    result.grounded_intent.unresolved_activity_mentions
                    or result.grounded_intent.unresolved_place_mentions
                )
            if grounded_ok:
                counters["grounding_correct"] += 1
            else:
                mismatches.append("grounding")

        if mismatches:
            failures.append(
                {
                    "id": case["id"],
                    "text": case["text"],
                    "mismatches": mismatches,
                    "actual_primary": result.semantic_draft.primary_intent,
                    "actual_operations": result.grounded_intent.operation_types,
                    "actual_route": result.policy_decision.route,
                    "unresolved_activity_mentions": result.grounded_intent.unresolved_activity_mentions,
                    "unresolved_place_mentions": result.grounded_intent.unresolved_place_mentions,
                    "missing_fields": result.grounded_intent.missing_fields,
                    "ambiguities": result.grounded_intent.ambiguities,
                }
            )

    after = await _fingerprint()
    unauthorized_writes = 0 if before == after else 1

    def ratio(numerator: str, denominator: str) -> float:
        return round(counters[numerator] / counters[denominator], 4) if counters[denominator] else 0.0

    return {
        "dataset_version": "roamsync-intent-v1",
        "use_model": use_model,
        "case_count": counters["cases"],
        "metrics": {
            "primary_intent_accuracy": ratio("primary_correct", "primary_scored"),
            "operation_exact_match": ratio("operations_correct", "operations_scored"),
            "entity_grounding_accuracy": ratio("grounding_correct", "grounding_scored"),
            "target_day_accuracy": ratio("day_correct", "day_scored"),
            "clarification_recall": ratio("clarify_true_positive", "clarify_positive"),
            "clarification_false_block_rate": ratio("clarify_false_positive", "clarify_negative"),
            "route_accuracy": ratio("route_correct", "route_scored"),
            "unauthorized_write_count": unauthorized_writes,
            "latency_ms_mean": round(statistics.fmean(latencies), 2),
            "latency_ms_p50": round(_percentile(latencies, 0.50), 2),
            "latency_ms_p95": round(_percentile(latencies, 0.95), 2),
        },
        "parser_counts": {
            key.removeprefix("parser:"): value
            for key, value in counters.items()
            if key.startswith("parser:")
        },
        "model_calls": int(getattr(provider, "call_count", 0)) if provider else 0,
        "model_failures": int(getattr(provider, "failure_count", 0)) if provider else 0,
        "model_total_tokens": int(getattr(provider, "total_tokens", 0)) if provider else 0,
        "model_latency_ms_p50": round(
            _percentile(list(getattr(provider, "latencies_ms", [])), 0.50), 2
        ) if provider else 0.0,
        "model_latency_ms_p95": round(
            _percentile(list(getattr(provider, "latencies_ms", [])), 0.95), 2
        ) if provider else 0.0,
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the RoamSync intent control layer.")
    parser.add_argument("--use-model", action="store_true", help="Enable configured semantic model fallback.")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            report = runner.run(run(args.use_model))
    else:
        report = asyncio.run(run(args.use_model))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if report["metrics"]["unauthorized_write_count"]:
        raise SystemExit(2)
    if args.use_model and report["model_failures"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
