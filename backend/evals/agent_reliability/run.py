"""Live fixed-demo reliability benchmark. Only the dedicated demo is reset/rejected."""
import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from sqlalchemy import select
from app.config import get_settings
from app.database import session_factory, Trip, DayPlan, PlanRevision, PlanningRun
from app.demo_seed import TRAVEL_DECISION_DEMO_TRIP_ID, seed_travel_decision_demo_data
from app.planning_context import build_planning_context
from app.planning_run_repository import create_planning_run, get_latest_revision, reject_revision
from app.schemas import PlanningRunCreate
from app.openai_planner import OpenAIResponsesPlanner
from app.openai_intent_parser import build_semantic_intent_provider
from app import planning_graph_runtime as runtime
from evals.travel_benchmark import BenchmarkTrace

FIRST = "请帮我调整 2026-10-20 当天的行程。我希望轻松一点，尽量少走路，18:00 前结束，现有活动尽量不要大改。"
SECOND = "请再调整一次 2026-10-20 当天的行程，节奏轻松一点，尽量少走路，18:00 前结束，现有活动尽量不要大改。"
FEEDBACK = "五项活动仍显得紧凑，希望多留休息与停留时间"
observations = {}
traces = {}


class ObservedPlanner(OpenAIResponsesPlanner):
    async def generate(self, state):
        self.last_reliability = {}
        try:
            return await super().generate(state)
        finally:
            observations.setdefault(state["run_id"], []).append(dict(self.last_reliability))


original_build = runtime.build_planning_graph

def observed_build(*args, **kwargs):
    kwargs["trace_observer"] = current_trace
    return original_build(*args, **kwargs)


async def formal():
    async with session_factory() as session:
        context = (await build_planning_context(session, TRAVEL_DECISION_DEMO_TRIP_ID)).model_dump(mode="json")
        return {"version": context["trip"]["version"], "days": context["days"]}


async def reset():
    async with session_factory() as session:
        await seed_travel_decision_demo_data(session, reset=True)


async def one(request):
    global current_trace
    started = monotonic()
    settings = get_settings()
    async with session_factory() as session:
        day = await session.scalar(select(DayPlan).where(DayPlan.trip_id == TRAVEL_DECISION_DEMO_TRIP_ID))
        run = await create_planning_run(session, TRAVEL_DECISION_DEMO_TRIP_ID,
            PlanningRunCreate(run_type="replan", user_request=request, selected_day_id=day.id),
            semantic_provider=build_semantic_intent_provider(settings))
        run_id = run.id
    current_trace = BenchmarkTrace("agent_reliability", run_id=str(run_id))
    try:
        await runtime.execute_planning_run(run_id)
    except Exception as exc:
        # Record an unexpected production exception; never infer success.
        print(json.dumps({"unexpected_exception": type(exc).__name__, "run_id": str(run_id)}), flush=True)
    current_trace.finish()
    async with session_factory() as session:
        run = await session.get(PlanningRun, run_id)
        revision = await get_latest_revision(session, run_id)
        metrics = observations.get(str(run_id), [])
        attempts = [attempt for call in metrics for attempt in call.get("attempts", [])]
        failures = [a["category"] for a in attempts if a["category"] != "success"]
        event_data = [event.data for event in current_trace.events if event.graph_step == "memory_retrieved"]
        memory = event_data[-1] if event_data else {}
        category = (run.error_details or {}).get("category")
        if run.status == "failed" and not category:
            category = "provider_failure" if any(x in (run.error_code or "") for x in ("unavailable", "timeout", "rate", "research", "authentication", "provider", "map")) else "unclassified_failure"
        return {"run_id": str(run_id), "request": request, "status": run.status,
            "intent_reached": bool(run.intent_resolution), "planner_reached": bool(metrics),
            "parse_success": bool(metrics and metrics[-1].get("parse_success")),
            "reference_resolution_success": bool(metrics and metrics[-1].get("reference_resolution_success")),
            "candidate_valid": bool(revision and (revision.validation_result or {}).get("valid")),
            "revision_produced": bool(revision and revision.status == "pending"),
            "revision_id": str(revision.id) if revision else None,
            "memory_count": memory.get("count", 0), "memory_source_revision_ids": memory.get("source_revision_ids", []),
            "memory_visible_to_planner": bool(metrics and metrics[0].get("memory_count")),
            "failure_category": category, "error_code": run.error_code,
            "attempt_failure_categories": failures, "planner_calls": metrics,
            "provider": run.model_provider, "model": run.model_name, "token_usage": run.token_usage,
            "elapsed_seconds": round(monotonic() - started, 2),
            "ledger_status": (revision.difference_summary or {}).get("decision_ledger_status") if revision else None}


def summarize(rows):
    n = len(rows)
    counts = {key: sum(bool(row.get(key)) for row in rows) for key in (
        "intent_reached", "planner_reached", "parse_success", "reference_resolution_success", "candidate_valid", "revision_produced")}
    categories = Counter(row["failure_category"] for row in rows if row.get("failure_category"))
    attempts = Counter(category for row in rows for category in row.get("attempt_failure_categories", []))
    rate_keys = {"planner_reached_rate":"planner_reached", "structured_output_parse_rate":"parse_success",
        "reference_resolution_success_rate":"reference_resolution_success", "candidate_validation_rate":"candidate_valid",
        "plan_revision_rate":"revision_produced"}
    rates = {key: {"numerator":counts[field], "denominator":n, "rate":counts[field]/n if n else None} for key,field in rate_keys.items()}
    for key,cat in (("provider_failure_rate","provider_failure"),("malformed_json_rate","planner_malformed_output"),("invalid_reference_rate","planner_invalid_reference")):
        count = sum(row.get("failure_category")==cat or cat in row.get("attempt_failure_categories",[]) for row in rows)
        rates[key]={"numerator":count,"denominator":n,"rate":count/n if n else None}
    return {"success_counts":counts,"failure_categories":dict(categories),"attempt_failure_categories":dict(attempts),"rates":rates}


