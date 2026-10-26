import hashlib, json, pathlib, subprocess, sys
from dotenv import dotenv_values

A = pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W = pathlib.Path(sys.argv[2]) if len(sys.argv)>2 else pathlib.Path(r'E:\Study\RoamSync-planner-reliability-clean-20261008')
SHA = sys.argv[3] if len(sys.argv)>3 else '26e33f7ecec848403c0992953c61216ddb305fec'
TAG = SHA[:7]
mode = sys.argv[1]
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=W).decode().strip() == SHA
assert not subprocess.check_output(['git', '-c', 'core.autocrlf=false', 'status', '--porcelain'], cwd=W)
args = ['docker','build','--progress=plain']
if mode in ('backend','test'):
    args += ['--target', 'production' if mode=='backend' else 'test', '-t', f'roamsync-reliability-{mode}:{TAG}', str(W/'backend')]
elif mode == 'web':
    cfg = dotenv_values(r'E:\Study\RoamSync\.env')
    assert cfg.get('AMAP_WEB_KEY') and cfg.get('AMAP_SECURITY_CODE')
    args += ['--build-arg','VITE_AMAP_WEB_KEY='+cfg['AMAP_WEB_KEY'],'--build-arg','VITE_AMAP_SECURITY_CODE='+cfg['AMAP_SECURITY_CODE'],'-t',f'roamsync-reliability-web:{TAG}',str(W/'web')]
else:
    raise ValueError(mode)
with (A/f'candidate_{TAG}_{mode}_build.log').open('w',encoding='utf-8') as out:
    result = subprocess.run(args, stdout=out, stderr=subprocess.STDOUT)
print(mode, 'build exit', result.returncode)
if result.returncode: sys.exit(result.returncode)
info=json.loads(subprocess.check_output(['docker','image','inspect',f'roamsync-reliability-{mode}:{TAG}']))[0]
(A/f'candidate_{TAG}_{mode}_image.json').write_text(json.dumps({'git_commit':SHA,'image':info['Id'],'rootfs':info['RootFS'],'build_log_sha256':hashlib.sha256((A/f'candidate_{TAG}_{mode}_build.log').read_bytes()).hexdigest()},indent=2),encoding='utf-8')
