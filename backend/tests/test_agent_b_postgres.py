"""B's exclusive DB: persisted withdrawal, reload and receipt-date anchoring."""
import asyncio
import os
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.assistant_capabilities import CapabilityDecision
from app.assistant_memory import MemoryUpdate
from app.assistant_service import send_message
from app.companion_contracts import CompanionDraft
from app.database import AssistantSession, Trip, Activity, PlanningRun, PlanRevision, SavedIntention


@pytest.fixture
def sessions():
    if os.environ.get("ROAMSYNC_AGENT_B_POSTGRES") != "1":
        pytest.skip("requires B's exclusive disposable PostgreSQL")
    url = os.environ["DATABASE_URL"]
    assert url == "postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_agent_b_test"
    engine = create_async_engine(url, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


def test_saved_withdrawal_survives_reload_without_unrequested_formal_writes(sessions, monkeypatch):
    seen = []
    async def generate(self, context, need):
        seen.append(context.assistant_context["conversation_memory"])
        return CompanionDraft(response_text="按当前有效条件继续讨论。")
    monkeypatch.setattr("app.companion_provider.ModelCompanionProvider.generate", generate)
    async def selector(settings, message, history, envelope, summary):
        if message == "我去柳州，11月22日出发":
            updates = [MemoryUpdate(field="city", value="柳州", source_quote="我去柳州")]
        elif message == "取消目的地，日期也先不定，原来的柳州先放下":
            # The semantic selector may mention the old city without emitting
            # its clear patch; literal withdrawal must still win.
            return CapabilityDecision(intent="direct", city="柳州", reason_code="stable_knowledge",
                memory_updates=[MemoryUpdate(field="start_date", operation="clear", source_quote="日期也先不定")])
        else:
            updates = []
        return CapabilityDecision(intent="direct", reason_code="stable_knowledge", memory_updates=updates)
    async def run():
        async with sessions() as db:
            before = [await db.scalar(select(func.count()).select_from(m)) for m in (Trip, Activity, PlanningRun, PlanRevision, SavedIntention)]
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row); await db.commit(); sid = row.id
            for message in ("我去柳州，11月22日出发", "取消目的地，日期也先不定，原来的柳州先放下"):
                await send_message(db, sid, message, uuid4(), context={}, capability_selector=selector)
        async with sessions() as db:
            row = await send_message(db, sid, "我们现在还确定去哪天去哪里吗？", uuid4(), context={}, capability_selector=selector)
            memory = row.messages[-1]["context"]["conversation_memory"]
            assert "city" not in memory["slots"] and "start_date" not in memory["slots"]
            assert row.messages[-1]["context"]["browsing_city"] is None
            assert "city" in memory["withdrawn"] and "start_date" in memory["withdrawn"]
            assert row.trip_id is None and row.pending_action is None and row.latest_run_id is None
            after = [await db.scalar(select(func.count()).select_from(m)) for m in (Trip, Activity, PlanningRun, PlanRevision, SavedIntention)]
            assert before == after
    asyncio.run(run())
    assert "start_date" not in seen[-1]["slots"]


def test_retry_anchors_relative_condition_to_saved_receipt_date(sessions, monkeypatch):
    async def generate(*args): return CompanionDraft(response_text="已读取这次出发日期。")
    monkeypatch.setattr("app.companion_provider.ModelCompanionProvider.generate", generate)
    async def selector(*args):
        return CapabilityDecision(intent="direct", reason_code="stable_knowledge", memory_updates=[
            MemoryUpdate(field="start_date", value="明天", source_quote="明天出发")])
    async def run():
        async with sessions() as db:
            mid = uuid4()
            # Simulate receipt before a midnight-spanning retry. Neither machine
            # date nor evaluation execution date determines this statement.
            receipt = datetime(2026, 10, 19, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
            row = AssistantSession(messages=[], applied_actions={f"message-capture:{mid}": receipt.isoformat()})
            db.add(row); await db.commit()
            row = await send_message(db, row.id, "明天出发", mid, context={}, capability_selector=selector)
            assert row.messages[-1]["context"]["conversation_memory"]["slots"]["start_date"]["value"] == "2026-10-20"
    asyncio.run(run())
