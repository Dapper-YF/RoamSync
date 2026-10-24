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
    from _database_safety import validate_test_databases
    validate_test_databases(os.environ)
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


def test_composite_read_keeps_residual_day_and_scopes_meal_to_its_own_clause(sessions):
    from app.saved_trip_reads import render_saved_request
    async def run():
        async with sessions() as db:
            trip, days, activities = await seed(db)
            message = '总天数、第一天第一项、第二天所有活动、第三天午餐留白'
            snapshot = await load_saved_trip_read(db, trip.id, message)
            answer = render_saved_request(snapshot, message)
            assert '共3天' in answer and '合成地点1，' in answer
            assert '合成地点6，' in answer and '合成地点10，' in answer
            assert '2026-11-12 12:00—13:00 · 午餐留白' in answer
            assert '合成地点11，' not in answer
            ordinals = render_saved_request(snapshot, '第一天第一项和第一天第二项各停留多久')
            assert '合成地点1，' in ordinals and '合成地点2，' in ordinals
    asyncio.run(run())


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
            receipt = answer['read_tools']['original_rationale']
            assert receipt['decision_history_required'] and receipt['status'] == 'not_found'
            assert receipt['activity_ids'] == [str(activities[12].id)]
            assert not row.latest_run_id and not row.pending_action
    asyncio.run(run())


def test_compound_fallback_preserves_saved_day_scalar_question():
    from app.assistant_capabilities import component_question
    message='只查第三天，看看我选中的这个原来留了多久；同时查酒店到车站的驾车路线。'
    result=component_question('itinerary',message)
    assert all(t in result for t in ['第三天','选中','多久'])


def test_saved_state_task_does_not_require_unused_model_search_paraphrase():
    from app.assistant_capabilities import CapabilityDecision, validate_decision
    from app.assistant_context import ContextEnvelope
    message='第一天同名展馆的保存时长也查一下，不调整。'
    decision=CapabilityDecision(intent='itinerary',reason_code='saved_state',capabilities=['itinerary'],read_tasks=[
        {'source_quote':message,'capabilities':['itinerary'],'itinerary_purpose':'saved_values',
         'query':'第一天同名展馆保存的停留时长','names':['并非原句的规范名称']}])
    result=validate_decision(decision,message,[],ContextEnvelope())
    assert result.intent=='itinerary' and result.read_tasks
    assert result.read_tasks[0].query=='' and result.read_tasks[0].names==[]
    assert result.read_tasks[0].source_quote==message
    assert result.read_tasks[0].itinerary_purpose=='saved_values'


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
    async def route(*args, **kwargs):
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


@pytest.mark.parametrize('change', ['status_without_trip_version', 'trip', 'preferences'])
def test_real_pg_interleaved_commit_cannot_mix_snapshot_rows(sessions,monkeypatch,change):
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.saved_trip_reads import SavedTripReadStale
    original = AsyncSession.execute
    armed, fired = False, False
    async def run():
        nonlocal armed, fired
        async with sessions() as db:
            trip,days,activities = await seed(db)
            pref = TripPreferences(trip_id=trip.id,pace='balanced')
            db.add(pref);await db.commit()
            initial_trip_version, initial_pref_version = trip.version, pref.version
            async def interleave(reader, statement, *args, **kwargs):
                nonlocal fired
                result = await original(reader, statement, *args, **kwargs)
                if armed and not fired and 'count(activities.id)' in str(statement):
                    fired = True
                    async with sessions() as writer:
                        if change == 'preferences':
                            await writer.execute(update(TripPreferences).where(TripPreferences.trip_id==trip.id)
                                .values(pace='relaxed',version=TripPreferences.version+1))
                        else:
                            await writer.execute(update(Activity).where(Activity.id==activities[12].id)
                                .values(status='active',duration_minutes=99))
                            if change == 'trip':
                                await writer.execute(update(Trip).where(Trip.id==trip.id).values(version=Trip.version+1))
                        await writer.commit()
                return result
            monkeypatch.setattr(AsyncSession,'execute',interleave)
            armed = True
            if change != 'status_without_trip_version':
                with pytest.raises(SavedTripReadStale,match='重新读取'):
                    await load_saved_trip_read(db,trip.id,'第三天保存安排')
            else:
                snapshot = await load_saved_trip_read(db,trip.id,'第三天保存安排')
                value = next(a for a in snapshot.activities if a['activity_id']==str(activities[12].id))
                assert value['status']=='planned' and value['duration_minutes']==60
                assert snapshot.preferences['pace']=='balanced'
                # Reader does not commit, roll back or refresh caller ORM state.
                assert trip.version==initial_trip_version and pref.version==initial_pref_version
                async with sessions() as current:
                    stored = (await current.execute(select(Activity.status,Activity.duration_minutes)
                        .where(Activity.id==activities[12].id))).one()
                    assert stored.status=='active' and stored.duration_minutes==99
                    assert await current.scalar(select(Trip.version).where(Trip.id==trip.id))==initial_trip_version
            assert fired
    asyncio.run(run())


