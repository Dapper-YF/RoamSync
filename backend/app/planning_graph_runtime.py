import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.openai_planner import OpenAIResponsesPlanner
from app.planning_errors import (
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
from app.schemas import PlanningRunDecision


@dataclass(frozen=True)
class PlanningExecutionResult:
    pending_interrupt: dict | None


async def invoke_compiled_graph(
    graph,
    run: PlanningRun,
    *,
    resume: dict | None = None,
) -> PlanningExecutionResult:
    config = {"configurable": {"thread_id": str(run.id)}}
    graph_input: PlanningGraphState | Command
    if resume is None:
        graph_input = {
            "run_id": str(run.id),
            "trip_id": str(run.trip_id),
            "user_request": run.user_request,
            "clarification_count": 0,
        }
    else:
        graph_input = Command(resume=resume)
    result = await graph.ainvoke(graph_input, config=config)
    interrupts = result.get("__interrupt__", ())
    pending = interrupts[0].value if interrupts else None
    return PlanningExecutionResult(pending_interrupt=pending)


async def execute_planning_run(
    run_id: uuid.UUID,
    *,
    decision: PlanningRunDecision | None = None,
    provider: DraftProvider | None = None,
) -> PlanningExecutionResult:
    async with session_factory() as session:
        run = await session.get(PlanningRun, run_id)
        if run is None:
            raise PlanningRunNotFoundError
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
            graph = build_planning_graph(checkpointer, draft_provider)
            result = await invoke_compiled_graph(graph, run, resume=resume)
            async with session_factory() as session:
                persisted = await session.get(PlanningRun, run_id)
                if persisted is not None:
                    persisted.pending_interrupt = result.pending_interrupt
                    await session.commit()
            return result
    except PlannerNotConfiguredError as exc:
        await _mark_failed(run_id, "planner_not_configured", str(exc))
        return PlanningExecutionResult(pending_interrupt=None)
    except PlannerProviderError as exc:
        await _mark_failed(run_id, exc.code, str(exc))
        return PlanningExecutionResult(pending_interrupt=None)
    except PlannerConstraintsUnsatisfiedError as exc:
        await _mark_failed(run_id, "planner_constraints_unsatisfied", str(exc))
        return PlanningExecutionResult(pending_interrupt=None)
    except Exception as exc:
        await _mark_failed(run_id, "planning_graph_failed", str(exc))
        raise


async def _mark_failed(run_id: uuid.UUID, code: str, message: str) -> None:
    async with session_factory() as session:
        run = await session.get(PlanningRun, run_id)
        if run is None or run.status in {"accepted", "rejected", "cancelled"}:
            return
        run.status = "failed"
        run.error_code = code
        run.error_message = message[:2000]
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
