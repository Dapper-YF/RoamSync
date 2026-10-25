import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol, TypedDict
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.candidate_route_service import enrich_candidate_routes
from app.candidate_schedule import repair_route_schedule
from app.database import PlanningRun, PlanRevision, TripPreferences, TripDisruptionEvent, session_factory
from app.config import get_settings
from app.external_facts import ExternalFactError, fetch_open_meteo, search_tavily
from app.plan_revision_service import accept_plan_revision, validate_candidate_plan
from app.planning_context import build_planning_context
from app.candidate_edit import candidate_base_from_context
from app.decision_context import assert_decision_context_invariants, build_decision_context
from app.candidate_decisions import collect_candidate_route_facts, compare_candidates, review_candidate_decisions, unsupported_decision_claims
from app.decision_memory import retrieve_decision_memory
from app.decision_ledger import reconcile_route_repair_ledger, validate_decision_ledger
from app.planning_explanation import describe_plan_changes
from app.planning_progress import report_progress
from app.planning_claim import assert_planning_claim
from app.agent_observation import observed, project_state, record
from app.maps_service import MapProviderError
from app.planning_errors import GoalConstraintsUnsatisfiedError, PlannerConstraintsUnsatisfiedError, PlannerNotConfiguredError
from app.planning_goals import can_repair_hard_goals, check_goal_satisfaction, extract_planning_goals, formal_route_facts, hard_goal_feedback
from app.planning_intent_service import SemanticIntentProvider, resolve_planning_intent, load_planning_intent_snapshot, resolve_planning_intent_snapshot
from app.planning_preparation import assert_planning_context_current
from app.planning_run_repository import reject_revision, save_plan_revision
from app.navigation.recovery import RecoveryActivity, enumerate_recovery_options
from app.schemas import (
    CandidatePlanSnapshot,
    GroundedIntent,
    GoalSatisfactionResult,
    PlanningIntent,
    PlanningGoals,
    PlanningIntentParseRequest,
    PlanningIntentResolution,
    PlanValidationIssue,
    SemanticIntentDraft,
)


class LegacyClarificationRestartRequired(ValueError):
    def __init__(self):
        super().__init__("legacy_clarification_restart_required")


async def _migrate_legacy_clarification(session, run, state, answer):
    """Recover only the exact pre-upgrade server checkpoint append format.

    The expanded request and its old operations are never authorization. Only
    the run's original request and a fully validated original prepared envelope
    may supply operations; supplements can fill the existing missing-day slot.
    The caller owns the claim-fenced transaction and commits both writes.
    """
    fail = LegacyClarificationRestartRequired
    expanded = state.get("user_request")
    count = state.get("clarification_count")
    separator = "\n用户补充："
    if (type(count) is not int or not 1 <= count < 2 or len(answer) > 4000
            or not isinstance(expanded, str)
            or not expanded.startswith(run.user_request + separator)):
        raise fail()
    supplements = expanded[len(run.user_request + separator):].split(separator)
    if (len(supplements) != count or any(not value.strip() or value != value.strip()
            or len(value) > 4000 for value in supplements)):
        raise fail()
    try:
        old = PlanningIntentResolution.model_validate(state.get("intent_resolution"))
    except (ValueError, TypeError):
        raise fail() from None
    request = old.request
    if (state.get("trip_id") != str(run.trip_id) or state.get("run_type") != run.run_type
            or request.trip_id != run.trip_id or request.user_request != expanded
            or request.intent.source_text != expanded or old.grounded_intent is None
            or old.grounded_intent.trip_id != run.trip_id or not old.requires_clarification
            or old.policy_decision is None or old.policy_decision.route != "clarify"):
        raise fail()
    for field in ("entry_point", "selected_day_id", "selected_activity_id"):
        value = getattr(run, field)
        if (getattr(request, field) != value
                or state.get(field, "trip_planner" if field == "entry_point" else None)
                != (str(value) if isinstance(value, uuid.UUID) else value)):
            raise fail()
    snapshot = dict(run.trigger_snapshot or {})
    stored_answers = snapshot.get("clarification_answers", [])
    if (not isinstance(stored_answers, list) or any(not isinstance(value, str)
            or not value.strip() or len(value) > 4000 for value in stored_answers)):
        raise fail()
    merged = [*supplements, answer]
    if stored_answers not in ([], supplements, merged):
        # API claim receipts contain only the newly accepted answer on old runs.
        # Check its binding before inserting legacy history ahead of it.
        from app.planning_claim import checkpoint_thread
        receipts = snapshot.get("clarification_receipts", [])
        receipt = receipts[-1] if isinstance(receipts, list) and receipts else None
        if (stored_answers != [answer] or not isinstance(receipt, dict)
                or receipt.get("answer") != answer
                or receipt.get("original_request") != run.user_request
                or receipt.get("checkpoint_thread") != checkpoint_thread(run)):
            raise fail()
    payload = PlanningIntentParseRequest(message=run.user_request, entry_point=run.entry_point,
        selected_day_id=run.selected_day_id, selected_activity_id=run.selected_activity_id)
    facts = await load_planning_intent_snapshot(session, run.trip_id, payload)
    prepared = None
    if "prepared_intent" in snapshot:
        # Reconstruct only the helper's validation input. Nothing from the old
        # expanded operations is handed to the new resolver or persisted.
        from app.planning_intent_service import restore_approved_planning_draft
        marker = snapshot["prepared_intent"]
        try:
            marker_draft = SemanticIntentDraft.model_validate(marker["draft"])
        except (ValueError, TypeError, KeyError):
            raise fail() from None
        probe = old.model_copy(update={
            "request": request.model_copy(update={"user_request":run.user_request}),
            "semantic_draft":marker_draft,
        })
        bound_run = SimpleNamespace(trip_id=run.trip_id, base_trip_version=run.base_trip_version,
            user_request=run.user_request, entry_point=run.entry_point,
            selected_day_id=run.selected_day_id, selected_activity_id=run.selected_activity_id,
            trigger_snapshot=snapshot, intent_resolution=probe.model_dump(mode="json"))
        prefs = await session.get(TripPreferences, run.trip_id)
        if prefs is None:
            raise fail()
        prepared = restore_approved_planning_draft(bound_run, run.trip_id, run.user_request,
            facts.trip.version, preferences_version=prefs.version)
        if prepared is None:
            raise fail()
    resolution = await resolve_planning_intent_snapshot(facts, payload,
        prepared_draft=prepared, clarification_answers=tuple(merged))
    run.intent_resolution = resolution.model_dump(mode="json")
    run.trigger_snapshot = {**snapshot, "clarification_answers":merged,
        "legacy_clarification_migrated":True}
    return {"user_request":run.user_request, "intent_resolution":run.intent_resolution,
        "clarification_count":len(merged)}


