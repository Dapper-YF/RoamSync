import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('E:/Study/RoamSync')
OUT = Path(__file__).parent
DATABASE = 'roamsync_s6_official_full_20261026_test'
PROMOTION_DATABASE = 'roamsync_s6_official_promotion_20261026_test'
from sqlalchemy.engine import make_url
url = make_url(os.environ['DATABASE_URL'])
assert url.host == '127.0.0.1' and url.port == 15435 and url.database == DATABASE
os.environ.update(APP_ENV='test', PYTHONUTF8='1', PLANNER_API_KEY='', PLANNER_MODEL='',
                  ALLOW_MAP_ESTIMATES='true',
                  ROAMSYNC_AGENT_B_POSTGRES='1',
                  PROMOTION_TEST_DATABASE_URL=url.set(database=PROMOTION_DATABASE).render_as_string(hide_password=False),
                  LANGGRAPH_DATABASE_URL=url.set(drivername='postgresql').render_as_string(hide_password=False))
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import psycopg
from psycopg import sql
with psycopg.connect(url.set(drivername='postgresql', database='postgres').render_as_string(hide_password=False), autocommit=True) as connection:
    for database in (DATABASE, PROMOTION_DATABASE):
        assert not connection.execute('select 1 from pg_database where datname=%s', (database,)).fetchone(), 'Refusing to reuse a database'
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
from sqlalchemy import create_engine, text
from app.database import Base
from app import read_calculations
engine = create_engine(url)
Base.metadata.create_all(engine)
from app.place_content.repository import metadata as content_metadata
from app.drafts.repository import metadata as draft_metadata
from app.draft_promotion.repository import metadata as promotion_metadata
for metadata in (content_metadata, draft_metadata, promotion_metadata):
    metadata.create_all(engine)
with engine.connect() as connection:
    identity = dict(connection.execute(text('select current_database() as database, current_user as username, inet_server_addr()::text as server, inet_server_port() as port')).mappings().one())
engine.dispose()

def freeze():
    paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z', '--',
        'backend/app', 'backend/tests', 'backend/migrations', 'backend/pyproject.toml',
        'web/src', 'web/package.json', 'web/pnpm-lock.yaml', 'web/vite.config.ts']).decode('utf-8').split('\0')
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths if p and (ROOT / p).is_file()}

before = freeze()
(OUT / 'official-source-freeze.json').write_text(json.dumps(before, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'cwd': str(Path.cwd()), 'python': sys.executable, 'module': read_calculations.__file__,
                  'database_identity': identity, 'configured_port': 15435, 'frozen_files': len(before)}))
import pytest
result = pytest.main(['-o', 'addopts=', '-q', '--tb=short', f'--junitxml={OUT / "official-backend-full.xml"}', 'tests'])
after = freeze()
report = {'pytest_exit_code': int(result), 'source_unchanged': before == after, 'frozen_files': len(before),
          'database_identity': identity, 'root': str(ROOT), 'module': read_calculations.__file__}
(OUT / 'official-backend-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
raise SystemExit(int(result) if result else (0 if before == after else 1))
