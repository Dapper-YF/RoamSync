import hashlib,json,pathlib,subprocess
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-final-20261008')
APP='322f55334d16e8cacec60e5e6c126d61cfcca122';DOC='54b8888754448615e9310bc20ba085349ffc9c4f'
def git(*args):return subprocess.check_output(['git','-C',str(W),'-c','core.autocrlf=false',*args])
def load(n):return json.loads((A/n).read_text(encoding='utf-8'))
assert git('rev-parse','HEAD').decode().strip()==DOC
assert git('rev-parse','HEAD^').decode().strip()==APP
assert not git('status','--porcelain')
scope=load('blocked_docs_staged_audit.json');paths=git('diff','--name-only',APP,DOC).decode().splitlines()
assert set(paths)==set(scope['exact_four_paths'])
for p,h in scope['sha256'].items():assert hashlib.sha256((W/p).read_bytes()).hexdigest()==h
source=load('scope_fix_source_manifest.json')
for p,h in source['files'].items():assert hashlib.sha256((W/'backend'/p).read_bytes()).hexdigest()==h,p
web=load('candidate322f553_web_binding.json')
for p,h in web['web_files'].items():assert hashlib.sha256((W/p).read_bytes()).hexdigest()==h,p
images={}
for mode in ('backend','test','web'):
 newer=load('candidate_54b8888_'+mode+'_image.json');older=load('candidate_322f553_'+mode+'_image.json')
 assert newer['rootfs']==older['rootfs'],mode
 images[mode]={'final_image':newer['image'],'application_image':older['image'],'rootfs_identical':True,'build_log_sha256':newer['build_log_sha256']}
manifest={p:hashlib.sha256((W/p).read_bytes()).hexdigest() for p in git('ls-files','-z').decode().split('\0') if p}
for ref in ('8ee7dbf0ddc27fdb8fd55bc20fad9777ec4bf209','0b5010fe5a7b06dcec1ab7b159b5b337244247ae',APP):git('cat-file','-e',ref+'^{commit}')
record={'status':'EXTERNAL_PROVIDER_BLOCKED','application_commit':APP,'documentation_checkpoint':DOC,'branch':'codex/roamsync-planner-reliability-20261008','final_clean_checkout':str(W),'git_clean':True,'docs_only_four_paths':paths,'full_tracked_manifest':manifest,'backend_source_sha256':source['sha256'],'web_source_sha256':web['web_source_sha256'],'locked_builds':images,'runtime_matches_application_source':True,'current_backend_full_regression':load('current_regression_summary.json'),'web_tests':125,'web_tests_reused_for_identical_source':True,'provider_gate':'2/3, strict Research streaming RemoteProtocolError, deeper root UNLOCATED','candidate_gate':'NOT PASSED','full_real_E2E':'PAUSED','production':'UNCHANGED / DEPLOYMENT NOT AUTHORIZED','next_gate':'external service restoration then newly prescribed finite real health batch and fresh same-application full browser lifecycle','previous_failure_history_preserved':True,'production_deploy_or_main_merge':False}
(A/'blocked_final_binding.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
app_paths=git('diff','--name-only',APP+'^',APP).decode().splitlines()
app_record={'commit':APP,'parent':git('rev-parse',APP+'^').decode().strip(),'paths':app_paths,'repository_manifest':load('candidate322f553_final_audit.json')['tracked_manifest'],'backend_source_sha256':source['sha256'],'regression':load('current_regression_summary.json'),'candidate_gate':'NOT PASSED','provider_gate':'EXTERNAL_PROVIDER_BLOCKED'}
(A/'candidate322f553_commit_record.json').write_text(json.dumps(app_record,indent=2),encoding='utf-8')
print(json.dumps({'app':APP,'docs':DOC,'git_clean':True,'backend_worker_web_final_rootfs_identical':True,'status':record['status']}))
