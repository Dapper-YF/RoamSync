"""Real-provider acceptance in an isolated DB. Never resets or writes official trips."""
import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from app.config import Settings, get_settings
source = Settings(_env_file=str(ROOT.parent / '.env'))
for name in ('planner_provider','planner_api_key','planner_model','planner_base_url','planner_proxy_url',
             'amap_rest_key','tavily_api_key','roamsync_tavily_api_key','tavily_base_url','tavily_proxy_url'):
    value=getattr(source,name)
    value=value.get_secret_value() if hasattr(value,'get_secret_value') else str(value)
    os.environ[name.upper()]=value.replace('host.docker.internal','127.0.0.1')
# Match the official container's effective model egress, without logging its env.
if not os.environ.get('PLANNER_PROXY_URL'):
    info=json.loads(subprocess.check_output(['docker','inspect','roamsync-api']))[0]
    runtime_env=dict(item.split('=',1) for item in info['Config']['Env'] if '=' in item)
    os.environ['PLANNER_PROXY_URL']=runtime_env.get('HTTP_PROXY','').replace('host.docker.internal','127.0.0.1')
os.environ.update(APP_ENV='test',DATABASE_URL='postgresql+psycopg://roamsync_test:roamsync_test_password@127.0.0.1:51421/roamsync_p0_test',
    LANGGRAPH_DATABASE_URL='postgresql://roamsync_test:roamsync_test_password@127.0.0.1:51421/roamsync_p0_test',
    PLANNER_MAX_RETRIES='0', ROAMSYNC_ISOLATED_INTEGRATION='1', ROAMSYNC_INTEGRATION_TOKEN='p0-isolated-test-only',
    ROAMSYNC_INTEGRATION_OWNER='p0-synthetic-user',ROAMSYNC_LOCAL_ORIGINS='http://127.0.0.1:3024',ALLOW_MAP_ESTIMATES='false')
get_settings.cache_clear()
OUT=ROOT.parent/'docs/evidence/assistant-p0-20261021'
OUT.mkdir(parents=True,exist_ok=True)
logging.basicConfig(level=logging.WARNING)


async def selection_run():
    from app.assistant_capabilities import select_capabilities
    from app.assistant_context import ContextEnvelope
    from app.assistant_reliability import TurnDiagnostics,active_turn,error_details
    from evals.assistant_capability_cases import CASES
    sem=asyncio.Semaphore(3);rows=[]
    async def one(case):
        async with sem:
            t=TurnDiagnostics(case['id']);token=active_turn.set(t);start=time.monotonic()
            try:
                d=await select_capabilities(get_settings(),case['message'],case.get('history',[]),ContextEnvelope(browsing_city='成都'),{'destination':'成都','title':'合成测试旅行'})
                ok=d.intent==case['intent'] and set(d.capabilities)==set(case['capabilities'])
                r={**case,'decision':d.model_dump(mode='json'),'pass':ok}
            except Exception as exc:
                r={**case,'pass':False,'error':error_details(exc,'selection')}
            finally:active_turn.reset(token)
            r['seconds']=round(time.monotonic()-start,2);rows.append(r)
            (OUT/'selection.json').write_text(json.dumps(sorted(rows,key=lambda r:r['id']),ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'id':case['id'],'pass':r['pass'],'seconds':r['seconds']},ensure_ascii=False),flush=True)
    await asyncio.gather(*(one(c) for c in CASES))


