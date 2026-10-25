"""Capture only the genuine explicitly adopted Trip; never construct facts."""
import hashlib,json
from pathlib import Path
from clone_saved_fixture import capture,digest

root=Path(__file__).parent
out=root/'saved-real-fixture-final.json'
if out.exists(): raise ValueError('Refuse overwrite')
report=json.loads((root/'contract-real-after12.json').read_text(encoding='utf-8'))
if not report['source_unchanged'] or len(report['records'])!=10:
    raise ValueError('Complete source-bound public run required')
trip_id=report['records'][-1]['raw']['context']['read_trip_id']
snapshot=capture('roamsync_agent_b3_stage4_contract_after12_test',trip_id)
if snapshot['trips'][0]['version']!=3:
    raise ValueError('Expected actual accepted modification version')
result={'provenance':{'database':'roamsync_agent_b3_stage4_contract_after12_test',
    'trip_id':trip_id,'capture':'contract-real-after12.json',
    'capture_sha256':hashlib.sha256((root/'contract-real-after12.json').read_bytes()).hexdigest(),
    'product_commit':report['source_commit'],'app_sha256':report['app_sha256_after'],
    'real_model_and_amap':True,'source_formal_version':snapshot['trips'][0]['version'],
    'selection':'Only this actually generated/adopted Trip; unrelated synthetic fixture excluded',
    'no_planning_candidate_history':True},'snapshot':snapshot}
with out.open('x',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'path':str(out),'snapshot_sha256':digest(snapshot),
    'counts':{key:len(rows) for key,rows in snapshot.items()}}))
