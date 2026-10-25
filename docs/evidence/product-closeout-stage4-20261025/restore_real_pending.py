"""Restore an EXACT captured real pending object for isolated fault experiments.
This creates a fresh exclusive DB, no candidate construction or fact edits.
"""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path
import psycopg
from psycopg import sql
p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--database',required=True)
p.add_argument('--snapshot-sha256',required=True);p.add_argument('--product-commit',required=True)
p.add_argument('--app-sha256',required=True);p.add_argument('--receipt',type=Path,required=True)
a=p.parse_args()
root=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def app_sha():
    files={f.relative_to(root).as_posix():sha(f) for f in sorted((root/'backend/app').rglob('*.py'))}
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
if a.receipt.exists(): raise ValueError('Refuse receipt overwrite')
if sha(a.snapshot)!=a.snapshot_sha256: raise ValueError('Frozen snapshot hash differs')
if subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=a.product_commit or app_sha()!=a.app_sha256:
    raise ValueError('Frozen product source differs')
if not a.database.startswith('roamsync_agent_b3_stage4_safety_') or not a.database.endswith('_test'): raise ValueError('Exclusive safety DB required')
data=json.loads(a.snapshot.read_text(encoding='utf-8'))
if data['git_commit']!=a.product_commit or data['app_sha256']!=a.app_sha256:
    raise ValueError('Captured source is not current frozen source')
snapshot={key:rows for key,rows in data['tables'].items() if key!='assistant_sessions'}
tables=['trips','source_records','place_candidates','day_plans','trip_preferences','activities','route_legs','trip_arrangement_items','planning_runs','plan_revisions']
if set(snapshot)!=set(tables) or sum(r['status']=='pending' for r in snapshot['plan_revisions'])!=1: raise ValueError('Exactly one actual pending revision required')
snapshot={k:sorted(v,key=lambda r:str(r.get('id',r.get('trip_id')))) for k,v in snapshot.items()}
base='postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/'
with psycopg.connect(base+'postgres',autocommit=True) as db:
    if db.execute('select 1 from pg_database where datname=%s',(a.database,)).fetchone(): raise ValueError('Refuse existing DB')
    db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(a.database)))
os.environ.update(APP_ENV='test',DATABASE_URL=(base+a.database).replace('postgresql://','postgresql+psycopg://'),LANGGRAPH_DATABASE_URL=base+a.database)
sys.path.insert(0,str(root/'backend'))
from app.database import Base
from sqlalchemy import create_engine
engine=create_engine(os.environ['DATABASE_URL']);Base.metadata.create_all(engine);engine.dispose()
with psycopg.connect(base+a.database) as db:
    for table in tables:
        for row in snapshot[table]:
            db.execute(sql.SQL('INSERT INTO {} SELECT * FROM jsonb_populate_record(NULL::{}, %s::jsonb)').format(sql.Identifier(table),sql.Identifier(table)),(json.dumps(row),))
    actual={table:sorted([r[0] for r in db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier(table)))],key=lambda r:str(r.get('id',r.get('trip_id')))) for table in tables}
    if actual!=snapshot: raise ValueError('Exact captured business/run/revision state differs')
    if sha(a.snapshot)!=a.snapshot_sha256 or app_sha()!=a.app_sha256: raise ValueError('Source changed during restore')
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
receipt={'source_snapshot':str(a.snapshot),'source_app_sha256':data['app_sha256'],'source_commit':data['git_commit'],
    'snapshot_file_sha256':sha(a.snapshot),'restore_helper_sha256':sha(__file__),
    'database':a.database,'business_state_equal':True,'source_sha256':digest(snapshot),'target_sha256':digest(actual),'counts':{k:len(v) for k,v in actual.items()}}
with a.receipt.open('x',encoding='utf-8') as handle: json.dump(receipt,handle,indent=2)
print(json.dumps(receipt))
