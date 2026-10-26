import hashlib,json
from pathlib import Path
m=json.loads(Path('/tmp/collector_baseline_source.json').read_text(encoding='utf-8-sig'))
checks={n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest()==h for n,h in m['files'].items() if not n.startswith('tests/') and n!='Dockerfile'}
print(json.dumps({'source_sha256':m['sha256'],'runtime_files_verified':len(checks),'matches':all(checks.values()),'mismatches':[n for n,v in checks.items() if not v]}))
assert all(checks.values())
