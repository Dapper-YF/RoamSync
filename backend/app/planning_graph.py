import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidate_route_service import enrich_candidate_routes
from app.database import PlanningRun, session_factory
from app.plan_revision_service import accept_plan_revision, validate_candidate_plan
from app.planning_context import build_planning_context
from app.planning_errors import PlannerConstraintsUnsatisfiedError, PlannerNotConfiguredError
from app.planning_intent_service import resolve_planning_intent
from app.planning_run_repository import reject_revision, save_plan_revision
from app.schemas import (
    CandidatePlanSnapshot,
    PlanningIntentParseRequest,
    PlanningIntentResolution,
)


class PlanningGraphState(TypedDict, total=False):
    run_id: str
    trip_id: str
    user_request: str
    selected_day_id: str | None
    selected_activity_id: str | None
    planning_context: dict
    intent_resolution: dict
    clarification_count: int
    proposed_snapshot: dict
    validation_result: dict
    review_count: int
    revision_id: str
    outcome: str


class DraftProvider(Protocol):
    async def generate(self, state: PlanningGraphState) -> "DraftGeneration": ...


@dataclass(frozen=True)
class DraftGeneration:
    snapshot: CandidatePlanSnapshot
    provider: str
    model: str
    token_usage: int


class UnavailableDraftProvider:
    async def generate(self, state: PlanningGraphState) -> DraftGeneration:
        raise PlannerNotConfiguredError("planner model provider is not configured")


async def _set_run_status(
    session: AsyncSession, run_id: uuid.UUID, status: str
) -> None:
    run = await session.get(PlanningRun, run_id)
    if run is None:
        raise RuntimeError("planning run disappeared")
    run.status = status
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    await session.commit()


def build_planning_graph(checkpointer, provider: DraftProvider | None = None):
    draft_provider = provider or UnavailableDraftProvider()

    async def resolve_intent_node(state: PlanningGraphState) -> dict:
        run_id = uuid.UUID(state["run_id"])
        trip_id = uuid.UUID(state["trip_id"])
        async with session_factory() as session:
            await _set_run_status(session, run_id, "researching")
            context = await build_planning_context(session, trip_id)
            resolution = await resolve_planning_intent(
                session,
                trip_id,
                PlanningIntentParseRequest(
                    message=state["user_request"],
                    selected_day_id=state.get("selected_day_id"),
                    selected_activity_id=state.get("selected_activity_id"),
                ),
            )
            if resolution.requires_clarification:
                await _set_run_status(session, run_id, "awaiting_clarification")
        return {
            "planning_context": context.model_dump(mode="json"),
            "intent_resolution": resolution.model_dump(mode="json"),
        }

    def route_after_intent(state: PlanningGraphState) -> str:
        resolution = PlanningIntentResolution.model_validate(state["intent_resolution"])
        return "clarify" if resolution.requires_clarification else "plan"

    def clarify_node(state: PlanningGraphState) -> dict:
        resolution = PlanningIntentResolution.model_validate(state["intent_resolution"])
        if state.get("clarification_count", 0) >= 2:
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
        return {
            "user_request": f"{state['user_request']}\n用户补充：{answer}",
            "clarification_count": state.get("clarification_count", 0) + 1,
        }

    async def plan_node(state: PlanningGraphState) -> dict:
        async with session_factory() as session:
            await _set_run_status(session, uuid.UUID(state["run_id"]), "planning")
        generation = await draft_provider.generate(state)
        async with session_factory() as session:
            run = await session.get(PlanningRun, uuid.UUID(state["run_id"]))
            if run is None:
                raise RuntimeError("planning run disappeared")
            run.model_provider = generation.provider
            run.model_name = generation.model
            run.token_usage += generation.token_usage
            await session.commit()
        return {"proposed_snapshot": generation.snapshot.model_dump(mode="json")}

    async def validate_node(state: PlanningGraphState) -> dict:
        run_id = uuid.UUID(state["run_id"])
        trip_id = uuid.UUID(state["trip_id"])
        snapshot = CandidatePlanSnapshot.model_validate(state["proposed_snapshot"])
        async with session_factory() as session:
            await _set_run_status(session, run_id, "validating")
            snapshot = await enrich_candidate_routes(session, trip_id, snapshot)
            result = await validate_candidate_plan(session, trip_id, snapshot)
        return {
            "proposed_snapshot": snapshot.model_dump(mode="json"),
            "validation_result": result.model_dump(mode="json"),
        }

    def route_after_validation(state: PlanningGraphState) -> str:
        if state["validation_result"]["valid"]:
            return "persist"
        if state.get("review_count", 0) < 1:
            return "review"
        raise PlannerConstraintsUnsatisfiedError(
            [issue["code"] for issue in state["validation_result"]["errors"]]
        )

    def review_node(state: PlanningGraphState) -> dict:
        return {"review_count": state.get("review_count", 0) + 1}

    async def persist_node(state: PlanningGraphState) -> dict:
        run_id = uuid.UUID(state["run_id"])
        snapshot = CandidatePlanSnapshot.model_validate(state["proposed_snapshot"])
        async with session_factory() as session:
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
                reason="Agent planning candidate",
                difference_summary={
                    "candidate_activity_count": len(snapshot.activities),
                    "review_count": state.get("review_count", 0),
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
    builder.add_node("resolve_intent", resolve_intent_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("plan", plan_node)
    builder.add_node("validate", validate_node)
    builder.add_node("review", review_node)
    builder.add_node("persist", persist_node)
    builder.add_node("approval", approval_node)
    builder.add_node("accept", accept_node)
    builder.add_node("reject", reject_node)
    builder.add_edge(START, "resolve_intent")
    builder.add_conditional_edges(
        "resolve_intent", route_after_intent, {"clarify": "clarify", "plan": "plan"}
    )
    builder.add_edge("clarify", "resolve_intent")
    builder.add_edge("plan", "validate")
    builder.add_conditional_edges(
        "validate", route_after_validation, {"review": "review", "persist": "persist"}
    )
    builder.add_edge("review", "plan")
    builder.add_edge("persist", "approval")
    builder.add_edge("accept", END)
    builder.add_edge("reject", END)
    return builder.compile(checkpointer=checkpointer)
