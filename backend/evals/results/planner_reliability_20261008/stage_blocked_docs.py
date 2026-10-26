import hashlib,json,pathlib,re,subprocess
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-release-20261008')
paths=['docs/agent/REPOSITORY_REPRODUCIBILITY_20261007.md','docs/agent/ROAMSYNC_DEMO_ACCEPTANCE_20261007.md','docs/agent/ROAMSYNC_LONG_TERM_PROGRESS.md','docs/handoff/LATEST_HANDOFF.md']
def run(*args):return subprocess.check_output(['git','-C',str(W),'-c','core.autocrlf=false',*args])
assert run('rev-parse','HEAD').decode().strip()=='322f55334d16e8cacec60e5e6c126d61cfcca122'
assert run('branch','--show-current').decode().strip()=='codex/roamsync-planner-reliability-20261008'
assert not run('diff','--cached','--name-only')
assert set(run('diff','--name-only').decode().splitlines())==set(paths)
assert not run('ls-files','--others','--exclude-standard')
expected=json.loads((A/'scope_fix_source_manifest.json').read_text(encoding='utf-8'))
for p,h in expected['files'].items():assert hashlib.sha256((W/'backend'/p).read_bytes()).hexdigest()==h,p
hashes={p:hashlib.sha256((W/p).read_bytes()).hexdigest() for p in paths}
spec=A/'blocked_docs_pathspec.bin';spec.write_bytes(b'\0'.join(p.encode() for p in paths)+b'\0')
run('add','--pathspec-from-file='+str(spec),'--pathspec-file-nul')
assert set(run('diff','--cached','--name-only').decode().splitlines())==set(paths)
run('diff','--cached','--check')
for p,h in hashes.items():assert hashlib.sha256(run('show',':'+p)).hexdigest()==h
patch=run('diff','--cached','--no-ext-diff');(A/'blocked_docs_staged_review.patch').write_bytes(patch)
added='\n'.join(l[1:] for l in patch.decode().splitlines() if l.startswith('+') and not l.startswith('+++'))
patterns=[r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY',r'(?i)\b(?:sk|ghp|github_pat)-[a-z0-9_]{16,}',r'(?i)(?:api_key|password|token|secret)\s*[=:]\s*[\"\x27][^\"\x27]{8,}']
assert not any(re.search(p,added) for p in patterns),'sensitive added content'
(A/'blocked_docs_staged_audit.json').write_text(json.dumps({'parent':run('rev-parse','HEAD').decode().strip(),'exact_four_paths':paths,'sha256':hashes,'source_manifest_unchanged':expected['sha256'],'added_content_sensitive_scan':'passed','whitespace_check':'passed','unknown_paths':[],'staged_patch_sha256':hashlib.sha256(patch).hexdigest()},indent=2),encoding='utf-8')
print('Exact four documentation paths staged; source unchanged; full review patch saved.')
