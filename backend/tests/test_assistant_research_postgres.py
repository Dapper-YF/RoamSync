import asyncio
import os
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from app.database import AssistantSession
from app.assistant_service import send_message, AssistantToolError
from app.assistant_context import ContextEnvelope

def test_no_lock_during_network_and_late_result_rejected():
    async def scenario():
        url = os.environ["DATABASE_URL"]
        assert make_url(url).database == "roamsync_test_write_protection"
        engine = create_async_engine(url, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                row = AssistantSession(messages=[], applied_actions={})
                db.add(row); await db.commit(); sid = row.id
                async def lookup(*args):
                    assert not db.in_transaction()
                    async with sessions() as other:
                        saved = await other.scalar(select(AssistantSession).where(AssistantSession.id == sid).with_for_update(nowait=True))
                        saved.messages = [{"id": str(uuid.uuid4()), "user": "新决定", "assistant": "保留"}]
                        await other.commit()
                    return {"assistant": "迟到结果"}
                with pytest.raises(AssistantToolError, match="新的决定"):
                    await send_message(db, sid, "成都哪家火锅好吃", uuid.uuid4(), context=ContextEnvelope().model_dump(), researcher=lookup)
                await db.refresh(row)
                assert len(row.messages) == 1 and row.messages[0]["user"] == "新决定"
        finally: await engine.dispose()
    asyncio.run(scenario())

def test_retry_idempotent_and_failed_save_rolled_back():
    async def scenario():
        url = os.environ["DATABASE_URL"]
        assert make_url(url).database == "roamsync_test_write_protection"
        engine = create_async_engine(url, poolclass=NullPool)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                row = AssistantSession(messages=[], applied_actions={})
                db.add(row); await db.commit(); sid = row.id
                calls = []
                async def lookup(*args):
                    assert not db.in_transaction(); calls.append(1)
                    return {"assistant": "已查到", "place_cards": [], "read_tools": {}}
                mid = uuid.uuid4()
                await send_message(db, sid, "成都哪家火锅好吃", mid, context=ContextEnvelope().model_dump(), researcher=lookup)
                await send_message(db, sid, "成都哪家火锅好吃", mid, context=ContextEnvelope().model_dump(), researcher=lookup)
                assert len(calls) == 1 and len(row.messages) == 1
                await db.commit()
                original = db.commit
                async def fail_commit():
                    if len(row.messages) > 1: raise RuntimeError("injected commit failure")
                    await original()
                db.commit = fail_commit
                with pytest.raises(RuntimeError, match="commit failure"):
                    await send_message(db, sid, "成都哪家火锅好吃", uuid.uuid4(), context=ContextEnvelope().model_dump(), researcher=lookup)
                await db.rollback(); await db.refresh(row)
                assert len(row.messages) == 1
        finally: await engine.dispose()
    asyncio.run(scenario())
