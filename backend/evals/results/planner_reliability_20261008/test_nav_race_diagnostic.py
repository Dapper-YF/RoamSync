import asyncio
from datetime import datetime,timedelta
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from test_navigation_sessions import _start_and_create_session,app,session_factory,DEMO_TRIP_ID,TZ
from app.database import Trip,NavigationSession
from app.navigation.session_service import refresh_route,supersede_navigation_sessions_for_itinerary,StaleNavigationWriteError
from app.navigation.providers import RoutingResult

@pytest.mark.parametrize('ordering',['commit_before_response','response_before_commit'])
def test_explicit_real_transaction_provider_ordering(ordering):
    with TestClient(app) as client:
        navigation_session_id=_start_and_create_session(client)['session']['id']
        async def run():
            entered,release=asyncio.Event(),asyncio.Event()
            class Controlled:
                async def route(self,request):
                    entered.set()
                    await asyncio.wait_for(release.wait(),timeout=10)
                    return RoutingResult(900,9,datetime(2026,9,5,9,tzinfo=TZ)+timedelta(minutes=9),'diagnostic_unit_fixture')
            pending=asyncio.create_task(refresh_route(session_factory,navigation_session_id,Controlled()))
            await asyncio.wait_for(entered.wait(),timeout=10)
            if ordering=='response_before_commit':
                release.set()
                result=await pending
                assert result.status=='active'
            async with session_factory() as session:
                trip=await session.scalar(select(Trip).where(Trip.id==DEMO_TRIP_ID).with_for_update())
                await supersede_navigation_sessions_for_itinerary(session,trip.id,trip.version)
                trip.version+=1
                await session.commit()
            if ordering=='commit_before_response':
                release.set()
                with pytest.raises(StaleNavigationWriteError):await pending
            async with session_factory() as session:
                item=await session.get(NavigationSession,navigation_session_id)
                assert item.status=='superseded' and item.itinerary_version==1
        asyncio.run(run())