class PlanningGraphState(TypedDict, total=False):
    run_id: str
    trip_id: str
    user_request: str
    run_type: str
    entry_point: str
    selected_day_id: str | None
    selected_activity_id: str | None
    planning_context: dict
    intent_resolution: dict
    clarification_count: int
    proposed_snapshot: dict
    validation_result: dict
    planning_goals: dict
    goal_satisfaction: dict
    decision_summary: dict
    goal_review_count: int
    goal_feedback: list[dict]
    decision_review: dict
    review_count: int
    revision_id: str
    outcome: str
    schedule_adjustments: list[dict]
    required_day_dates: list[str]
    conversation: list[dict]


class DraftProvider(Protocol):
    async def generate(self, state: PlanningGraphState) -> "DraftGeneration": ...


class PlanningTraceObserver(Protocol):
    """Optional observer used by Stage 0 evaluation; it cannot alter the run."""

    def record(self, graph_step: str, kind: str, *, input_fact_refs: list[str] | tuple[str, ...] = (),
               data: dict[str, Any] | None = None, elapsed_ms: int | None = None) -> None: ...


@dataclass(frozen=True)
class DraftGeneration:
    snapshot: CandidatePlanSnapshot
    provider: str
    model: str
    token_usage: int


@dataclass(frozen=True)
class AnswerGeneration:
    text: str
    provider: str
    model: str
    token_usage: int


class UnavailableDraftProvider:
    async def generate(self, state: PlanningGraphState) -> DraftGeneration:
        raise PlannerNotConfiguredError("planner model provider is not configured")


async def _set_run_status(
    session: AsyncSession, run_id: uuid.UUID, status: str
) -> None:
    await assert_planning_claim(session, run_id)
    run = await session.get(PlanningRun, run_id)
    if run is None:
        raise RuntimeError("planning run disappeared")
    run.status = status
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    await session.commit()


def should_research_destinations(
    operations: set[str], intent: PlanningIntent, grounded: GroundedIntent | None,
) -> bool:
    """Research destinations only when the request needs place discovery.

    A same-day itinerary replan with no new place request already has formal
    places, sources and route facts in context. Sending that request through
    the destination-research model adds a slow, unrelated generation step.
    New-trip creation, add/replace operations, and replans with unresolved or
    explicit place requests keep the existing research path.
    """
    if operations & {"create_plan", "add_activity", "replace_activity"}:
        return True
    if "replan_trip" not in operations:
        return False
    return bool(
        intent.requested_place_queries
        or (grounded and (grounded.candidate_place_ids or grounded.unresolved_place_mentions))
    )


