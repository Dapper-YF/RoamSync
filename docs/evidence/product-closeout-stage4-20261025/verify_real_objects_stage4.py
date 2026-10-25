"""Fault/version tests on clones of an actual GLM+AMap generated pending Revision."""
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID
from copy import deepcopy

if not __debug__: raise RuntimeError('Assertions must be enabled')
sys.dont_write_bytecode = True

ROOT = Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
OUT = Path('E:/Study/RoamSync-stage4-evidence-20261025/real-object-safety-final.json')
FREEZE = OUT.parent/'safety-freeze.json'
frozen = json.loads(FREEZE.read_text(encoding='utf-8'))
freeze_sha = hashlib.sha256(FREEZE.read_bytes()).hexdigest()
if subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT,text=True).strip() != frozen['product_commit']:
    raise SystemExit('Frozen product commit differs')
if OUT.exists(): raise SystemExit('Refuse overwrite')
def app_sha():
    files = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'backend/app').rglob('*.py'))}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
def verify_source():
    if (app_sha() != frozen['app_sha256'] or hashlib.sha256(FREEZE.read_bytes()).hexdigest()!=freeze_sha
        or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=frozen['product_commit']):
        raise RuntimeError('Frozen application source differs')
    for path,key in ((Path(__file__),'runner_sha256'),(Path(__file__).with_name('restore_real_pending.py'),'restore_helper_sha256'),
        (Path(frozen['snapshot_path']),'snapshot_sha256'),(Path(frozen['restore_receipt_path']),'restore_receipt_sha256')):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=frozen[key]: raise RuntimeError('Frozen evidence differs: '+key)
verify_source()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
snapshot_data=json.loads(Path(frozen['snapshot_path']).read_text(encoding='utf-8'))
snapshot={k:sorted(v,key=lambda r:str(r.get('id',r.get('trip_id')))) for k,v in snapshot_data['tables'].items() if k!='assistant_sessions'}
receipt=json.loads(Path(frozen['restore_receipt_path']).read_text(encoding='utf-8'))
if (snapshot_data['git_commit']!=frozen['product_commit'] or snapshot_data['app_sha256']!=frozen['app_sha256']
    or receipt['source_commit']!=frozen['product_commit'] or receipt['source_app_sha256']!=frozen['app_sha256']
    or receipt['snapshot_file_sha256']!=frozen['snapshot_sha256'] or receipt['restore_helper_sha256']!=frozen['restore_helper_sha256']
    or not receipt['business_state_equal'] or receipt['source_sha256']!=digest(snapshot) or receipt['target_sha256']!=digest(snapshot)):
    raise RuntimeError('Restore provenance mismatch')
sys.path.insert(0,str(ROOT/'backend'))
os.environ['APP_ENV']='test'
base='postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/'
source='roamsync_agent_b3_stage4_safety_template_test'
if receipt['database']!=source: raise RuntimeError('Wrong restored template')
import psycopg
from psycopg import sql
cases=['rollback','duplicate','stale','fixed','concurrent']
names={case:'roamsync_agent_b3_stage4_real_'+case+'_test' for case in cases}
def check_snapshot_database(name):
    with psycopg.connect(base+name) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        actual={table:sorted([r[0] for r in db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier(table)))],key=lambda r:str(r.get('id',r.get('trip_id')))) for table in snapshot}
        if actual!=snapshot: raise RuntimeError('Template/clone differs from frozen capture: '+name)
check_snapshot_database(source)
with psycopg.connect(base+'postgres',autocommit=True) as conn:
    for name in names.values():
        if conn.execute('select 1 from pg_database where datname=%s',(name,)).fetchone():
            raise SystemExit('Exclusive clone already exists: '+name)
    for name in names.values():
        conn.execute(sql.SQL('create database {} template {}').format(sql.Identifier(name),sql.Identifier(source)))
        check_snapshot_database(name)
os.environ.update(DATABASE_URL=(base+names[cases[0]]).replace('postgresql://','postgresql+psycopg://'),
    LANGGRAPH_DATABASE_URL=base+names[cases[0]],ALLOW_MAP_ESTIMATES='false')
from app.config import Settings, get_settings
official=Settings(_env_file='E:/Study/RoamSync/.env')
for key in ('amap_rest_key','planner_provider','planner_model','planner_api_key','planner_base_url','planner_proxy_url'):
    value=getattr(official,key)
    os.environ[key.upper()]=value.get_secret_value() if hasattr(value,'get_secret_value') else str(value)
