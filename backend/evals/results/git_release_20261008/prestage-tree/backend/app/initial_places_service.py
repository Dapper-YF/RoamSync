"""Prepare sourced candidates for an empty trip without adding scheduled activities."""
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Trip
from app.maps_service import search_amap_places
from app.planner_repository import get_candidates, save_candidate_snapshot
from app.planning_errors import PlannerConstraintsUnsatisfiedError
from app.repository import get_trip_preferences
from app.schemas import PlaceSearchResultResponse

PlaceSearch = Callable[[str, str], Awaitable[list[PlaceSearchResultResponse]]]


async def prepare_initial_candidates(
    session: AsyncSession, trip_id: uuid.UUID, *, search: PlaceSearch = search_amap_places
) -> None:
    if await get_candidates(session, trip_id):
        return
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise ValueError("旅行不存在")
    preferences = await get_trip_preferences(session, trip_id)
    keywords = {"culture": "博物馆", "history": "名胜古迹", "nature": "公园", "food": "本地美食", "photography": "风景名胜", "shopping": "商业街", "family": "公园", "nightlife": "夜市"}
    queries = list(dict.fromkeys([keywords[item] for item in preferences.interest_categories if item in keywords] + ["风景名胜", "本地美食"]))[:3]
    snapshots = {}
    # Sequential requests keep provider QPS bounded; all results are staged first.
    for query in queries:
        for item in await search(query, trip.destination_adcode or trip.destination):
            snapshots[item.provider_place_id] = item
    if not snapshots:
        raise PlannerConstraintsUnsatisfiedError(["initial_places_unavailable"])
    # Lock the trip and recheck so concurrent first plans do not duplicate candidates.
    await session.scalar(select(Trip).where(Trip.id == trip_id).with_for_update())
    if await get_candidates(session, trip_id):
        return
    for item in snapshots.values():
        await save_candidate_snapshot(session, trip_id, item)
    await session.commit()
