"""Real selector/answer capture on exclusively created synthetic test databases.

Can run against a supplied baseline checkout with the same public input. No
production writes, schema updates or old sealed questions. Refuses overwrite.
"""
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
    engine=create_async_engine(settings.database_url,poolclass=NullPool)
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    async with sessions() as db:
        trip=Trip(title='Synthetic B3 read evaluation',destination='开封',start_date=date(2026,11,10),end_date=date(2026,11,12))
        db.add(trip);await db.flush()
        source=SourceRecord(trip_id=trip.id,title='Synthetic only; no venue facts',url='https://fixture.invalid/b3',
            provider='fixture',confidence='medium',queried_at=datetime.now(UTC));db.add(source);await db.flush()
        days=[DayPlan(trip_id=trip.id,date=date(2026,11,10+i),position=i,label=f'Day{i+1}',theme='Synthetic') for i in range(3)]
        db.add_all(days);await db.flush();activities=[]
        for i in range(15):
            place=PlaceCandidate(trip_id=trip.id,source_record_id=source.id,slug=f'b3-{i}',
                name='同名展馆' if i in {2,12} else f'合成地点{i+1}',category='sight',neighborhood='',description='Synthetic only',
                longitude=114.3+i/10000,latitude=34.8,suggested_duration_minutes=45,estimated_cost_fen=0,rating=0,tags=[])
            db.add(place);await db.flush()
            a=Activity(day_plan_id=days[i//5].id,place_candidate_id=place.id,scheduled_time=time(9+i%5),
                duration_minutes=60 if i==12 else 45,estimated_cost_fen=0,position=i%5,schedule_locked=i==14,status='planned')
            db.add(a);activities.append(a)
        db.add(TripPreferences(trip_id=trip.id))
        db.add(TripArrangementItem(trip_id=trip.id,kind='optional',label='南岸茶室',source_ref='message:fixture',
            decision_ref='fixture',identity_key='tea',day_date=days[2].date))
        db.add(TripArrangementItem(trip_id=trip.id,kind='free_window',label='午餐留白',source_ref='message:fixture',
            decision_ref='fixture',identity_key='lunch',day_date=days[2].date,start_time=time(12),end_time=time(13)))
        row=AssistantSession(trip_id=trip.id,messages=[],applied_actions={});db.add(row);await db.commit()
        sid,tid=row.id,trip.id;selected_ids=[a.id for a in activities]
    async def formal_state():
        async with sessions() as db:
            result={}
            for model in (Trip,DayPlan,Activity,TripPreferences,TripArrangementItem,RouteLeg,PlanningRun,PlanRevision):
                records=[dict(r) for r in (await db.execute(select(model.__table__))).mappings()]
                records.sort(key=lambda r: str(r.get('id',r.get('trip_id'))))
                result[model.__name__]={'count':len(records),'sha256':hashlib.sha256(json.dumps(records,sort_keys=True,default=str).encode()).hexdigest()}
            return result
    report={'split':data['split'],'label':args.label,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.app_root,text=True).strip(),
        'app_sha256_before':source_hash(args.app_root),'fixture_sha256':hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
        'model':settings.planner_model,'provider':settings.planner_provider,'model_and_selector_real':True,
        'synthetic_trip_state':True,'external_provider_facts_seeded':False,
        'before':await formal_state(),'records':[]}
    report['config_fingerprint']=hashlib.sha256(json.dumps({'model':settings.planner_model,'provider':settings.planner_provider,
        'base':settings.planner_base_url,'timeout':settings.planner_timeout_seconds,'retries':settings.planner_max_retries},sort_keys=True,default=str).encode()).hexdigest()
    dump(output,report)
    current_observation=[]
    for module_name in ['assistant_capabilities','companion_provider']:
        module=importlib.import_module('app.'+module_name);original=module.create_model_response
        async def observed(*a,_fn=original,_stage=module_name,**kw):
            result=await _fn(*a,**kw)
            current_observation.append({'stage':_stage,'status':result.status,'visible_output':result.output_text})
            return result
        module.create_model_response=observed
    for index,turn in enumerate(data['turns'],1):
        current_observation=[];choices=[];calls=[]
        port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(sync)),owner='b3-synthetic')
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
        record={'turn':index,'user':turn['user'],'must':turn['must'],'selection_supplied':turn['selected'] is not None}
        started=monotonic()
        try:
            async with sessions() as db:
                row=await asyncio.wait_for(send_message(db,sid,turn['user'],uuid4(),context={'topic_id':'b3-public','read_trip_id':str(tid)},
                    selected_activity_id=selected_ids[turn['selected']] if turn['selected'] is not None else None,
                    place_port=port,capability_selector=selector),timeout=120)
                record.update(raw=row.messages[-1],pending_action=row.pending_action,latest_run_id=str(row.latest_run_id) if row.latest_run_id else None)
        except Exception as exc:
            record.update(error_type=type(exc).__name__,error_code=getattr(exc,'code',None))
        record.update(seconds=round(monotonic()-started,3),choices=choices,calls=calls,model_outputs=current_observation,formal_state=await formal_state())
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
    if args.output.exists():raise SystemExit('Refusing to overwrite a previous raw capture')
    if not re.fullmatch(r'roamsync_agent_b3_[a-z0-9_]+_test',args.database_name):raise SystemExit('Exclusive synthetic test database required')
    import psycopg
    from psycopg import sql
    with psycopg.connect('postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/postgres',autocommit=True) as conn:
        if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(args.database_name,)).fetchone():raise SystemExit('Test database already exists; use a new name')
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(args.database_name)))
    sys.path.insert(0,str(args.app_root/'backend'))
    from app.config import Settings,get_settings
    configured=Settings(_env_file=args.settings_source)
    for name in ['planner_provider','planner_api_key','planner_model','planner_base_url','planner_proxy_url',
                 'amap_rest_key','tavily_api_key','roamsync_tavily_api_key','tavily_base_url','tavily_proxy_url']:
        value=getattr(configured,name);value=value.get_secret_value() if hasattr(value,'get_secret_value') else str(value)
        os.environ[name.upper()]=value.replace('host.docker.internal','127.0.0.1')
    if not os.environ.get('PLANNER_PROXY_URL'):
        runtime=json.loads(subprocess.check_output(['docker','inspect','roamsync-api']))[0]
        env=dict(v.split('=',1) for v in runtime['Config']['Env'] if '=' in v)
        os.environ['PLANNER_PROXY_URL']=env.get('HTTP_PROXY','').replace('host.docker.internal','127.0.0.1')
    url='postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/'+args.database_name
    os.environ.update(APP_ENV='test',DATABASE_URL=url,LANGGRAPH_DATABASE_URL=url.replace('+psycopg',''),
        PLANNER_MAX_RETRIES='0',ALLOW_MAP_ESTIMATES='false')
    get_settings.cache_clear();settings=get_settings()
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args,settings,json.loads(args.fixture.read_text(encoding='utf-8')),args.output))


if __name__=='__main__':main()
