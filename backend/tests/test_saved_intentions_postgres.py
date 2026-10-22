"""Dedicated test DB only: persistence, source deletion, CAS and atomic transfer."""
import asyncio
import os
from datetime import datetime, date
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.database import AssistantSession, SavedIntention, TripArrangementItem, Trip, Activity
from app.saved_intentions import (IntentionProposal, persist_proposals, listing, revoke, transfer,
    IntentionCommand, TransferCommand)


@pytest.fixture
def sessions():
    assert 'test' in os.environ['DATABASE_URL'].rsplit('/',1)[-1]
    engine=create_async_engine(os.environ['DATABASE_URL'],poolclass=NullPool)
    yield async_sessionmaker(engine,expire_on_commit=False)
    asyncio.run(engine.dispose())


def test_save_retry_reload_revoke_and_source_deletion(sessions):
    async def run():
        async with sessions() as db:
            row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit();sid=row.id;mid=uuid4()
            p=IntentionProposal(place_text='人民公园',source_quote='我明天下午去人民公园',date_text='明天',time_period='下午')
            stamp=datetime(2026,10,22,23,59,tzinfo=ZoneInfo('Asia/Shanghai'))
            first=await persist_proposals(db,sid,mid,[p],stamp,'成都');await db.commit()
            again=await persist_proposals(db,sid,mid,[p],stamp,'成都');await db.commit()
            assert first[0]['id']==again[0]['id'] and first[0]['intended_date']=='2026-10-23'
            iid=SavedIntention.__table__.c.id.type.python_type(first[0]['id'])
            # A second connection, not browser storage, restores saved data.
        async with sessions() as db:
            items=await listing([sid],db);assert any(i['id']==str(iid) for i in items)
            assert await listing([],db)==[]
            await db.execute(delete(AssistantSession).where(AssistantSession.id==sid));await db.commit()
            saved=await db.get(SavedIntention,iid);assert saved.source_session_id is None
            assert saved.intended_date==date(2026,10,23)
            command=IntentionCommand(source_session_id=sid,expected_version=1)
            revoked=await revoke(iid,command,db);assert revoked['version']==2
            assert (await revoke(iid,command,db))['version']==2
            with pytest.raises(HTTPException) as e: await revoke(iid,IntentionCommand(source_session_id=sid,expected_version=9),db)
            assert e.value.status_code==409
    asyncio.run(run())


def test_atomic_transfer_respects_date_version_and_does_not_create_activity(sessions):
    async def run():
        from app.repository import create_trip
        from app.schemas import TripCreate
        async with sessions() as db:
            trip=await create_trip(db,TripCreate(title='测试手册',destination='成都',start_date=date(2026,11,2),end_date=date(2026,11,5)))
            row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit()
            sid,tid=row.id,trip.id
            stamp=datetime(2026,10,22,tzinfo=ZoneInfo('Asia/Shanghai'))
            items=await persist_proposals(db,sid,uuid4(),[IntentionProposal(place_text='人民公园',source_quote='记下人民公园')],stamp,'成都');await db.commit()
            iid=SavedIntention.__table__.c.id.type.python_type(items[0]['id']);version=trip.version
            before=await db.scalar(select(func.count()).select_from(Activity))
            command=TransferCommand(source_session_id=sid,expected_version=1,trip_id=tid,expected_trip_version=version)
            result=await transfer(iid,command,db);assert result['status']=='transferred'
            assert (await transfer(iid,command,db))['linked_arrangement_item_id']==result['linked_arrangement_item_id']
            assert await db.scalar(select(func.count()).select_from(Activity))==before
            assert await db.scalar(select(func.count()).select_from(TripArrangementItem).where(TripArrangementItem.trip_id==tid))==1
    asyncio.run(run())


