"""Read-only evidence snapshots of the named isolated browser database."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import psycopg
from psycopg.rows import dict_row

label=sys.argv[1]
if not re.fullmatch('[a-z0-9-]+', label): raise SystemExit('Safe snapshot label required')
root=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
out=Path('E:/Study/RoamSync-stage4-evidence-20261025/runtime-current/browser-states')
out.mkdir(parents=True,exist_ok=True)
path=out/(label+'.json')
if path.exists():raise SystemExit('Refuse overwrite')
with psycopg.connect('postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_a2_public_stage4_current_20261025_test', row_factory=dict_row) as db:
    db.execute('SET TRANSACTION READ ONLY')
    tables=['trips','day_plans','activities','trip_preferences','trip_arrangement_items','route_legs','planning_runs','plan_revisions','assistant_sessions']
    state={table:db.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall() for table in tables}
value={'at':datetime.now(UTC),'label':label,'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'tables':state}
path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
print(json.dumps({'path':str(path),'formal_counts':{k:len(v) for k,v in state.items() if k!='assistant_sessions'}}))
