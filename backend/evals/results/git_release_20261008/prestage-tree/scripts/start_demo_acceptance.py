"""Create an isolated real-provider acceptance runtime; never resets production.

Reuse only containers carrying this fixture label. Credentials are inherited from
the configured runtime through a temporary env file, never printed or archived.
"""
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'com.roamsync.acceptance=20261007'
NETWORK = 'roamsync-acceptance-20261007'


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Docker operation failed: ' + args[0])
    return result.stdout


def exists(name):
    return subprocess.run(['docker', 'inspect', name], capture_output=True).returncode == 0


def ensure(name, args):
    if exists(name):
        state = json.loads(docker('inspect', name))[0]
        if state['Config'].get('Labels', {}).get('com.roamsync.acceptance') != '20261007':
            raise RuntimeError('Refusing unrelated container: ' + name)
        if not state['State']['Running']:
            docker('start', name)
    else:
        docker('run', '-d', '--name', name, '--label', LABEL, '--network', NETWORK, *args)
    print(name, 'running', flush=True)


def main():
    api = json.loads(docker('inspect', 'roamsync-api'))[0]
    worker = json.loads(docker('inspect', 'roamsync-agent-worker-1'))[0]
    subprocess.run(['docker', 'network', 'inspect', NETWORK], capture_output=True)
    if subprocess.run(['docker', 'network', 'inspect', NETWORK], capture_output=True).returncode:
        docker('network', 'create', '--label', LABEL, NETWORK)
    ensure('roamsync-acceptance-pg', ['--tmpfs', '/var/lib/postgresql/data',
           '-e', 'POSTGRES_DB=roamsync_acceptance', '-e', 'POSTGRES_USER=acceptance',
           '-e', 'POSTGRES_PASSWORD=acceptance_fixture', 'postgres:17-alpine'])
    docker('exec', 'roamsync-acceptance-pg', 'sh', '-c',
           'until pg_isready -U acceptance -d roamsync_acceptance; do sleep 1; done')
    for source, name in [(api, 'roamsync-acceptance-api'), (worker, 'roamsync-acceptance-worker')]:
        values = dict(e.split('=', 1) for e in source['Config']['Env'])
        values.update(APP_ENV='acceptance',
                      DATABASE_URL='postgresql+psycopg://acceptance:acceptance_fixture@roamsync-acceptance-pg:5432/roamsync_acceptance',
                      LANGGRAPH_DATABASE_URL='postgresql://acceptance:acceptance_fixture@roamsync-acceptance-pg:5432/roamsync_acceptance')
        env_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.env', delete=False) as stream:
                env_path = Path(stream.name)
                for key, value in values.items():
                    if '\n' in value or '\r' in value:
                        raise ValueError('Multiline environment value cannot be copied safely')
                    stream.write(key + '=' + value + '\n')
            args = ['--env-file', str(env_path), '-v', str(ROOT / 'backend/app') + ':/app/app:ro',
                    '-v', str(ROOT / 'backend/evals') + ':/app/evals:ro',
                    '-v', str(ROOT / 'backend/evals/results/demo_acceptance_20261007') + ':/evidence']
            if name.endswith('api'):
                if not exists(name):
                    docker('run', '--rm', '--network', NETWORK, *args, source['Image'], 'sh', '-c',
                           'alembic upgrade head && python -m app.init_checkpoints')
                args += ['-p', '127.0.0.1:8001:8000', source['Image']]
            else:
                args += [source['Image'], 'python', '-m', 'app.agent_worker']
            ensure(name, args)
        finally:
            if env_path is not None:
                env_path.unlink(missing_ok=True)
    print('Isolated API: http://127.0.0.1:8001; no production DB or trip reset.')


if __name__ == '__main__':
    main()
