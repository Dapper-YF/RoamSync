"""Server-owned planning input prepared before any business write transaction."""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import TripPreferences
from app.planning_intent_service import (
    SemanticIntentProvider, load_planning_intent_snapshot,
    resolve_planning_intent_snapshot,
)
from app.schemas import (
    PlanningIntentParseRequest, PlanningIntentResolution, PlanningRunCreate,
    SemanticIntentDraft,
)


class PlanningPreparationRequiredError(RuntimeError):
    """A caller must prepare network work before opening its atomic transaction."""


@dataclass(frozen=True)
class PreparedPlanningIntent:
    trip_id: uuid.UUID
    user_request: str
    entry_point: str
    selected_day_id: uuid.UUID | None
    selected_activity_id: uuid.UUID | None
    base_trip_version: int
    preferences_version: int | None
    draft: SemanticIntentDraft

    def matches(self, trip_id: uuid.UUID, payload: PlanningRunCreate) -> bool:
        return (self.trip_id, self.user_request, self.entry_point,
                self.selected_day_id, self.selected_activity_id) == (
            trip_id, payload.user_request, payload.entry_point,
            payload.selected_day_id, payload.selected_activity_id)


async def resolve_planning_without_transaction(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: PlanningIntentParseRequest,
    *,
    semantic_provider: SemanticIntentProvider | None = None,
    default_planning_intent=None,
) -> tuple[PlanningIntentResolution, int, int | None]:
    # Never guess whether an existing transaction is read-only: flushed writes
    # and locks are invisible to session.dirty. Its owner must end it explicitly.
    if session.in_transaction():
        raise PlanningPreparationRequiredError("prepare planning before opening the caller transaction")
    sessions = async_sessionmaker(session.bind, expire_on_commit=False)
    async with sessions() as reader:
        snapshot = await load_planning_intent_snapshot(reader, trip_id, payload)
        preferences_version = await reader.scalar(
            select(TripPreferences.version).where(TripPreferences.trip_id == trip_id))
    resolution = await resolve_planning_intent_snapshot(
        snapshot, payload, semantic_provider=semantic_provider,
        default_planning_intent=default_planning_intent)
    return resolution, snapshot.trip.version, preferences_version


async def prepare_planning_intent(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: PlanningRunCreate,
    *,
    semantic_provider: SemanticIntentProvider | None = None,
) -> PreparedPlanningIntent:
    resolution, trip_version, preferences_version = await resolve_planning_without_transaction(
        session, trip_id, PlanningIntentParseRequest(
            message=payload.user_request, entry_point=payload.entry_point,
            selected_day_id=payload.selected_day_id,
            selected_activity_id=payload.selected_activity_id),
        semantic_provider=semantic_provider,
        default_planning_intent="create_plan" if payload.run_type == "initial_plan" else "replan_trip")
    if resolution.semantic_draft is None:
        raise PlanningPreparationRequiredError("planning resolution has no semantic draft")
    return PreparedPlanningIntent(
        trip_id, payload.user_request, payload.entry_point,
        payload.selected_day_id, payload.selected_activity_id,
        trip_version, preferences_version, resolution.semantic_draft.model_copy(deep=True))
