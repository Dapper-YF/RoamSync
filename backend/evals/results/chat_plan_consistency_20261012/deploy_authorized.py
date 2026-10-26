"""User-authorized API/Web-only release; never migrate or submit a Trip decision."""
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent
repo = root.parents[3]
result = {'authorized': True, 'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'preflight'}
def save():
    (root / 'deployment_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
def call(*args, input=None):
    return subprocess.check_output(args, cwd=repo, input=input, text=True, encoding='utf-8')
def inspect():
    return json.loads(call('docker', 'inspect', 'roamsync-api', 'roamsync-web', 'roamsync-agent-worker-1', 'roamsync-postgres'))
def summary(containers):
    return [{'name': c['Name'], 'id': c['Id'], 'image': c['Image']} for c in containers]
def db_read():
    code = '''import asyncio,json
from sqlalchemy import text
from app.database import session_factory
async def main():
    async with session_factory() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        out={}
        for name in ["trips","day_plans","activities","route_legs","expenses","trip_preferences","place_candidates","source_records","planning_runs","plan_revisions"]:
            q="SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text, chr(10) ORDER BY row_to_json(t)::text),'')) FROM "+name+" t"
            row=(await db.execute(text(q))).first()
            out[name]={"count":row[0],"digest":row[1]}
        out["working_runs"]=(await db.execute(text("SELECT count(*) FROM planning_runs WHERE status IN ('queued','researching','planning','validating')"))).scalar()
        print(json.dumps(out))
asyncio.run(main())
'''
    return json.loads(call('docker', 'exec', '-i', 'roamsync-api', 'python', '-', input=code))

before = inspect()
expected = ['sha256:60723c02c240875e3956744440ab19ea609dcf8ca31b6668a00845b57c2ef7a5',
            'sha256:9794c7029f6ca25800174e7072d701065df2b6bbff6110dd168f4c6b614f99b8']
assert [c['Image'] for c in before[:2]] == expected, 'Runtime baseline changed; no release performed'
target = ['sha256:23248fc5bf2b722dbd2ba94f8e5b07fa37469aeaf652b70d979167560a707618',
          'sha256:4e2d793b8918a750f7bc8b42685160262943277f29b5420cf93e805768202fa3']
assert [json.loads(call('docker','image','inspect',tag))[0]['Id'] for tag in
        ['roamsync-chat-api-hotfix:20261012','roamsync-chat-web-hotfix:20261012']] == target
base = ['docker','compose','-p','roamsync','-f','compose.yaml','-f']
config = json.loads(call(*base, str(root / 'release.override.yaml'), 'config','--format','json'))
for service, container in zip(['api','web','agent-worker','postgres'], before):
    actual = dict(v.split('=',1) for v in container['Config']['Env'])
    differences = [k for k,v in config['services'][service].get('environment',{}).items() if actual.get(k)!=str(v)]
    assert not differences, 'Configuration drift in '+service+': '+str(differences)
assert 'alembic' not in ' '.join(config['services']['api']['command'])
result['before_containers'] = summary(before)
result['before_database'] = db_read()
save()
with (root / 'deployment.log').open('w',encoding='utf-8') as log:
    subprocess.run([*base,str(root/'release.override.yaml'),'up','-d','--no-build','--no-deps','api','web'],
                   cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
try:
    healthy = False
    for _ in range(20):
        try:
            health = {}
            for endpoint in ['live','ready']:
                with urllib.request.urlopen('http://127.0.0.1:8000/health/'+endpoint,timeout=2) as response:
                    health[endpoint] = {'http_status':response.status,'body':json.load(response)}
            with urllib.request.urlopen('http://127.0.0.1:3000/',timeout=2) as response:
                html = response.read().decode()
                assert response.status == 200 and '/assets/index-' in html
            healthy = True
            break
        except Exception:
            time.sleep(2)
    assert healthy, 'Health gate failed'
    after = inspect()
    assert [c['Image'] for c in after[:2]] == target, 'Wrong release image'
    assert [c['Id'] for c in after[2:]] == [c['Id'] for c in before[2:]], 'Worker or Postgres was replaced'
    result['after_containers'] = summary(after)
    result['after_database'] = db_read()
    result['database_unchanged'] = result['before_database'] == result['after_database']
    assert result['database_unchanged'], 'Database fingerprint changed; investigate'
    result['health'] = health
    result['web_html'] = html
    result['status'] = 'deployed_health_passed'
    result['completed_at'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({'status':result['status'],'working_runs_before':result['before_database']['working_runs'],
                      'database_unchanged':True,'worker_postgres_unchanged':True}))
except Exception as error:
    result['error_type'] = type(error).__name__
    result['status'] = 'rollback_required'
    save()
    with (root / 'rollback.log').open('w',encoding='utf-8') as log:
        subprocess.run([*base,str(root/'rollback.override.yaml'),'up','-d','--no-build','--no-deps','api','web'],
                       cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
    result['status'] = 'rolled_back'
    save()
    raise
