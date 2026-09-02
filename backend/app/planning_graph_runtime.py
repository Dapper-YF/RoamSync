import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.planning_graph import (
    DraftProvider,
    PlannerNotConfiguredError,
    PlanningGraphState,
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
        async with AsyncPostgresSaver.from_conn_string(
            settings.checkpoint_database_url
        ) as checkpointer:
            graph = build_planning_graph(checkpointer, provider)
            return await invoke_compiled_graph(graph, run, resume=resume)
    except PlannerNotConfiguredError as exc:
        await _mark_failed(run_id, "planner_not_configured", str(exc))
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