get_settings.cache_clear()
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.database import Base,Trip,DayPlan,Activity,TripArrangementItem,RouteLeg,TripPreferences,PlanRevision,PlanningRun,session_factory
from app.plan_revision_service import accept_plan_revision, validate_candidate_plan
from app.schemas import CandidatePlanSnapshot
from app.revision_presentation import revision_presentation_hash
from app.main import app
import httpx

def save(report):
    temp=OUT.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8');temp.replace(OUT)

class InjectedAfterWrites(RuntimeError): pass

async def database_state(db):
    # Every mapped application table, including execution/navigation and sources.
    return {table.name:[dict(row) for row in (await db.execute(select(table).order_by(*table.primary_key.columns))).mappings()]
        for table in sorted(Base.metadata.tables.values(),key=lambda t:t.name)}

def row(state,table,identity): return next(r for r in state[table] if str(r['id'])==str(identity))

def assert_note_only(before,after,aid,tid,note):
    expected=deepcopy(before)
    for table,identity,fields in [('activities',aid,{'note','version','updated_at'}),('trips',tid,{'version','updated_at'})]:
        old,new=row(expected,table,identity),row(after,table,identity)
        assert new['version']==old['version']+1
        if table=='activities': assert new['note']==note
        assert new['updated_at']>=old['updated_at']
        for field in fields: old[field]=new[field]
    assert expected==after, 'Concurrent form changed unexpected state'

