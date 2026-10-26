"""Real selector/answer capture on exclusively created synthetic test databases.

Can run against a supplied baseline checkout with the same public input. No
production writes, schema updates or old sealed questions. Refuses overwrite.
"""
import logging
logging.disable(logging.CRITICAL)
import argparse
import asyncio
from datetime import date, time, datetime, UTC
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic
from uuid import uuid4


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8')


def source_hash(root):
    values={p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root/'backend/app').rglob('*.py'))}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


async def run(args, settings, data, output):
    from sqlalchemy import create_engine, select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.database import (Base, AssistantSession, Trip, DayPlan, Activity, SourceRecord, PlaceCandidate,
        TripArrangementItem, TripPreferences, RouteLeg, PlanningRun, PlanRevision)
    from app.assistant_service import send_message
    from app.assistant_capabilities import select_capabilities
    from app.assistant_places import ContentServicePlaces
    from app.place_content.provider import AMapContentProvider
    from app.place_content.repository import ContentRepository, metadata as content_metadata
    from app.place_content.service import PlaceContentService
    sync=create_engine(settings.database_url,poolclass=NullPool)
    Base.metadata.create_all(sync);content_metadata.create_all(sync)
    from app.drafts.repository import metadata as draft_metadata, DraftRepository
    from app.draft_promotion.repository import metadata as promotion_metadata
    draft_metadata.create_all(sync);promotion_metadata.create_all(sync)
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as saver:
        await saver.setup()
    engine=create_async_engine(settings.database_url,poolclass=NullPool)
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    case_sessions={}
    selected_ids=[]
    async with sessions() as db:
        for case in data['cases']:
            row=AssistantSession(messages=[],applied_actions={})
            db.add(row);await db.flush();case_sessions[case['id']]=row.id
        await db.commit()
    async def formal_state():
        async with sessions() as db:
            result={}
            for model in (Trip,DayPlan,Activity,TripPreferences,TripArrangementItem,RouteLeg,PlanningRun,PlanRevision):
                records=[dict(r) for r in (await db.execute(select(model.__table__))).mappings()]
                records.sort(key=lambda r: str(r.get('id',r.get('trip_id'))))
                result[model.__name__]={'count':len(records),'sha256':hashlib.sha256(json.dumps(records,sort_keys=True,default=str).encode()).hexdigest(), 'rows':records}
            return result
    report={'split':data['split'],'label':args.label,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.app_root,text=True).strip(),
        'app_sha256_before':source_hash(args.app_root),'fixture_sha256':hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
        'model':settings.planner_model,'provider':settings.planner_provider,'model_and_selector_real':True,
        'synthetic_trip_state':False,'blank_formal_database':True,'external_provider_facts_seeded':False,
        'before':await formal_state(),'records':[]}
    report['config_fingerprint']=hashlib.sha256(json.dumps({'model':settings.planner_model,'provider':settings.planner_provider,
        'base':settings.planner_base_url,'timeout':settings.planner_timeout_seconds,'retries':settings.planner_max_retries},sort_keys=True,default=str).encode()).hexdigest()
    dump(output,report)
    report['runtime_source']={'cwd':os.getcwd(),'python':sys.executable,
        'database_module':sys.modules['app.database'].__file__,
        'assistant_module':sys.modules['app.assistant_service'].__file__}
    current_observation=[]
    for module_name in ['assistant_capabilities','companion_provider','assistant_research','openai_planner']:
        module=importlib.import_module('app.'+module_name);original=module.create_model_response
        async def observed(*a,_fn=original,_stage=module_name,**kw):
            try:
                result=await _fn(*a,**kw)
            except Exception as exc:
                body = getattr(exc, 'body', None)
                err = body.get('error', body) if isinstance(body, dict) else {}
                current_observation.append({'stage':_stage,'status':'failed','error_type':type(exc).__name__,
                    'http_status':getattr(exc,'status_code',None), 'provider_error_code':err.get('code')})
                raise
            current_observation.append({'stage':_stage,'status':result.status,'visible_output':result.output_text,'request':{k:v for k,v in kw.items() if k in ('model','instructions','input_text','text_format','reasoning_effort','max_output_tokens','temperature')}})
            return result
        module.create_model_response=observed
    current_external=[]
    def observe_external(fn, name):
        async def wrapped(*a, **kw):
            rec={'tool':name,'args':[v for v in a if isinstance(v,(str,int,float,bool))], 'kwargs':kw}
            current_external.append(rec)
            try:
                value=await fn(*a,**kw)
                rec['result']=value.model_dump(mode='json') if hasattr(value,'model_dump') else value
                return value
            except Exception as exc:
                rec['error_type']=type(exc).__name__;raise
        return wrapped
    for module_name, function_name in [('assistant_search','search_tavily'),('external_facts','search_tavily'),('external_facts','extract_tavily')]:
        module=importlib.import_module('app.'+module_name)
        setattr(module,function_name,observe_external(getattr(module,function_name),module_name+'.'+function_name))
    for index,turn in enumerate(data['turns'],1):
        current_observation=[];current_external=[];choices=[];calls=[]
        port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(sync)),DraftRepository(sync),owner='stage6-public-empty')
        for service_name in ['search', 'get_place', 'route']:
            service_fn = getattr(port.service, service_name, None)
            if service_fn:
                setattr(port.service, service_name, observe_external(service_fn, 'content_service.'+service_name))
        for name in ['get_place','search','research_search','query_route']:
            original=getattr(port,name,None)
            if not original:continue
            async def observed_tool(*a,_fn=original,_name=name,**kw):
                record={'tool':_name,'args':a,'kwargs':kw};calls.append(record)
                try:
                    result=await _fn(*a,**kw)
                    record['result']=[v.model_dump(mode='json') for v in result] if isinstance(result,list) else result.model_dump(mode='json') if hasattr(result,'model_dump') else result
                    return result
                except Exception as exc:
                    record['error_type']=type(exc).__name__;raise
            setattr(port,name,observed_tool)
        async def selector(*a):
            value=await select_capabilities(*a);choices.append(value.model_dump(mode='json'));return value
        record={'case_id':turn['case_id'],'case_turn':turn['case_turn'],'turn':index,'user':turn['user'],'must':turn['must'],'selection_supplied':turn['selected'] is not None}
        started=monotonic()
        mid = uuid4()
        ctx = {'topic_id':turn['case_id'], 'prefer_flexible':True}
        async with sessions() as db:
            current = await db.get(AssistantSession,case_sessions[turn['case_id']])
            if current.trip_id:
                current_trip = await db.get(Trip,current.trip_id)
                ctx.update(surface='trip',read_trip_id=str(current.trip_id),action_target={
                    'trip_id':str(current.trip_id),'expected_version':current_trip.version,
                    'operation':'plan_trip','authorization_message_id':str(mid)})
                if current.latest_run_id:
                    revision = await db.scalar(select(PlanRevision).where(PlanRevision.planning_run_id==current.latest_run_id,
                        PlanRevision.trip_id==current.trip_id, PlanRevision.status=='pending'))
                    if revision:
                        from app.schemas import PlanRevisionResponse
                        shown=PlanRevisionResponse.model_validate(revision).model_dump(mode='json')
                        record['displayed_revision']=shown
                        ctx['action_target'].update(revision_id=str(revision.id),revision_hash=shown['presentation_hash'])
        record['request_context'] = ctx
        record['before_state'] = await formal_state()
        try:
            async with sessions() as db:
                row=await asyncio.wait_for(send_message(db,case_sessions[turn['case_id']],turn['user'],mid,context=ctx,
                    selected_activity_id=selected_ids[turn['selected']] if turn['selected'] is not None else None,
                    place_port=port,capability_selector=selector),timeout=120)
                record.update(raw=row.messages[-1],session_applied_actions=row.applied_actions,pending_action=row.pending_action,latest_run_id=str(row.latest_run_id) if row.latest_run_id else None)
                next_run = row.latest_run_id
            if next_run:
                async with sessions() as db:
                    run_now = await db.get(PlanningRun,next_run)
                    queued = run_now is not None and run_now.status=='queued'
                if queued:
                    from app.agent_worker import claim_next_run,execute_claimed_run
                    claim = await claim_next_run()
                    if claim:
                        record['worker_claim']={'run_id':str(claim.run_id), 'matches_requested':claim.run_id==next_run}
                        try:
                            await asyncio.wait_for(execute_claimed_run(claim),240)
                        except Exception as exc:
                            record['worker_error_type']=type(exc).__name__
        except Exception as exc:
            record.update(error_type=type(exc).__name__,error_code=getattr(exc,'code',None))
        record.update(seconds=round(monotonic()-started,3),choices=choices,calls=calls,external_calls=current_external,model_outputs=current_observation,formal_state=await formal_state())
        report['records'].append(record);dump(output,report)
        print(json.dumps({'label':args.label,'turn':index,'seconds':record['seconds'],'error_type':record.get('error_type')}),flush=True)
    report.update(after=await formal_state(),app_sha256_after=source_hash(args.app_root))
    report['source_unchanged']=report['app_sha256_before']==report['app_sha256_after']
    report['formal_state_unchanged']=report['before']==report['after']
    dump(output,report)
    await engine.dispose();sync.dispose()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app-root',type=Path,required=True)
    parser.add_argument('--settings-source',type=Path,required=True);parser.add_argument('--database-name',required=True)
    parser.add_argument('--label',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,default=Path(__file__).parent/'fixtures/b3_scoped_read_public.json');args=parser.parse_args()
    if args.app_root.resolve() != Path('E:/Study/RoamSync').resolve():
        raise SystemExit('Official source directory required by this authorized merge review')

    if args.output.exists():raise SystemExit('Refusing to overwrite a previous raw capture')
    if not re.fullmatch(r'roamsync_s6_(?:a|b)_[a-z0-9_]+_test',args.database_name):raise SystemExit('Exclusive official-review test database required')
    import psycopg
    from psycopg import sql
    with psycopg.connect('postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/postgres',autocommit=True) as conn:
        if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(args.database_name,)).fetchone():raise SystemExit('Test database already exists; use a new name')
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(args.database_name)))
    os.chdir(args.app_root/'backend')
    sys.path.insert(0,str(args.app_root/'backend'))
    from app.config import Settings,get_settings
    configured=Settings(_env_file=args.settings_source)
    for name in ['planner_provider','planner_api_key','planner_model','planner_base_url','planner_proxy_url',
                 'planner_reasoning_effort','planner_max_output_tokens','planner_timeout_seconds','planner_max_candidates',
                 'intent_reasoning_effort','research_reasoning_effort','amap_rest_key','tavily_api_key','roamsync_tavily_api_key','tavily_base_url','tavily_proxy_url']:
        value=getattr(configured,name);value=value.get_secret_value() if hasattr(value,'get_secret_value') else str(value)
        os.environ[name.upper()]=value.replace('host.docker.internal','127.0.0.1')
    if not os.environ.get('PLANNER_PROXY_URL'):
        from dotenv import dotenv_values
        values=dotenv_values(args.settings_source)
        os.environ['PLANNER_PROXY_URL']=(values.get('HTTP_PROXY') or '').replace('host.docker.internal','127.0.0.1')
    url='postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/'+args.database_name
    os.environ.update(APP_ENV='test',DATABASE_URL=url,LANGGRAPH_DATABASE_URL=url.replace('+psycopg',''),
        PLANNER_MAX_RETRIES='0',ALLOW_MAP_ESTIMATES='false')
    get_settings.cache_clear();settings=get_settings()
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    cases=json.loads(args.fixture.read_text(encoding='utf-8'))
    turns=[{'case_id':c['id'],'case_turn':i+1,'user':message,'must':c['criteria'][i],'selected':None} for c in cases for i,message in enumerate(c['messages'])]
    asyncio.run(run(args,settings,{'split':'stage6-public-development-not-independent','cases':cases,'turns':turns},args.output))


if __name__=='__main__':main()
