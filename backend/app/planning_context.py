import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.planner_repository import get_candidates, get_day_plans, get_planning_budget
from app.repository import get_budget, get_trip, get_trip_preferences
from app.schemas import PlanningContextResponse, TripPreferencesResponse, TripResponse


async def build_planning_context(
    session: AsyncSession, trip_id: uuid.UUID
) -> PlanningContextResponse:
    trip = await get_trip(session, trip_id)
    preferences = await get_trip_preferences(session, trip_id)
    days = await get_day_plans(session, trip_id)
    candidates = await get_candidates(session, trip_id)
    actual_budget = await get_budget(session, trip_id)
    planning_budget = await get_planning_budget(session, trip_id)
    return PlanningContextResponse(
        trip=TripResponse.model_validate(trip),
        preferences=TripPreferencesResponse.model_validate(preferences),
        days=days,
        candidates=candidates,
        actual_budget=actual_budget,
        planning_budget=planning_budget,
        generated_at=datetime.now(UTC),
    )
