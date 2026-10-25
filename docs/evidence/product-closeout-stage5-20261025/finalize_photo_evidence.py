import hashlib,json,subprocess,shutil,sys
from pathlib import Path
import psycopg
from psycopg import sql
ROOT=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
OUT=Path(__file__).parent
runtime=OUT/'runtime-photos'
files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'backend/app').rglob('*.py'))}
app_hash=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
api_receipts=[json.loads(p.read_text(encoding='utf-8')) for p in runtime.glob('api-source-*.json')]
assert len(api_receipts)==1 and api_receipts[0]['app_before']==app_hash
old=json.loads((runtime/'photo-fixture-clone.json').read_text(encoding='utf-8'))['before']
with psycopg.connect('postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_a2_public_stage5_photos_20261025_test') as db:
    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    after={t:sorted([r[0] for r in db.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t').format(sql.Identifier(t)))],key=lambda r:str(r.get('id',r.get('trip_id')))) for t in old}
assert old==after
(runtime/'photo-state-after-refresh.json').write_text(json.dumps({'all_11_tables_unchanged':True,'formal_10_tables_unchanged':True,'after':after},ensure_ascii=False,indent=2),encoding='utf-8')
binding={'product_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'app_sha256':app_hash,'api_start_app_matches_final_product':True,'api_receipt':api_receipts[0],
    'web_files_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'web/src').rglob('*')) if p.is_file()},
    'note':'API source receipt HEAD was eeff461 with then-uncommitted photo code; its exact app bytes match committed product42b3398. Not a fresh model/golden/independent test.'}
(OUT/'photos-source-binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2),encoding='utf-8')
index={'overall':'NO-GO; no new independent score','product_commit':binding['product_commit'],
    'baseline':'photos-before.log: 1 failed, 2 passed; missing fallback',
    'backend':'photos-backend-final.xml:107 passed',
    'web_initial':'photos-web-full.log:272 passed,1 DiscoveryNavigation5000ms timeout',
    'web_isolated':'photos-navigation-isolated.log:7 passed; includes corrected same-city provider mismatch',
    'web_bounded':'photos-web-bounded.log:273 passed,49 files,maxWorkers2',
    'build':'photos-build-final.log:types and Vite pass',
    'real_providers':'photos-real-providers1/2.json retain unavailable attempts, no model calls',
    'browser':'runtime-photos:real exact historical11-table clone,real photos,refresh,credits,unchanged11tables',
    'review':'astra-reference-photos-review.md:three issues repaired,static only',
    'limitations':['search references are not independently verified scenes/licences/current conditions','no fresh whole golden or sealed evaluation','no full new backend engineering freeze','photo lookup external failures retained']}
(OUT/'photos-test-results-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
destination=ROOT/'docs/evidence/product-closeout-stage5-20261025'
assert not destination.exists(),'Refuse overwrite evidence'
destination.mkdir(parents=True)
# Raw evidence remains byte-identical despite Git text normalization.
(destination/'.gitattributes').write_text('* -text\n',encoding='utf-8')
manifest={}
for src in sorted(OUT.rglob('*')):
    if not src.is_file() or '__pycache__' in src.parts or src.suffix=='.pyc':continue
    relative=src.relative_to(OUT)
    target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,target)
    manifest[relative.as_posix()]=hashlib.sha256(src.read_bytes()).hexdigest()
(destination/'MANIFEST.sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'files':len(manifest),'source_bound':True,'all11_unchanged':True}))
