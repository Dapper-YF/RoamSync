"""Real PG saved-state reads; fixture names/itinerary are synthetic, no providers."""
import asyncio
from datetime import date, time, datetime, UTC
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import (Base, Trip, DayPlan, PlaceCandidate, SourceRecord, Activity,
                          TripArrangementItem, PlanningRun, PlanRevision, TripPreferences)
from app.companion_context import CompanionContextReader
from app.companion_contracts import CompanionContext, InformationNeed
from app.schemas import TravelGoalRouting
from app.saved_trip_reads import load_saved_trip_read, render_saved_read


@pytest.fixture
def sessions():
    assert os.environ['DATABASE_URL'].rsplit('/',1)[-1].startswith('roamsync_agent_b3_')
    engine=create_async_engine(os.environ['DATABASE_URL'],poolclass=NullPool)
    async def initialize():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(initialize())
    yield async_sessionmaker(engine,expire_on_commit=False)
    asyncio.run(engine.dispose())


async def seed(db, count=15):
    trip=Trip(title='Synthetic B3 scope',destination='开封',start_date=date(2026,11,10),end_date=date(2026,11,12))
    db.add(trip);await db.flush()
    source=SourceRecord(trip_id=trip.id,title='Synthetic only',url='https://fixture.invalid/b3',provider='fixture',confidence='medium',queried_at=datetime.now(UTC))
    db.add(source);await db.flush()
    days=[DayPlan(trip_id=trip.id,date=date(2026,11,10+i),position=i,label=f'Day{i+1}',theme='Synthetic') for i in range(3)]
    db.add_all(days);await db.flush()
    activities=[]
    for i in range(count):
        day_index=min(i//5,2)
        place=PlaceCandidate(trip_id=trip.id,source_record_id=source.id,slug='b3-'+str(i),
            name='同名展馆' if i in {2,12} else '合成地点'+str(i+1),category='sight',neighborhood='',
            description='Synthetic fixture',longitude=114.3+i/10000,latitude=34.8,
            suggested_duration_minutes=45,estimated_cost_fen=0,rating=0,tags=[])
        db.add(place);await db.flush()
        a=Activity(day_plan_id=days[day_index].id,place_candidate_id=place.id,
            scheduled_time=time(9+(i%5)),duration_minutes=45 if i!=12 else 60,
            estimated_cost_fen=0,position=i%5 if count==15 else i,
            schedule_locked=i==14,status='planned')
        db.add(a);activities.append(a)
    db.add(TripArrangementItem(trip_id=trip.id,kind='optional',label='南岸茶室',source_ref='message:fixture',decision_ref='fixture',identity_key='optional',day_date=days[2].date))
    db.add(TripArrangementItem(trip_id=trip.id,kind='free_window',label='午餐留白',source_ref='message:fixture',decision_ref='fixture',identity_key='lunch',day_date=days[2].date,start_time=time(12),end_time=time(13)))
    await db.commit()
    return trip,days,activities


def context(message):
    return CompanionContext(current_message=message,travel_goal=TravelGoalRouting(goal_type='travel_chat',confidence=.9,
        target_runtime='companion',mutation_requested=False,trip_context_required=True,knowledge_required=False,
        live_fact_likely_required=False))


def test_third_day_read_is_not_truncated_to_first_ten(sessions):
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db)
            before=[await db.scalar(select(func.count()).select_from(m)) for m in (Trip,DayPlan,Activity,TripArrangementItem,PlanRevision)]
            result=await CompanionContextReader(db,trip.id).load(context('只看第三天已保存的安排，备选也说一下，不修改。'),
                InformationNeed(itinerary_required=True,trip_context_required=True))
            assert {a['date'] for a in result.formal_itinerary_summary}=={'2026-11-12'}
            assert len(result.formal_itinerary_summary)==5
            assert any(a['name']=='合成地点15' for a in result.formal_itinerary_summary)
            after=[await db.scalar(select(func.count()).select_from(m)) for m in (Trip,DayPlan,Activity,TripArrangementItem,PlanRevision)]
            assert before==after
    asyncio.run(run())


