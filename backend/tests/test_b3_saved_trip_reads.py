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
