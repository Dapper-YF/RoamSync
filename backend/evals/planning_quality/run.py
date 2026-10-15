"""Single-variable quality observations using the existing production Planner/Graph.

Deterministic mode has no DB/network. Graph modes require a positively identified
throwaway DB; they stop at approval and never call Accept/Reject or production UI.
Real mode means real LLM + frozen synthetic facts/routes, NOT real live providers.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import os
import sys
import uuid
from dataclasses import replace
from datetime import date, datetime, UTC, time
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import AsyncMock, patch

FIXTURE = Path(__file__).with_name("fixtures.json")
ROOT = FIXTURE.parents[3]


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def cases():
    fixture = load_fixture()
    return [{"pair": pair["id"], "variant": variant["id"], "variable": pair["variable"],
             "expectation": pair["expectation"], **variant} for pair in fixture["pairs"] for variant in pair["variants"]]


def isolation_target(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in {"postgresql+psycopg", "postgresql"} or parsed.hostname != "127.0.0.1"
        or parsed.username != "roamsync_phase0_eval" or parsed.path != "/roamsync_phase0_eval"
        or parsed.port in {None, 1, 5432, 54329, 55432}
        or os.environ.get("ROAMSYNC_PHASE0_ISOLATED") != "1"):
        raise ValueError("Refusing graph evaluation: only the dedicated loopback Phase 0 DB is allowed")
    return parsed.port


def verify_database():
    url = os.environ.get("DATABASE_URL", "")
    isolation_target(url)
    checkpoint = os.environ.get("LANGGRAPH_DATABASE_URL", "")
    if checkpoint != url.replace("postgresql+psycopg://", "postgresql://", 1):
        raise ValueError("checkpoint and business DB must be the same isolated target")
    import psycopg
    with psycopg.connect(checkpoint) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            row = conn.execute("SELECT owner_token FROM phase0_eval_marker").fetchone()
            if not row or row[0] != os.environ.get("ROAMSYNC_PHASE0_OWNER") or not row[0]:
                raise ValueError("isolated DB ownership marker does not match")


def identity(case_id, kind):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "roamsync-phase0:" + case_id + ":" + kind))


def facts_for(case):
    target = case.get("date", load_fixture()["base_date"])
    return {"status": "available", "fixture_only": True,
        "weather": {"status": "available", "provider": "synthetic_open_meteo", "queried_at": "2026-10-11T00:00:00Z",
            "payload": {"hourly": {"time": [target + "T10:00"], "temperature_2m": [22],
                "precipitation_probability": [case.get("rain", 0)], "weather_code": [case.get("weather_code", 0)]}}},
        "search": {"status": "available", "provider": "synthetic_tavily", "queried_at": "2026-10-11T00:00:00Z",
            "payload": {"results": [{"title": "评测节庆广场活动", "url": "https://example.org/phase0/festival",
                "content": "评测节庆广场举行文化节活动；活动是否有效应依据日期元数据核对。",
                "published_date": case.get("published_date", "2026-10-10"),
                "effective_from": case.get("effective_from", "2026-11-01"),
                "effective_until": case.get("effective_until", "2026-11-02")}]}}}


def state_for(case, case_id="deterministic"):
    fixture = load_fixture()
    target = case.get("date", fixture["base_date"])
    preferences = {"pace": "balanced", "interest_categories": case.get("interests", ["culture"]),
        "transport_modes": ["walk", "transit"], "daily_start_time": "09:00:00", "daily_end_time": "18:00:00",
        "meal_preferences": "", "avoid_categories": [], "max_walking_minutes": 90, "free_text_requirements": ""}
    candidates = [{"id": identity(case_id, p["key"]), "name": p["name"], "category": p["category"],
        "neighborhood": "controlled-zone", "description": p["description"], "longitude": 120.15 + i * .001,
        "latitude": 30.27, "suggested_duration_minutes": 60, "estimated_cost_fen": 1000,
        "rating": p["rating"], "tags": [p["exposure"], "synthetic_fixture"],
        "source": {"id": identity(case_id, "source-" + p["key"]), "provider": "Phase0 synthetic POI", "confidence": "low"}}
        for i, p in enumerate(fixture["places"])]
    return {"run_id": identity(case_id, "run"), "trip_id": identity(case_id, "trip"),
        "run_type": "initial_plan", "user_request": fixture["request"],
        "intent_resolution": {"request": {"intent": {"intent_type": "create_plan", "source_text": fixture["request"],
            "protected_activity_ids": [], "requested_place_queries": []}}},
        "planning_context": {"trip": {"destination": "杭州市", "start_date": target, "end_date": target,
            "accommodation": "controlled-zone", "total_budget_fen": 100000, "daily_budget_fen": 100000,
            "currency": "CNY", "timezone": "Asia/Shanghai"}, "preferences": preferences,
            "days": [{"id": identity(case_id, "day"), "date": target, "label": "第一天", "theme": "",
                      "route_mode": "transit", "activities": [], "route_legs": []}],
            "candidates": candidates, "external_facts": facts_for(case)}}


def stable(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def deterministic():
    from app.config import Settings
    from app.external_facts import SearchFact
    from app.openai_planner import build_planner_input
    from app.planner_entity_resolution import PlannerEntityBindings
    from app.planning_graph import _collect_external_facts
    from app.destination_research import search_results
    rows = []
    for case in cases():
        state = state_for(case)
        context = state["planning_context"]
        prompt, allowed, _ = build_planner_input(state, max_candidates=40)
        wire = PlannerEntityBindings(prompt, allowed).prompt(prompt)
        search = AsyncMock(return_value=SearchFact("tavily", "2026-10-11T00:00:00Z", "fixture", facts_for(case)["search"]["payload"]))
        # The real collector is exercised with network ports replaced; no DB.
        with patch("app.planning_graph.get_settings", return_value=Settings(_env_file=None, app_env="development", tavily_api_key="fixture")), \
             patch("app.planning_graph.search_tavily", search):
            await _collect_external_facts({"trip": context["trip"], "preferences": context["preferences"], "candidates": []}, load_fixture()["request"])
        changed_history = copy.deepcopy(state)
        changed_history["conversation"] = [{"user": "explicit historical preference"}]
        changed_history["planning_context"]["planning_brief"] = {"confirmed_preferences": [{"text": "explicit preference", "source_turn_id": "fixture-turn"}]}
        other, _, _ = build_planner_input(changed_history, max_candidates=40)
        rows.append({"pair": case["pair"], "variant": case["variant"], "variable": case["variable"],
            "expectation": case["expectation"], "input": wire, "input_sha256": stable(wire),
            "candidate_order": [p["name"] for p in wire["new_place_candidates"]],
            "discovery_queries": [call.kwargs["query"] for call in search.call_args_list],
            "research_source_projection": search_results(facts_for(case)),
            "brief_and_raw_history_directly_change_prompt": prompt != other,
            "final_generation": None, "validator": None, "decision_basis": "not_generated"})
    pairs = []
    for pair in load_fixture()["pairs"]:
        a, b = [r for r in rows if r["pair"] == pair["id"]]
        pairs.append({"pair": pair["id"], "input_changed": a["input_sha256"] != b["input_sha256"],
            "candidate_order_changed": a["candidate_order"] != b["candidate_order"],
            "discovery_query_changed": a["discovery_queries"] != b["discovery_queries"],
            "research_source_projection_changed": a["research_source_projection"] != b["research_source_projection"],
            "final_generation_changed": None, "decision_basis_changed": None,
            "quality_verdict": "not_measured_by_deterministic_input_test"})
    return {"mode": "deterministic", "rows": rows, "pairs": pairs, "real_model_calls": 0}


async def seed_case(case, case_id):
    from app.database import Trip, TripPreferences, DayPlan, PlaceCandidate, SourceRecord, session_factory
    state = state_for(case, case_id)
    ctx = state["planning_context"]
    trip_id = uuid.UUID(state["trip_id"])
    async with session_factory() as db:
        db.add(Trip(id=trip_id, title="Phase0 isolated " + case_id, **{k: v for k, v in ctx["trip"].items() if k not in {"start_date", "end_date"}},
                    start_date=date.fromisoformat(ctx["trip"]["start_date"]), end_date=date.fromisoformat(ctx["trip"]["end_date"])))
        await db.flush()
        prefs = ctx["preferences"]
        db.add(TripPreferences(trip_id=trip_id, **{k: v for k, v in prefs.items() if k not in {"daily_start_time", "daily_end_time"}},
                    daily_start_time=time(9), daily_end_time=time(18)))
        db.add(DayPlan(id=uuid.UUID(ctx["days"][0]["id"]), trip_id=trip_id, date=date.fromisoformat(ctx["trip"]["start_date"]),
                       position=0, label="第一天", theme="", route_mode="transit"))
        for item in ctx["candidates"]:
            db.add(SourceRecord(id=uuid.UUID(item["source"]["id"]), trip_id=trip_id, title=item["name"],
                url="https://example.org/phase0/" + item["name"], provider="Phase0 synthetic POI", confidence="low",
                queried_at=datetime(2026, 10, 11, tzinfo=UTC)))
        await db.flush()
        for i, item in enumerate(ctx["candidates"]):
            db.add(PlaceCandidate(id=uuid.UUID(item["id"]), trip_id=trip_id, source_record_id=uuid.UUID(item["source"]["id"]),
                slug="phase0-" + str(i), **{k: v for k, v in item.items() if k not in {"id", "source"}}))
        await db.commit()
    return state


async def formal_fingerprint(trip_id):
    from sqlalchemy import select
    from app.database import Trip, Activity, DayPlan, RouteLeg, session_factory
    async with session_factory() as db:
        trip = await db.get(Trip, trip_id)
        days = list((await db.scalars(select(DayPlan).where(DayPlan.trip_id == trip_id).order_by(DayPlan.position))).all())
        activities = list((await db.scalars(select(Activity).join(DayPlan).where(DayPlan.trip_id == trip_id))).all())
        routes = list((await db.scalars(select(RouteLeg).join(DayPlan).where(DayPlan.trip_id == trip_id))).all())
        return stable({"version": trip.version, "days": [(str(d.id), str(d.date), d.position) for d in days],
            "activities": sorted((str(a.id), a.version, str(a.scheduled_time), a.duration_minutes) for a in activities),
            "routes": sorted(str(r.id) for r in routes)})


class ObservedPlanner:
    """Observation adapter around the existing Planner, not an alternate planner."""
    def __init__(self, settings, mode):
        from app.openai_planner import OpenAIResponsesPlanner
        self.mode, self.inputs, self.outputs, self.calls = mode, [], [], []
        self.inner = OpenAIResponsesPlanner(settings, client=SimpleNamespace() if mode == "mock" else None)
        original = self.inner._create_response

        async def response(prompt, schema):
            call = {"input_sha256": stable(prompt), "schema_sha256": stable(schema),
                    "task": prompt.get("task"), "prior_error": bool(prompt.get("output_error"))}
            self.calls.append(call)
            if mode == "real":
                started = perf_counter()
                try:
                    result = await original(prompt, schema)
                    call["completion_status"] = result.status
                    return result
                except Exception as exc:
                    chain, cursor = [], exc
                    while cursor is not None and len(chain) < 8:
                        chain.append(type(cursor).__name__)
                        cursor = cursor.__cause__
                    call["error_chain"] = chain
                    raise
                finally:
                    call["elapsed_seconds"] = round(perf_counter() - started, 3)
            # Fixed outputs deliberately ignore every A/B variable. Never score as intelligence.
            refs = prompt["allowed_candidate_refs"][-2:]
            output = {"explanation": "受控固定输出，仅验证原有规划和确认边界，不证明推荐质量。", "activities": [
                {"source": "candidate", "candidate_ref": ref, "day_date": prompt["allowed_dates"][0],
                 "planned_start_time": f"{10 + i * 2}:00", "duration_minutes": 60,
                 "transport_mode_to_here": "transit", "reason": "受控反例：安排露天体验及资讯中的文化节，仅测试现有验证边界，不是真实决策证据。"}
                for i, ref in enumerate(refs)]}
            return SimpleNamespace(status="completed", output_text=json.dumps(output, ensure_ascii=False),
                usage=SimpleNamespace(total_tokens=0), model="phase0-fixed-response")
        self.inner._create_response = response

    async def generate(self, state):
        from app.openai_planner import build_planner_input
        from app.planner_entity_resolution import PlannerEntityBindings
        prompt, allowed, _ = build_planner_input(state, max_candidates=self.inner.max_candidates)
        wire = PlannerEntityBindings(prompt, allowed).prompt(prompt)
        self.inputs.append(copy.deepcopy(wire))
        result = await self.inner.generate(state)
        self.outputs.append(result.snapshot.model_dump(mode="json"))
        return replace(result, provider="mock", model="phase0-fixed-response") if self.mode == "mock" else result


async def graph_case(case, repetition, batch, settings, mode):
    from langgraph.checkpoint.memory import InMemorySaver
    from sqlalchemy import select
    from app.database import PlanningRun, PlanRevision, session_factory
    from app.planning_graph import build_planning_graph
    from app.planning_run_repository import create_planning_run
    from app.planning_graph_runtime import invoke_compiled_graph
    from app.schemas import PlanningRunCreate
    from evals.travel_benchmark import BenchmarkTrace
    case_id = f"{batch}-{case['pair']}-{case['variant']}-{repetition}"
    state = await seed_case(case, case_id)
    trip_id = uuid.UUID(state["trip_id"])
    before = await formal_fingerprint(trip_id)
    planner = ObservedPlanner(settings, mode)
    trace = BenchmarkTrace(case_id)
    row = {"pair": case["pair"], "variant": case["variant"], "repetition": repetition, "mode": mode,
        "fact_origin": "frozen_synthetic", "route_origin": "frozen_synthetic", "research_discovery": "not_executed_controlled_pool",
        "brief": {"available_at_router": "not_exercised", "planner_field_present": False}, "expected": case["expectation"]}
    if mode == "mock":
        row["mock_output_policy"] = "fixed_last_two_negative_control; intentionally ignores A/B variables"
    async def route(*args, **kwargs):
        return SimpleNamespace(distance_meters=1000, duration_minutes=15, provider="Phase0 synthetic route",
                               is_estimated=True, path=[], alternatives=[])
    try:
        async with session_factory() as db:
            run = await create_planning_run(db, trip_id, PlanningRunCreate(run_type="initial_plan", user_request=state["user_request"]))
        trace.run_id = str(run.id)
        graph = build_planning_graph(InMemorySaver(), provider=planner, trace_observer=trace)
        with patch("app.planning_graph._collect_external_facts", AsyncMock(return_value=facts_for(case))), \
             patch("app.candidate_route_service.resolve_route_result", route):
            async with asyncio.timeout(settings.agent_run_timeout_seconds):
                result = await invoke_compiled_graph(graph, run)
        async with session_factory() as db:
            revision = await db.scalar(select(PlanRevision).where(PlanRevision.planning_run_id == run.id))
            saved = await db.get(PlanningRun, run.id)
            row.update(status=saved.status, interrupt=result.pending_interrupt,
                revision_status=revision.status if revision else None,
                validator=revision.validation_result if revision else None,
                selected=revision.proposed_snapshot if revision else None,
                candidate_diff=revision.difference_summary if revision else None,
                formal_mutation_authorized=False)
    except Exception as exc:
        row.update(status="evaluation_failed", error_type=type(exc).__name__,
                   error_code=getattr(exc, "code", type(exc).__name__))
    finally:
        if mode == "real":
            await planner.inner.client.close()
    trace.finish()
    ids = {item["id"]: load_fixture()["places"][i]["key"] for i, item in enumerate(state["planning_context"]["candidates"])}
    selected = (row.get("selected") or {}).get("activities", [])
    selected_keys = [ids.get(a["place_candidate_id"], "unknown") for a in selected]
    row.update(planner_inputs=planner.inputs, planner_generations=planner.outputs, provider_attempts=planner.calls,
        candidate_identity={key: {"fixture_key": value, "provider_place_id": "synthetic-phase0-" + value,
            "identity_origin": "synthetic; not a real AMap lookup"} for key, value in ids.items()}, candidate_pool=state["planning_context"]["candidates"],
        selected_keys=selected_keys, excluded_keys=sorted(set(ids.values()) - set(selected_keys)),
        exclusion_reasons={k: "missing: production Planner has no structured per-alternative exclusion output" for k in set(ids.values()) - set(selected_keys)},
        formal_state_unchanged=before == await formal_fingerprint(trip_id), trace=trace.to_dict(),
        decision_basis_status=((row.get("candidate_diff") or {}).get("decision_summary") or {}).get("status", "missing"))
    labels = {p["key"]: p for p in load_fixture()["places"]}
    row["quality_observations"] = {
        "interest_match_share": sum(labels[k]["category"] in case.get("interests", ["culture"]) for k in selected_keys) / len(selected_keys) if selected_keys else None,
        "outdoor_share": sum(labels[k]["exposure"] == "outdoor" for k in selected_keys) / len(selected_keys) if selected_keys else None,
        "festival_venue_selected": "festival" in selected_keys,
        "event_claim_validity": "requires_manual_claim_review; venue selection alone is not an event claim",
        "temporal_evidence": facts_for(case)["search"]["payload"]["results"][0],
        "verified_rationale": row["decision_basis_status"] == "validated"}
    row["mechanical_pass"] = bool(row.get("status") == "awaiting_confirmation" and row.get("revision_status") == "pending"
        and (row.get("validator") or {}).get("valid") is True and row["formal_state_unchanged"]
        and (row.get("interrupt") or {}).get("kind") == "approval")
    return row


def compare_generations(rows, mode, repetitions=1):
    results = []
    for pair in load_fixture()["pairs"]:
        members = [r for r in rows if r["pair"] == pair["id"]]
        groups = {v["id"]: [r for r in members if r["variant"] == v["id"]] for v in pair["variants"]}
        fingerprints = {key: [stable(r.get("selected_keys", [])) for r in group] for key, group in groups.items()}
        selections = {key: [r.get("selected_keys", []) for r in group] for key, group in groups.items()}
        def observations(group):
            result = []
            for row in group:
                prompt = (row.get("planner_inputs") or [{}])[0]
                selected = (row.get("selected") or {}).get("activities", [])
                result.append({"input": {"preferences": prompt.get("preferences"), "facts": prompt.get("external_facts"),
                                           "dates": prompt.get("allowed_dates")},
                    "order": [p["name"] for p in prompt.get("new_place_candidates", [])],
                    "generation": [(key, a.get("planned_start_time"), a.get("duration_minutes"), a.get("transport_mode_to_here"))
                                   for key, a in zip(row.get("selected_keys", []), selected)],
                    "reasons": [a.get("reason") for a in selected]})
            return result
        left, right = [observations(groups[v["id"]]) for v in pair["variants"]]
        both = bool(left and right)
        results.append({"pair": pair["id"], "selections": selections,
            "within_variant_unique_selections": {k: len(set(v)) for k, v in fingerprints.items()},
            "all_requested_repetitions_succeeded": all(len(group) == repetitions for group in groups.values()) and all(r.get("mechanical_pass") for r in members),
            "candidate_selection_changed": None if not all(groups.values()) else selections[pair["variants"][0]["id"]] != selections[pair["variants"][1]["id"]],
            "input_changed": None if not both else [r["input"] for r in left] != [r["input"] for r in right],
            "candidate_order_changed": None if not both else [r["order"] for r in left] != [r["order"] for r in right],
            "final_generation_changed": None if not both else [r["generation"] for r in left] != [r["generation"] for r in right],
            "visible_reasons_changed": None if not both else [r["reasons"] for r in left] != [r["reasons"] for r in right],
            "basis_statuses": [r.get("decision_basis_status") for r in members],
            "quality_verdict": "not_applicable_mock" if mode == "mock" else "requires_fact_and_goal_review_not_inferred_from_change_alone"})
    return results


async def execute(mode, repetitions, output):
    from evals.planning_quality.version_audit import source_manifest
    initial_manifest = source_manifest()
    report = {"schema": "planning-quality-phase0-v1", "fixture_sha256": stable(load_fixture()),
        "source_manifest": initial_manifest, "python": sys.version, "mode": mode,
        "requested_repetitions": repetitions, "ui_e2e": "not_executed", "complete": False}
    if mode == "deterministic":
        report.update(await deterministic())
    else:
        verify_database()
        from app.config import Settings
        from app.database import engine
        settings = Settings(_env_file=ROOT / ".env")
        settings = settings.model_copy(update={"planner_max_retries": 0, "planner_timeout_seconds": 90})
        if mode == "mock":
            settings = settings.model_copy(update={"planner_provider": "openai", "planner_model": "phase0-fixed-response", "planner_api_key": "fixture"})
            # Pydantic model_copy does not coerce SecretStr; use validated construction.
            settings = Settings(_env_file=None, **settings.model_dump())
        elif not settings.planner_api_key.get_secret_value() or not settings.planner_model:
            raise ValueError("real mode requires configured model credentials")
        report["model_parameters"] = {"provider": settings.planner_provider, "model": settings.planner_model,
            "reasoning_effort": settings.planner_reasoning_effort, "max_output_tokens": settings.planner_max_output_tokens,
            "transport_retries": 0, "format_repair_limit": 1, "graph_correction_limit": 1,
            "temperature": 1.0 if settings.planner_provider in {"glm", "bigmodel", "zhipu"} else "provider default",
            "top_p": 0.95 if settings.planner_provider in {"glm", "bigmodel", "zhipu"} else "provider default",
            "seed": "not exposed by existing Planner; no provider determinism claimed",
            "ledger_mode": settings.decision_ledger_validation_mode, "real_model_with_frozen_facts": mode == "real"}
        report["rows"] = []
        batch = uuid.uuid4().hex[:12]
        # Counterbalance pair order on alternate repetitions. Abort bounded batch on a provider failure.
        try:
            stop = False
            for rep in range(repetitions):
                sequence = cases()
                if rep % 2:
                    sequence = [c for pair in load_fixture()["pairs"] for c in reversed([x for x in cases() if x["pair"] == pair["id"]])]
                for case in sequence:
                    row = await graph_case(case, rep, batch, settings, mode)
                    report["rows"].append(row)
                    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps({k: row.get(k) for k in ("pair", "variant", "repetition", "status", "mechanical_pass", "error_code")}), flush=True)
                    if mode == "real" and row.get("error_code"):
                        stop = True
                        break
                if stop:
                    break
        finally:
            await engine.dispose()
        report["pairs"] = compare_generations(report["rows"], mode, repetitions)
        report["real_model_calls"] = sum(len(r["provider_attempts"]) for r in report["rows"]) if mode == "real" else 0
        report["requested_cases"] = 8 * repetitions
        report["completed_cases"] = len(report["rows"])
        report["attempted_cases"] = len(report["rows"])
        report["successful_cases"] = sum(bool(r["mechanical_pass"]) for r in report["rows"])
        report["blocked_unexecuted_cases"] = report["requested_cases"] - report["completed_cases"]
    report["changed_source_files_during_run"] = [k for k in initial_manifest.keys() | source_manifest().keys()
        if initial_manifest.get(k) != source_manifest().get(k)]
    report["eval_manifest"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [*Path(__file__).parent.glob("*.py"), FIXTURE]}
    report["complete"] = (not report["changed_source_files_during_run"] and
        (mode == "deterministic" or len(report["rows"]) == 8 * repetitions and all(r["mechanical_pass"] for r in report["rows"])))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("deterministic", "mock", "real"), default="deterministic")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 5 or args.mode == "real" and args.repetitions < 3:
        parser.error("repetitions must be 1..5; real comparisons require at least 3")
    if args.mode == "deterministic":
        os.environ.update(APP_ENV="test", DATABASE_URL="postgresql+psycopg://audit:audit@127.0.0.1:1/audit")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(execute(args.mode, args.repetitions, args.output),
                         loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
    print(json.dumps({"mode": report["mode"], "complete": report["complete"], "real_model_calls": report["real_model_calls"]}))
    raise SystemExit(0 if report["complete"] else 1)


if __name__ == "__main__":
    main()
