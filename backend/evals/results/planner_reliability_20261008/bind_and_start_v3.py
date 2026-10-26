import hashlib, json, pathlib, subprocess, urllib.request, time
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-clean-v3-20261008')
SHA='322f55334d16e8cacec60e5e6c126d61cfcca122'
def cmd(*args): return subprocess.check_output(args)
def inspect(name): return json.loads(cmd('docker','inspect',name))[0]
expected=json.loads((A/'scope_fix_source_manifest.json').read_text(encoding='utf-8'))
for p,h in expected['files'].items(): assert hashlib.sha256((W/'backend'/p).read_bytes()).hexdigest()==h,p
assert cmd('git','-C',str(W),'rev-parse','HEAD').decode().strip()==SHA
assert not cmd('git','-C',str(W),'-c','core.autocrlf=false','status','--porcelain')
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8001/api/v1/'+path,timeout=30) as r: return json.load(r)
trips=get('trips')
if isinstance(trips,dict): raise RuntimeError('unexpected Trip list envelope')
before={t['id']:{'trip':get('trips/'+t['id']),'days':get('trips/'+t['id']+'/days'),'runs':get('trips/'+t['id']+'/planning-runs')} for t in trips}
active=[r for f in before.values() for r in f['runs'] if r['status'] in ('queued','researching','planning','validating')]
assert not active,'live planning work must finish before switch'
(A/'all_isolated_fixtures_before_v3_switch.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
old={n:inspect(n) for n in ('roamsync-reliability-v2-api','roamsync-reliability-v2-worker','roamsync-reliability-v2-web')}
for n,i in old.items():
    assert i['Config']['Image'].endswith(':4a523b7')
    assert not i['HostConfig']['Binds']
envs={m:dict(x.split('=',1) for x in old[n]['Config']['Env']) for m,n in [('api','roamsync-reliability-v2-api'),('worker','roamsync-reliability-v2-worker')]}
for m,e in envs.items():
    assert 'roamsync-release-pg' in e['DATABASE_URL'] and 'roamsync_release' in e['DATABASE_URL']
    assert e.get('ALLOW_MAP_ESTIMATES','false').lower()=='false'
    assert e.get('PLANNER_API_KEY') and e.get('AMAP_REST_KEY')
for n in old: cmd('docker','stop',n)
for m,e in envs.items():
    p=A/('private_runtime_'+m+'.env')
    p.write_text('\n'.join(k+'='+v for k,v in e.items())+'\n',encoding='utf-8')
    args=['docker','run','-d','--name','roamsync-reliability-v3-'+m,'--network','roamsync-release-8ee7dbf','--env-file',str(p)]
    if m=='api':args+=['--network-alias','api','-p','127.0.0.1:8001:8000']
    args+=['roamsync-reliability-backend:322f553']
    if m=='worker':args+=['python','-m','app.agent_worker']
    try:cmd(*args)
    finally:p.unlink()
cmd('docker','run','-d','--name','roamsync-reliability-v3-web','--network','roamsync-release-8ee7dbf','-p','127.0.0.1:3001:80','roamsync-reliability-web:322f553')
for attempt in range(30):
    try:
        after={t['id']:{'trip':get('trips/'+t['id']),'days':get('trips/'+t['id']+'/days'),'runs':get('trips/'+t['id']+'/planning-runs')} for t in trips}
        break
    except (OSError,ValueError):time.sleep(1)
else:raise RuntimeError('isolated API did not become ready')
assert before==after,'existing isolated fixture history changed'
runtime={}
script="import pathlib,hashlib,json; p=pathlib.Path('/app'); print(json.dumps({str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file() and '__pycache__' not in str(f) and '.venv' not in f.parts and 'results' not in f.parts and f.suffix in ('.py','.json','.toml','.lock','.ini')}))"
for m in ('api','worker'):
    name='roamsync-reliability-v3-'+m
    files=json.loads(cmd('docker','exec',name,'python','-c',script))
    for p,h in files.items():assert p in expected['files'] and expected['files'][p]==h,p
    assert len(files)==175,len(files)
    i=inspect(name); assert not i['Mounts']
    runtime[m]={'image':i['Image'],'runtime_files':files,'no_source_mounts':True}
assert runtime['api']['runtime_files']==runtime['worker']['runtime_files']
(A/'candidate322f553_clean_binding.json').write_text(json.dumps({'commit':SHA,'source_manifest':expected,'runtime':runtime,'existing_trip_days_runs_preserved':True,'original_release_containers_stopped_preserved':True,'production_touched':False},indent=2),encoding='utf-8')
print('Clean commit/source bound; API and Worker 175 exact files; existing isolated Trips and failed Runs unchanged.')
