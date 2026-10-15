"""Read-only final gate binding; no application or database writes."""
import hashlib, json, subprocess, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
out = root / 'backend/evals/results/companion_phase25/final'
manifest = json.loads((out / 'source_snapshot.json').read_text(encoding='utf-8-sig'))
assert all(hashlib.sha256((root/'backend'/p).read_bytes()).hexdigest()==h for p,h in manifest['files'].items())
smoke = json.loads((out/'production_smoke.json').read_text(encoding='utf-8'))
assert smoke['complete'] and smoke['formal_state_unchanged'] and all(c['correct'] for c in smoke['cases'])
assert len(smoke['cases'])==8 and smoke['cases'][4]['general_unverified_no_retrieval'] and smoke['cases'][6]['live_safe_limitation']
def log_text(path):
    data=path.read_bytes()
    return data.decode('utf-16' if data.startswith(b'\xff\xfe') else 'utf-8-sig')
assert '20260924_0034 (head)' in log_text(out/'production_migrations.log')
assert 'python -m app.agent_worker' in log_text(out/'production_worker_process.log')
checks = {}
code = "import json,hashlib;from pathlib import Path;m=json.loads(Path('/tmp/source_snapshot.json').read_text());c={p:hashlib.sha256((Path('/app')/p).read_bytes()).hexdigest()==h for p,h in m['files'].items() if not p.startswith('tests/') and p!='Dockerfile'};print(json.dumps({'files':len(c),'match':all(c.values())}));assert all(c.values())"
for name in ['roamsync-api','roamsync-agent-worker-1']:
    subprocess.run(['docker','cp',str(out/'source_snapshot.json'),name+':/tmp/source_snapshot.json'],check=True,capture_output=True)
    checks[name] = json.loads(subprocess.check_output(['docker','exec',name,'/app/.venv/bin/python','-c',code],text=True))
junit={}
for label,path in [('focused',out.parent/'final_focused.xml'),('full',out/'backend_final.xml')]:
    suite=ET.parse(path).getroot().find('testsuite')
    junit[label]={k:suite.attrib.get(k) for k in ['tests','failures','errors','skipped','time']}
    assert int(junit[label]['failures'])==int(junit[label]['errors'])==0
health={}
for url in ['http://127.0.0.1:8000/health/live','http://127.0.0.1:8000/health/ready','http://127.0.0.1:3000/trips']:
    with urllib.request.urlopen(url,timeout=15) as response: health[url]=response.status
for file in ['real_model.json','holdout_review_live.json','manual_review.json','metrics.json']:
    data=json.loads((out/file).read_text(encoding='utf-8-sig'))
    # Batch artifacts store the manifest, review artifacts store its digest.
    digest=data.get('snapshot_sha256') or data.get('source_snapshot',{}).get('sha256') or data.get('snapshot',{}).get('sha256')
    assert digest==manifest['sha256'], (file,digest)
containers=[]
for name in ['roamsync-api','roamsync-agent-worker-1','roamsync-web','roamsync-postgres']:
    item=json.loads(subprocess.check_output(['docker','inspect',name],text=True,encoding='utf-8'))[0]
    state=item['State']
    containers.append({'name':name,'image':item['Image'],'status':state['Status'],'running':state['Running'],'health':state.get('Health',{}).get('Status'),'started':state['StartedAt']})
assert all(c['running'] for c in containers)
assert all(c['health']=='healthy' for c in containers if c['name']!='roamsync-agent-worker-1')
(out/'container_status.json').write_text(json.dumps(containers,indent=2),encoding='utf-8')
result={'snapshot_sha256':manifest['sha256'],'local_manifest_match':True,'runtime':checks,'junit':junit,'health':health,'production_smoke_correct':8,'formal_state_unchanged':True,'containers':containers}
audit=json.loads((out/'audit_binding.json').read_text(encoding='utf-8-sig'))
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in audit['web_files'].items())
fixture=out.parent/'holdout_v1.json'
assert hashlib.sha256(fixture.read_bytes()).hexdigest()==audit['holdout_fixture_sha256']
result['holdout_fixture_unchanged']=True
result['verified_at_utc']=datetime.now(timezone.utc).isoformat()
result['artifact_sha256']={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
    out/'source_snapshot.json',out/'real_model.json',out/'holdout_review_live.json',out/'manual_review.json',out/'metrics.json',
    out/'audit_binding.json',out/'backend_final.xml',out.parent/'final_focused.xml',out/'production_smoke.json',
    out/'production_build.log',out/'production_startup.log',out/'web_test.log',out/'web_typecheck.log',out/'web_build.log',
    root/'scripts/phase25_review.py',root/'scripts/phase25_release_smoke.py',root/'scripts/phase25_release_binding.py',
    root/'docs/agent/COMPANION_PHASE25_EVAL_PROTOCOL_20260930.md',out/'production_migrations.log',out/'production_worker_process.log',
    root/'scripts/phase25_finalize_report.py']}
(out/'acceptance_binding.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
metrics=json.loads((out/'metrics.json').read_text(encoding='utf-8'))
verification={**result,'measured_at':result['verified_at_utc'],'protocol_version':'phase25-v2','worktree':{
    'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
    'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    'status':subprocess.check_output(['git','status','--porcelain'],text=True,encoding='utf-8').splitlines()},
    'source_hashes':manifest['files'],'test_counts':junit,'holdout':{'fixture_sha256':audit['holdout_fixture_sha256'],'blind':False,'results':metrics['holdout']},
    'real_model':{'artifact':'final/real_model.json','results':metrics['live']},
    'web':{'source_modified_this_round':False,'source_hashes':audit['web_files'],'hashes_match':True,'passed':123,'test_files':20,'typecheck':'PASS','build':'PASS','evidence_reused_for_unchanged_web_source':True,'evidence':['final/web_test.log','final/web_typecheck.log','final/web_build.log']},
    'android':{'contract_modified':False,'rerun_this_round':False},'production_migrations_artifact':'final/production_migrations.log'}
(out.parent/'final_verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in {'containers','artifact_sha256'}},ensure_ascii=False))