async def live_run(fixed=False, compound=False):
    from sqlalchemy import create_engine,select,func
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.database import AssistantSession,Trip,Activity,PlanningRun,PlanRevision
    from app.assistant_service import send_message
    from app.assistant_places import ContentServicePlaces
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository
    from app.place_content.service import PlaceContentService
    from app.assistant_reliability import error_details
    settings=get_settings();assert '127.0.0.1:51421/roamsync_p0_test' in settings.database_url
    engine=create_async_engine(settings.database_url,poolclass=NullPool);sessions=async_sessionmaker(engine,expire_on_commit=False)
    sync=create_engine(settings.database_url,poolclass=NullPool)
    port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(sync)),owner='p0-synthetic-user')
    bound_trip = None
    if compound:
        from app.repository import create_trip
        from app.schemas import TripCreate
        from datetime import date
        async with sessions() as db:
            trip = await create_trip(db, TripCreate(title='复合查询验收旅行',destination='成都市',start_date=date(2026,11,7),end_date=date(2026,11,8)))
            bound_trip = trip.id
    records=[];sem=asyncio.Semaphore(2)
    async def counts():
        async with sessions() as db:
            return {m.__tablename__:await db.scalar(select(func.count()).select_from(m)) for m in (Trip,Activity,PlanningRun,PlanRevision)}
    before=await counts()
    async def scenario(name,questions,case=None,bound=None):
        async with sem:
            async with sessions() as db:
                history=[{**m,'id':str(uuid4()),'assistant':m.get('assistant',''),'context':{'topic_id':'p0-eval','version':'assistant-context-v1','browsing_city':'成都','prefer_flexible':True}} for m in (case or {}).get('history',[])]
                row=AssistantSession(messages=history,applied_actions={},trip_id=bound);db.add(row);await db.commit();sid=row.id
            for n,q in enumerate(questions,1):
                start=time.monotonic();record={'scenario':name,'turn':n,'user':q}
                try:
                    async with sessions() as db:
                        row=await send_message(db,sid,q,uuid4(),context={'browsing_city':'成都','topic_id':'p0-eval','prefer_flexible':True,**({'read_trip_id':str(bound)} if bound else {})},place_port=port)
                        m=row.messages[-1]
                        record.update(answer=m.get('assistant'),summary=m.get('execution_summary'),goal=m.get('goal_routing'),
                            actual_tools=list(m.get('read_tools',{})),place_count=len(m.get('place_cards',[])),trip_id=str(row.trip_id) if row.trip_id else None,
                            pending_action=bool(row.pending_action),tool=m.get('tool'))
                        if case:
                            selected=(m.get('execution_summary')or{}).get('selection',{})
                            stages=[e['stage'] for e in (m.get('execution_summary')or{}).get('events',[]) if e.get('status')=='running']
                            tool_stages=[s for s in stages if s in {'poi','web','web_extract','route','facts'}]
                            permitted=set(case['capabilities'])|({'web','web_extract'} if 'facts' in case['capabilities'] else set())|({'web_extract'} if 'web' in case['capabilities'] else set())
                            record.update(expected=case,actual_call_order=tool_stages,
                                passed=(m.get('execution_summary')or{}).get('answer_status') in {'complete','partial'} and selected.get('intent')==case['intent'] and set(selected.get('capabilities',[]))==set(case['capabilities']) and set(tool_stages)<=permitted
                                and (case['intent'] in {'create','modify'} or (row.trip_id is None and row.latest_run_id is None and row.pending_action is None)))
                except Exception as exc:record['error']=error_details(exc,'turn')
                record['seconds']=round(time.monotonic()-start,2);records.append(record)
                (OUT/('fixed-live.json' if fixed else 'compound-live.json' if compound else 'live.json')).write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'scenario':name,'turn':n,'status':(record.get('summary') or {}).get('answer_status'),'seconds':record['seconds']},ensure_ascii=False),flush=True)
    chengdu=['展开说说：尝试成都牛油老火锅与串串香','如果我明天去成都的话，计划玩几天比较合适','那就玩四天的吧，帮我罗列一下成都的所有热门景点']
    combinations=[
        ('direct-list',['列出成都十五个著名景点，简单介绍']),('food',['牛油火锅和串串香有什么区别？']),
        ('culture',['介绍成都的茶馆文化']),('days',['成都慢慢逛玩几天合适？']),
        ('no-write',['先别创建行程，告诉我成都四天够不够']),('hypothetical',['如果把四天改成三天，会有什么取舍？']),
        ('address',['查一下成都武侯祠的地址']),('map',['帮我定位成都人民公园']),
        ('nearby',['找成都人民公园附近的火锅店，只要店名地址']),('reviews',['成都玉林路有哪些值得吃的火锅店，帮我查查评价']),
        ('web-culture',['联网搜索成都的茶馆文化资料']),('booking',['帮我查成都博物馆最新官方预约规则']),
        ('event',['查成都本周的展览活动']),('walk',['从成都人民公园步行到宽窄巷子要多久？']),
        ('drive',['成都春熙路驾车到熊猫基地怎么走？']),('transit',['成都人民公园到武侯祠坐公交怎么走？']),
        ('weather',['成都明天会下雨吗？']),('hours',['成都博物馆今天几点闭馆？']),
        ('saved',['我的当前行程是什么？']),('create',['帮我安排成都四天行程']),
        ('walk-unambiguous',['从成都武侯祠博物馆步行到成都杜甫草堂博物馆要多久？']),
        ('drive-unambiguous',['从成都武侯祠博物馆驾车到成都杜甫草堂博物馆怎么走？']),
    ]
    if compound:
        await asyncio.gather(
            scenario('weather-route',['查成都明天的天气，并查询成都武侯祠博物馆到成都杜甫草堂博物馆的驾车路线']),
            scenario('web-route',['查询成都武侯祠博物馆到成都杜甫草堂博物馆的步行路线，并搜索成都博物馆官方预约资料']),
            scenario('itinerary-web-missing-target',['告诉我当前保存的行程，并联网搜索成都本周的展览']),
            scenario('weather-saved-itinerary',['查成都明天的天气，并告诉我当前已保存的行程有哪些安排'],bound=bound_trip),
            scenario('creation-field-continuation',['帮我安排成都四天行程','明天出发','先不要保存，只看建议']),
        )
    elif fixed:
        from evals.assistant_capability_cases import CASES
        await asyncio.gather(*(scenario(c['id'],[c['message']],c) for c in CASES))
    else:
        await asyncio.gather(*(scenario(f'chengdu-{i}',chengdu) for i in range(1,6)),*(scenario(n,qs) for n,qs in combinations))
    after=await counts();(OUT/('fixed-business-counts.json' if fixed else 'compound-business-counts.json' if compound else 'business-counts.json')).write_text(json.dumps({'before':before,'after':after,'unchanged':before==after},indent=2),encoding='utf-8')
    await engine.dispose();sync.dispose()


