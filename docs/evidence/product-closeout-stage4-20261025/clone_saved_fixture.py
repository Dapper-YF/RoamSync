"""Exact saved business snapshot cloning, no candidate/run/revision seeding."""
import hashlib
import json
from pathlib import Path
from uuid import UUID

TABLES=('trips','source_records','place_candidates','day_plans','trip_preferences','activities','route_legs','trip_arrangement_items')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def capture(database,trip_id):
    import psycopg
    from psycopg import sql
    if not database.startswith('roamsync_agent_b3_stage4_') or not database.endswith('_test'):
        raise ValueError('Exclusive development database required')
    trip_id=UUID(str(trip_id))
    with psycopg.connect('postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/'+database) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        result={}
        for table in TABLES:
            predicate=(sql.SQL('id=%s') if table=='trips' else sql.SQL('day_plan_id IN (SELECT id FROM day_plans WHERE trip_id=%s)')
                if table in {'activities','route_legs'} else sql.SQL('trip_id=%s'))
            rows=db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t WHERE ').format(sql.Identifier(table))+predicate,(trip_id,)).fetchall()
            result[table]=sorted([r[0] for r in rows],key=lambda r:str(r.get('id',r.get('trip_id'))))
        if len(result['trips'])!=1 or not result['day_plans'] or not result['activities']:
            raise ValueError('Actual saved trip with activities required')
        return result


async def clone(db,fixture_path,expected_hash):
    from sqlalchemy import text
    data=json.loads(Path(fixture_path).read_text(encoding='utf8'))
    snapshot=data['snapshot']
    if digest(snapshot)!=expected_hash or set(snapshot)!=set(TABLES):
        raise ValueError('Frozen saved fixture differs')
    for table in TABLES:
        for row in snapshot[table]:
            await db.execute(text(f'INSERT INTO "{table}" SELECT * FROM jsonb_populate_record(NULL::"{table}", CAST(:row AS jsonb))'),
                {'row':json.dumps(row,ensure_ascii=False)})
    actual={}
    for table in TABLES:
        rows=(await db.execute(text(f'SELECT to_jsonb(t) FROM "{table}" t'))).scalars().all()
        actual[table]=sorted(rows,key=lambda r:str(r.get('id',r.get('trip_id'))))
    if actual!=snapshot:
        raise ValueError('Exact saved snapshot clone mismatch')
    return UUID(snapshot['trips'][0]['id']),{'source':data['provenance'],'source_sha256':expected_hash,
        'target_sha256':digest(actual),'equal_business_snapshot':True,'id_mapping':'identity IDs across independent databases',
        'no_candidate_run_revision_history_seeded':True,'tables':{k:len(v) for k,v in actual.items()}}
