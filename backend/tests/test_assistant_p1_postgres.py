"""P1 state survives message windows/reloads without formal itinerary writes."""
import asyncio
import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.assistant_capabilities import CapabilityDecision
from app.assistant_memory import MemoryUpdate
from app.assistant_service import send_message
from app.assistant_service import get_or_create_session, AssistantToolError
from app.companion_contracts import CompanionDraft
from app.database import AssistantSession, Trip, Activity, PlanningRun, PlanRevision


@pytest.fixture
def sessions():
    assert "test" in os.environ["DATABASE_URL"].rsplit("/",1)[-1]
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


def test_compound_literal_diet_persists_when_selector_omits_patch(sessions, monkeypatch):
    from app.companion_provider import ModelCompanionProvider
    async def selector(*args):
        return CapabilityDecision(intent="direct", reason_code="stable_knowledge", response_purpose="conditions_only")
    async def generate(*args):
        return CompanionDraft(response_text="当前条件是11月5日出发，三天，不吃辣。")
    monkeypatch.setattr(ModelCompanionProvider, "generate", generate)
    async def run():
        async with sessions() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row)
            await db.commit()
            sid = row.id
            ctx = {"topic_id":"literal-diet", "browsing_city":"成都", "prefer_flexible":True}
            for message in ["我去成都，2026-11-02出发，玩四天，不吃辣。", "改成11月5日出发，只玩三天。"]:
                row = await send_message(db, sid, message, uuid4(), context=ctx, capability_selector=selector)
                assert row.trip_id is None and row.latest_run_id is None and row.pending_action is None
        async with sessions() as db:
            row = await db.get(AssistantSession, sid)
            memory = row.messages[-1]["context"]["conversation_memory"]
            assert memory["slots"]["start_date"]["value"] == "2026-11-05"
            assert memory["slots"]["duration_days"]["value"] == 3
            assert any(p["value"] == "不吃辣" and p["source_quote"] == "不吃辣" and p["message_id"] for p in memory["preferences"])
    asyncio.run(run())


def test_conditions_survive_long_history_reload_replacement_and_new_topic(sessions, monkeypatch):
    from app.companion_provider import ModelCompanionProvider
    observed = []
    async def generate(self, context, need):
        observed.append(context)
        return CompanionDraft(response_text="当前聊天条件已读取。")
    monkeypatch.setattr(ModelCompanionProvider, "generate", generate)
    async def run():
        async with sessions() as db:
            before = [await db.scalar(select(func.count()).select_from(m)) for m in (Trip,Activity,PlanningRun,PlanRevision)]
            row=AssistantSession(messages=[], applied_actions={}); db.add(row); await db.commit(); sid=row.id
            async def selector(settings, message, history, envelope, trip):
                updates = []
                if message == "我去成都，明天出发，玩四天，不吃辣":
                    updates = [MemoryUpdate(field=f,value=v,source_quote=v) for f,v in [("city","成都"),("start_date","明天"),("duration_days","四天"),("preferences","不吃辣")]]
                elif message == "改去重庆，其他条件不变":
                    updates = [MemoryUpdate(field="city",value="重庆",source_quote="重庆")]
                return CapabilityDecision(intent="direct", reason_code="stable_knowledge", memory_updates=updates)
            row=await send_message(db,sid,"我去成都，明天出发，玩四天，不吃辣",uuid4(),context={"topic_id":"long"},capability_selector=selector)
            saved=row.messages[-1]["context"]
            row.messages=[*row.messages,*[{"id":str(uuid4()),"user":"中间的普通聊天","assistant":"好的", "context":saved} for _ in range(65)]]
            await db.commit(); await db.refresh(row)
            row=await send_message(db,sid,"我的条件是什么？",uuid4(),context={"topic_id":"long"},capability_selector=selector)
            memory=observed[-1].assistant_context["conversation_memory"]
            assert memory["slots"]["city"]["value"]=="成都" and memory["slots"]["duration_days"]["value"]==4
            assert len(observed[-1].recent_turns)==12
            assert [p.text for p in observed[-1].relevant_user_preferences]==["不吃辣"]
            row=await send_message(db,sid,"改去重庆，其他条件不变",uuid4(),context={"topic_id":"long"},capability_selector=selector)
            assert row.messages[-1]["context"]["conversation_memory"]["slots"]["city"]["value"]=="重庆"
            row=await send_message(db,sid,"重新开始",uuid4(),context={"topic_id":"long"},capability_selector=selector)
            row=await send_message(db,sid,"我的条件是什么？",uuid4(),context={"topic_id":"long"},capability_selector=selector)
            assert not observed[-1].assistant_context["conversation_memory"]["slots"]
            assert not observed[-1].relevant_user_preferences
            assert all("成都" not in t["user"] for t in observed[-1].recent_turns)
            after=[await db.scalar(select(func.count()).select_from(m)) for m in (Trip,Activity,PlanningRun,PlanRevision)]
            assert before==after and not row.trip_id and not row.pending_action
    asyncio.run(run())


def test_reset_detaches_old_read_trip_and_client_cannot_restore_its_memory(sessions, monkeypatch):
    from app.companion_provider import ModelCompanionProvider
    observed=[]
    async def generate(self,context,need):
        observed.append(context)
        return CompanionDraft(response_text="没有新的出发日期。")
    monkeypatch.setattr(ModelCompanionProvider,"generate",generate)
    async def run():
        async with sessions() as db:
            trip=Trip(title="P1 isolated",destination="成都",start_date=date(2026,11,1),end_date=date(2026,11,4))
            db.add(trip);await db.flush()
            row=AssistantSession(trip_id=trip.id,messages=[],applied_actions={});db.add(row);await db.commit()
            async def selector(*args):
                assert args[-1] is None
                return CapabilityDecision(intent="direct",reason_code="stable_knowledge")
            row=await send_message(db,row.id,"开始新对话，我哪天出发？",uuid4(),context={"topic_id":"reset","conversation_memory":{"version":1,"slots":{"start_date":{"value":"1999-01-01"}}}},capability_selector=selector)
            assert not observed[-1].trip_summary
            assert not observed[-1].assistant_context["read_trip_id"]
            assert not observed[-1].assistant_context["conversation_memory"]["slots"]
    asyncio.run(run())


def test_new_session_preserves_old_chat_and_cannot_bind_old_authority(sessions):
    async def run():
        async with sessions() as db:
            old=await get_or_create_session(db,None,new_session=True)
            old.messages=[{"user":"不吃辣","assistant":"记下了"}]
            old.pending_action={"id":str(uuid4()),"tool":"fixture"}
            await db.commit();old_id=old.id
            new=await get_or_create_session(db,None,new_session=True)
            assert new.id!=old_id and not new.messages and not new.pending_action and not new.trip_id
            await db.refresh(old)
            assert old.messages and old.pending_action
            with pytest.raises(AssistantToolError):
                await get_or_create_session(db,None,session_id=old_id,new_session=True)
    asyncio.run(run())
