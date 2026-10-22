"""Real persistence, read-transaction and write-fence checks in the test database."""
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from app.assistant_capabilities import CapabilityDecision
from app.assistant_service import send_message, AssistantToolError
from app.companion_contracts import CompanionDraft
from app.database import session_factory, AssistantSession, Trip, Activity, PlanningRun, PlanRevision


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    assert 'test' in os.environ['DATABASE_URL'].rsplit('/',1)[-1]
    engine=create_async_engine(os.environ['DATABASE_URL'],poolclass=NullPool)
    monkeypatch.setattr(__import__(__name__,fromlist=['session_factory']),'session_factory',async_sessionmaker(engine,expire_on_commit=False))
    yield
    asyncio.run(engine.dispose())


CONTEXT={'version':'assistant-context-v1','topic_id':'p0-tests','browsing_city':'成都','prefer_flexible':True}


async def new_session(db):
    row=AssistantSession(messages=[],applied_actions={})
    db.add(row);await db.commit()
    return row


def test_original_three_turns_persist_summary_and_replay_is_idempotent_without_writes(monkeypatch):
    from app.companion_provider import ModelCompanionProvider
    calls=[]
    async def generate(self,context,need):
        calls.append('answer')
        return CompanionDraft(response_text='成都可以逛人民公园、宽窄巷子、武侯祠、锦里和熊猫基地。')
    monkeypatch.setattr(ModelCompanionProvider,'generate',generate)
    async def run():
        async with session_factory() as db:
            row=await new_session(db)
            before=[await db.scalar(select(func.count()).select_from(m)) for m in [Trip,Activity,PlanningRun,PlanRevision]]
            await db.commit()
            async def selector(*args):
                assert not db.in_transaction()
                calls.append('selection')
                return CapabilityDecision(intent='direct',reason_code='stable_knowledge')
            for message in ['展开说说：尝试成都牛油老火锅与串串香','如果我明天去成都的话，计划玩几天比较合适','那就玩四天的吧，帮我罗列一下成都的所有热门景点']:
                mid=uuid4()
                row=await send_message(db,row.id,message,mid,context=CONTEXT,capability_selector=selector)
                assert row.messages[-1]['execution_summary']['answer_status']=='complete'
                assert row.messages[-1]['goal_routing']['target_runtime']=='companion'
                n=len(calls)
                row=await send_message(db,row.id,message,mid,context=CONTEXT,capability_selector=selector)
                assert len(calls)==n
            after=[await db.scalar(select(func.count()).select_from(m)) for m in [Trip,Activity,PlanningRun,PlanRevision]]
            assert before==after and len(row.messages)==3
            await db.rollback()
    asyncio.run(run());assert calls==['selection','answer']*3


def test_failure_summary_survives_a_new_session_and_retry_uses_new_id(monkeypatch):
    from app.companion_provider import ModelCompanionProvider
    async def generate(*args):raise RuntimeError('private provider response not for storage')
    monkeypatch.setattr(ModelCompanionProvider,'generate',generate)
    async def selector(*args):return CapabilityDecision(intent='direct',reason_code='stable_knowledge')
    async def run():
        async with session_factory() as db:
            row=await new_session(db);sid=row.id;mid=uuid4()
            row=await send_message(db,sid,'列出成都热门景点',mid,context=CONTEXT,capability_selector=selector)
            assert row.messages[-1]['execution_summary']['answer_status']=='failed'
        async with session_factory() as db:
            row=await db.get(AssistantSession,sid)
            summary=row.messages[-1]['execution_summary']
            assert summary['events'][-1]['exception_chain']==['RuntimeError']
            assert 'private provider' not in str(summary)
            row=await send_message(db,sid,'列出成都热门景点',uuid4(),context=CONTEXT,capability_selector=selector)
            assert len(row.messages)==2
    asyncio.run(run())


def test_late_query_cannot_overwrite_a_new_conversation_decision():
    async def run():
        async with session_factory() as db:
            row=await new_session(db);sid=row.id
            async def selector(*args):
                async with session_factory() as other:
                    current=await other.get(AssistantSession,sid)
                    current.messages=[{'id':str(uuid4()),'user':'新问题','assistant':'新决定'}]
                    await other.commit()
                return CapabilityDecision(intent='clarify',clarification='哪个地点？',reason_code='missing_arguments')
            with pytest.raises(AssistantToolError,match='新的决定'):
                await send_message(db,sid,'查地点',uuid4(),context=CONTEXT,capability_selector=selector)
            current=await db.get(AssistantSession,sid)
            assert len(current.messages)==1 and current.messages[0]['user']=='新问题'
    asyncio.run(run())


