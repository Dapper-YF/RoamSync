"""Public regression replay of an actual generated pending object, real model.

No new candidate construction, source fact edits, model/AMap mock or production
write. This tests reading a historical real object, not fresh golden generation.
"""
import asyncio,hashlib,importlib.util,json,os,re,subprocess,sys
from datetime import UTC,datetime
from pathlib import Path
from time import monotonic
from uuid import UUID,uuid4

ROOT=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
OUT=Path(__file__).parent/'batch2-real-duration-after7.json'
CAPTURE=Path('E:/Study/RoamSync-stage4-evidence-20261025/runtime-final-v6/browser-states/pending60.json')
DATABASE='roamsync_agent_b3_stage6_duration7_test'
if OUT.exists():raise ValueError('Refuse overwrite')
def source_hash():
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'backend/app').rglob('*.py'))}
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
before_hash=source_hash()
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
configured=Settings(_env_file='E:/Study/RoamSync/.env')
for key in ('planner_provider','planner_api_key','planner_model','planner_base_url','planner_proxy_url',
    'planner_max_output_tokens','planner_max_candidates','planner_reasoning_effort','intent_reasoning_effort','research_reasoning_effort','planner_timeout_seconds','amap_rest_key','tavily_api_key','roamsync_tavily_api_key',
    'tavily_base_url','tavily_proxy_url','search_timeout_seconds','companion_knowledge_strategy'):
    value=getattr(configured,key)
    value=value.get_secret_value() if hasattr(value,'get_secret_value') else str(value)
    os.environ[key.upper()]=value.replace('host.docker.internal','127.0.0.1')
if not os.environ.get('PLANNER_PROXY_URL'):
    from dotenv import dotenv_values
    os.environ['PLANNER_PROXY_URL']=(dotenv_values('E:/Study/RoamSync/.env').get('HTTP_PROXY') or '').replace('host.docker.internal','127.0.0.1')
base='postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/'
os.environ.update(APP_ENV='test',DATABASE_URL=(base+DATABASE).replace('postgresql://','postgresql+psycopg://'),
    LANGGRAPH_DATABASE_URL=base+DATABASE,PLANNER_MAX_RETRIES='0',ALLOW_MAP_ESTIMATES='false')
spec=importlib.util.spec_from_file_location('recording_only','E:/Study/RoamSync-stage4-evidence-20261025/run_stage4_sealed.py')
observer=importlib.util.module_from_spec(spec);spec.loader.exec_module(observer)
observer.SECRETS=[getattr(configured,key).get_secret_value() for key in type(configured).model_fields
    if hasattr(getattr(configured,key),'get_secret_value')]
events=[];observer.install_observers(events)
from app.config import get_settings
get_settings.cache_clear();settings=get_settings()
import psycopg
from psycopg import sql
data=json.loads(CAPTURE.read_text(encoding='utf-8'))
tables=['trips','source_records','place_candidates','day_plans','trip_preferences','activities','route_legs',
    'trip_arrangement_items','planning_runs','plan_revisions','assistant_sessions']
with psycopg.connect(base+'postgres',autocommit=True) as db:
    if db.execute('select 1 from pg_database where datname=%s',(DATABASE,)).fetchone():raise ValueError('Refuse DB reuse')
    db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(DATABASE)))
from sqlalchemy import create_engine,event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from app.database import Base,AssistantSession,PlanRevision,session_factory
from app.place_content.repository import ContentRepository,metadata as content_metadata
from app.place_content.provider import AMapContentProvider
from app.place_content.service import PlaceContentService
from app.drafts.repository import DraftRepository,metadata as draft_metadata
from app.draft_promotion.repository import metadata as promotion_metadata
from app.assistant_places import ContentServicePlaces
from app.assistant_service import send_message
from app.revision_presentation import revision_presentation_hash
sync=create_engine(settings.database_url,poolclass=NullPool)
for metadata in (Base.metadata,content_metadata,draft_metadata,promotion_metadata):metadata.create_all(sync)
with psycopg.connect(base+DATABASE) as db:
    for table in tables:
        for row in data['tables'][table]:
            db.execute(sql.SQL('INSERT INTO {} SELECT * FROM jsonb_populate_record(NULL::{}, %s::jsonb)').format(sql.Identifier(table),sql.Identifier(table)),(json.dumps(row),))
    cloned={table:sorted([r[0] for r in db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier(table)))],key=lambda r:str(r.get('id',r.get('trip_id')))) for table in tables}
    assert cloned==data['tables'],'Exact captured rows differ'
formal=tables[:-1]
def state():
    with psycopg.connect(base+DATABASE) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return {table:sorted([r[0] for r in db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier(table)))],key=lambda r:str(r.get('id',r.get('trip_id')))) for table in formal}
@event.listens_for(Engine,'before_cursor_execute')
def writes(conn,cursor,statement,parameters,context,executemany):
    if re.match(r'\s*(INSERT|UPDATE|DELETE)\b',statement,re.I) and any(re.search(r'\b'+name+r'\b',statement,re.I) for name in formal):
        events.append({'kind':'formal_sql_attempt','statement':statement[:200]})