def build_planning_graph(
    checkpointer,
    provider: DraftProvider | None = None,
    semantic_provider: SemanticIntentProvider | None = None,
    candidate_researcher: Callable[[AsyncSession, uuid.UUID], Awaitable[None]] | None = None,
    destination_researcher=None,
    trace_observer: PlanningTraceObserver | None = None,
):
    draft_provider = provider or UnavailableDraftProvider()

    def trace(step: str, kind: str, *, refs: list[str] | tuple[str, ...] = (), data: dict | None = None) -> None:
        if trace_observer is not None:
            trace_observer.record(step, kind, input_fact_refs=refs, data=data)

    async def resolve_intent_node(state: PlanningGraphState) -> dict:
        trace("resolve_intent", "graph", refs=("user_request", "trip_id"))
        run_id = uuid.UUID(state["run_id"])
        trip_id = uuid.UUID(state["trip_id"])
        async with session_factory() as session:
            await _set_run_status(session, run_id, "researching")
            context = await build_planning_context(session, trip_id)
            context_data = context.model_dump(mode="json")
            trace("resolve_intent", "context", refs=("trip", "preferences", "days", "candidates", "budget", "execution_recovery"), data={
                "day_count": len(context_data.get("days", [])), "candidate_count": len(context_data.get("candidates", [])),
            })
            await report_progress("intent", "正在核对你的需求与调整范围…")
            from app.planning_intent_service import restore_current_turn_modification, restore_approved_planning_draft
            stored_run = await session.get(PlanningRun, run_id)
            expected_duration_changes = ((stored_run.intent_resolution or {}).get('grounded_intent') or {}).get('duration_changes', [])
            approved_draft = restore_approved_planning_draft(stored_run, trip_id,
                state["user_request"], context_data["trip"]["version"],
                preferences_version=context_data["preferences"]["version"])
            clarification_answers = tuple((stored_run.trigger_snapshot or {}).get("clarification_answers", []))
            if (approved_draft is None and stored_run is not None and
                ("prepared_intent" in (stored_run.trigger_snapshot or {}) or
                 (stored_run.intent_resolution or {}).get("semantic_draft", {}).get("parser_version") == "approved-operation-v2")):
                raise PlannerConstraintsUnsatisfiedError(["approved_operation_stale_or_invalid"])
            current_operation = restore_current_turn_modification(stored_run, trip_id,
                state["user_request"], context_data["trip"]["version"])
            active_semantic_provider = (None if (stored_run.trigger_snapshot or {}).get(
                "legacy_clarification_migrated") else current_operation or semantic_provider)
            intent_payload = PlanningIntentParseRequest(
                message=state["user_request"], entry_point=state.get("entry_point", "trip_planner"),
                selected_day_id=state.get("selected_day_id"),
                selected_activity_id=state.get("selected_activity_id"))
            intent_snapshot = await load_planning_intent_snapshot(session, trip_id, intent_payload)
        original_context = context_data
        resolution = await resolve_planning_intent_snapshot(
            intent_snapshot, intent_payload, semantic_provider=active_semantic_provider,
            prepared_draft=approved_draft,
            clarification_answers=clarification_answers,
            default_planning_intent="create_plan" if state["run_type"] == "initial_plan" else "replan_trip")
        if expected_duration_changes and (resolution.grounded_intent is None or
            [item.model_dump(mode='json') for item in resolution.grounded_intent.duration_changes] != expected_duration_changes):
            raise PlannerConstraintsUnsatisfiedError(['saved_duration_binding_stale'])
        trace("resolve_intent", "decision", refs=("user_request", "itinerary"), data={
            "route": resolution.policy_decision.route if resolution.policy_decision else None,
            "requires_clarification": resolution.requires_clarification,
        })
        operations = set(resolution.grounded_intent.operation_types) if resolution.grounded_intent else set()
        needs_destination_research = should_research_destinations(
            operations, resolution.request.intent, resolution.grounded_intent)
        await record("research_decision", "completed", data={"destination_research_required": needs_destination_research,
                     "destination_research_available": destination_researcher is not None})
        if approved_draft is not None and operations == {"create_plan"} and all(
                op.raw_text == state["user_request"] for op in approved_draft.operations):
            context_data["approved_requested_places"] = list(dict.fromkeys(
                name for op in approved_draft.operations for name in op.place_mentions))
        external_facts = await _collect_external_facts(
            context_data, state["user_request"], include_search=needs_destination_research)
        context_data["external_facts"] = external_facts
        trace("external_facts", "tool_result", refs=("trip", "preferences"), data={
            "search_status": external_facts.get("search", {}).get("status"),
            "weather_status": external_facts.get("weather", {}).get("status"),
        })
        await report_progress("intent", "网页检索已结束，正在核对你的需求与调整范围…")
        if destination_researcher is not None and needs_destination_research:
            async with session_factory() as session:
                research = await destination_researcher(session, trip_id,
                    context={**context_data, "research_target_day_ids": [str(day_id) for day_id in
                        (resolution.grounded_intent.target_day_ids if resolution.grounded_intent else [])]},
                    user_request=state["user_request"], external_facts=external_facts)
            trace("destination_research", "tool_result", refs=("external_facts", "preferences"), data={
                "status": research.get("status"), "place_count": len(research.get("places", {})),
            })
            async with session_factory() as session:
                await assert_planning_context_current(session, trip_id, original_context)
                context = await build_planning_context(session, trip_id)
                context_data = context.model_dump(mode="json")
                context_data["external_facts"] = external_facts
                context_data["destination_research"] = research
                resolution = await resolve_planning_intent(session, trip_id, intent_payload,
                    prepared_draft=resolution.semantic_draft, clarification_answers=clarification_answers)
        if (candidate_researcher is not None and state.get("run_type") == "initial_plan"
            and resolution.policy_decision is not None and resolution.policy_decision.route == "plan_preview"
            and not context.candidates and not any(day.activities for day in context.days)):
            async with session_factory() as session:
                await candidate_researcher(session, trip_id)
            async with session_factory() as session:
                await assert_planning_context_current(session, trip_id, original_context)
                context = await build_planning_context(session, trip_id)
                context_data = context.model_dump(mode="json")
                context_data["external_facts"] = external_facts
        async with session_factory() as session:
            await assert_planning_context_current(session, trip_id, original_context)
            run = await session.get(PlanningRun, run_id)
            if run is None:
                raise RuntimeError("planning run disappeared")
            from app.candidate_edit import load_initial_candidate, CandidateEditUnavailable
            try:
                candidate_base = await load_initial_candidate(session, run)
            except CandidateEditUnavailable as exc:
                raise PlannerConstraintsUnsatisfiedError(["candidate_edit_base_unavailable"]) from exc
            if candidate_base is not None:
                context_data["candidate_edit_base"] = candidate_base.model_dump(mode="json")
            refreshed_trigger = {}
            refreshed_fingerprint = None
            if run.trigger_type == "experience_impact":
                from app.experience_replanning_service import refresh_experience_trigger_snapshot
                try:
                    experience = await refresh_experience_trigger_snapshot(session, run, update_run=False)
                except ValueError as exc:
                    raise PlannerConstraintsUnsatisfiedError([str(exc)]) from exc
                refreshed_trigger = experience
                refreshed_fingerprint = experience["fingerprint"]
                recovery = context_data.setdefault("execution_recovery", {})
                # Deliberately curated execution constraint, not an ORM or raw
                # trigger dump. The validator independently protects this activity.
                recovery["experience_constraint"] = {
                    "activity_execution_id": experience["activity_execution_id"],
                    "formal_itinerary_version": experience["formal_itinerary_version"],
                    "status": experience["activity_execution_status"],
                    "actual_started_at": experience["actual_started_at"],
                    "actual_ended_at": experience["actual_ended_at"],
                    "fingerprint": experience["fingerprint"],
                    **{key: experience["impact"].get(key) for key in (
                        "time_shift_minutes", "minimum_downstream_slack_minutes",
                        "first_impacted_activity_id", "fixed_window_feasible",
                        "day_end_feasible", "downstream_schedule",
                    )},
                }
            if run.disruption_event_id is not None:
                disruption = await session.get(TripDisruptionEvent, run.disruption_event_id)
                if disruption is None or disruption.status != "active":
                    raise PlannerConstraintsUnsatisfiedError(["disruption_no_longer_active"])
                recovery = context_data.setdefault("execution_recovery", {})
                deficit = max(0, -int(disruption.impact_snapshot.get("minimum_slack_minutes", 0)))
                mutable = set(recovery.get("mutable_activity_ids", []))
                activities = [
                    RecoveryActivity(str(item["id"]), item["duration_minutes"])
                    for day in context_data["days"] for item in day["activities"]
                    if str(item["id"]) in mutable
                ]
                recovery.update({
                    "disruption": {
                        "id": str(disruption.id), "event_type": disruption.event_type,
                        "itinerary_version": disruption.itinerary_version,
                        "navigation_session_id": str(disruption.navigation_session_id),
                        "impacted_identity": disruption.impacted_identity,
                        "impact_snapshot": disruption.impact_snapshot,
                    },
                    "recovery_options": [item.as_dict() for item in enumerate_recovery_options(
                        deficit_minutes=deficit, activities=activities
                    )],
                })
            goals = extract_planning_goals(
                user_request=state["user_request"],
                intent_resolution=resolution.model_dump(mode="json"),
                context=context_data,
            )
            context_data["planning_goals"] = goals.model_dump(mode="json")
            from app.requirements import project_requirements
            requirement_records = context_data.get("preferences", {}).get("requirement_records")
            if requirement_records is None:
                requirement_records = (run.trigger_snapshot or {}).get("effective_requirements", [])
            context_data["effective_requirements_by_date"] = {
                day["date"]: project_requirements(
                    requirement_records, trip_id=str(trip_id), city=context_data["trip"]["destination"],
                    target_date=day["date"], day_index=context_data["days"].index(day) + 1,
                    target_activity_ids=[str(item["id"]) for item in day.get("activities", [])],
                ) for day in context_data["days"] if day["date"] in goals.target_days
            }
            context_data["effective_requirements"] = list({
                item["id"]: item for items in context_data["effective_requirements_by_date"].values() for item in items
            }.values())
            context_data["weather_sensitive"] = bool(
                resolution.grounded_intent and resolution.grounded_intent.constraints.weather_sensitive
            )
            decision_memory = await retrieve_decision_memory(
                session, trip_id=trip_id, target_days=goals.target_days,
                base_trip_version=run.base_trip_version)
            existing_snapshot = dict(run.trigger_snapshot or {})
        async with session_factory() as route_session:
            context_data["candidate_route_facts"] = await collect_candidate_route_facts(
                route_session, context_data, target_dates=set(goals.target_days))
        _, context_data["candidate_comparison"] = compare_candidates(
            context_data, context_data.get("candidates", []), allowed_dates=set(goals.target_days))
        context_data["formal_route_facts"] = formal_route_facts(context_data, goals)
        context_data["decision_context"] = build_decision_context(
            context=context_data, goals=context_data["planning_goals"],
            resolution=resolution.model_dump(mode="json"), decision_memory=decision_memory)
        # Persist a compact, non-prompt provenance record with the run so
        # live evaluations can establish what the Planner was allowed to
        # see without recording hidden reasoning or provider input text.
        decision = context_data["decision_context"]
        execution = decision["execution_context"]
        existing_snapshot["decision_context_summary"] = {
            "candidate_comparison": context_data["candidate_comparison"],
            "candidate_route_fact_count": len(context_data["candidate_route_facts"]),
            "effective_requirement_ids": [item["id"] for item in context_data["effective_requirements"]],
            "target_days": goals.target_days,
            "formal_activity_count": sum(
                len(day["activities"])
                for day in decision["formal_itinerary"]["days"]
            ),
            "route_fact_statuses": [
                {"date": day["date"], "status": day["route_fact_status"]}
                for day in decision["route_context"]["days"]
            ],
            "protected_activity_ids": decision["protected_constraints"]["protected_activity_ids"],
            "editable_activity_ids": decision["protected_constraints"]["editable_activity_ids"],
            "execution_fields_present": {
                key: execution.get(key) is not None
                for key in ("current_activity_id", "navigation_target_activity_id", "current_eta",
                            "delay_minutes", "minimum_downstream_slack_minutes", "first_impacted_activity_id")
            },
            "provenance": decision["provenance"],
            "decision_memory": {
                "count": len(decision_memory),
                "source_revision_ids": [item["source_revision_id"] for item in decision_memory],
                "source_run_ids": [item["source_run_id"] for item in decision_memory],
                "feedback": [
                    {
                        "source_revision_id": item["source_revision_id"],
                        "reason_code": item["rejection_reason_code"],
                        "reason_text": item["rejection_reason_text"],
                    }
                    for item in decision_memory
                ],
            },
        }
        trace("goal_extracted", "goal", refs=("user_request", "grounded_intent"), data={
            "hard_goal_count": sum(value is not None for value in goals.hard_goals.model_dump().values()),
            "soft_goals": goals.soft_goals.model_dump(mode="json"),
        })
        trace("decision_context_built", "context", refs=("planning_goals", "formal_route_facts", "execution_recovery"), data={
            "target_days": goals.target_days,
            "formal_route_day_count": len(context_data["formal_route_facts"].get("days", [])),
            "route_context_available": any(
                day["route_fact_status"] == "available"
                for day in context_data["decision_context"]["route_context"]["days"]
            ),
            "protected_count": len(context_data["decision_context"]["protected_constraints"]["protected_activity_ids"]),
            "editable_count": len(context_data["decision_context"]["protected_constraints"]["editable_activity_ids"]),
        })
        trace("memory_retrieved", "decision_memory", refs=("rejected_plan_revisions",), data={
            "count": len(decision_memory),
            "source_revision_ids": [item["source_revision_id"] for item in decision_memory],
        })
        async with session_factory() as session:
            await assert_planning_context_current(session, trip_id, original_context, lock=True)
            await assert_planning_claim(session, run_id)
            run = await session.scalar(select(PlanningRun).where(PlanningRun.id == run_id)
                .with_for_update().execution_options(populate_existing=True))
            if run is None or run.status not in {"queued", "researching", "planning", "validating"}:
                raise PlannerConstraintsUnsatisfiedError(["planning_run_no_longer_active"])
            run.intent_resolution = resolution.model_dump(mode="json")
            run.trigger_snapshot = {**(run.trigger_snapshot or {}), **refreshed_trigger,
                "decision_context_summary": existing_snapshot["decision_context_summary"]}
            if refreshed_fingerprint is not None:
                run.trigger_fingerprint = refreshed_fingerprint
            run.token_usage += context_data.get("destination_research", {}).get("token_usage", 0)
            if resolution.requires_clarification:
                run.status = "awaiting_clarification"
            await session.commit()
        await record("goal", "completed", data=goals.model_dump(mode="json"))
        from app.agent_observation import project_context
        await record("context", "completed", data=project_context(context_data))
        return {
            "planning_context": context_data,
            "intent_resolution": resolution.model_dump(mode="json"),
            "planning_goals": goals.model_dump(mode="json"),
            "clarification_count": len(clarification_answers),
        }

    def route_after_intent(state: PlanningGraphState) -> str:
        resolution = PlanningIntentResolution.model_validate(state["intent_resolution"])
        route = resolution.policy_decision.route if resolution.policy_decision else None
        if route == "clarify":
            return "clarify"
        if route == "plan_preview":
            return "plan"
        if route == "answer":
            return "answer"
        raise ValueError(f"planning graph cannot execute intent route: {route}")

    async def answer_node(state: PlanningGraphState) -> dict:
        await report_progress("answer_model", "正在结合正式行程整理回答，等待模型返回…")
        answer = getattr(draft_provider, "answer", None)
        if answer is None:
            raise PlannerNotConfiguredError("assistant answer provider is not configured")
        async with session_factory() as session:
            previous = list((await session.scalars(select(PlanningRun).where(
                PlanningRun.trip_id == uuid.UUID(state["trip_id"]),
                PlanningRun.id != uuid.UUID(state["run_id"]),
            ).order_by(PlanningRun.created_at.desc()).limit(6))).all())
            conversation = [{"user": item.user_request, "assistant": item.response_text, "status": item.status} for item in reversed(previous)]
            revisions = list((await session.scalars(select(PlanRevision).where(
                PlanRevision.planning_run_id.in_([item.id for item in previous]),
                PlanRevision.status.in_(["pending", "accepted"]),
            ).order_by(PlanRevision.created_at.desc()).limit(2))).all())
            context = state["planning_context"]
            names = {item["id"]: item["name"] for item in context.get("candidates", [])}
            names.update({item["place_id"]: item["display_name"] for day in context["days"] for item in day["activities"]})
            for revision in reversed(revisions):
                conversation.append({"proposal_status": revision.status, "proposal_explanation": revision.reason,
                    "proposal_activities": [{"name": names.get(item["place_candidate_id"], "未知地点"),
                        **{key: item.get(key) for key in ("day_date", "planned_start_time", "duration_minutes", "reason")}
                    } for item in revision.proposed_snapshot.get("activities", [])]})
        result = await answer({**state, "conversation": conversation})
        if not result.text.strip():
            raise ValueError("assistant returned an empty answer")
        async with session_factory() as session:
            await assert_planning_claim(session, uuid.UUID(state["run_id"]))
            run = await session.get(PlanningRun, uuid.UUID(state["run_id"]))
            run.response_text = result.text.strip()
            run.status = "answered"
            run.model_provider, run.model_name = result.provider, result.model
            run.token_usage += result.token_usage
            run.completed_at = datetime.now(UTC)
            run.pending_interrupt = None
            await session.commit()
        return {"outcome": "answered"}

    async def clarify_node(state: PlanningGraphState) -> dict:
        try:
            resolution = PlanningIntentResolution.model_validate(state["intent_resolution"])
        except (ValueError, TypeError):
            async with session_factory() as session:
                run = await session.get(PlanningRun, uuid.UUID(state["run_id"]))
                if run is not None and run.user_request != state.get("user_request"):
                    raise LegacyClarificationRestartRequired() from None
            raise
        count = state.get("clarification_count", 0)
        if type(count) is not int or count >= 2:
            async with session_factory() as session:
                run = await session.get(PlanningRun, uuid.UUID(state["run_id"]))
                if run is not None and run.user_request != state["user_request"]:
                    raise LegacyClarificationRestartRequired()
            raise ValueError("planning intent is still ambiguous after two clarifications")
        response = interrupt(
            {
                "kind": "clarification",
                "questions": resolution.clarification_questions,
                "run_id": state["run_id"],
            }
        )
        answer = str(response.get("answer") or "").strip()
        if not answer:
            raise ValueError("clarification answer cannot be blank")
        # The answer fills a missing target, not the original authority. Keep
        # it server-owned and checkpoint-replay-idempotent at this question's index.
        async with session_factory() as session:
            run_id = uuid.UUID(state["run_id"])
            await assert_planning_claim(session, run_id)
            run = await session.scalar(select(PlanningRun).where(PlanningRun.id == run_id)
                .with_for_update().execution_options(populate_existing=True))
            if run is None:
                raise PlannerConstraintsUnsatisfiedError(["clarification_original_request_changed"])
            if run.user_request != state["user_request"]:
                migrated = await _migrate_legacy_clarification(session, run, state, answer)
                await session.commit()
                return migrated
            snapshot = dict(run.trigger_snapshot or {})
            answers = list(snapshot.get("clarification_answers", []))
            index = state.get("clarification_count", 0)
            if len(answers) > index and answers[index] != answer:
                raise PlannerConstraintsUnsatisfiedError(["clarification_answer_changed"])
            if len(answers) == index:
                snapshot["clarification_answers"] = [*answers, answer]
                run.trigger_snapshot = snapshot
            await session.commit()
        return {
            "clarification_count": state.get("clarification_count", 0) + 1,
        }

    async def plan_node(state: PlanningGraphState) -> dict:
        trace("plan", "graph", refs=("planning_context", "intent_resolution"))
        assert_decision_context_invariants(state["planning_context"]["decision_context"])
        async with session_factory() as session:
            await _set_run_status(session, uuid.UUID(state["run_id"]), "planning")
            await assert_planning_claim(session, uuid.UUID(state["run_id"]))
            run = await session.get(PlanningRun, uuid.UUID(state["run_id"]))
            if run is not None:
                snapshot = dict(run.trigger_snapshot or {})
                memory_summary = dict((snapshot.get("decision_context_summary") or {}).get("decision_memory") or {})
                memory_summary.update({
                    "context_propagated": True,
                    "visible_to_planner": True,
                })
                decision_summary = dict(snapshot.get("decision_context_summary") or {})
                decision_summary["decision_memory"] = memory_summary
                snapshot["decision_context_summary"] = decision_summary
                run.trigger_snapshot = snapshot
                await session.commit()
        await report_progress("planning", "正在根据景点资料编排每天的游览顺序、时长与预算，等待模型返回…")
        trace("goal_visible_to_planner", "planner_input", refs=("decision_context",), data={
            "goals_present": bool(state["planning_context"].get("planning_goals")),
            "formal_route_facts_present": bool(state["planning_context"].get("formal_route_facts", {}).get("days")),
            "execution_state_present": bool(state["planning_context"]["decision_context"].get("execution_context")),
        })
        trace("memory_context_propagated", "planner_input", refs=("decision_context",), data={
            "memory_count": len(state["planning_context"]["decision_context"].get("decision_memory") or []),
        })
        trace("memory_visible_to_planner", "planner_input", refs=("decision_context",), data={
            "memory_present": bool(state["planning_context"]["decision_context"].get("decision_memory")),
        })
        generation = await draft_provider.generate(state)
        trace("plan", "planner", refs=("trip", "preferences", "allowed_places", "external_facts", "planning_goals", "formal_route_facts"), data={
            "provider": generation.provider, "model": generation.model,
            "candidate_count": len(generation.snapshot.activities), "decision_count": len(generation.snapshot.decision_ledger or []), "token_usage": generation.token_usage,
        })
        async with session_factory() as session:
            await assert_planning_claim(session, uuid.UUID(state["run_id"]))
            run = await session.get(PlanningRun, uuid.UUID(state["run_id"]))
            if run is None:
                raise RuntimeError("planning run disappeared")
            run.model_provider = generation.provider
            run.model_name = generation.model
            run.token_usage += generation.token_usage
            await session.commit()
        return {"proposed_snapshot": generation.snapshot.model_dump(mode="json")}

    async def goal_check_node(state: PlanningGraphState) -> dict:
        goals = state.get("planning_goals") or state["planning_context"].get("planning_goals") or {}
        result = check_goal_satisfaction(
            goals=PlanningGoals.model_validate(goals),
            before_context=state["planning_context"],
            snapshot=CandidatePlanSnapshot.model_validate(state["proposed_snapshot"]),
        )
        serialized = result.model_dump(mode="json")
        trace("goal_satisfaction", "deterministic_check", refs=("planning_goals", "candidate", "route_facts"), data={
            "statuses": [{"goal": item.goal, "status": item.status} for item in result.results],
        })
        return {"goal_satisfaction": serialized}

    async def validate_node(state: PlanningGraphState) -> dict:
        trace("validate", "graph", refs=("candidate", "route_facts", "budget", "execution_recovery"))
        run_id = uuid.UUID(state["run_id"])
        trip_id = uuid.UUID(state["trip_id"])
        snapshot = CandidatePlanSnapshot.model_validate(state["proposed_snapshot"])
        from app.arrangement_service import bind_arrangement_references
        snapshot = bind_arrangement_references(snapshot, state["planning_context"])
        required_dates: set[date] = set()
        if state.get("run_type") == "initial_plan" and not any(day["activities"] for day in state["planning_context"]["days"]):
            intent = state["intent_resolution"]["request"]["intent"]
            scope = intent.get("time_scope") or {}
            if intent["intent_type"] == "modify_day" and scope.get("day_date"):
                required_dates = {date.fromisoformat(scope["day_date"])}
            else:
                required_dates = {date.fromisoformat(day["date"]) for day in state["planning_context"]["days"]}
        async with session_factory() as session:
            await _set_run_status(session, run_id, "validating")
            run = await session.get(PlanningRun, run_id)
            enforce_execution = bool(run and (run.disruption_event_id or run.trigger_type == "experience_impact"))
        async with session_factory() as route_session:
            await report_progress("routes", "候选活动已生成，正在查询实际交通路线…")
            try:
                snapshot = await enrich_candidate_routes(route_session, trip_id, snapshot,
                    enforce_execution_invariants=enforce_execution)
            except MapProviderError as exc:
                if exc.code != "map_route_unavailable":
                    raise
                return {"proposed_snapshot": snapshot.model_dump(mode="json"), "validation_result": {
                    "valid": False, "errors": [{"code": "route_unavailable", "message": str(exc), "details": getattr(exc, "route_details", {})}], "warnings": []},
                    "required_day_dates": [day.isoformat() for day in sorted(required_dates)]}
        async with session_factory() as session:
            await assert_planning_context_current(session, trip_id, state["planning_context"])
            await report_progress("validation", "路线查询已完成，正在核对时间、日期与预算冲突…")
            result = await validate_candidate_plan(
                session,
                trip_id,
                snapshot,
                required_dates=required_dates,
                intent_resolution=PlanningIntentResolution.model_validate(
                    state["intent_resolution"]
                ),
                enforce_execution_invariants=enforce_execution,
                candidate_edit_base=candidate_base_from_context(state),
            )
            trace("validate", "validation", refs=("candidate", "route_facts", "budget"), data={
                "valid": result.valid, "error_codes": [issue.code for issue in result.errors],
            })
            adjustments: list[dict] = []
            if result.errors and all(
                issue.code in {"time_overlap", "route_travel_time_conflict", "outside_daily_window"}
                for issue in result.errors
            ):
                # Do not move a user's explicit clock time earlier automatically.
                explicit_time = re.search(r"\d{1,2}[:：]\d{2}|[零一二三四五六七八九十两\d]+\s*[点时]", state["user_request"])
                repaired, proposed_adjustments = repair_route_schedule(snapshot, state["planning_context"], allow_earlier=not explicit_time)
                if proposed_adjustments:
                    repaired_result = await validate_candidate_plan(
                        session, trip_id, repaired,
                        required_dates=required_dates,
                        intent_resolution=PlanningIntentResolution.model_validate(state["intent_resolution"]),
                        enforce_execution_invariants=enforce_execution,
                        candidate_edit_base=candidate_base_from_context(state),
                    )
                    if repaired_result.valid:
                        snapshot = reconcile_route_repair_ledger(
                            original=snapshot, repaired=repaired, context=state["planning_context"], adjustments=proposed_adjustments,
                        )
                        result, adjustments = repaired_result, proposed_adjustments
                        result.warnings.append(PlanValidationIssue(
                            code="route_schedule_adjusted",
                            message="已根据查询到的路线时长和每日时间窗调整活动时间，预留交通时间。",
                            details={"adjustments": adjustments},
                        ))
        decision_review = review_candidate_decisions(state["planning_context"], snapshot)
        decision_review["explanation_errors"] = unsupported_decision_claims(state["planning_context"], snapshot)
        if decision_review["explanation_errors"]:
            result.valid = False
            result.errors.extend(PlanValidationIssue(code="decision_explanation_unsupported",
                message="候选解释与已知事实或实际系统能力冲突。", details=item)
                for item in decision_review["explanation_errors"])
        if decision_review["hard_errors"]:
            result.valid = False
            result.errors.extend(PlanValidationIssue.model_validate(item) for item in decision_review["hard_errors"])
        trace("candidate_decision_review", "deterministic_check", refs=("candidate_comparison", "effective_requirements", "route_facts"), data={
            "status": decision_review["status"], "hard_error_count": len(decision_review["hard_errors"]),
            "unknown_requirement_count": len(decision_review["uncheckable_requirement_ids"]),
        })
        ledger_issues, decision_summary = validate_decision_ledger(
            context=state["planning_context"], snapshot=snapshot, schedule_adjustments=adjustments,
        )
        ledger_mode = get_settings().decision_ledger_validation_mode
        if ledger_issues and ledger_mode == "enforced":
            result.valid = False
            result.errors.extend(ledger_issues)
        trace("decision_ledger", "deterministic_check", refs=("formal_itinerary", "candidate_diff", "goals", "memory", "semantics", "route_facts"), data={
            "status": decision_summary["status"], "mode": ledger_mode,
            "candidate_valid": result.valid, "entry_count": len(snapshot.decision_ledger or []),
            "error_codes": decision_summary["error_codes"],
        })
        return {
            "proposed_snapshot": snapshot.model_dump(mode="json"),
            "validation_result": result.model_dump(mode="json"),
            "schedule_adjustments": adjustments,
            "decision_summary": decision_summary,
            "decision_review": decision_review,
            "required_day_dates": [day.isoformat() for day in sorted(required_dates)],
        }

    def route_after_validation(state: PlanningGraphState) -> str:
        if state["validation_result"]["valid"]:
            return "goal_check"
        if state.get("review_count", 0) < 1:
            return "review"
        raise PlannerConstraintsUnsatisfiedError(
            [issue["code"] for issue in state["validation_result"]["errors"]],
            issues=state["validation_result"]["errors"],
        )

    def review_node(state: PlanningGraphState) -> dict:
        return {"review_count": state.get("review_count", 0) + 1}

    def route_after_goal_check(state: PlanningGraphState) -> str:
        feedback = hard_goal_feedback(GoalSatisfactionResult.model_validate(state["goal_satisfaction"]))
        if not feedback:
            return "persist"
        if can_repair_hard_goals(repair_count=state.get("goal_review_count", 0), result=GoalSatisfactionResult.model_validate(state["goal_satisfaction"])):
            return "goal_repair"
        raise GoalConstraintsUnsatisfiedError(feedback)

    def goal_repair_node(state: PlanningGraphState) -> dict:
        return {
            "goal_review_count": state.get("goal_review_count", 0) + 1,
            "goal_feedback": hard_goal_feedback(GoalSatisfactionResult.model_validate(state["goal_satisfaction"])),
        }

    async def persist_node(state: PlanningGraphState) -> dict:
        trace("persist", "graph", refs=("candidate", "validation"))
        run_id = uuid.UUID(state["run_id"])
        snapshot = CandidatePlanSnapshot.model_validate(state["proposed_snapshot"])
        async with session_factory() as session:
            from app.planning_explanation import candidate_cost_totals
            planned_total, original_total = candidate_cost_totals(state["planning_context"], snapshot)
            source_ids = list(
                dict.fromkeys(
                    source_id
                    for activity in snapshot.activities
                    for source_id in activity.source_ids
                )
            )
            revision = await save_plan_revision(
                session,
                run_id,
                before_snapshot=state["planning_context"],
                proposed_snapshot=snapshot,
                reason=describe_plan_changes(state["planning_context"], snapshot, state["user_request"], decision_review=state.get("decision_review")),
                difference_summary={
                    "candidate_activity_count": len(snapshot.activities),
                    "planned_total_fen": planned_total,
                    "planned_budget_delta_fen": planned_total - original_total,
                    "review_count": state.get("review_count", 0),
                    "schedule_adjustments": state.get("schedule_adjustments", []),
                    "required_day_dates": state.get("required_day_dates", []),
                    "destination_research": state["planning_context"].get("destination_research", {}),
                    "recovery": state["planning_context"].get("execution_recovery"),
                    "planning_goals": state.get("planning_goals") or state["planning_context"].get("planning_goals"),
                    "goal_satisfaction": state.get("goal_satisfaction", {"results": []}),
                    "candidate_comparison": state["planning_context"].get("candidate_comparison", {}),
                    "decision_review": state.get("decision_review", {}),
                    "decision_summary": state.get("decision_summary", {"status": "unavailable", "entries": []}),
                    "decision_ledger_status": state.get("decision_summary", {}).get("status", "unavailable"),
                    "decision_ledger_errors": state.get("decision_summary", {}).get("error_codes", []),
                },
                validation_result=state["validation_result"],
                source_ids=source_ids,
                enrich_routes=False,
            )
        return {
            "revision_id": str(revision.id),
        }

    def approval_node(state: PlanningGraphState) -> Command:
        response = interrupt(
            {
                "kind": "approval",
                "run_id": state["run_id"],
                "revision_id": state["revision_id"],
            }
        )
        decision = response.get("decision")
        if decision not in {"accept", "reject"}:
            raise ValueError("approval decision must be accept or reject")
        trace("approval", "decision", refs=("revision",), data={"decision": decision})
        return Command(goto=decision)

    async def accept_node(state: PlanningGraphState) -> dict:
        async with session_factory() as session:
            await accept_plan_revision(session, uuid.UUID(state["revision_id"]))
        return {"outcome": "accepted"}

    async def reject_node(state: PlanningGraphState) -> dict:
        async with session_factory() as session:
            await reject_revision(session, uuid.UUID(state["revision_id"]))
        return {"outcome": "rejected"}

    builder = StateGraph(PlanningGraphState)
    builder.add_node("resolve_intent", observed("intent", graph=True, output_summary=project_state)(resolve_intent_node))
    builder.add_node("clarify", clarify_node)
    builder.add_node("plan", observed("planner", graph=True, purpose="Generate Candidate", output_summary=project_state)(plan_node))
    builder.add_node("answer", observed("answer", graph=True, output_summary=project_state)(answer_node))
    builder.add_node("validate", observed("validator", graph=True, output_summary=project_state)(validate_node))
    builder.add_node("goal_check", observed("goal_check", graph=True, output_summary=project_state)(goal_check_node))
    builder.add_node("review", review_node)
    builder.add_node("goal_repair", goal_repair_node)
    builder.add_node("persist", observed("revision", graph=True, output_summary=project_state)(persist_node))
    builder.add_node("approval", approval_node)
    builder.add_node("accept", observed("user_decision", graph=True, output_summary=project_state)(accept_node))
    builder.add_node("reject", observed("user_decision", graph=True, output_summary=project_state)(reject_node))
    builder.add_edge(START, "resolve_intent")
    builder.add_conditional_edges(
        "resolve_intent", route_after_intent, {"clarify": "clarify", "plan": "plan", "answer": "answer"}
    )
    builder.add_edge("clarify", "resolve_intent")
    builder.add_edge("plan", "validate")
    builder.add_conditional_edges(
        "validate", route_after_validation, {"review": "review", "goal_check": "goal_check"}
    )
    builder.add_edge("review", "plan")
    builder.add_conditional_edges(
        "goal_check", route_after_goal_check, {"persist": "persist", "goal_repair": "goal_repair"}
    )
    builder.add_edge("goal_repair", "plan")
    builder.add_edge("persist", "approval")
    builder.add_edge("accept", END)
    builder.add_edge("reject", END)
    builder.add_edge("answer", END)
    return builder.compile(checkpointer=checkpointer)


