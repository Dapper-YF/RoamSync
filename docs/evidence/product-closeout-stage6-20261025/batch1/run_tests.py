"""Windows-compatible tests on the dedicated fixture-only DB, never production."""
import asyncio,os,sys
from pathlib import Path
root=Path('E:/Study/RoamSync-product-closeout-stage2-20261024/backend')
os.environ.update(APP_ENV='test',DATABASE_URL='postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_test_write_protection',
    LANGGRAPH_DATABASE_URL='postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_test_write_protection',
    PLANNER_API_KEY='',PLANNER_MODEL='',ALLOW_MAP_ESTIMATES='false')
if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
os.chdir(root);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
import pytest
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
