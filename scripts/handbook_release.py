"""Local release evidence: source manifests and aggregate DB hashes, no row export."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
assert str(ROOT).replace('\\','/').lower()=='e:/study/roamsync'
OUT=ROOT/'docs/evidence/handbook-20261022'
OUT.mkdir(parents=True,exist_ok=True)
DB_CODE='''
import os,json,psycopg
from psycopg import sql
url=os.environ['DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')
with psycopg.connect(url) as db:
 with db.cursor() as c:
  c.execute("select tablename from pg_tables where schemaname='public' order by tablename")
  names=[r[0] for r in c.fetchall()];data={}
  for name in names:
   c.execute(sql.SQL("select count(*),md5(coalesce(string_agg(row_to_json(t)::text,E'\\n' order by row_to_json(t)::text),'')) from public.{} t").format(sql.Identifier(name)))
   n,h=c.fetchone();data[name]={'count':n,'sha':h}
  c.execute('select version_num from alembic_version');version=c.fetchone()[0]
print(json.dumps({'tables':data,'migration':version}))
'''


def db_state():
    raw=subprocess.check_output(['docker','exec','-i','roamsync-api','python','-'],input=DB_CODE.encode())
    return json.loads(raw)


def manifest():
    result={}
    for folder in ('backend/app','backend/migrations','web/src'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':result[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


mode=sys.argv[1]
if len(sys.argv)>2:
    label=sys.argv[2]
    assert label in {'photos','place-handoff'}
    OUT=OUT/label
    OUT.mkdir(parents=True,exist_ok=True)
if mode=='before':
    stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')
    backup=Path('E:/Study/RoamSync-deployment-backups')/('handbook-'+stamp)
    backup.mkdir(parents=True,exist_ok=False)
    state=db_state();state['captured_at']=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat();state['backup_path']=str(backup)
    with (backup/'database.dump').open('wb') as f:
        subprocess.run(['docker','exec','roamsync-postgres','sh','-c','pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],stdout=f,check=True)
    images={}
    for service in ('api','web'):
        container='roamsync-'+service
        image=subprocess.check_output(['docker','inspect','--format','{{.Image}}',container],text=True).strip()
        tag='roamsync-'+service+':before-handbook-'+stamp
        subprocess.run(['docker','tag',image,tag],check=True);images[service]={'image':image,'tag':tag}
    worker_image=subprocess.check_output(['docker','inspect','--format','{{.Image}}','roamsync-agent-worker-1'],text=True).strip()
    tag='roamsync-worker:before-handbook-'+stamp;subprocess.run(['docker','tag',worker_image,tag],check=True);images['worker']={'image':worker_image,'tag':tag}
    state['images']=images
    (OUT/'production-before.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    (backup/'production-before.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print('Backed up production database and tagged current images. Tables:',len(state['tables']))
elif mode in ('after-page','after','after-smoke'):
    before=json.loads((OUT/'production-before.json').read_text(encoding='utf-8'));after=db_state()
    changes=[k for k,v in before['tables'].items() if k!='alembic_version' and after['tables'].get(k)!=v]
    added=sorted(set(after['tables'])-set(before['tables']))
    observation_tables={'assistant_sessions','v2_content_places','route_cache','checkpoint_blobs','checkpoint_writes','checkpoints'}
    unexpected=[k for k in changes if k not in observation_tables]
    after.update({'unchanged_formal_travel_tables':not unexpected,'read_side_effect_tables':[k for k in changes if k in observation_tables],'unchanged_existing_business_tables':not changes,'changed_existing_tables':changes,'added_tables':added,'source_manifest':manifest(),'captured_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()})
    (OUT/f'production-{mode}.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    print('Existing business tables unchanged:',not changes,'Added tables:',added,'Migration:',after['migration'])
    if (unexpected if mode=='after-smoke' else changes):raise SystemExit(1)