def test_selected_same_name_identity_survives_detached_snapshot(sessions):
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db)
            snapshot=await load_saved_trip_read(db,trip.id,'选中的这个馆原来留多久？',selected_activity_id=activities[12].id)
            tid=trip.id
            await db.commit()
        async with sessions() as db:
            value=await CompanionContextReader(db,tid,read_snapshot=snapshot).load(context('选中的这个馆原来留多久？'),
                InformationNeed(itinerary_required=True,trip_context_required=True))
            assert [r['activity_id'] for r in value.formal_itinerary_summary]==[str(activities[12].id)]
            assert value.formal_itinerary_summary[0]['duration_minutes']==60
            assert value.itinerary_read_coverage['complete']
            text=render_saved_read(snapshot.project('选中的这个馆原来留多久？'))
            assert '60分钟' in text and '2026-11-12' in text and '2026-11-10' not in text
    asyncio.run(run())


def test_duplicate_name_without_selection_requires_disambiguation(sessions):
    async def run():
        async with sessions() as db:
            trip,_,_=await seed(db)
            snapshot=await load_saved_trip_read(db,trip.id,'同名展馆保存的时长是多少？')
            projection=snapshot.project('同名展馆保存的时长是多少？')
            assert len(projection['activities'])==2
            assert projection['coverage']['ambiguous'] and not projection['coverage']['complete']
            assert '没有唯一确定' in render_saved_read(projection)
            narrowed=snapshot.project('第三天同名展馆保存的时长是多少？')
            assert len(narrowed['activities'])==1 and narrowed['coverage']['complete']
    asyncio.run(run())


def test_requested_day_prioritized_before_limit_and_coverage_honest(sessions):
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db,count=105)
            snapshot=await load_saved_trip_read(db,trip.id,'只读第三天已保存安排',limit=10)
            projected=snapshot.project('只读第三天已保存安排')
            assert {r['date'] for r in projected['activities']}=={'2026-11-12'}
            assert projected['coverage']['matched_count']==95 and projected['coverage']['returned_count']==10
            assert not projected['coverage']['complete']
            assert '读取范围尚不完整' in render_saved_read(projected)
            focused=await load_saved_trip_read(db,trip.id,'我选中的活动留多久',selected_activity_id=activities[-1].id,limit=10)
            value=focused.project('我选中的活动留多久')
            assert [r['activity_id'] for r in value['activities']]==[str(activities[-1].id)]
            assert value['coverage']['complete']
    asyncio.run(run())


def test_outside_day_and_selected_conflict_do_not_fall_back_to_whole_trip(sessions):
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db)
            snapshot=await load_saved_trip_read(db,trip.id,'读第四天',selected_activity_id=activities[2].id)
            projection=snapshot.project('读第四天')
            assert not projection['activities'] and not projection['coverage']['complete']
            assert '没有匹配到这次旅行中的日期' in render_saved_read(projection)
            conflict=snapshot.project('读第三天我选中的这个馆')
            assert not conflict['activities'] and conflict['coverage']['ambiguous']
    asyncio.run(run())


def test_selected_context_cannot_cross_trip(sessions):
    async def run():
        async with sessions() as db:
            first,_,_=await seed(db)
            other,days,activities=await seed(db)
            with pytest.raises(ValueError,match='不属于'):
                await load_saved_trip_read(db,first.id,'选中活动',selected_activity_id=activities[0].id)
            with pytest.raises(ValueError,match='不属于'):
                await load_saved_trip_read(db,first.id,'选中日期',selected_day_id=days[0].id)
    asyncio.run(run())


def test_semantic_saved_scalar_uses_same_snapshot_and_never_calls_answer_model(sessions,monkeypatch):
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_service import send_message
    from app.database import AssistantSession
    from app.companion_provider import ModelCompanionProvider
    async def explode(*args,**kwargs):
        raise AssertionError('saved scalar must not ask prose model')
    monkeypatch.setattr(ModelCompanionProvider,'generate',explode)
    seen=[]
    async def selector(settings,message,history,envelope,trip):
        seen.append(trip)
        return CapabilityDecision(intent='itinerary',capabilities=['itinerary'],reason_code='saved_state',itinerary_purpose='saved_values')
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db)
            row=AssistantSession(trip_id=trip.id,messages=[],applied_actions={});db.add(row);await db.commit()
            before=[(a.id,a.version,a.duration_minutes,a.schedule_locked,a.status) for a in activities]
            row=await send_message(db,row.id,'选中的这个馆原来保存了多久？只查不改。',uuid4(),
                context={'topic_id':'b3-selected','read_trip_id':str(trip.id)},selected_activity_id=activities[12].id,
                capability_selector=selector)
            answer=row.messages[-1]
            assert '60分钟' in answer['assistant'] and '2026-11-12' in answer['assistant']
            assert '2026-11-10' not in answer['assistant']
            assert seen[-1]['activities'][0]['activity_id']==str(activities[12].id)
            assert seen[-1]['read_coverage']==answer['read_tools']['itinerary_read']
            assert not row.pending_action and not row.latest_run_id
            rows=(await db.scalars(select(Activity).where(Activity.id.in_([a.id for a in activities])))).all()
            assert sorted(before)==sorted((a.id,a.version,a.duration_minutes,a.schedule_locked,a.status) for a in rows)
    asyncio.run(run())


