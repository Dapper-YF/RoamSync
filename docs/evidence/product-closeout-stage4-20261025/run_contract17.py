import json, os, subprocess, sys
from pathlib import Path
root = Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
out = Path(__file__).parent
files = ['read_references.py', 'assistant_capabilities.py', 'revision_presentation.py']
saved = {name: (root/'backend/app'/name).read_bytes() for name in files}
env = dict(os.environ, PYTHONUTF8='1')
base = [sys.executable, 'E:/Study/RoamSync-stage3-evidence-20261024/run_unit.py', '--root', str(root)]
results = {}
try:
    for name in files:
        (root/'backend/app'/name).write_bytes(subprocess.check_output(['git','show','cd56320:backend/app/'+name], cwd=root))
    with (out/'contract17-baseline.log').open('w', encoding='utf-8') as log:
        results['baseline'] = subprocess.run(base + ['--db', 'roamsync_stage3_stage4_contract17_before_test',
            'tests/test_stage4_task_contract.py','tests/test_stage4_revision_binding.py','-q',
            '--junitxml='+str(out/'contract17-baseline.xml')], env=env, stdout=log, stderr=subprocess.STDOUT).returncode
finally:
    for name, data in saved.items():
        (root/'backend/app'/name).write_bytes(data)
with (out/'contract17-after.log').open('w', encoding='utf-8') as log:
    results['after'] = subprocess.run(base + ['--db', 'roamsync_stage3_stage4_contract17_after_test',
        'tests/test_stage4_task_contract.py','tests/test_stage4_revision_binding.py',
        'tests/test_stage3_continuity.py','tests/test_stage2_read_continuity.py','tests/test_decision_memory.py','-q',
        '--junitxml='+str(out/'contract17-after.xml')], env=env, stdout=log, stderr=subprocess.STDOUT).returncode
(out/'contract17-results.json').write_text(json.dumps(results), encoding='utf-8')
