import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant_service import AssistantToolError, confirm_action, get_or_create_session, reset_pre_trip_session, send_message, session_response
from app.database import get_session, session_factory
from app.maps_service import MapProviderError
from app.planning_errors import PlannerProviderError
from app.planning_intent_service import UnsupportedPlanningIntentError, IntentContextError
from app.repository import TripNotFoundError

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


class SessionInput(BaseModel):
    trip_id: uuid.UUID | None = None


class MessageInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    message_id: uuid.UUID
    selected_day_id: uuid.UUID | None = None
    selected_activity_id: uuid.UUID | None = None


class DecisionInput(BaseModel):
    action_id: uuid.UUID
    accept: bool


async def respond(operation):
    try:
        return session_response(await operation)
    except TripNotFoundError as exc:
        raise HTTPException(404, "旅行不存在") from exc
    except (AssistantToolError, UnsupportedPlanningIntentError, IntentContextError) as exc:
        raise HTTPException(422, {"message": str(exc)}) from exc
    except (MapProviderError, PlannerProviderError) as exc:
        raise HTTPException(502, {"message": str(exc)}) from exc


@router.post("/sessions")
async def session_endpoint(payload: SessionInput, db: AsyncSession = Depends(get_session)):
    return await respond(get_or_create_session(db, payload.trip_id))


@router.post("/sessions/{session_id}/reset")
async def reset_session_endpoint(session_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    return await respond(reset_pre_trip_session(db, session_id))


@router.post("/sessions/{session_id}/messages")
async def message_endpoint(session_id: uuid.UUID, payload: MessageInput, db: AsyncSession = Depends(get_session)):
    if not payload.message.strip():
        raise HTTPException(422, "请输入你的需求")
    return await respond(send_message(db, session_id, payload.message.strip(), payload.message_id,
        selected_day_id=payload.selected_day_id, selected_activity_id=payload.selected_activity_id))


@router.post("/sessions/{session_id}/decision")
async def decision_endpoint(session_id: uuid.UUID, payload: DecisionInput, db: AsyncSession = Depends(get_session)):
    return await respond(confirm_action(db, session_id, str(payload.action_id), payload.accept))


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message_endpoint(session_id: uuid.UUID, payload: MessageInput):
    if not payload.message.strip():
        raise HTTPException(422, "请输入你的需求")
    from app.assistant_stream import session_events
    async def events():
        # Own the DB lifetime inside the iterator, including older FastAPI
        # versions that finalize yield dependencies before sending the body.
        async with session_factory() as db:
            async def operation():
                return await respond(send_message(db, session_id, payload.message.strip(), payload.message_id,
                    selected_day_id=payload.selected_day_id, selected_activity_id=payload.selected_activity_id))
            async for event in session_events(operation, db):
                yield event
    return StreamingResponse(events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