report={'kind':'public real-generated-object replay, not independent score or fresh golden',
    'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'app_sha256_before':before_hash,'snapshot':str(CAPTURE),'snapshot_sha256':hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
    'exact_11_table_clone':True,'database':DATABASE,'real_model':settings.planner_model,
    'provider':settings.planner_provider,'provider_retries':settings.planner_max_retries,'model_config':{key:getattr(settings,key) for key in ('planner_reasoning_effort','intent_reasoning_effort','research_reasoning_effort','planner_max_candidates','planner_timeout_seconds','planner_max_output_tokens','allow_map_estimates')},
    'config_endpoint_sha256':{key:hashlib.sha256(str(getattr(settings,key)).encode()).hexdigest()
        for key in ['planner_base_url','planner_proxy_url','tavily_base_url','tavily_proxy_url']},
    'config_note':'Same official read-only config and host proxy mapping as the prior successful runtime; no persisted config edits',
    'events':events,'before':state(),
    'baseline':'stage4 runtime-final-v6 original trace / saved conversation: same question answered candidate unavailable'}
def save():
    OUT.write_text(json.dumps(observer.normalized(report),ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
async def run():
    engine=create_async_engine(settings.database_url,poolclass=NullPool)
    sessions=async_sessionmaker(engine,expire_on_commit=False);session_factory.configure(bind=engine)
    port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(sync)),DraftRepository(sync),owner='stage5-public-replay')
    original=next(row for row in cloned['assistant_sessions'] if row['messages'])
    sid=UUID(original['id']);revision=next(row for row in cloned['plan_revisions'] if row['status']=='pending')
    mid=uuid4();message='请以当前保存版本为基线，把第一天第一项活动的停留时长增加15分钟，其他活动、午餐留白、日期、交通方式和个人偏好都保持原样。先只预览修改，暂不采用。'
    async with sessions() as db:
        stored=await db.get(PlanRevision,UUID(revision['id']))
        ctx=dict(original['messages'][-1]['context']);ctx['read_trip_id']=revision['trip_id']
        ctx['action_target']={'trip_id':revision['trip_id'],'expected_version':2,'operation':'plan_trip',
            'authorization_message_id':str(mid),'revision_id':revision['id'],'revision_hash':revision_presentation_hash(stored)}
        report.update(message=message,context=ctx,model_calls_before=len(events));save()
        started=monotonic()
        try:
            selector=None
            if '--recorded-selection' in sys.argv:
                trace=Path('E:/Study/RoamSync-stage4-evidence-20261025/runtime-final-v6/api-trace.ndjson')
                prior=[json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
                prior=[item for item in prior if item.get('kind')=='model'
                    and item.get('request',{}).get('text_format',{}).get('name')=='assistant_capabilities'
                    and json.loads(item['request']['input_text'])['message']==message]
                if len(prior)!=1:raise ValueError('Unique actual original failed selector required')
                proposal=json.loads(prior[0]['output'])
                from app.assistant_capabilities import CapabilityDecision
                async def selector(*_args):return CapabilityDecision.model_validate(proposal)
                report.update(selection_mode='Replay original actual selector output; answer provider is live',
                    recorded_selection=proposal,recorded_trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())
            else:report['selection_mode']='Live selector and answer provider'
            result=await asyncio.wait_for(send_message(db,sid,message,mid,context=ctx,place_port=port,capability_selector=selector),120)
            report.update(raw=result.messages[-1],pending_action=result.pending_action)
            next_run = result.latest_run_id
            prior_runs = {row['id'] for row in report['before']['planning_runs']}
            if next_run and str(next_run) not in prior_runs:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as saver:
                    await saver.setup()
                from app.agent_worker import claim_next_run,execute_claimed_run
                claim = await claim_next_run()
                if claim is None or claim.run_id != next_run:
                    raise ValueError('Worker did not claim this exclusive new Run')
                report['worker_claim'] = str(claim.run_id);save()
                try:
                    await asyncio.wait_for(execute_claimed_run(claim),240)
                except Exception as error:
                    report['worker_error']=observer.error(error)
                from sqlalchemy import select
                from app.database import PlanningRun
                from app.schemas import PlanRevisionResponse
                async with sessions() as check:
                    run_now=await check.get(PlanningRun,next_run)
                    report['run_after_worker']={key:getattr(run_now,key) for key in ('id','status','error_code','error_message','error_details') if hasattr(run_now,key)}
                    revisions=list(await check.scalars(select(PlanRevision).where(PlanRevision.planning_run_id==next_run)))
                    report['new_revisions']=[PlanRevisionResponse.model_validate(value).model_dump(mode='json') for value in revisions]

        except Exception as exc:report['error']=observer.error(exc)
        finally:report['seconds']=round(monotonic()-started,3)
    report['after']=state();report['formal_unchanged']=report['before']==report['after'];report['business_8_tables_unchanged']=all(report['before'][table]==report['after'][table] for table in tables[:8])
    report['app_sha256_after']=source_hash();report['source_unchanged']=before_hash==source_hash();save()
    await engine.dispose();sync.dispose()
    print(json.dumps({'output':str(OUT),'formal_unchanged':report['formal_unchanged'],'source_unchanged':report['source_unchanged'],
        'answer':report.get('raw',{}).get('assistant'),'error':report.get('error')},ensure_ascii=False))
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(run())
