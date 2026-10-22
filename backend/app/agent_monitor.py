"""Read-only projection of persisted observations, checkpoints and revisions."""
import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_observation import clean, project_context, project_state, project_facts
from app.config import get_settings
from app.database import AssistantSession, PlanningRun, PlanRevision, Trip, get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agent-monitor", tags=["agent-monitor"])


@router.get("/sessions/{session_id}/messages/{message_id}")
async def dialogue_trace(session_id: uuid.UUID, message_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    from app.dialogue_observation import snapshot
    live = snapshot(session_id, message_id)
    row = await db.get(AssistantSession, session_id)
    message = next((m for m in row.messages if m.get("id") == str(message_id)), None) if row else None
    if message and message.get("execution_summary"):
        return {**live, "execution_summary": message["execution_summary"], "source": "persisted_session_and_process_local"}
    return live

STAGES = [("message", "User Message"), ("intent", "Intent Understanding"),
          ("goal", "Goal Extraction"), ("context", "Context Building"),
          ("research", "Destination Research"), ("poi", "Place Resolution"),
          ("planner", "Planner / Candidate"), ("route", "Route Enrichment"),
          ("validator", "Deterministic Validation"), ("revision", "Plan Revision"),
          ("user_decision", "Awaiting User Decision")]
PROGRESS_STAGE = {"intent": "intent", "web_search": "research", "focused_search": "research",
                  "weather": "research", "research_model": "research", "map_places": "poi",
                  "planning": "planner", "routes": "route", "validation": "validator", "answer_model": "intent"}
TERMINAL = {"failed", "accepted", "rejected", "answered", "cancelled", "awaiting_confirmation", "awaiting_clarification"}


def iso(value):
    return value.isoformat() if value else None


def overview(run, trip):
    end = run.completed_at
    # Planning latency excludes the human approval wait, when its boundary is observed.
    return clean({"id": str(run.id), "trip_id": str(run.trip_id), "trip_title": trip.title,
                  "status": run.status, "run_type": run.run_type, "base_trip_version": run.base_trip_version,
                  "current_trip_version": trip.version, "model": run.model_name, "provider": run.model_provider,
                  "created_at": iso(run.created_at), "started_at": iso(run.started_at), "completed_at": iso(end),
                  "intent": ((run.intent_resolution or {}).get("request", {}).get("intent", {}).get("intent_type")),
                  "error_code": run.error_code})


async def checkpoint_state(run_id):
    async def load():
        async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
            saved = await saver.aget_tuple({"configurable": {"thread_id": str(run_id)}})
            return (saved.checkpoint.get("channel_values", {}) if saved else {}), bool(saved)
    try:
        return await asyncio.wait_for(load(), timeout=2)
    except Exception:
        logger.warning("Monitor checkpoint unavailable")
        return {}, False


def context_items(context, summary):
    decision = context.get("decision_context") or {}
    execution = decision.get("execution_context") or context.get("execution_recovery") or {}
    days = context.get("days")
    activities = [item for day in days or [] for item in day.get("activities", [])]
    memory = decision.get("decision_memory")
    return [{"label": label, "available": value is not None, "data": clean(value)} for label, value in (
        ("Formal Itinerary", days), ("Trip Version", context.get("trip", {}).get("version")),
        ("Current Execution State", execution or None), ("User Preferences", context.get("preferences")),
        ("Must-do Activities", [item for item in activities if item.get("importance") == "must_do"] if days is not None else None),
        ("Locked Activities", [item for item in activities if item.get("schedule_locked")] if days is not None else None),
        ("Travel Events", execution.get("recent_events", execution.get("travel_events"))),
        ("Navigation ETA", execution.get("current_eta")),
        ("Slack", execution.get("minimum_downstream_slack_minutes", execution.get("minimum_slack_minutes"))),
        ("Previous Revision / Reject Feedback", memory if memory is not None else (summary.get("decision_memory") or None)),
        ("Research Candidates", context.get("candidates")),
        ("Route Facts", context.get("formal_route_facts")),
        ("Decision Context Provenance", decision.get("provenance", summary.get("provenance"))),
    )]


def validation_checks(result, context, goals_result):
    errors = result.get("errors") or []
    codes = {
        "Time Windows": {"outside_daily_window", "date_outside_trip", "required_days_missing"},
        "Activity Overlap": {"time_overlap"},
        "Protected Activities": {"execution_activity_changed", "activity_must_do_removed", "activity_cannot_be_skipped", "activity_minimum_duration_violated"},
        "Route Feasibility": {"route_travel_time_conflict", "candidate_route_set_mismatch", "candidate_route_structure_mismatch", "route_unavailable"},
        "Budget Constraint": {"daily_budget_exceeded", "total_budget_exceeded", "total_budget_with_actual_spend_exceeded", "intent_budget_increase_forbidden"},
    }
    checks = []
    for label, group in codes.items():
        failures = [item for item in errors if item.get("code") in group]
        status = "FAIL" if failures else "PASS" if result.get("valid") is True else "unavailable"
        if label == "Budget Constraint" and context.get("trip") and context["trip"].get("total_budget_fen") is None:
            status = "N/A"
        checks.append({"label": label, "status": status, "facts": clean(failures)})
    for item in goals_result.get("results") or []:
        checks.append({"label": item.get("goal", "Goal"), "status": item.get("status", "unavailable"), "facts": clean(item)})
    return checks


def build_trace(run, trip, revision=None, checkpoint=None, checkpoint_available=False):
    """No current-trip context reconstruction: replay must use run-time facts."""
    observations = clean((run.progress or {}).get("events") or [])
    observations.sort(key=lambda event: event.get("sequence", 0))
    state = {}
    for event in observations:
        if event.get("status") == "completed" and event.get("stage") in {"intent", "planner", "validator", "goal_check", "revision"}:
            state.update(event.get("data") or {})
    state.update(project_state(checkpoint or {}))
    before = revision.before_snapshot if revision else {}
    difference = revision.difference_summary if revision else {}
    context = project_context(before or state.get("planning_context") or {})
    candidate = clean(revision.proposed_snapshot if revision else state.get("proposed_snapshot") or {})
    goals = clean(difference.get("planning_goals") or state.get("planning_goals") or context.get("planning_goals") or {})
    validation = clean(revision.validation_result if revision else state.get("validation_result") or {})
    goal_result = clean(difference.get("goal_satisfaction") or state.get("goal_satisfaction") or {})
    resolution = clean(state.get("intent_resolution") or run.intent_resolution or {})
    research = clean(context.get("destination_research") or {})
    decision = clean(difference.get("decision_summary") or state.get("decision_summary") or {})
    summary = clean((run.trigger_snapshot or {}).get("decision_context_summary") or {})
    # Partial observed Goal/Context survive a checkpoint/provider failure.
    for event in observations:
        if event["stage"] == "goal" and not goals:
            goals = event["data"]
        if event["stage"] == "context" and not context:
            context = event["data"]
    facts = clean(state.get("external_facts")) if state.get("external_facts") else project_facts(before.get("external_facts", {}))
    items = context_items(context, summary)
    names = {item.get("id"): item.get("name") for item in context.get("candidates", [])}
    names.update({item.get("place_id"): item.get("display_name") for day in context.get("days", []) for item in day.get("activities", [])})
    candidate = {**candidate, "activities": [{**item, "display_name": names.get(item.get("place_candidate_id"))} for item in candidate.get("activities", [])]}
    route_legs = candidate.get("route_legs") or []
    route_events = [event for event in observations if event["stage"] == "route" and event["status"] == "completed"]
    if not route_legs and route_events:
        route_legs = route_events[-1]["data"].get("route_legs", [])
    route_names = {item.get("candidate_id"): item.get("display_name") for item in candidate.get("activities", [])}
    route_names.update({f"activity:{item.get('id')}": item.get("display_name") for day in context.get("days", []) for item in day.get("activities", [])})
    route_legs = [{**leg, "from_name": route_names.get(leg.get("from_activity_ref")), "to_name": route_names.get(leg.get("to_activity_ref"))} for leg in route_legs]
    route_choice = resolution.get("policy_decision", {}).get("route")
    research_decisions = [event["data"] for event in observations if event["stage"] == "research_decision"]
    skipped_research = bool(research_decisions and not research_decisions[-1].get("destination_research_required")) or facts.get("search", {}).get("status") == "not_required"
    stage_data = {
        "message": {"message": run.user_request, "received_at": iso(run.created_at), "entry_point": run.entry_point, "current_activity_id": str(run.selected_activity_id) if run.selected_activity_id else None},
        "intent": resolution,
        "goal": goals,
        "context": {"items": items, "available_count": sum(item["available"] for item in items), "context_summary": summary},
        "research": {"research": research, "external_facts": facts},
        "poi": {"places": research.get("places", {})},
        "planner": {"candidate": candidate, "decision_summary": decision, "goals": goals},
        "route": {"route_legs": route_legs},
        "validator": {"validation": validation, "checks": validation_checks(validation, context, goal_result), "goal_satisfaction": goal_result},
        "revision": {"id": str(revision.id), "number": revision.revision_number, "status": revision.status,
                     "before": context.get("days", []), "proposed": candidate, "difference": clean(difference), "change_summary": revision.reason} if revision else {},
        "user_decision": {"status": run.status, "revision_id": str(revision.id) if revision else None,
                          "decided_at": iso(revision.decided_at) if revision else None,
                          "base_trip_version": run.base_trip_version,
                          "accepted_trip_version": run.base_trip_version + 1 if revision and revision.status == "accepted" else None,
                          "feedback_persisted": bool(revision and (revision.rejection_reason_code or revision.rejection_reason_text)),
                          "feedback": clean({"reason_code": revision.rejection_reason_code, "reason_text": revision.rejection_reason_text}) if revision else None,
                          "clarification": clean(run.pending_interrupt) if run.status == "awaiting_clarification" else None},
    }
    evidence = {"message": True, "intent": bool(resolution), "goal": bool(goals), "context": bool(context or summary),
                "research": bool(research), "poi": bool(research.get("places")), "planner": bool(candidate.get("activities")),
                "route": bool(route_legs), "validator": bool(validation), "revision": bool(revision),
                "user_decision": run.status in {"accepted", "rejected"}}
    progress_stage = PROGRESS_STAGE.get((run.progress or {}).get("stage"))
    failures = [event for event in observations if event["status"] == "failed"]
    specific_failures = [event for event in failures if event["stage"] in {"search", "weather", "research", "poi", "planner", "route", "goal_check"}]
    failed_stage = ((specific_failures or failures)[-1]["stage"] if failures else progress_stage) if run.status == "failed" else None
    if run.status == "failed" and run.error_code in {"goal_constraints_unsatisfied", "planner_constraints_unsatisfied", "decision_context_invalid"}:
        failed_stage = "validator"
    if failed_stage in {"search", "weather"}:
        failed_stage = "research"
    if failed_stage == "goal_check":
        failed_stage = "validator"
    stages = []
    for stage, title in STAGES:
        events = [event for event in observations if event["stage"] == stage]
        last = events[-1] if events else None
        status = last["status"] if last else "completed" if evidence[stage] else "pending" if run.status not in TERMINAL else "unavailable"
        if stage in {"research", "poi"} and skipped_research and not events and not evidence[stage]:
            status = "skipped"
        if route_choice == "answer" and stage in {"planner", "route", "validator", "revision", "user_decision"}:
            status = "skipped"
        if run.status not in TERMINAL and stage == progress_stage and not (last and last["status"] == "completed"):
            status = "running"
        if run.status == "failed" and stage == failed_stage:
            status = "failed"
        elif run.status in TERMINAL and status == "running":
            status = "unavailable"
        if stage == "user_decision" and run.status in {"awaiting_confirmation", "awaiting_clarification"}:
            status = "running"
        if stage == "validator" and validation.get("valid") is False:
            status = "failed"
        data = stage_data[stage]
        if stage == failed_stage:
            data = {**data, "error": {"code": run.error_code, "message": clean(run.error_message), "details": clean(run.error_details)}}
        starts = [event for event in events if event["status"] == "running"]
        stages.append({"id": stage, "title": title, "status": status,
                       "started_at": starts[0]["at"] if starts else iso(run.created_at) if stage == "message" else None,
                       "completed_at": last["at"] if last and last["status"] in {"completed", "failed"} else iso(revision.created_at) if stage == "revision" and revision else None,
                       "duration_ms": last.get("duration_ms") if last else None, "attempts": len(starts),
                       "source": "progress.events" if events else "run" if stage == "user_decision" and run.status in {"awaiting_confirmation", "awaiting_clarification"} else "revision / checkpoint / run" if evidence[stage] else "execution decision" if status == "skipped" else "unavailable",
                       "data": data})
    # Each call is one real observed invocation, including a failed invocation.
    tools = []
    for event in observations:
        if event.get("stage") not in {"search", "weather", "research", "poi", "planner", "route"} or not event.get("call_id"):
            continue
        if event["status"] != "running":
            continue
        end = next((item for item in observations if item.get("call_id") == event["call_id"] and item["status"] != "running"), None)
        output = end["data"] if end else {}
        if event["stage"] == "planner":
            output = {"candidate_activity_count": len(output.get("proposed_snapshot", {}).get("activities", [])), "model": run.model_name, "provider": run.model_provider,
                      **({"error_code": output["error_code"]} if "error_code" in output else {})}
        elif event["stage"] == "route":
            output = {"route_count": len(output.get("route_legs", [])), "scope": "Enrichment including cache; individual HTTP calls not captured",
                      "route_legs": [{k: v for k, v in leg.items() if k not in {"path", "alternatives"}} for leg in output.get("route_legs", [])],
                      **({"error_code": output["error_code"]} if "error_code" in output else {})}
        tools.append({"id": event["call_id"], "stage": event["stage"], "provider": event.get("provider") or (run.model_provider if event["stage"] == "planner" else "AMap / cache" if event["stage"] == "route" else output.get("provider")),
                      "purpose": event.get("purpose"), "status": end["status"] if end else "unavailable" if run.status in TERMINAL else "running",
                      "started_at": event["at"], "duration_ms": end.get("duration_ms") if end else None,
                      "input": event["data"], "output": output})
    data = overview(run, trip)
    revision_at = iso(revision.created_at) if revision else None
    data["planning_finished_at"] = revision_at or iso(run.completed_at)
    open_calls = [event for event in observations if event["status"] == "running" and not any(
        other.get("call_id") == event.get("call_id") and other["status"] != "running" for other in observations)]
    active_stage = open_calls[-1]["stage"] if open_calls else progress_stage
    if active_stage in {"search", "weather"}: active_stage = "research"
    if run.status == "awaiting_confirmation": active_stage = "user_decision"
    return clean({"contract_version": 1, "run": data, "stages": stages, "tools": tools, "active_stage": active_stage,
                  "events": observations, "checkpoint_available": checkpoint_available,
                  "observations_truncated": bool((run.progress or {}).get("observations_truncated")),
                  "error": {"code": run.error_code, "message": clean(run.error_message), "stage": failed_stage} if run.error_code else None,
                  "limitations": ["Old runs have no per-stage latency or tool-call history."] if not observations else []})


@router.get("/runs")
async def recent_runs(trip_id: uuid.UUID | None = None, limit: int = Query(30, ge=1, le=100), db: AsyncSession = Depends(get_session)):
    query = select(PlanningRun, Trip).join(Trip, PlanningRun.trip_id == Trip.id)
    if trip_id:
        query = query.where(PlanningRun.trip_id == trip_id)
    rows = (await db.execute(query.order_by(PlanningRun.created_at.desc(), PlanningRun.id.desc()).limit(limit))).all()
    return [overview(run, trip) for run, trip in rows]


@router.get("/runs/{run_id}")
async def run_trace(run_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    row = (await db.execute(select(PlanningRun, Trip).join(Trip, PlanningRun.trip_id == Trip.id).where(PlanningRun.id == run_id))).first()
    if row is None:
        raise HTTPException(404, "planning run not found")
    run, trip = row
    revision = await db.scalar(select(PlanRevision).where(PlanRevision.planning_run_id == run_id, PlanRevision.trip_id == run.trip_id).order_by(PlanRevision.revision_number.desc()).limit(1))
    # New runs already have durable projections. Load checkpoint only for legacy/partial runs.
    checkpoint, available = await checkpoint_state(run_id) if not (run.progress or {}).get("events") else ({}, False)
    result = build_trace(run, trip, revision, checkpoint, available)
    # Exact persisted message-to-run link. Do not match free text or timestamps.
    # Query only sessions containing this run ID (historical JSON column).
    from sqlalchemy import cast, String
    sessions = (await db.scalars(select(AssistantSession).where(
        cast(AssistantSession.messages, String).contains(str(run_id))
    ).order_by(AssistantSession.created_at.asc()))).all()
    for session in sessions:
        for message in session.messages:
            if message.get("run_id") == str(run_id) and message.get("tool") in {"plan_trip", "query_trip"}:
                result["stages"][0]["data"].update(clean({"message": message.get("user"),
                    "planning_request": run.user_request, "assistant_session_id": str(session.id),
                    "goal_routing": message.get("goal_routing"), "planning_brief": message.get("planning_brief")}))
                return result
    return result
