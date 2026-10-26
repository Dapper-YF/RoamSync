import hashlib, json, pathlib, subprocess, urllib.request
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-clean-v3-20261008')
OLD=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-clean-v2-20261008')
SHA='322f55334d16e8cacec60e5e6c126d61cfcca122'
def run(*args):return subprocess.check_output(args)
def read(n):return json.loads((A/n).read_text(encoding='utf-8-sig'))
def save(n,d):(A/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def digest(b):return hashlib.sha256(b).hexdigest()
def tracked(root,prefix=''):
 return {p:digest((root/p).read_bytes()) for p in run('git','-C',str(root),'ls-files','-z',*( [prefix] if prefix else [])).decode().split('\0') if p}
assert run('git','-C',str(W),'rev-parse','HEAD').decode().strip()==SHA
assert not run('git','-C',str(W),'diff','--name-only','HEAD')
expected=read('scope_fix_source_manifest.json')
for p,h in expected['files'].items():assert digest((W/'backend'/p).read_bytes())==h,p
rows=[read('api_health_current322/call7.json'),read('worker_health_current322/call8.json'),read('worker_health_current322/call9.json')]
assert len(rows)==3 and sum(bool(r['success']) for r in rows)==2
save('provider_health_current322_gate.json',{'application_commit':SHA,'status':'EXTERNAL_PROVIDER_BLOCKED','protocol':read('health_current322_protocol.json'),'success_count':2,'call_count':3,'calls':rows,'deeper_transport_root':'UNLOCATED','historical_JSON_root':'UNLOCATED; raw malformed response and terminal state not retained','further_model_calls':0,'candidate_gate':'NOT PASSED','full_E2E':'PAUSED'})
web=tracked(W,'web');assert web==tracked(OLD,'web')
assert read('candidate_322f553_web_image.json')['rootfs']==read('candidate_4a523b7_web_image.json')['rootfs']
assert (A/'candidate322f553_web_artifacts.sha256').read_bytes()==(A/'candidate4a523b7_web_artifacts.sha256').read_bytes()
save('candidate322f553_web_binding.json',{'commit':SHA,'web_source_sha256':digest(json.dumps(web,sort_keys=True).encode()),'web_files':web,'all_web_source_files_identical_to_4a523b7':True,'rootfs_identical':True,'built_artifacts_identical':True,'locked_dependency_files_identical':True,'checks_reused_from_exact_source':'candidate_web_checks.log: 125 tests, typecheck and build passed','container_build_pnpm':'11.19.0','browser_cli_pnpm':'11.25.0'})
def get(p):
 with urllib.request.urlopen('http://127.0.0.1:8001/api/v1/'+p,timeout=30) as r:return json.load(r)
baseline=read('all_isolated_fixtures_before_v3_switch.json')
after={i:{'trip':get('trips/'+i),'days':get('trips/'+i+'/days'),'runs':get('trips/'+i+'/planning-runs')} for i in baseline}
save('all_isolated_fixtures_after_v3_blocked.json',after);assert baseline==after
prod=json.loads(run('docker','exec','-e','PYTHONPATH=/app','roamsync-api','python','/tmp/goal_state.py','--snapshot-only'))
save('production_after_candidate322_blocked.json',prod);assert prod==read('production_before.json')
binding=read('candidate322f553_clean_binding.json')
runtime={}
code="import pathlib,hashlib,json;p=pathlib.Path('/app');print(json.dumps({str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file() and '__pycache__' not in str(f) and '.venv' not in f.parts and 'results' not in f.parts and f.suffix in ('.py','.json','.toml','.lock','.ini')}))"
for m in ('api','worker'):
 name='roamsync-reliability-v3-'+m
 actual=json.loads(run('docker','exec',name,'python','-c',code))
 assert actual==binding['runtime'][m]['runtime_files'] and len(actual)==175
 info=json.loads(run('docker','inspect',name))[0];assert not info['Mounts']
 runtime[m]={'image':info['Image'],'files':175,'manifest':actual,'no_mounts':True}
prod_source=read('production_shipped_source_manifest.json')
current=runtime['api']['manifest']
diff=[p for p in sorted(set(prod_source)|set(current)) if prod_source.get(p)!=current.get(p)]
save('candidate322f553_final_audit.json',{'application_commit':SHA,'backend_source_sha256':expected['sha256'],'runtime':runtime,'tracked_manifest':tracked(W),'production_source_differences':diff,'production_formal_state_exact':True,'all_existing_isolated_trip_days_runs_exact':True,'current_new_trip_created':False,'status':'EXTERNAL_PROVIDER_BLOCKED','initial_failed_full_regression_retained':True})
print(json.dumps({'status':'EXTERNAL_PROVIDER_BLOCKED','runtime_files_each':175,'production_exact':True,'existing_fixtures_exact':True,'production_source_diff_count':len(diff),'web_source_identical':True}))