async def run():
    global latest_report
    report={'at':datetime.now(UTC),'freeze':frozen,'template_database':source,'cases':[],
        'provenance':frozen['snapshot_provenance'],'passed':False}
    latest_report=report
    save(report)
    for case in cases:
        verify_source()
        engine=create_async_engine((base+names[case]).replace('postgresql://','postgresql+psycopg://'),poolclass=NullPool)
        sessions=async_sessionmaker(engine,expire_on_commit=False);session_factory.configure(bind=engine)
        async def state():
            async with sessions() as db:
                return await database_state(db)
        async with sessions() as db:
            pending=list((await db.scalars(select(PlanRevision).where(PlanRevision.status=='pending'))).all())
            if len(pending)!=1 or str(pending[0].id)!=frozen['revision_id']: raise RuntimeError('Frozen unique pending revision missing')
            revision=pending[0]
            rid,tid=revision.id,revision.trip_id
            presented_hash=revision_presentation_hash(revision)
            candidate=CandidatePlanSnapshot.model_validate(revision.proposed_snapshot)
            changed=[]
            for proposal in candidate.activities:
                if not proposal.replaces_activity_id: continue
                current=await db.get(Activity,proposal.replaces_activity_id)
                day=await db.get(DayPlan,current.day_plan_id) if current else None
                if current and day.trip_id==tid and not current.schedule_locked and current.status=='planned' and (
                    current.duration_minutes!=proposal.duration_minutes or current.scheduled_time!=proposal.planned_start_time
                    or current.place_candidate_id!=proposal.place_candidate_id or day.date!=proposal.day_date
                    or current.estimated_cost_fen!=proposal.estimated_cost_fen): changed.append((current,proposal))
            if not changed: raise RuntimeError('Real revision needs a changed unlocked existing activity')
            activity,changed_candidate=changed[0]
            aid,av=activity.id,activity.version
            version=(await db.get(Trip,tid)).version
            baseline_validation=await validate_candidate_plan(db,tid,candidate)
            assert baseline_validation.valid, baseline_validation.model_dump(mode='json')
            await db.rollback()
        rec={'case':case,'database':names[case],'revision_id':rid,'trip_id':tid,'target_activity_id':aid,
            'baseline_validation':baseline_validation.model_dump(mode='json'),'presentation_hash':presented_hash,'before':await state()}
        rec['passed']=False;report['cases'].append(rec);save(report)
        for table,rows in rec['before'].items():
            if table not in snapshot: assert not rows, 'Unexpected noncaptured state: '+table
        accepted_transaction=None
        async def accept():
            nonlocal accepted_transaction
            async with sessions() as db:
                try:
                    item=await accept_plan_revision(db,rid,expected_presentation_hash=presented_hash,commit=case!='concurrent')
                    if case=='concurrent':
                        accepted_transaction=await database_state(db)
                        await db.commit()
                    return {'status':item.status}
                except Exception as exc:
                    await db.rollback()
                    return {'error_type':type(exc).__name__}
        if case=='rollback':
            import app.arrangement_service as arrangement
            original=arrangement.bind_accepted_items
            fault_hits=0
            async def fail(db,*args,**kwargs):
                nonlocal fault_hits
                fault_hits+=1
                await db.flush()
                rec['transaction_at_fault']=await database_state(db)
                assert rec['transaction_at_fault']['activities']!=rec['before']['activities'], 'No actual activity write reached'
                assert row(rec['transaction_at_fault'],'activities',aid)['version']>av
                if candidate.route_legs:
                    assert rec['transaction_at_fault']['route_legs']!=rec['before']['route_legs'], 'No flushed route delta reached'
                    assert len([r for r in rec['transaction_at_fault']['route_legs'] if r['day_plan_id'] in {
                        d['id'] for d in rec['before']['day_plans'] if d['trip_id']==tid}])==len(candidate.route_legs)
                raise InjectedAfterWrites('explicit synthetic fault after flushed activity/route writes')
            arrangement.bind_accepted_items=fail
            try: rec['fault_result']=await accept()
            finally: arrangement.bind_accepted_items=original
            assert fault_hits==1 and rec['fault_result']=={'error_type':'InjectedAfterWrites'}
            rec['fault_hits']=fault_hits
            rec['after_fault']=await state()
            assert rec['after_fault']==rec['before']
            rec['retry_result']=await accept()
            assert rec['retry_result']=={'status':'accepted'}
        elif case=='duplicate':
            rec['first']=await accept();first=await state()
            rec['second']=await accept();assert await state()==first
            assert rec['first']==rec['second']=={'status':'accepted'}
        elif case in {'stale','fixed'}:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated') as c:
                if case=='stale': response=await c.put(f'/api/v1/trips/{tid}',json={'version':version,'title':'Explicit conflict test'})
                else: response=await c.put(f'/api/v1/activities/{aid}',json={'version':av,'schedule_locked':True})
                rec['explicit_form']={'status_code':response.status_code,'response':response.json()}
                assert response.status_code==200, response.text
            changed=await state();rec['after_explicit_form']=changed
            rec['accept_result']=await accept()
            assert rec['accept_result'].get('error_type')=='StalePlanningRunError'
            assert await state()==changed
            if case=='fixed':
                async with sessions() as db:
                    revision=await db.get(PlanRevision,rid)
                    result=await validate_candidate_plan(db,tid,CandidatePlanSnapshot.model_validate(revision.proposed_snapshot))
                    rec['fixed_validation']=result.model_dump(mode='json')
                    assert not result.valid and any(issue.code=='execution_activity_changed' and str(issue.details.get('activity_id'))==str(aid) for issue in result.errors)
                assert await state()==changed
        else:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated') as c:
                async with sessions() as guard:
                    await guard.scalar(select(Trip).where(Trip.id==tid).with_for_update())
                    a=asyncio.create_task(accept())
                    b=asyncio.create_task(c.put(f'/api/v1/activities/{aid}',headers={'X-Trip-Version':str(version)},json={'version':av,'note':'Explicit concurrent form'}))
                    for _ in range(200):
                        async with sessions() as db:
                            waiting=await db.scalar(text('select count(*) from pg_stat_activity where datname=current_database() and cardinality(pg_blocking_pids(pid))>0'))
                        if waiting>=2:break
                        await asyncio.sleep(.01)
                    else: raise RuntimeError('Two actual lock waiters not observed')
                    rec['observed_lock_waiters']=waiting
                    await guard.rollback()
                result_a,result_b=await asyncio.wait_for(asyncio.gather(a,b),30)
                rec['accept_result']=result_a;rec['form_result']={'status_code':result_b.status_code,'response':result_b.json()}
                assert (result_a=={'status':'accepted'} and result_b.status_code==409) or (
                    result_a.get('error_type')=='StalePlanningRunError' and result_b.status_code==200)
                final=await state()
                if result_a=={'status':'accepted'}:
                    assert accepted_transaction is not None and final==accepted_transaction
                    assert row(final,'activities',aid)['note']==row(rec['before'],'activities',aid)['note']
                    assert row(final,'activities',aid)['version']==av+1
                    assert row(final,'trips',tid)['version']==version+1
                    assert row(final,'plan_revisions',rid)['status']=='accepted'
                    rec['accepted_transaction']=accepted_transaction
                else:
                    assert accepted_transaction is None
                    assert_note_only(rec['before'],final,aid,tid,'Explicit concurrent form')
        verify_source()
        rec['after']=await state();rec['passed']=True;save(report)
        await engine.dispose()
    report['passed']=True;save(report)

if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
latest_report=None
try:
    asyncio.run(run())
except BaseException as exc:
    if latest_report is not None:
        latest_report['passed']=False
        latest_report['failure']={'type':type(exc).__name__,'message':str(exc)}
        save(latest_report)
    raise
