from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.database import Trip, get_session
from app.arrangement_service import ItemWrite, ItemSchedule, item_dict, read_items, write_item, schedule_item
from app.maps_service import MapProviderError

router = APIRouter(prefix="/api/v1/trips", tags=["arrangements"])


async def result(session, operation):
    try:
        return item_dict(await operation)
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, MapProviderError) as exc:
        await session.rollback()
        raise HTTPException(422, str(exc)) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "事项身份或关联已变化，请刷新后核对") from exc


@router.get("/{trip_id}/arrangement-items")
async def listing(trip_id: UUID, session=Depends(get_session)):
    trip = await session.scalar(select(Trip).where(Trip.id == trip_id).with_for_update(read=True).execution_options(populate_existing=True))
    if trip is None:
        raise HTTPException(404, "旅行不存在")
    from app.planner_repository import get_day_plans
    from app.schemas import TripResponse
    return {"trip_id": trip.id, "version": trip.version, "trip": TripResponse.model_validate(trip),
            "days": await get_day_plans(session, trip_id), "items": [item_dict(i) for i in await read_items(session, trip_id)]}


@router.post("/{trip_id}/arrangement-items", status_code=201)
async def adding(trip_id: UUID, payload: ItemWrite, session=Depends(get_session)):
    return await result(session, write_item(session, trip_id, payload))


@router.put("/{trip_id}/arrangement-items/{item_id}")
async def changing(trip_id: UUID, item_id: UUID, payload: ItemWrite, session=Depends(get_session)):
    return await result(session, write_item(session, trip_id, payload, item_id=item_id))


@router.post("/{trip_id}/arrangement-items/{item_id}/schedule")
async def scheduling(trip_id: UUID, item_id: UUID, payload: ItemSchedule, session=Depends(get_session)):
    return await result(session, schedule_item(session, trip_id, item_id, payload))