def test_original_rationale_purpose_reaches_existing_reader_without_inventing_reason(sessions,monkeypatch):
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_service import send_message
    from app.database import AssistantSession
    from app.companion_provider import ModelCompanionProvider
    async def explode(*args,**kwargs):
        raise AssertionError('missing original rationale is not a prose-generation task')
    monkeypatch.setattr(ModelCompanionProvider,'generate',explode)
    async def selector(*args):
        return CapabilityDecision(intent='itinerary',capabilities=['itinerary'],reason_code='saved_state',itinerary_purpose='original_rationale')
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db)
            row=AssistantSession(trip_id=trip.id,messages=[],applied_actions={});db.add(row);await db.commit()
            row=await send_message(db,row.id,'当时为什么把选中的这个馆排在这里？没保存理由就告诉我。',uuid4(),
                context={'topic_id':'b3-reason','read_trip_id':str(trip.id)},selected_activity_id=activities[12].id,
                capability_selector=selector)
            answer=row.messages[-1]
            assert '没有保存可验证的原始理由' in answer['assistant']
            assert answer['companion_result']['information_need']['decision_history_required']
            assert not row.latest_run_id and not row.pending_action
    asyncio.run(run())


def test_compound_fallback_preserves_saved_day_scalar_question():
    from app.assistant_capabilities import component_question
    message='只查第三天，看看我选中的这个原来留了多久；同时查酒店到车站的驾车路线。'
    result=component_question('itinerary',message)
    assert all(t in result for t in ['第三天','选中','多久'])


def test_calendar_date_and_day_selection_are_same_saved_scope(sessions):
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db)
            snapshot=await load_saved_trip_read(db,trip.id,'11月12日已保存什么？')
            for query in ['11月12日已保存什么？','2026-11-12已保存什么？','第三天已保存什么？','最后一天已保存什么？']:
                result=snapshot.project(query)
                assert len(result['activities'])==5 and result['coverage']['complete']
                assert {r['date'] for r in result['activities']}=={'2026-11-12'}
            redirected=snapshot.project('第三天以后再讨论。现在只列第二天正式安排，不改。')
            assert {r['date'] for r in redirected['activities']}=={'2026-11-11'}
    asyncio.run(run())


def test_independent_compound_saved_read_survives_route_failure(sessions,monkeypatch):
    import app.assistant_capabilities as module
    async def route(*args):
        return {'assistant':'车站名称有歧义，请选择具体车站。','place_cards':[],
            'read_tools':{'route':{'status':'unavailable'}}},'partial'
    monkeypatch.setattr(module,'route_answer',route)
    message='列出第三天正式安排；查酒店到车站的驾车路线。'
    decision=module.CapabilityDecision(intent='lookup',capabilities=['itinerary','route'],reason_code='saved_state',read_tasks=[
        {'source_quote':'列出第三天正式安排','capabilities':['itinerary'],'itinerary_purpose':'overview'},
        {'source_quote':'查酒店到车站的驾车路线','capabilities':['route'],'origin':'酒店','destination':'车站','mode':'driving'}])
    async def run():
        async with sessions() as db:
            trip,days,activities=await seed(db)
            snapshot=await load_saved_trip_read(db,trip.id,message)
            bundle,status=await module.answer_with_capabilities(None,decision,message,[],
                __import__('app.assistant_context',fromlist=['ContextEnvelope']).ContextEnvelope(),None,db,trip.id,'s','m',
                context(message).travel_goal,read_snapshot=snapshot)
            assert status=='partial'
            assert '合成地点15' in bundle['assistant'] and '车站名称有歧义' in bundle['assistant']
            assert bundle['read_tools']['tasks'][0]['read_tools']['itinerary_read']['complete']
            assert '2026-11-10' not in bundle['assistant']
    asyncio.run(run())