@pytest.mark.parametrize('message', ['为什么把选中的这个馆排这里？', '为什么这样安排行程？'])
def test_original_reason_and_notes_reject_detached_stale_version(sessions,message):
    from sqlalchemy import update
    from app.saved_trip_reads import SavedTripReadStale
    async def run():
        async with sessions() as db:
            trip,_,activities=await seed(db)
            snapshot=await load_saved_trip_read(db,trip.id,message,selected_activity_id=activities[12].id)
            async with sessions() as writer:
                await writer.execute(update(Trip).where(Trip.id==trip.id).values(version=Trip.version+1))
                await writer.commit()
            # The caller still holds its old ORM identity: checks must query DB.
            assert trip.version==snapshot.trip['version']
            with pytest.raises(SavedTripReadStale,match='重新读取'):
                await CompanionContextReader(db,trip.id,read_snapshot=snapshot).load(context(message),
                    InformationNeed(itinerary_required=True,decision_history_required=True))
    asyncio.run(run())


def test_detached_preferences_do_not_mix_later_commits(sessions):
    from sqlalchemy import update
    async def run():
        async with sessions() as db:
            trip,_,_=await seed(db)
            db.add(TripPreferences(trip_id=trip.id,pace='balanced'));await db.commit()
            snapshot=await load_saved_trip_read(db,trip.id,'第三天安排')
            async with sessions() as writer:
                await writer.execute(update(TripPreferences).where(TripPreferences.trip_id==trip.id)
                    .values(pace='relaxed',version=TripPreferences.version+1));await writer.commit()
            value=await CompanionContextReader(db,trip.id,read_snapshot=snapshot).load(context('第三天安排'),
                InformationNeed(itinerary_required=True,preferences_required=True,trip_context_required=True))
            assert value.saved_trip_preferences['pace']=='balanced'
            assert value.itinerary_read_coverage['preferences_version']==snapshot.trip['preferences_version']
    asyncio.run(run())


def test_legacy_reader_captures_before_projecting_trip_and_preferences(sessions,monkeypatch):
    import app.saved_trip_reads as module
    from sqlalchemy import update
    original=module.load_saved_trip_read
    async def run():
        async with sessions() as db:
            trip,_,_=await seed(db)
            db.add(TripPreferences(trip_id=trip.id,pace='balanced'));await db.commit()
            old_version=trip.version
            async def interleave(*args,**kwargs):
                async with sessions() as writer:
                    await writer.execute(update(Trip).where(Trip.id==trip.id).values(version=Trip.version+1))
                    await writer.execute(update(TripPreferences).where(TripPreferences.trip_id==trip.id)
                        .values(pace='relaxed',version=TripPreferences.version+1));await writer.commit()
                return await original(*args,**kwargs)
            monkeypatch.setattr(module,'load_saved_trip_read',interleave)
            value=await CompanionContextReader(db,trip.id).load(context('第三天已保存什么安排？'),
                InformationNeed(itinerary_required=True,trip_context_required=True,preferences_required=True))
            assert value.trip_summary['version']==value.itinerary_read_coverage['trip_version']==old_version+1
            assert value.saved_trip_preferences['pace']=='relaxed'
    asyncio.run(run())


def test_fixture_safety_accepts_standard_isolated_runner_database():
    from _database_safety import validate_test_databases
    validate_test_databases({'APP_ENV':'test','DATABASE_URL':
        'postgresql+psycopg://synthetic:synthetic@localhost:15435/roamsync_test_write_protection'})
    with pytest.raises(ValueError):
        validate_test_databases({'APP_ENV':'test','DATABASE_URL':
            'postgresql+psycopg://synthetic:synthetic@localhost:15435/roamsync'})