def memory_rates(rows):
    n = len(rows)
    eligible = [row for row in rows if row.get("feedback_persisted")]
    count = lambda field: sum(bool(row.get("second", {}).get(field)) for row in rows)
    values = {
        "first_revision_rate": (sum(bool(row["first"].get("revision_produced")) for row in rows), n),
        "feedback_persistence_rate": (len(eligible), sum(bool(row["first"].get("revision_produced")) for row in rows)),
        "memory_retrieval_rate": (sum(bool(row.get("memory_retrieved")) for row in eligible), len(eligible)),
        "second_parse_rate": (count("parse_success"), n),
        "second_reference_resolution_rate": (count("reference_resolution_success"), n),
        "second_revision_rate": (count("revision_produced"), n),
        "memory_replan_revision_rate": (count("revision_produced"), n),
    }
    return {key: {"numerator": a, "denominator": b, "rate": a / b if b else None}
            for key, (a, b) in values.items()}


async def main(args):
    runtime.OpenAIResponsesPlanner = ObservedPlanner
    runtime.build_planning_graph = observed_build
    settings = get_settings()
    artifact = {"phase":"Agent Reliability Phase — Entity Resolution & Structured Output Stability",
        "started_at":datetime.now(UTC).isoformat(), "provider":settings.planner_provider,
        "model":settings.planner_model, "reasoning_effort":settings.planner_reasoning_effort,
        "trip_id":str(TRAVEL_DECISION_DEMO_TRIP_ID), "normal_runs":[],"memory_replan_runs":[],
        "thresholds":{"normal_revision":9,"first_revision":9,"second_parse":8,"second_revision":8,"eligible_memory_retrieval_rate":1.0},
        "decision_ledger":"MVP REMAINS OPEN; shadow"}
    def save():
        normal=artifact["normal_runs"]; memory=artifact["memory_replan_runs"]
        artifact["memory_rates"]=memory_rates(memory)
        artifact["normal_summary"]=summarize(normal)
        artifact["memory_first_summary"]=summarize([row["first"] for row in memory])
        seconds=[row["second"] for row in memory if row.get("second")]
        artifact["memory_second_summary"]=summarize(seconds)
        eligible=[row for row in memory if row.get("feedback_persisted")]
        artifact["memory_success_counts"]={"first_revision":sum(row["first"]["revision_produced"] for row in memory),
            "feedback_persistence":len(eligible),"memory_retrieval":sum(row.get("memory_retrieved",False) for row in memory),
            "second_parse":sum(row.get("second",{}).get("parse_success",False) for row in memory),
            "second_reference_resolution":sum(row.get("second",{}).get("reference_resolution_success",False) for row in memory),
            "second_revision":sum(row.get("second",{}).get("revision_produced",False) for row in memory),
            "memory_eligible_denominator":len(eligible)}
        artifact["memory_replan_revision_rate"]={"numerator":artifact["memory_success_counts"]["second_revision"],"denominator":len(memory),"rate":artifact["memory_success_counts"]["second_revision"]/len(memory) if memory else None}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding="utf-8")
    for index in range(args.runs):
        await reset(); before=await formal()
        row=await one(FIRST); row.update(attempt=index+1, formal_unchanged=(before==await formal()))
        artifact["normal_runs"].append(row); save()
        print(json.dumps({"group":"normal","attempt":index+1,"status":row["status"],"category":row["failure_category"]}),flush=True)
    for index in range(args.runs):
        await reset(); before=await formal()
        first=await one(FIRST); row={"attempt":index+1,"first":first,"feedback_persisted":False}
        if first["revision_produced"]:
            async with session_factory() as session:
                rejected=await reject_revision(session, __import__('uuid').UUID(first["revision_id"]), reason_code="too_rushed",reason_text=FEEDBACK)
                row["feedback_persisted"]=rejected.rejection_reason_code=="too_rushed" and rejected.rejection_reason_text==FEEDBACK
            second=await one(SECOND); row["second"]=second
            row["memory_retrieved"]=first["revision_id"] in second["memory_source_revision_ids"] and second["memory_visible_to_planner"]
        row["formal_unchanged"]=before==await formal()
        artifact["memory_replan_runs"].append(row); save()
        print(json.dumps({"group":"memory","attempt":index+1,"first":first["status"],"second":row.get("second",{}).get("status"),"memory":row.get("memory_retrieved")}),flush=True)
    counts=artifact["memory_success_counts"]
    complete=(args.runs==10 and artifact["normal_summary"]["success_counts"]["revision_produced"]>=9
        and counts["first_revision"]>=9 and counts["memory_retrieval"]==counts["memory_eligible_denominator"]
        and counts["second_parse"]>=8 and counts["second_revision"]>=8
        and all(row["formal_unchanged"] for row in artifact["normal_runs"]+artifact["memory_replan_runs"]))
    artifact["benchmark_gate_passed"]=complete
    artifact["completed_at"]=datetime.now(UTC).isoformat(); save()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs",type=int,default=10)
    parser.add_argument("--output",type=Path,default=Path("evals/results/agent_reliability/reliability_20260928.json"))
    asyncio.run(main(parser.parse_args()))
