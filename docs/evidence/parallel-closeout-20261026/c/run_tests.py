"""Windows-compatible tests on the dedicated fixture-only DB, never production."""
import asyncio,os,sys
from pathlib import Path
root=Path('E:/Study/RoamSync-closeout-c-engineering-20261026/backend')
database_name=os.environ.get('ROAMSYNC_C_TEST_DATABASE','roamsync_s6_c_regression_20261026_test')
if not database_name.startswith('roamsync_s6_c_'):
    raise SystemExit('C-lane database prefix required')
os.environ.update(APP_ENV='test',DATABASE_URL=f'postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/{database_name}',
    LANGGRAPH_DATABASE_URL=f'postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/{database_name}',
    PLANNER_API_KEY='',PLANNER_MODEL='',ALLOW_MAP_ESTIMATES='false')
if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
os.chdir(root);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
import pytest
if '--init-schema' in sys.argv:
    from sqlalchemy import create_engine
    from app.database import Base
    from app.place_content.repository import metadata as content_metadata
    from app.drafts.repository import metadata as draft_metadata
    from app.draft_promotion.repository import metadata as promotion_metadata
    engine=create_engine(os.environ['DATABASE_URL'])
    for metadata in (Base.metadata,content_metadata,draft_metadata,promotion_metadata):
        metadata.create_all(engine)
    engine.dispose()
    sys.argv.remove('--init-schema')
if '--legacy-unit-estimates' in sys.argv:
    os.environ['ALLOW_MAP_ESTIMATES']='true'
    sys.argv.remove('--legacy-unit-estimates')
if '--baseline-binder' in sys.argv:
    from app import read_references
    read_references.bind_read_task_reference = lambda task, places: task
    sys.argv.remove('--baseline-binder')
if '--baseline-saved' in sys.argv:
    import subprocess
    from app import saved_trip_reads
    exec(compile(subprocess.check_output(['git','show','d0545e8:backend/app/saved_trip_reads.py'],cwd=root,text=True),
        'd0545e8:backend/app/saved_trip_reads.py','exec'),saved_trip_reads.__dict__)
    sys.argv.remove('--baseline-saved')
if '--baseline-context' in sys.argv:
    # Execute the committed baseline implementation in memory. No checkout
    # file is reverted, and no production/candidate state is constructed.
    import subprocess,types
    from app import companion_context
    baseline=types.ModuleType('stage5_committed_baseline_context')
    exec(compile(subprocess.check_output(['git','show','6318c2d:backend/app/companion_context.py'],cwd=root,text=True),
        '6318c2d:backend/app/companion_context.py','exec'),baseline.__dict__)
    companion_context.CompanionContextReader=baseline.CompanionContextReader
    sys.argv.remove('--baseline-context')
raise SystemExit(pytest.main(sys.argv[1:]))