@pytest.mark.parametrize('cancel', [False, True])
def test_read_unit_is_readonly_and_closes_on_failure_without_flushing_caller(sessions,monkeypatch,cancel):
    import app.saved_trip_reads as module
    from sqlalchemy import event, text
    async def run():
        async with sessions() as db:
            trip,_,_=await seed(db)
            pending=Trip(id=uuid4(),title='must remain unflushed',destination='开封',
                start_date=date(2026,11,10),end_date=date(2026,11,12))
            db.add(pending)
            connections=[]
            def checkout(*args): connections.append('out')
            def checkin(*args): connections.append('in')
            event.listen(db.bind.sync_engine,'checkout',checkout)
            event.listen(db.bind.sync_engine,'checkin',checkin)
            captured=[]
            async def fail(reader,*args,**kwargs):
                captured.append(reader.bind)
                assert await reader.scalar(text('SHOW transaction_isolation'))=='repeatable read'
                assert await reader.scalar(text('SHOW transaction_read_only'))=='on'
                if cancel: raise asyncio.CancelledError()
                raise RuntimeError('synthetic capture failure')
            monkeypatch.setattr(module,'_capture_saved_trip_read',fail)
            try:
                with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
                    await module.load_saved_trip_read(db,trip.id)
                assert connections==[]  # independent read channel, no business pool borrowing
                assert captured[0].closed
                assert pending in db.new and db.in_transaction()
                assert await db.scalar(select(func.count()).select_from(Trip).where(Trip.id==pending.id),
                    execution_options={'autoflush':False})==0
            finally:
                event.remove(db.bind.sync_engine,'checkout',checkout)
                event.remove(db.bind.sync_engine,'checkin',checkin)
    asyncio.run(run())


def test_real_pg_saturated_business_pool_does_not_starve_saved_reads(sessions):
    from sqlalchemy import text
    async def run():
        async with sessions() as seed_db:
            trip,_,_=await seed(seed_db)
        engine=create_async_engine(os.environ['DATABASE_URL'],pool_size=2,max_overflow=0,pool_timeout=.25)
        factory=async_sessionmaker(engine,expire_on_commit=False)
        try:
            async with factory() as first, factory() as second:
                await first.execute(text('SELECT 1'));await second.execute(text('SELECT 1'))
                assert engine.pool.checkedout()==2
                reads=await asyncio.wait_for(asyncio.gather(
                    load_saved_trip_read(first,trip.id,'第三天已保存什么'),
                    load_saved_trip_read(second,trip.id,'第三天已保存什么')),timeout=5)
                assert all(len(r.project('第三天')['activities'])==5 for r in reads)
                assert engine.pool.checkedout()==2  # callers retain their own transactions
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_read_channel_admission_is_bounded_and_cancel_does_not_lose_permits(sessions,monkeypatch):
    import app.saved_trip_reads as module
    original=module._capture_saved_trip_read
    async def run():
        async with sessions() as db:
            trip,_,_=await seed(db)
        active,peak=0,0
        entered=asyncio.Event();release=asyncio.Event()
        async def hold(reader,*args,**kwargs):
            nonlocal active,peak
            active+=1;peak=max(peak,active)
            if active==2:entered.set()
            try:
                await release.wait()
                return await original(reader,*args,**kwargs)
            finally:active-=1
        monkeypatch.setattr(module,'_capture_saved_trip_read',hold)
        async def read():
            async with sessions() as db:
                return await module.load_saved_trip_read(db,trip.id,'第三天')
        tasks=[asyncio.create_task(read()) for _ in range(2)]
        pending=None
        try:
            await asyncio.wait_for(entered.wait(),5)
            pending=asyncio.create_task(read())
            await asyncio.sleep(.05)
            assert peak==2 and active==2
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):await pending
            release.set()
            assert len(await asyncio.gather(*tasks))==2
            # Subsequent reads still acquire permits after cancellation in queue.
            assert (await asyncio.wait_for(read(),5)).trip['id']==str(trip.id)
            assert peak==2
        finally:
            release.set()
            for task in [*tasks,*([pending] if pending else [])]:
                if not task.done():task.cancel()
            await asyncio.gather(*tasks,*([pending] if pending else []),return_exceptions=True)
    asyncio.run(run())
