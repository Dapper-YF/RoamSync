"""Explicit, independently durable user decisions; no schedule or booking writes."""
import re
from datetime import datetime, date
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.config import get_settings
from app.database import SavedIntention, get_session
from app.assistant_memory import anchored_date


class IntentionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_text: str = Field(min_length=1, max_length=160)
    source_quote: str = Field(min_length=1, max_length=400)
    date_text: str = Field(default="", max_length=30)
    time_period: Literal["", "上午", "中午", "下午", "晚上", "全天"] = ""


def validate_proposals(proposals, message, focused_name=None):
    # Conservative current-user evidence. Extracted names never confer POI identity.
    if re.search(r"如果|假如|假设|要是|朋友|别人|他想|她想|听说|据说|[“”「」\"？?]|别保存|不保存|不要保存|先别记|不要记|先不记|不去|取消|只是看看", message):
        return []
    valid = []
    for p in proposals:
        q = p.source_quote
        if q not in message or not re.search(r"记下|记住|决定|确定|我(?:们)?(?:明天|后天|今天|下周|\d|上午|下午|晚上|打算|要|准备|就|去|想去)", q):
            continue
        if p.place_text not in q and not (p.place_text == focused_name and re.search(r"这里|这个地方|它", q)):
            continue
        if p.date_text and p.date_text not in message:
            continue
        if p.time_period and p.time_period not in message:
            continue
        if any(v.place_text == p.place_text and v.date_text == p.date_text and v.time_period == p.time_period for v in valid):
            continue
        valid.append(p)
    return valid


def intention_dict(row):
    return {"id": str(row.id), "source_session_id": str(row.scope_session_id),
        "source_message_id": str(row.source_message_id), "source_text": row.source_text,
        "captured_at": row.captured_at.isoformat(), "timezone": row.timezone,
        "place_text": row.place_text, "city_text": row.city_text,
        "intended_date": row.intended_date.isoformat() if row.intended_date else None,
        "time_period": row.time_period, "identity_status": "unverified",
        "status": row.status, "version": row.version,
        "linked_arrangement_item_id": str(row.linked_arrangement_item_id) if row.linked_arrangement_item_id else None}


async def persist_proposals(db, session_id, message_id, proposals, captured_at, city=None):
    items = []
    for index, p in enumerate(proposals):
        row = await db.scalar(select(SavedIntention).where(SavedIntention.scope_session_id == session_id,
            SavedIntention.source_message_id == message_id, SavedIntention.source_index == index))
        chosen = anchored_date(p.date_text, captured_at.date()) if p.date_text else None
        if p.date_text and not chosen:
            raise ValueError("打算中的日期无法核实，请保留原话后重试。")
        if row is None:
            row = SavedIntention(id=uuid4(), scope_session_id=session_id, source_session_id=session_id,
                source_message_id=message_id, source_index=index, source_text=p.source_quote,
                captured_at=captured_at, timezone="Asia/Shanghai", place_text=p.place_text,
                city_text=city, intended_date=date.fromisoformat(chosen) if chosen else None,
                time_period=p.time_period or None, status="active", version=1)
            db.add(row)
        items.append(row)
    await db.flush()
    return [intention_dict(i) for i in items]


router = APIRouter(prefix="/api/v1/saved-intentions", tags=["saved-intentions"])


def enabled():
    if not get_settings().saved_intentions_enabled:
        raise HTTPException(404, "独立打算暂未启用")


@router.get("")
async def listing(session_id: list[UUID] = Query(default=[], max_length=100), db=Depends(get_session)):
    enabled()
    # Existing local-session access model: caller supplies known IDs, never enumerate all sessions.
    if not session_id:
        return []
    rows = await db.scalars(select(SavedIntention).where(SavedIntention.scope_session_id.in_(session_id)).order_by(SavedIntention.captured_at.desc(), SavedIntention.id))
    return [intention_dict(r) for r in rows]


class IntentionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_session_id: UUID
    expected_version: int = Field(ge=1)


class TransferCommand(IntentionCommand):
    trip_id: UUID
    expected_trip_version: int = Field(ge=1)


async def locked(db, intention_id, payload):
    enabled()
    row = await db.scalar(select(SavedIntention).where(SavedIntention.id == intention_id,
        SavedIntention.scope_session_id == payload.source_session_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "打算不存在")
    return row


@router.post("/{intention_id}/revoke")
async def revoke(intention_id: UUID, payload: IntentionCommand, db=Depends(get_session)):
    row = await locked(db, intention_id, payload)
    if row.status == "cancelled" and row.version == payload.expected_version + 1:
        return intention_dict(row)
    if row.version != payload.expected_version or row.status != "active":
        raise HTTPException(409, "打算已经改变，请重新读取")
    row.status = "cancelled"
    row.version += 1
    await db.commit()
    return intention_dict(row)


@router.post("/{intention_id}/transfer")
async def transfer(intention_id: UUID, payload: TransferCommand, db=Depends(get_session)):
    from app.arrangement_service import ItemWrite, write_item
    from app.database import TripArrangementItem, Trip
    # Lock Trip before intention to match existing formal writer lock order.
    from app.formal_write import lock_trip
    await lock_trip(db, payload.trip_id)
    row = await locked(db, intention_id, payload)
    if row.status == "transferred":
        item = await db.get(TripArrangementItem, row.linked_arrangement_item_id)
        if item and item.trip_id == payload.trip_id and row.version == payload.expected_version + 1:
            return intention_dict(row)
        raise HTTPException(409, "打算已转入其他安排，请重新核对")
    if row.version != payload.expected_version or row.status != "active":
        raise HTTPException(409, "打算已经改变，请重新读取")
    trip = await db.get(Trip, payload.trip_id)
    from app.assistant_memory import local_today
    if trip.status in {"archived", "completed"} or trip.end_date < local_today():
        raise HTTPException(422, "历史旅行只供回看，请选择正在筹划或即将出发的旅行")
    if row.city_text and row.city_text.rstrip("市") != trip.destination.rstrip("市"):
        raise HTTPException(422, "地点城市与旅行不一致，请先核对")
    if row.intended_date and not trip.start_date <= row.intended_date <= trip.end_date:
        raise HTTPException(422, "打算日期不在这趟旅行内，不会自动移动日期")
    try:
        item = await write_item(db, payload.trip_id, ItemWrite(expected_version=payload.expected_trip_version,
            kind="selected", label=row.place_text, day_date=row.intended_date,
            source_ref=f"saved-intention:{row.id}"), commit=False)
        row.status = "transferred"
        row.version += 1
        row.linked_arrangement_item_id = item.id
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return intention_dict(row)
