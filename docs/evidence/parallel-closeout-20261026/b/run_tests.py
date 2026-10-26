"""Lane B tests against the B worktree and exclusive fixture database."""
import asyncio
import os
import sys
from pathlib import Path

root = Path('E:/Study/RoamSync-closeout-b-answers-20261026/backend')
database = 'roamsync_s6_b_unit_test'
os.environ.update(
    PYTHONUTF8='1', APP_ENV='test',
    DATABASE_URL=f'postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/{database}',
    LANGGRAPH_DATABASE_URL=f'postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/{database}',
    PLANNER_API_KEY='', PLANNER_MODEL='', ALLOW_MAP_ESTIMATES='false',
)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
os.chdir(root)
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests'))
import pytest
if '--legacy-unit-estimates' in sys.argv:
    os.environ['ALLOW_MAP_ESTIMATES'] = 'true'
    sys.argv.remove('--legacy-unit-estimates')
raise SystemExit(pytest.main(sys.argv[1:]))
