"""Small explicit-requirement API, mounted only behind the existing owner gate."""
from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.database import TripPreferences, get_session
from app.repository import get_trip
from app.requirements import add_requirement, project_requirements, revoke_requirement, valid_records


class RequirementWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    text: str = Field(min_length=1, max_length=1000)
    key: Literal["user_requirement", "pace", "avoid_category", "budget_fen", "daily_budget_fen", "interest", "max_walking_minutes", "walking_preference"] = "user_requirement"
    value: str | int | None = None
    strength: Literal["hard", "soft"] = "soft"
    day_date: date | None = None


class RequirementRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    requirement_id: str
    day_date: date | None = None


def create_router(owner_dependency):
    router = APIRouter(prefix="/api/v1/trips", tags=["effective-requirements"],
        dependencies=[Depends(owner_dependency)])

    async def state(session, trip_id, version=None):
        trip = await get_trip(session, trip_id)
        pref = await session.scalar(select(TripPreferences).where(TripPreferences.trip_id == trip_id).with_for_update())
        if pref is None:
            raise HTTPException(404, detail={"code": "trip_preferences_not_found"})
        if version is not None and pref.version != version:
            raise HTTPException(409, detail={"code": "requirements_version_conflict"})
        return trip, pref

    def response(trip, pref):
        records = valid_records(pref.requirement_records)
        return {"version": pref.version, "records": records,
            "effective_by_date": {(trip.start_date.fromordinal(trip.start_date.toordinal() + i)).isoformat():
                project_requirements(records, trip_id=str(trip.id), city=trip.destination,
                    target_date=trip.start_date.fromordinal(trip.start_date.toordinal() + i))
                for i in range((trip.end_date - trip.start_date).days + 1)}}

    def scope_for(trip, day):
        if day and not trip.start_date <= day <= trip.end_date:
            raise HTTPException(422, detail={"code": "requirements_scope_out_of_range"})
        return {"kind": "day" if day else "trip", "trip_id": str(trip.id), "city": trip.destination,
            "date": day.isoformat() if day else None}

    @router.get("/{trip_id}/requirements")
    async def listing(trip_id: UUID, session=Depends(get_session)):
        trip, pref = await state(session, trip_id)
        return response(trip, pref)

    @router.post("/{trip_id}/requirements")
    async def add(trip_id: UUID, data: RequirementWrite, session=Depends(get_session)):
        trip, pref = await state(session, trip_id, data.expected_version)
        if (data.key == "pace" and data.value not in {"relaxed", "balanced", "intensive"}
                or data.key == "avoid_category" and data.value not in {"sight", "food", "culture", "nature", "shopping"}
                or data.key == "interest" and data.value not in {"history", "culture", "nature", "food", "photography", "shopping", "family", "nightlife"}
                or data.key == "walking_preference" and data.value != "minimal"
                or data.key in {"budget_fen", "daily_budget_fen", "max_walking_minutes"} and (isinstance(data.value, bool) or not isinstance(data.value, int) or data.value <= 0)
                or data.key == "max_walking_minutes" and isinstance(data.value, int) and data.value > 480):
            raise HTTPException(422, detail={"code": "invalid_requirement_value"})
        pref.requirement_records = add_requirement(pref.requirement_records, text=data.text,
            scope=scope_for(trip, data.day_date), source_ref=f"explicit-control:{uuid4()}",
            key=data.key, value=data.value, strength=data.strength)
        pref.version += 1
        await session.commit()
        return response(trip, pref)

    @router.post("/{trip_id}/requirements/revoke")
    async def revoke(trip_id: UUID, data: RequirementRevoke, session=Depends(get_session)):
        trip, pref = await state(session, trip_id, data.expected_version)
        scope = scope_for(trip, data.day_date) if data.day_date else None
        try:
            pref.requirement_records = revoke_requirement(pref.requirement_records, data.requirement_id,
                scope=scope, source_ref=f"explicit-control:{uuid4()}")
        except ValueError:
            raise HTTPException(404, detail={"code": "active_requirement_not_found"}) from None
        pref.version += 1
        await session.commit()
        return response(trip, pref)

    return router