@pytest.mark.parametrize('text',['如果改成三天会怎样','先别修改，只讨论轻松游','四天吧，列出景点'])
def test_model_write_proposal_does_not_grant_authority(text,monkeypatch):
    from app.companion_provider import ModelCompanionProvider
    async def generate(*args):return CompanionDraft(response_text='可以先讨论旅行选择。')
    monkeypatch.setattr(ModelCompanionProvider,'generate',generate)
    async def selector(*args):return CapabilityDecision(intent='modify',authorization_quote=text,reason_code='explicit_write')
    async def run():
        async with session_factory() as db:
            row=await new_session(db)
            row=await send_message(db,row.id,text,uuid4(),context=CONTEXT,capability_selector=selector)
            assert row.trip_id is None and row.pending_action is None and row.latest_run_id is None
            assert row.messages[-1]['goal_routing']['mutation_requested'] is False
    # A model quoting the whole '四天吧' cannot create authority. No action verb.
    asyncio.run(run())


def test_total_read_deadline_persists_a_retryable_failure(monkeypatch):
    import app.assistant_turn as module
    from app.assistant_reliability import TurnDiagnostics
    monkeypatch.setattr(module,'TurnDiagnostics',lambda ref:TurnDiagnostics(ref,seconds=.04))
    async def selector(*args):
        await asyncio.sleep(.2)
        raise AssertionError('must be cancelled')
    async def run():
        async with session_factory() as db:
            row=await new_session(db)
            row=await send_message(db,row.id,'列出成都热门景点',uuid4(),context=CONTEXT,capability_selector=selector)
            summary=row.messages[-1]['execution_summary']
            assert summary['answer_status']=='failed' and summary['answer_attempts']==0
            assert any(e.get('category')=='timeout' for e in summary['events'])
    asyncio.run(run())


def test_legacy_client_keeps_legacy_history_and_uses_the_same_read_pipeline(monkeypatch):
    from app.companion_provider import ModelCompanionProvider
    async def generate(*args):return CompanionDraft(response_text='成都可以慢慢逛。')
    monkeypatch.setattr(ModelCompanionProvider,'generate',generate)
    seen=[]
    async def selector(settings,message,history,envelope,summary):
        seen.append([m['user'] for m in history])
        return CapabilityDecision(intent='direct',reason_code='stable_knowledge')
    async def run():
        async with session_factory() as db:
            row=await new_session(db)
            row.messages=[{'id':str(uuid4()),'user':'我想去成都','assistant':'可以先了解景点。'}];await db.commit()
            for question in ['成都玩几天？','那就四天吧，先讨论']:
                row=await send_message(db,row.id,question,uuid4(),capability_selector=selector)
                assert row.messages[-1]['execution_summary']['answer_status']=='complete'
    asyncio.run(run())
    assert seen==[['我想去成都'],['我想去成都','成都玩几天？']]


def test_field_answer_continues_saved_planning_dialogue_without_new_authority():
    from app.assistant_turn import semantic_turn
    from app.config import Settings
    async def run():
        async with session_factory() as db:
            row=await new_session(db)
            row.messages=[{'id':str(uuid4()),'user':'帮我安排成都四天行程','assistant':'准备什么时候出发？','tool':'reply',
                'context':CONTEXT,'goal_routing':{'target_runtime':'planning','mutation_requested':True,'signals':['semantic_explicit_user_request']}}]
            await db.commit()
            async def forbidden(*args):raise AssertionError('existing clarification must not invoke another semantic selector')
            handled,goal,meta=await semantic_turn(db,row.id,'明天出发',uuid4(),CONTEXT,None,Settings(),forbidden)
            assert handled is None and goal.target_runtime=='planning' and not goal.mutation_requested
            assert meta['execution_summary']['selection']['reason_code']=='planning_field_follow_up'
            assert row.trip_id is None and row.pending_action is None
    asyncio.run(run())
