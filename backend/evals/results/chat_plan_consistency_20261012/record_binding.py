from pathlib import Path
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parent
repo = root.parents[3]
def call(*args):
    return subprocess.check_output(args, cwd=repo, text=True, encoding='utf-8')
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
folders = ['backend/app', 'backend/tests', 'backend/evals', 'web/src']
files = [p for folder in folders for p in (repo / folder).rglob('*')
         if p.is_file() and p.suffix in {'.py', '.ts', '.tsx', '.json'} and
         'results' not in p.parts and '__pycache__' not in p.parts]
files += [repo / p for p in ['backend/pyproject.toml', 'backend/uv.lock', 'backend/Dockerfile',
                            'web/package.json', 'web/pnpm-lock.yaml', 'web/Dockerfile', 'compose.yaml', 'compose.test.yaml']]
runtime = json.loads(call('docker', 'inspect', 'roamsync-api', 'roamsync-web', 'roamsync-agent-worker-1'))
planned = json.loads(call('docker', 'compose', '-p', 'roamsync', '-f', 'compose.yaml', '-f',
                         str(root / 'release.override.yaml'), 'config', '--format', 'json'))
env_checks = {}
for service, container in zip(['api', 'web', 'agent-worker'], runtime):
    actual = dict(v.split('=', 1) for v in container['Config']['Env'])
    wanted = planned['services'][service].get('environment', {})
    # No environment values, credentials, URLs or private message text are emitted.
    different = [k for k, v in wanted.items() if actual.get(k) != str(v)]
    env_checks[service] = {'compared_compose_keys': len(wanted), 'different_keys': different}
images = ['roamsync-chat-api-hotfix:20261012', 'roamsync-chat-web-hotfix:20261012',
          'roamsync-chat-consistency-20261012-api-test', 'roamsync-chat-hotfix-test-20261012-api-test']
data = {'head': call('git', 'rev-parse', 'HEAD').strip(), 'source': {str(p.relative_to(repo)): digest(p) for p in files},
        'runtime': [{'name': c['Name'], 'container_id': c['Id'], 'image_id': c['Image']} for c in runtime],
        'built_images': {name: json.loads(call('docker', 'image', 'inspect', name))[0]['Id'] for name in images},
        'environment_comparison': env_checks,
        'release_sources': {str(p.relative_to(root)): digest(p) for p in (root / 'release').rglob('*') if p.is_file()},
        'production_deployed': False, 'production_business_writes': False}
(root / 'verification_manifest.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
print(json.dumps({'source_files': len(data['source']), 'environment_comparison': env_checks,
                  'built_images': data['built_images']}, indent=2))
