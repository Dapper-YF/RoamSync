"""Freeze evidence index and copy the retained package; no product execution."""
from datetime import UTC,datetime
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
from xml.etree import ElementTree

root=Path(__file__).parent
source=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
destination=source/'docs/evidence/product-closeout-stage4-20261025'
if destination.exists(): raise ValueError('Refuse package overwrite')
sys.path.insert(0,str(source/'backend'))
from app.config import Settings
settings=Settings(_env_file='E:/Study/RoamSync/.env')
secrets=[]
for name in type(settings).model_fields:
    value=getattr(settings,name)
    if hasattr(value,'get_secret_value') and len(value.get_secret_value())>=8:
        secrets.append(value.get_secret_value().encode())
text_types={'.json','.ndjson','.log','.md','.txt','.ps1','.py','.env','.xml','.toml','.yaml','.yml'}
def included(path):
    return path.is_file() and not {'__pycache__','.pytest_cache','node_modules'}.intersection(path.parts) and path.suffix!='.pyc'
hits=[]
for path in root.rglob('*'):
    if included(path) and path.suffix in text_types and any(secret in path.read_bytes() for secret in secrets):
        hits.append(path.relative_to(root).as_posix())
for path in [source/'docs/PRODUCT_CLOSEOUT_STAGE4_20261025.md',source/'docs/handoff/LATEST_HANDOFF.md',source/'docs/handoff/PROJECT_STATE.md']:
    if any(secret in path.read_bytes() for secret in secrets): hits.append(str(path))
if hits: raise ValueError('Credential presence found in retained evidence: '+json.dumps(hits))
def read(name):return json.loads((root/name).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
freeze=read('sealed/final-freeze.json');grade=read('sealed-final-grade.json');evaluation=read('sealed-final.json')
files={p.relative_to(source).as_posix():sha(p) for p in sorted((source/'backend/app').rglob('*.py'))}
app_hash=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
assert app_hash==freeze['app_sha256'] and subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==freeze['git_commit']
assert evaluation['execution_status']=='completed_once' and evaluation['completed_turns']==20 and evaluation['evaluator_reruns']==0
assert grade['score']==4 and grade['complete_groups']==0
assert read('full-final-v6/run.json')['passed'] and read('full-final-v6/run.json')['source_unchanged_during_run']
assert read('real-object-safety-final.json')['passed']
assert all(read('web-final-v6-result.json')[key]==0 for key in ['tests','typecheck','build'])
official=Path('E:/Study/RoamSync')
official_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=official,text=True).strip()
dirty=subprocess.check_output(['git','status','--short','--untracked-files=no'],cwd=official,text=True).splitlines()
assert official_head=='ea3ba833e6a77122c08c1c9327c18a346e3c48ef'
expected={'.env.example','README.md','backend/evals/assistant_capability_cases.py','backend/scripts/quality_runtime.py','docs/QUALITY_INTEGRATION_20261021.md','web/nginx.conf'}
assert {line[3:] for line in dirty}==expected
verification={'verdict':'NO-GO','product_goal_complete':False,'frozen_product_commit':freeze['git_commit'],
    'app_sha256':app_hash,'source_worktree':str(source),'external_evidence_root':str(root),
    'official_head_at_end':official_head,'official_tracked_changes_preserved':dirty,
    'official_source_modified_by_this_round':False,'official_database_modified':False,'deployed':False,'obsidian_written':False,
    'independent_evaluation':{'strict_usable':grade['score'],'total':20,'complete_groups':grade['complete_groups'],
        'groups':grade['groups'],'critical_unsupported_guarantees':grade['critical_unsupported_guarantees']['count'],
        'unauthorized_formal_writes':grade['unauthorized_formal_writes']['count'],'evaluator_reruns':0,
        'raw':'sealed-final.json','grade':'sealed-final-grade.json','old_used_questions':'regression only',
        'requested_review_model':'gpt-6-astra','requested_review_effort':'medium',
        'identity_attestation':'dispatch tool metadata, not a provider identity certificate'},
    'engineering':{'backend_main':2019,'backend_dedicated':38,'web_tests':268,'web_files':48,
        'typecheck':True,'build':True,'source_and_tests_stable':True,
        'evidence':['full-final-v6/run.json','full-final-v6/backend-main.xml','full-final-v6/backend-dedicated.xml','web-final-v6-result.json'],
        'invalidated_earlier_freeze':'full-final-v5/run.json source_unchanged=false; execution passed but tests changed'},
    'actual_revision_safety':{'all_five_passed':True,'cases':['rollback','duplicate','stale','fixed','concurrent'],
        'evidence':'real-object-safety-final.json','source':'runtime-final-v6/browser-states/pending60.json',
        'clone_identity_verified':'pending-restore-receipt.json','scope':'Actual generated Revision, exclusive DB per experiment; no constructed candidate'},
    'browser':{'full_natural_golden_passed':False,'actual_cross_city':'Suzhou',
        'preseeded_candidate':False,'manual_database_rescue':False,'initial_formal_trip_count':0,
        'reference_photos_visibly_displayed':True,'photo_claim_limit':'Search reference photos, not independently verified current scene identity/license',
        'route_meters':588,'route_minutes':8,'first_saved_duration':75,'pending_duration':60,'final_saved_duration':60,
        'trip_versions':[2,2,3],'explicit_final_adoption_surface':'Trip page button after environment interruption',
        'blockers':['Opening query returns conflicting excerpts without sufficient specific verification method',
            'After-refresh chat denies candidate contents while the actual review card is present',
            'UI button recovery is not substituted for a full natural-language chain'],
        'evidence':['BROWSER_FULL_CHAIN.md','browser-final-state-comparisons.json','runtime-final-v6/browser-states','runtime-final-v6/screenshots'],
        'owned_runtimes_stopped':'runtime-final-v6/owned-runtime-stop-final.json'},
    'product_commits':'batch-commits.json','test_index':'test-results-index.json','visible_development_outputs':'DEVELOPMENT_FULL_OUTPUTS.md',
    'architecture_audit':'ARCHITECTURE_EVIDENCE_AUDIT.md','architecture_acceptance':'incomplete; no passing SSOT',
    'credential_scan':{'official_secret_values_scanned':len(secrets),'hits':0,'secret_values_disclosed':False},
    'recorded_at':datetime.now(UTC).isoformat()}
(root/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
inventory={p.relative_to(root).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)}
    for p in sorted(root.rglob('*')) if included(p) and p.name!='external-manifest.json'}
manifest={'frozen_product_commit':freeze['git_commit'],'app_sha256':app_hash,'files':inventory,
    'recorded_at':datetime.now(UTC).isoformat(),'semantics':'Hash inventory of success and retained failures, not a claim of product completion'}
(root/'external-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
destination.mkdir(parents=True)
for path in sorted(root.rglob('*')):
    if included(path):
        target=destination/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
for relative,entry in inventory.items():
    if sha(destination/relative)!=entry['sha256']: raise RuntimeError('Copied evidence differs: '+relative)
print(json.dumps({'verdict':'NO-GO','copied_files':len(inventory)+1,'credential_hits':0,'app_hash_matches_freeze':True,'destination':str(destination)}))
