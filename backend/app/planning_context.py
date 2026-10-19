import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.planner_repository import get_candidates, get_day_plans, get_planning_budget
from app.repository import get_budget, get_trip, get_trip_preferences
from app.schemas import PlanningContextResponse, TripPreferencesResponse, TripResponse
from app.navigation.execution_context import build_execution_recovery_context
from app.requirements import valid_records


async def build_planning_context(
    session: AsyncSession, trip_id: uuid.UUID
) -> PlanningContextResponse:
    trip = await get_trip(session, trip_id)
    preferences = await get_trip_preferences(session, trip_id)
    # Promotion may update preferences inside this same transaction. PostgreSQL
    # expires its server-generated onupdate timestamp; load it asynchronously
    # before Pydantic reads ORM attributes (no implicit async database I/O).
    await session.refresh(preferences, attribute_names=["updated_at"])
    days = await get_day_plans(session, trip_id)
    candidates = await get_candidates(session, trip_id)
    actual_budget = await get_budget(session, trip_id)
    planning_budget = await get_planning_budget(session, trip_id)
    execution_recovery = await build_execution_recovery_context(session, trip_id)
    activity_ids = {str(activity.id) for day in days for activity in day.activities}
    frozen = set(execution_recovery["frozen_activity_ids"])
    protected = set(execution_recovery["protected_activity_ids"])
    execution_recovery["mutable_activity_ids"] = sorted(activity_ids - frozen - protected)
    from app.arrangement_service import read_items, item_dict
    return PlanningContextResponse(
        trip=TripResponse.model_validate(trip),
        preferences=TripPreferencesResponse.model_validate(preferences),
        days=days,
        candidates=candidates,
        actual_budget=actual_budget,
        planning_budget=planning_budget,
        generated_at=datetime.now(UTC),
        external_facts={},
        execution_recovery=execution_recovery,
        effective_requirements=valid_records(getattr(preferences, "requirement_records", [])),
        arrangement_items=[item_dict(item) for item in await read_items(session, trip_id)],
    )
