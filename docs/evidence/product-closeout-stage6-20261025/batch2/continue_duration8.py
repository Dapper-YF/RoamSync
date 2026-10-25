"""Continue the exact live-generated Revision: read, defer, adopt, reread."""
import asyncio,hashlib,importlib.util,json,os,re,subprocess,sys
from pathlib import Path
from time import monotonic
from uuid import UUID,uuid4
ROOT=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
OUT=Path(__file__).parent/'batch2-real-duration-followup4.json'
if OUT.exists():raise ValueError('Refuse overwrite')
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
configured=Settings(_env_file='E:/Study/RoamSync/.env')
for key in type(configured).model_fields:
    if key.startswith(('planner_','tavily_','roamsync_tavily_')) or key in ('amap_rest_key','intent_reasoning_effort','research_reasoning_effort'):
        value=getattr(configured,key)
        os.environ[key.upper()]=(value.get_secret_value() if hasattr(value,'get_secret_value') else str(value)).replace('host.docker.internal','127.0.0.1')
if not os.environ.get('PLANNER_PROXY_URL'):
    from dotenv import dotenv_values
    os.environ['PLANNER_PROXY_URL']=(dotenv_values('E:/Study/RoamSync/.env').get('HTTP_PROXY') or '').replace('host.docker.internal','127.0.0.1')
DSN='postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_agent_b3_stage6_duration8_test'
os.environ.update(APP_ENV='test',DATABASE_URL=DSN.replace('postgresql://','postgresql+psycopg://'),LANGGRAPH_DATABASE_URL=DSN,ALLOW_MAP_ESTIMATES='false')
from app.config import get_settings
get_settings.cache_clear();settings=get_settings()
spec=importlib.util.spec_from_file_location('recording_only','E:/Study/RoamSync-stage4-evidence-20261025/run_stage4_sealed.py')
observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
observer.SECRETS=[getattr(configured,k).get_secret_value() for k in type(configured).model_fields if hasattr(getattr(configured,k),'get_secret_value')]
events=[];observer.install_observers(events)
import psycopg
from psycopg import sql
from sqlalchemy import create_engine,select
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from app.database import AssistantSession,PlanRevision,Trip,session_factory
from app.place_content.repository import ContentRepository
from app.place_content.provider import AMapContentProvider
from app.place_content.service import PlaceContentService
from app.drafts.repository import DraftRepository
from app.assistant_places import ContentServicePlaces
from app.assistant_service import send_message
prior=json.loads((OUT.parent/'batch2-real-duration-after8.json').read_text(encoding='utf-8'))
view=prior['new_revisions'][0];trip_id=UUID(view['trip_id']);revision_id=UUID(view['id'])
tables=['trips','source_records','place_candidates','day_plans','trip_preferences','activities','route_legs','trip_arrangement_items','planning_runs','plan_revisions']
def state():
    with psycopg.connect(DSN) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return {table:sorted([r[0] for r in db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier(table)))],key=lambda r:str(r.get('id',r.get('trip_id')))) for table in tables}
def app_hash():
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'backend/app').rglob('*.py'))}
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
before_hash=app_hash()
assert before_hash==prior['app_sha256_after'],'Continuation source differs'
report={'kind':'same real generated object service continuation; not browser/independent score','source_sha256_before':before_hash,
    'prior':str(OUT.parent/'batch2-real-duration-after8.json'),'displayed_api_revision':view,'before':state(),'events':events,'records':[]}
def save():OUT.write_text(json.dumps(observer.normalized(report),ensure_ascii=False,indent=2,default=str),encoding='utf-8')
async def run():
    engine=create_async_engine(settings.database_url,poolclass=NullPool);sessions=async_sessionmaker(engine,expire_on_commit=False);session_factory.configure(bind=engine)
    sync=create_engine(settings.database_url,poolclass=NullPool)
    port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(sync)),DraftRepository(sync),owner='stage5-public-replay')
    async with sessions() as db:
        conversations=list(await db.scalars(select(AssistantSession).where(AssistantSession.latest_run_id==UUID(view['planning_run_id']))))
        assert len(conversations)==1;sid=conversations[0].id
    for message in ['这份修改候选具体改了哪一项、原来多久、建议多久？先不采用。','暂不采用，我再考虑一下。','明确采用当前这份修改候选并保存。','按当前保存状态回答：第一天第一项活动停留多久，其他活动与午餐留白是什么？']:
        mid=uuid4();item={'message':message,'before':state()};start=monotonic()
        async with sessions() as db:
            trip=await db.get(Trip,trip_id)
            context={'surface':'trip','read_trip_id':str(trip_id),'browsing_city':'苏州','action_target':{
                'trip_id':str(trip_id),'expected_version':trip.version,'operation':'plan_trip','authorization_message_id':str(mid),
                'revision_id':str(revision_id),'revision_hash':view['presentation_hash']}}
            item['request_context']=context
            try:
                result=await asyncio.wait_for(send_message(db,sid,message,mid,context=context,place_port=port),120)
                item['raw']=result.messages[-1]
            except Exception as error:item['error']=observer.error(error)
        item.update(after=state(),seconds=monotonic()-start)
        item['business_8_unchanged']=all(item['before'][table]==item['after'][table] for table in tables[:8])
        report['records'].append(item);save()
        print(json.dumps({'message':message,'answer':item.get('raw',{}).get('assistant'),'error':item.get('error'),'business_unchanged':item['business_8_unchanged']},ensure_ascii=False),flush=True)
    report.update(after=state(),source_sha256_after=app_hash(),source_unchanged=app_hash()==before_hash);save()
    await engine.dispose();sync.dispose()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(run())
