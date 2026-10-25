import atexit, hashlib, json, os, runpy, subprocess, sys
from pathlib import Path
root = Path(os.environ['RS_PUBLIC_SOURCE'])
out = Path(os.environ['RS_PUBLIC_OUTPUT']); out.mkdir(parents=True, exist_ok=True)
def source():
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root/'backend/app').rglob('*.py'))}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
before = source()
receipt = {'pid': os.getpid(), 'mode': sys.argv[1], 'app_before': before,
    'git_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
path = out/f'{sys.argv[1]}-source-{os.getpid()}.json'
path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
def finalize():
    receipt.update(app_after=source(), source_unchanged=source()==before)
    path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
atexit.register(finalize)
runpy.run_path('E:/Study/RoamSync-stage3-evidence-20261024/runtime_recorded.py', run_name='__main__')