async def _collect_external_facts(context: dict, user_request: str, *, include_search: bool = True) -> dict:
    """Search does not depend on coordinates or weather availability."""
    settings = get_settings()
    if settings.app_env == "test":
        return {"status": "disabled_in_test"}
    trip = context["trip"]
    result = {"status": "partial", "search": {"status": "not_configured" if include_search else "not_required"}, "weather": {"status": "no_coordinate_source"}}
    if include_search and settings.search_api_key:
        try:
            await report_progress("web_search", "正在检索目的地特色、热门景点与旅行事宜…")
            search = await search_tavily(settings, query=(
                f"{trip['destination']} 旅游 代表性热门景点 特色 预约 开放 注意事项 "
                f"{' '.join(context.get('preferences', {}).get('interest_categories', []))}"), max_results=8)
            result["search"] = {"status": "available" if search.payload.get("results") else "unavailable",
                "provider": search.provider, "queried_at": search.queried_at, "query": search.query, "payload": search.payload}
            if re.search(r"、|想去|希望.*(?:包含|看到)|加入", user_request):
                await report_progress("focused_search", "已完成目的地检索，正在补充查询你提到的景点…")
                focus = re.sub(r"请重新规划完整行程|请调整|希望|包含|行程中|可以看到|等(?:知名|著名)?景点|[，。、；]", " ", user_request)
                try:
                    focused = await search_tavily(settings, query=f"{trip['destination']} {focus[:350]} 景点名称 官方 交通限制", max_results=4)
                    merged = []
                    urls = set()
                    for item in focused.payload.get("results", []) + search.payload.get("results", []):
                        url = item.get("url")
                        if url and url not in urls:
                            merged.append(item)
                            urls.add(url)
                    if merged:
                        result["search"]["payload"] = {"results": merged[:8]}
                        result["search"]["status"] = "available"
                    result["search"]["queries"] = [search.query, focused.query]
                except ExternalFactError as exc:
                    result["search"]["focused_search_status"] = "unavailable"
                    result["search"]["focused_search_reason"] = str(exc)
        except ExternalFactError as exc:
            result["search"] = {"status": "unavailable", "reason": str(exc)}
    latitude, longitude = trip.get("center_latitude"), trip.get("center_longitude")
    if latitude is None or longitude is None:
        coordinates = [(float(item["latitude"]), float(item["longitude"])) for item in context.get("candidates", [])[:10]
                       if item.get("latitude") is not None and item.get("longitude") is not None]
        if coordinates:
            latitude = sum(item[0] for item in coordinates) / len(coordinates)
            longitude = sum(item[1] for item in coordinates) / len(coordinates)
    if latitude is not None and longitude is not None:
        try:
            await report_progress("weather", "网页检索已结束，正在查询旅行日期的天气信息…")
            weather = await fetch_open_meteo(settings, latitude=float(latitude), longitude=float(longitude),
                start_date=date.fromisoformat(trip["start_date"]), end_date=date.fromisoformat(trip["end_date"]), timezone=trip["timezone"])
            result["weather"] = {"status": "available", "provider": weather.provider, "queried_at": weather.queried_at,
                "latitude": weather.latitude, "longitude": weather.longitude, "payload": weather.payload}
        except (ExternalFactError, ValueError) as exc:
            result["weather"] = {"status": "unavailable", "reason": str(exc)}
    if result["search"]["status"] == "available" and result["weather"]["status"] == "available":
        result["status"] = "available"
    return result
