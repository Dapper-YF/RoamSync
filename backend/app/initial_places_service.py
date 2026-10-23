"""Prepare sourced candidates for an empty trip without adding scheduled activities."""
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import Trip
from app.maps_service import search_amap_places
from app.planner_repository import get_candidates, save_candidate_snapshot
from app.planning_errors import PlannerConstraintsUnsatisfiedError
from app.repository import get_trip_preferences
from app.schemas import PlaceSearchResultResponse
from app.planning_preparation import PlanningPreparationRequiredError, assert_planning_context_current
from app.planning_claim import assert_planning_claim

PlaceSearch = Callable[[str, str], Awaitable[list[PlaceSearchResultResponse]]]


async def prepare_initial_candidates(
    session: AsyncSession, trip_id: uuid.UUID, *, search: PlaceSearch = search_amap_places
) -> None:
    if session.in_transaction():
        raise PlanningPreparationRequiredError("prepare initial places before opening the caller transaction")
    sessions = async_sessionmaker(session.bind, expire_on_commit=False)
    async with sessions() as reader:
        if await get_candidates(reader, trip_id):
            return
        trip = await reader.get(Trip, trip_id)
        if trip is None:
            raise ValueError("旅行不存在")
        preferences = await get_trip_preferences(reader, trip_id)
        city = trip.destination_adcode or trip.destination
        interests = list(preferences.interest_categories)
        versions = {"trip": {"version": trip.version}, "preferences": {"version": preferences.version}}
    keywords = {"culture": "博物馆", "history": "名胜古迹", "nature": "公园", "food": "本地美食", "photography": "风景名胜", "shopping": "商业街", "family": "公园", "nightlife": "夜市"}
    queries = list(dict.fromkeys([keywords[item] for item in interests if item in keywords] + ["风景名胜", "本地美食"]))[:3]
    snapshots = {}
    # Sequential requests keep provider QPS bounded; all results are staged first.
    for query in queries:
        for item in await search(query, city):
            snapshots[item.provider_place_id] = item
    if not snapshots:
        raise PlannerConstraintsUnsatisfiedError(["initial_places_unavailable"])
    # Lock the trip and recheck so concurrent first plans do not duplicate candidates.
    await assert_planning_context_current(session, trip_id, versions, lock=True)
    await assert_planning_claim(session, trip_id=trip_id)
    if await get_candidates(session, trip_id):
        return
    for item in snapshots.values():
        await save_candidate_snapshot(session, trip_id, item)
    await session.commit()