def test_semantic_save_is_atomic_with_message_and_does_not_create_trip(sessions):
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_service import send_message
    async def selector(*args):
        return CapabilityDecision(intent='direct',reason_code='explicit_write',saved_intentions=[IntentionProposal(place_text='人民公园',source_quote='我明天下午去人民公园，几点再说。',date_text='明天',time_period='下午')])
    async def run():
        async with sessions() as db:
            row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit();sid=row.id;mid=uuid4()
            before=await db.scalar(select(func.count()).select_from(Trip))
            row=await send_message(db,sid,'我明天下午去人民公园，几点再说。',mid,context={'topic_id':'intentions-test','browsing_city':'成都'},capability_selector=selector)
            assert row.messages[-1]['intention_write_result']=='saved'
            assert row.messages[-1]['saved_intentions'][0]['place_text']=='人民公园'
            assert row.trip_id is None and row.pending_action is None
            assert await db.scalar(select(func.count()).select_from(Trip))==before
            again=await send_message(db,sid,'我明天下午去人民公园，几点再说。',mid,context={'topic_id':'intentions-test'},capability_selector=selector)
            assert len(again.messages)==1
    asyncio.run(run())


def test_failed_attempt_receipt_anchors_retry_date(sessions):
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_service import send_message
    async def selector(*args):
        return CapabilityDecision(intent='direct',reason_code='explicit_write',saved_intentions=[IntentionProposal(place_text='人民公园',source_quote='我明天下午去人民公园',date_text='明天',time_period='下午')])
    async def run():
        async with sessions() as db:
            mid=uuid4()
            row=AssistantSession(messages=[],applied_actions={f'message-capture:{mid}':'2026-10-22T23:59:00+08:00'})
            db.add(row);await db.commit()
            row=await send_message(db,row.id,'我明天下午去人民公园',mid,context={'topic_id':'retry-date'},capability_selector=selector)
            assert row.messages[-1]['saved_intentions'][0]['intended_date']=='2026-10-23'
    asyncio.run(run())


def test_date_outside_trip_does_not_transfer_or_create_item(sessions):
    async def run():
        from app.repository import create_trip
        from app.schemas import TripCreate
        async with sessions() as db:
            trip=await create_trip(db,TripCreate(title='日期边界',destination='成都',start_date=date(2026,11,2),end_date=date(2026,11,5)))
            row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit()
            saved=await persist_proposals(db,row.id,uuid4(),[IntentionProposal(place_text='人民公园',source_quote='我明天去人民公园',date_text='明天')],datetime(2026,10,22,tzinfo=ZoneInfo('Asia/Shanghai')),'成都');await db.commit()
            iid=SavedIntention.__table__.c.id.type.python_type(saved[0]['id'])
            with pytest.raises(HTTPException) as e:await transfer(iid,TransferCommand(source_session_id=row.id,expected_version=1,trip_id=trip.id,expected_trip_version=trip.version),db)
            assert e.value.status_code==422
            assert (await db.get(SavedIntention,iid)).status=='active'
            assert await db.scalar(select(func.count()).select_from(TripArrangementItem).where(TripArrangementItem.trip_id==trip.id))==0
    asyncio.run(run())


def test_disabled_rollout_cannot_claim_an_intention_was_saved(sessions, monkeypatch):
    from app.config import get_settings
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_service import send_message
    monkeypatch.setattr(get_settings(), 'saved_intentions_enabled', False)
    async def selector(*args):
        return CapabilityDecision(intent='direct',reason_code='explicit_write',saved_intentions=[IntentionProposal(place_text='人民公园',source_quote='记下人民公园')])
    async def run():
        async with sessions() as db:
            row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit()
            before=await db.scalar(select(func.count()).select_from(SavedIntention))
            row=await send_message(db,row.id,'记下人民公园',uuid4(),context={'topic_id':'disabled'},capability_selector=selector)
            assert '尚未启用' in row.messages[-1]['assistant'] and 'saved_intentions' not in row.messages[-1]
            assert await db.scalar(select(func.count()).select_from(SavedIntention))==before
    asyncio.run(run())
