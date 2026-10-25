"""Read-only, source-bound snapshots from the exclusive final browser database."""
from datetime import UTC, datetime
import hashlib, json, re, subprocess, sys
from pathlib import Path
import psycopg
label = sys.argv[1]
if not re.fullmatch('[a-z0-9-]+', label): raise ValueError('Safe label required')
root = Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
out = Path(__file__).parent/'runtime-final/browser-states'; out.mkdir(exist_ok=True)
path = out/(label+'.json')
if path.exists(): raise ValueError('Refuse overwrite')
tables = ['trips','source_records','place_candidates','day_plans','trip_preferences',
    'activities','route_legs','trip_arrangement_items','planning_runs','plan_revisions','assistant_sessions']
with psycopg.connect('postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_a2_public_stage4_final_20261025_test') as db:
    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    state = {table: sorted([r[0] for r in db.execute('SELECT to_jsonb(t) FROM '+table+' t')],
        key=lambda r: str(r.get('id',r.get('trip_id')))) for table in tables}
files={p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'backend/app').rglob('*.py'))}
value={'at':datetime.now(UTC).isoformat(), 'label':label,
    'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    'app_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(), 'tables':state}
path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'path':str(path),'counts':{k:len(v) for k,v in state.items()}}))
