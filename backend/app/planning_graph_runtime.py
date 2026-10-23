import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
import logging

from app.destination_research import research_destination
from app.initial_places_service import prepare_initial_candidates
from app.planning_progress import track_progress
from app.planning_claim import (
    assert_planning_claim, checkpoint_thread, LostPlanningClaim, PlanningClaim,
    active_claim, release_planning_claim,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from pydantic import TypeAdapter

from app.config import get_settings
from app.maps_service import MapProviderError
from app.database import PlanningRun, session_factory
from app.openai_planner import OpenAIResponsesPlanner
from app.openai_intent_parser import build_semantic_intent_provider
from app.planning_errors import (
    DecisionContextInvariantError,
    GoalConstraintsUnsatisfiedError,
    PlannerConstraintsUnsatisfiedError,
    PlannerNotConfiguredError,
    PlannerProviderError,
)
from app.planning_graph import (
    DraftProvider,
    PlanningGraphState,
    UnavailableDraftProvider,
    build_planning_graph,
)
from app.planning_run_repository import PlanningRunNotFoundError
from app.schemas import PlanningPendingInterrupt, PlanningRunDecision


pending_interrupt_adapter = TypeAdapter(PlanningPendingInterrupt)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanningExecutionResult:
    pending_interrupt: dict | None


async def invoke_compiled_graph(
    graph,
    run: PlanningRun,
    *,
    resume: dict | None = None,
) -> PlanningExecutionResult:
    config = {"configurable": {"thread_id": checkpoint_thread(run)}}
    graph_input: PlanningGraphState | Command
    if resume is None:
        graph_input = {
            "run_id": str(run.id),
            "trip_id": str(run.trip_id),
            "user_request": run.user_request,
            "run_type": run.run_type,
            "entry_point": run.entry_point,
            "selected_day_id": str(run.selected_day_id) if run.selected_day_id else None,
            "selected_activity_id": (
                str(run.selected_activity_id) if run.selected_activity_id else None
            ),
            "clarification_count": 0,
        }
    else:
        graph_input = Command(resume=resume)
    result = await graph.ainvoke(graph_input, config=config)
    interrupts = result.get("__interrupt__", ())
    pending = (
        pending_interrupt_adapter.validate_python(interrupts[0].value).model_dump(
            mode="json"
        )
        if interrupts
        else None
    )
    return PlanningExecutionResult(pending_interrupt=pending)


async def execute_planning_run(
    run_id: uuid.UUID,
    *,
    decision: PlanningRunDecision | None = None,
    provider: DraftProvider | None = None,
) -> PlanningExecutionResult:
    settings = get_settings()
    resume_claim = None
    claim_token = None
    if decision is not None and decision.decision == "clarify" and active_claim.get() is None:
        resume_claim = await _claim_clarification(run_id, decision)
        claim_token = active_claim.set(resume_claim)
    try:
        async with asyncio.timeout(settings.agent_run_timeout_seconds):
            # Accept/reject resumes only database work, not a long model request.
            if decision is not None and decision.decision in {"accept", "reject"}:
                return await _execute_planning_run(run_id, decision=decision, provider=provider)
            async with track_progress(run_id):
                return await _execute_planning_run(run_id, decision=decision, provider=provider)
    except TimeoutError:
        await _mark_failed(
            run_id,
            "planning_run_timeout",
            f"Planning run exceeded its {settings.agent_run_timeout_seconds}-second execution deadline.",
            {"category": "execution_timeout", "timeout_seconds": settings.agent_run_timeout_seconds},
        )
        return PlanningExecutionResult(pending_interrupt=None)
    finally:
        if claim_token is not None:
            active_claim.reset(claim_token)
            try:
                await release_planning_claim(session_factory, resume_claim)
            except Exception as exc:
                logger.warning("Clarification lease cleanup failed: %s", type(exc).__name__)


async def _claim_clarification(run_id, decision):
    from app.database import Trip
    async with session_factory() as session:
        trip_id = await session.scalar(select(PlanningRun.trip_id).where(PlanningRun.id == run_id))
        if trip_id is None:
            raise PlanningRunNotFoundError
        await session.scalar(select(Trip.id).where(Trip.id == trip_id).with_for_update())
        run = await session.scalar(select(PlanningRun).where(PlanningRun.id == run_id)
            .with_for_update().execution_options(populate_existing=True))
        if run is None:
            raise PlanningRunNotFoundError
        _validate_decision(run, decision)
        if (run.pending_interrupt or {}).get("kind") != "clarification":
            raise ValueError("planning clarification checkpoint is not ready")
        claim = PlanningClaim(run_id, trip_id, f"resume:{uuid.uuid4().hex}")
        run.worker_id = claim.token
        run.worker_lease_expires_at = datetime.now(UTC) + timedelta(seconds=get_settings().agent_lease_seconds)
        # This atomic transition excludes a second clarification request. The
        # existing checkpoint thread must be resumed, not replaced by a claim.
        run.status = "researching"
        run.pending_interrupt = None
        await session.commit()
        return claim


async def _execute_planning_run(
    run_id: uuid.UUID,
    *,
    decision: PlanningRunDecision | None = None,
    provider: DraftProvider | None = None,
) -> PlanningExecutionResult:
    async with session_factory() as session:
        await assert_planning_claim(session, run_id)
        run = await session.get(PlanningRun, run_id)
        if run is None:
            raise PlanningRunNotFoundError
        if decision is not None and decision.decision == "clarify" and active_claim.get() is not None:
            if run.status != "researching":
                raise ValueError("clarification execution is no longer active")
        else:
            _validate_decision(run, decision)

    resume = None
    if decision is not None:
        resume = {"decision": decision.decision, "answer": decision.answer}
    settings = get_settings()
    try:
        draft_provider = provider
        if draft_provider is None:
            try:
                draft_provider = OpenAIResponsesPlanner(settings)
            except PlannerNotConfiguredError:
                # A resumed approval does not execute the planner node. Keep the
                # explicit unavailable provider so that new planning still fails
                # with planner_not_configured at the correct graph boundary.
                draft_provider = UnavailableDraftProvider()
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            graph = build_planning_graph(
                checkpointer,
                draft_provider,
                build_semantic_intent_provider(settings),
                destination_researcher=research_destination if provider is None else None,
                candidate_researcher=prepare_initial_candidates if provider is None else None,
            )
            result = await invoke_compiled_graph(graph, run, resume=resume)
            async with session_factory() as session:
                await assert_planning_claim(session, run_id)
                persisted = await session.get(PlanningRun, run_id)
                if persisted is not None:
                    persisted.pending_interrupt = result.pending_interrupt
                    await session.commit()
            return result
    except PlannerNotConfiguredError as exc:
        await _mark_failed(run_id, "planner_not_configured", str(exc))
        return PlanningExecutionResult(pending_interrupt=None)
    except PlannerProviderError as exc:
        await _mark_failed(run_id, exc.code, str(exc), {"category": getattr(exc, "category", "provider_failure"), "reliability": getattr(exc, "reliability", {})})
        return PlanningExecutionResult(pending_interrupt=None)
    except PlannerConstraintsUnsatisfiedError as exc:
        await _mark_failed(run_id, "planner_constraints_unsatisfied", str(exc), {"validation_errors": exc.issues, "category": "candidate_validation_failure"})
        return PlanningExecutionResult(pending_interrupt=None)
    except GoalConstraintsUnsatisfiedError as exc:
        await _mark_failed(run_id, "goal_constraints_unsatisfied", str(exc), {"goal_satisfaction": exc.feedback, "category": "planner_semantic_constraint_failure"})
        return PlanningExecutionResult(pending_interrupt=None)
    except DecisionContextInvariantError as exc:
        await _mark_failed(run_id, "decision_context_invalid", str(exc), {"invariant_errors": exc.codes})
        return PlanningExecutionResult(pending_interrupt=None)
    except MapProviderError as exc:
        await _mark_failed(run_id, "planner_map_unavailable", str(exc), {"map_error_code": exc.code, "category": "provider_failure"})
        return PlanningExecutionResult(pending_interrupt=None)
    except LostPlanningClaim:
        raise
    except Exception as exc:
        await _mark_failed(run_id, "planning_graph_failed", str(exc))
        raise


async def _mark_failed(run_id: uuid.UUID, code: str, message: str, details: dict | None = None) -> None:
    async with session_factory() as session:
        await assert_planning_claim(session, run_id)
        run = await session.get(PlanningRun, run_id)
        if run is None or run.status not in {"queued", "researching", "planning", "validating"}:
            return
        run.status = "failed"
        run.error_code = code
        run.error_message = message[:2000]
        run.error_details = details
        run.pending_interrupt = None
        run.completed_at = datetime.now(UTC)
        await session.commit()


def _validate_decision(
    run: PlanningRun, decision: PlanningRunDecision | None
) -> None:
    if decision is None:
        if run.status not in {"queued", "researching"}:
            raise ValueError("planning run cannot be started from its current state")
        return
    if run.status == "awaiting_clarification" and decision.decision != "clarify":
        raise ValueError("planning run is waiting for clarification")
    if run.status == "awaiting_confirmation" and decision.decision not in {
        "accept",
        "reject",
    }:
        raise ValueError("planning run is waiting for approval")
    if run.status not in {"awaiting_clarification", "awaiting_confirmation"}:
        raise ValueError("planning run is not waiting for a decision")
