"""Freeze hashes only. Never read or display sealed question content."""
from datetime import UTC,datetime
import hashlib,json,subprocess
from pathlib import Path
from clone_saved_fixture import digest

root=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
evidence=Path(__file__).parent
target=evidence/'sealed/final-freeze.json'
if target.exists(): raise ValueError('Refuse freeze overwrite')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
if commit!='736e3b7bd906bd11c1d7cb9384ba8d9582bb596d': raise ValueError('Unexpected product commit')
cases=sha(evidence/'sealed/cases.json');rubric=sha(evidence/'sealed/rubric.md')
if cases!='8c3ec6686d5ca5cf6c88cf048b6c6734788b3f3cd7a71f5b6c3c9dc9fddefcba' or rubric!='71f4ec8eca362cb263936f71422f244ec1684f5476ac8acbc746139e582d10b5':
    raise ValueError('Original sealed inputs changed')
files={p.relative_to(root).as_posix():sha(p) for p in sorted((root/'backend/app').rglob('*.py'))}
app_hash=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
if app_hash!='f5f37b0c0f5bc8133d36ec76188517f9429ae8281d35e7eb60960bb592a173ff': raise ValueError('Application changed')
fixture=evidence/'saved-real-fixture-final.json'
fixture_data=json.loads(fixture.read_text(encoding='utf-8'))
manifest={'frozen_at':datetime.now(UTC).isoformat(),'git_commit':commit,'app_sha256':app_hash,
    'cases_sha256':cases,'rubric_sha256':rubric,'runner_sha256':sha(evidence/'run_stage4_sealed.py'),
    'clone_helper_sha256':sha(evidence/'clone_saved_fixture.py'),'saved_fixture_sha256':sha(fixture),
    'saved_fixture_snapshot_sha256':digest(fixture_data['snapshot']),
    'saved_fixture_provenance':fixture_data['provenance'],
    'measurement':'Single execution; provider errors count, no resampling or editing after exposure'}
with target.open('x',encoding='utf-8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)
print(json.dumps({'path':str(target),'commit':commit,'app_sha256':app_hash,'sealed_inputs_unchanged':True}))
