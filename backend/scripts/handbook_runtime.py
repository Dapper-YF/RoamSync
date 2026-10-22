"""Explicitly isolated handbook runtime and real-provider acceptance."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from app.config import Settings,get_settings
source=Settings(_env_file=str(ROOT.parent/'.env'))
for name in ('planner_provider','planner_api_key','planner_model','planner_base_url','planner_proxy_url','planner_reasoning_effort','planner_max_candidates','planner_timeout_seconds','planner_max_output_tokens','amap_rest_key','tavily_api_key','roamsync_tavily_api_key','tavily_base_url','tavily_proxy_url'):
    v=getattr(source,name);v=v.get_secret_value() if hasattr(v,'get_secret_value') else str(v)
    os.environ[name.upper()]=v.replace('host.docker.internal','127.0.0.1')
if not os.environ.get('PLANNER_PROXY_URL'):
    info=json.loads(subprocess.check_output(['docker','inspect','roamsync-api']))[0]
    runtime=dict(i.split('=',1) for i in info['Config']['Env'] if '=' in i)
    os.environ['PLANNER_PROXY_URL']=runtime.get('HTTP_PROXY','').replace('host.docker.internal','127.0.0.1')
os.environ.update(APP_ENV='test',DATABASE_URL='postgresql+psycopg://handbook_test:handbook_test@127.0.0.1:15433/roamsync_handbook_test',LANGGRAPH_DATABASE_URL='postgresql://handbook_test:handbook_test@127.0.0.1:15433/roamsync_handbook_test',ROAMSYNC_ISOLATED_INTEGRATION='1',ROAMSYNC_INTEGRATION_TOKEN='handbook-isolated-only',ROAMSYNC_INTEGRATION_OWNER='handbook-synthetic-user',ROAMSYNC_LOCAL_ORIGINS='http://127.0.0.1:3033,http://localhost:3033',ALLOW_MAP_ESTIMATES='false')
get_settings.cache_clear()
OUT=ROOT.parent/'docs/evidence/handbook-20261022'
OUT.mkdir(parents=True,exist_ok=True)


async def real_intentions():
    from uuid import uuid4
    from sqlalchemy import select,func
    from app.database import session_factory,AssistantSession,SavedIntention,Trip,Activity
    from app.assistant_service import send_message
    from app.assistant_places import ContentServicePlaces
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository
    from app.place_content.service import PlaceContentService
    from sqlalchemy import create_engine
    sync=create_engine(get_settings().database_url)
    port=ContentServicePlaces(PlaceContentService(AMapContentProvider(get_settings().amap_rest_key),ContentRepository(sync)),owner='handbook-synthetic-user')
    cases=[('explicit-relative','我明天下午去人民公园，几点再说。',True),('undated','记下宽窄巷子，日期没定。',True),('hypothetical','如果我明天去人民公园，会不会太赶？',False),('third-party','朋友想去人民公园，我还没想好。',False),('no-save','人民公园先了解一下，不要保存。',False),('knowledge','成都人为什么喜欢喝茶？',False)]
    results=[]
    for label,message,expect in cases:
        async with session_factory() as db:
            row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit();sid=row.id
            before=[await db.scalar(select(func.count()).select_from(t)) for t in (Trip,Activity)]
            try:
                row=await send_message(db,sid,message,uuid4(),context={'version':'assistant-context-v1','topic_id':'handbook-live','browsing_city':'成都','prefer_flexible':True},place_port=port)
                last=row.messages[-1];saved=last.get('saved_intentions',[])
                after=[await db.scalar(select(func.count()).select_from(t)) for t in (Trip,Activity)]
                result={'case':label,'passed':bool(saved)==expect and after==before and row.trip_id is None,'saved_count':len(saved),'response':last.get('assistant'),'execution_summary':last.get('execution_summary'),'session_id':str(sid)}
                if expect:result['passed']=result['passed'] and last.get('intention_write_result')=='saved'
            except Exception as exc:result={'case':label,'passed':False,'error_type':type(exc).__name__}
            results.append(result);(OUT/'real-intentions.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'case':label,'passed':result['passed']},ensure_ascii=False),flush=True)
    return all(r['passed'] for r in results)


async def seed_handbook():
    from datetime import date,time
    from uuid import uuid4
    from sqlalchemy import select
    from app.database import session_factory,DayPlan,Activity,Trip
    from app.repository import create_trip
    from app.schemas import TripCreate
    from app.maps_service import search_amap_places
    from app.planner_repository import _resolve_place
    from app.arrangement_service import write_item,ItemWrite
    title='成都 · 四日慢旅行（隔离验收）'
    async with session_factory() as db:
        existing=await db.scalar(select(Trip).where(Trip.title==title))
        if existing and await db.scalar(select(Activity.id).join(DayPlan).where(DayPlan.trip_id==existing.id).limit(1)):
            print('Fixture exists',str(existing.id));return
        trip=existing or await create_trip(db,TripCreate(title=title,destination='成都',start_date=date(2026,11,2),end_date=date(2026,11,5)))
        days=list((await db.scalars(select(DayPlan).where(DayPlan.trip_id==trip.id).order_by(DayPlan.date))).all())
        for index,(query,clock,mins,locked) in enumerate([('人民公园',time(10),60,True),('宽窄巷子',time(13),90,False)]):
            results=await search_amap_places(query,'成都')
            fixture_ids={'人民公园':'B001C7X8QA','宽窄巷子':'B001C7YCM4'}
            exact=[p for p in results if p.provider_place_id==fixture_ids[query]]
            if len(exact)!=1:raise ValueError('Synthetic fixture needs unique real POI identity: '+query)
            place=await _resolve_place(db,days[1],None,exact[0]);await db.flush()
            db.add(Activity(id=uuid4(),day_plan_id=days[1].id,place_candidate_id=place.id,scheduled_time=clock,duration_minutes=mins,estimated_cost_fen=place.estimated_cost_fen,status='planned',position=index,schedule_locked=locked,custom_name='茶艺体验（合成预约，未核验订单）' if locked else None))
        await db.commit()
        await write_item(db,trip.id,ItemWrite(expected_version=trip.version,kind='free_window',label='自由活动',source_ref='synthetic-handbook-fixture',day_date=days[1].date,start=time(15),end=time(16)))
        data={'trip_id':str(trip.id),'day_id':str(days[1].id),'title':title,'poi_source':'actual AMap query','schedule_and_booking':'synthetic fixture only'}
        (OUT/'fixture.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(data,ensure_ascii=False),flush=True)


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='init':
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async def init():
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:await saver.setup()
        asyncio.run(init())
    elif mode=='api':
        import uvicorn
        asyncio.run(uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',port=18033,log_level='warning')).serve())
    elif mode=='worker':
        from app.agent_worker import main
        asyncio.run(main())
    elif mode=='real':raise SystemExit(0 if asyncio.run(real_intentions()) else 1)
    elif mode=='seed':asyncio.run(seed_handbook())
