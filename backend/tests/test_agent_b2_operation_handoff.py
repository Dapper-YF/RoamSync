import asyncio
from datetime import date
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
import pytest
import os

from app.assistant_capabilities import CapabilityDecision
from app.assistant_service import AssistantRouter, send_message
from app.database import AssistantSession
from app.schemas import CitySuggestionResponse


@pytest.fixture
def sessions():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


def test_single_approved_creation_prepares_preview_without_second_router(sessions, monkeypatch):
    message = "请创建绍兴2026年11月29日至30日的安排，第一天下午去鲁迅故里，第二天留空，先看候选等我采用。"
    async def selector(*args):
        return CapabilityDecision.model_validate({"intent":"create", "reason_code":"explicit_write",
            "authorization_quote":"请创建绍兴2026年11月29日至30日的安排", "names":["鲁迅故里"],
            "creation":{"destination":"绍兴", "start_date":"2026-11-29", "end_date":"2026-11-30",
                "flexible":True, "choices":[{"kind":"selected", "label":"鲁迅故里", "day_date":"2026-11-29",
                    "source_quote":"第一天下午去鲁迅故里"}]}})
    async def forbidden(*args):
        raise AssertionError("a second router changed the approved creation")
    monkeypatch.setattr(AssistantRouter, "decide", forbidden)
    async def cities(*args):
        return [CitySuggestionResponse(name="绍兴市", adcode="330600", citycode="0575", longitude=120.58, latitude=30.0)]
    async def run():
        async with sessions() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row); await db.commit()
            row = await send_message(db, row.id, message, uuid4(), capability_selector=selector,
                city_search=cities, context={"topic_id":"b2-create", "prefer_flexible":True})
            assert row.trip_id is None and row.latest_run_id is None
            assert row.pending_action["choices"][0]["label"] == "鲁迅故里"
            assert row.pending_action["user_request"] == message
            assert "第二天留空" in row.pending_action["preferences"]
            assert "第一天下午去鲁迅故里" in row.messages[-1]["assistant"]
            assert row.pending_action["total_budget_fen"] is None
    asyncio.run(run())


def test_creation_cannot_invent_dates_or_expand_literal_place_label():
    from app.assistant_operation import approved_tool_decision
    from app.assistant_context import ContextEnvelope
    decision = CapabilityDecision.model_validate({"intent":"create", "reason_code":"explicit_write",
        "authorization_quote":"请创建成都一日候选", "creation":{"destination":"成都",
        "start_date":"2026-11-09", "end_date":"2026-11-09", "flexible":True}})
    result = approved_tool_decision(decision, "请创建成都一日候选", ContextEnvelope(), today=date(2026,10,22))
    assert result.tool == "reply" and "出发" in result.reply


def test_draft_operations_require_original_source_and_literal_place_mentions():
    from app.assistant_operation import approved_draft
    message = "请把第二天加入乙馆，其他不动"
    for raw, name in [("请删除第一天甲馆", "甲馆"), (message, "乙馆景区")]:
        draft = {"primary_intent":"add_activity", "operations":[{"operation":"add_activity", "raw_text":raw,
                 "place_mentions":[name]}], "confidence":.9, "parser_version":"model-output"}
        decision = CapabilityDecision.model_validate({"intent":"modify", "reason_code":"explicit_write",
            "authorization_quote":message, "planning_draft":draft})
        with pytest.raises(ValueError):
            approved_draft(decision, message)
