"""Exact historical real-trip clone solely for photo rendering; not generation evidence."""
import hashlib,json
from pathlib import Path
import psycopg
from psycopg import sql
source=Path('E:/Study/RoamSync-stage4-evidence-20261025/runtime-final-v6/browser-states/adopted60-after-refresh.json')
out=Path(__file__).parent/'runtime-photos'/'photo-fixture-clone.json'
if out.exists():raise ValueError('Refuse overwrite')
data=json.loads(source.read_text(encoding='utf-8'))
tables=['trips','source_records','place_candidates','day_plans','trip_preferences','activities','route_legs','trip_arrangement_items','planning_runs','plan_revisions','assistant_sessions']
dsn='postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_a2_public_stage5_photos_20261025_test'
with psycopg.connect(dsn) as db:
    for table in tables:
        assert db.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]==0
        for row in data['tables'][table]:
            db.execute(sql.SQL('INSERT INTO {} SELECT * FROM jsonb_populate_record(NULL::{}, %s::jsonb)').format(sql.Identifier(table),sql.Identifier(table)),(json.dumps(row),))
    cloned={table:sorted([r[0] for r in db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier(table)))],key=lambda r:str(r.get('id',r.get('trip_id')))) for table in tables}
    assert cloned=={table:data['tables'][table] for table in tables}
out.write_text(json.dumps({'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'exact_11_table_clone':True,'before':cloned},ensure_ascii=False,indent=2),encoding='utf-8')
print('Exact real trip clone verified')