async def original_replay():
    """Read original context in memory; export no original conversation prose."""
    import hashlib
    from sqlalchemy import create_engine,select,func
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.database import AssistantSession,Trip,Activity,PlanningRun,PlanRevision
    from app.assistant_service import send_message
    from app.assistant_places import ContentServicePlaces
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository
    from app.place_content.service import PlaceContentService
    code="""import asyncio,json
from sqlalchemy import text
from app.database import engine
async def run():
 async with engine.connect() as c:
  history=(await c.execute(text(\"SELECT s.messages FROM assistant_sessions s WHERE EXISTS (SELECT 1 FROM json_array_elements(s.messages) m WHERE m->>'id'=:id)\"),{'id':'955ebf96-3426-46b5-96e2-be2ab61fcedf'})).scalar_one()
  m=next(m for m in history if m['id']=='955ebf96-3426-46b5-96e2-be2ab61fcedf')
  print(json.dumps({'history':history[:history.index(m)],'message':m},ensure_ascii=False))
 await engine.dispose()
asyncio.run(run())
"""
    original=json.loads(subprocess.check_output(['docker','exec','-i','roamsync-api','python','-'],input=code.encode('utf-8')))
    m=original['message'];context=m.get('context') or {}
    assert not context.get('read_trip_id') and not context.get('read_draft_id'), 'original replay requires additional private state'
    source_hash=hashlib.sha256(json.dumps(m,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    settings=get_settings();engine=create_async_engine(settings.database_url,poolclass=NullPool)
    sessions=async_sessionmaker(engine,expire_on_commit=False);sync=create_engine(settings.database_url,poolclass=NullPool)
    port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(sync)),owner='p0-synthetic-user')
    records=[]
    for i in range(1,6):
        async with sessions() as db:
            row=AssistantSession(messages=original['history'],applied_actions={});db.add(row);await db.commit();sid=row.id
            before=[await db.scalar(select(func.count()).select_from(model)) for model in (Trip,Activity,PlanningRun,PlanRevision)];await db.commit()
            row=await send_message(db,sid,m['user'],uuid4(),context=context,place_port=port)
            answer=row.messages[-1];after=[await db.scalar(select(func.count()).select_from(model)) for model in (Trip,Activity,PlanningRun,PlanRevision)]
            record={'replay':i,'source_message_sha256':source_hash,'summary':answer.get('execution_summary'),
                'answer':answer.get('assistant'),'formal_counts_unchanged':before==after,'trip_bound':row.trip_id is not None}
            records.append(record)
            (OUT/'original-replay-five.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'replay':i,'status':(record.get('summary')or{}).get('answer_status'),'characters':len(record.get('answer')or''),'formal_counts_unchanged':before==after}),flush=True)
    await engine.dispose();sync.dispose()


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='select':asyncio.run(selection_run())
    elif mode=='live':asyncio.run(live_run())
    elif mode=='fixed':asyncio.run(live_run(fixed=True))
    elif mode=='replay':asyncio.run(original_replay())
    elif mode=='compound':asyncio.run(live_run(compound=True))
    elif mode=='api':
        import uvicorn
        asyncio.run(uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',port=18024,log_level='warning')).serve())
