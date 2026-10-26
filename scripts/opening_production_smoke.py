"""Deployed HTTP smoke; synthetic Assistant session, no reset or approval."""
import asyncio
import hashlib
import json
import uuid
import urllib.request
from pathlib import Path
from sqlalchemy import text
from app.database import AssistantSession, session_factory

async def state():
    async with session_factory() as db:
        names=['trips','day_plans','activities','planning_runs','plan_revisions','trip_executions','navigation_sessions']
        result={}
        for name in names:
            rows=(await db.execute(text(f'SELECT row_to_json(t)::text FROM "{name}" t ORDER BY row_to_json(t)::text'))).scalars().all()
            result[name]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
        result['trip_versions']=[{'id':str(r.id),'version':r.version} for r in (await db.execute(text('SELECT id,version FROM trips ORDER BY id'))).all()]
        return result

async def session():
    async with session_factory() as db:
        row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit();return str(row.id)

if __name__=='__main__':
    import sys
    if '--snapshot-only' in sys.argv:
        print(json.dumps(asyncio.run(state())));sys.exit(0)
    manifest=json.loads(Path('/tmp/opening_source.json').read_text())
    checks={name:hashlib.sha256((Path('/app')/name).read_bytes()).hexdigest()==sha for name,sha in manifest['files'].items() if not name.startswith('tests/') and name!='Dockerfile'}
    assert all(checks.values())
    before=asyncio.run(state());sid=asyncio.run(session())
    report={'source_sha256':manifest['sha256'],'runtime_files_verified':len(checks),'before':before,'session_id':sid,'cases':[],'passed':False}
    texts=['你好','南京怎么样','根据可靠资料讲讲西湖历史','杭州明天下午天气怎么样','南京博物院明天几点开门？','浙江省博物馆之江馆区9月28日开馆吗？','南京博物院2027年10月2日开放时间？','南京博物院现在开着吗？','南京博物院明天几点开门，南京明天下午天气如何？','帮我规划南京三天']
    for i,message in enumerate(texts):
        request=urllib.request.Request(f'http://127.0.0.1:8000/api/v1/assistant/sessions/{sid}/messages',data=json.dumps({'message':message,'message_id':str(uuid.uuid4())},ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=120) as response: data=json.load(response)
            msg=data['messages'][-1];cr=msg.get('companion_result');goal=msg['goal_routing']
            correct=goal['target_runtime']==('planning' if i==9 else 'companion') and goal['mutation_requested']==(i==9)
            if i<9: correct &= msg.get('run_id') is None and data['latest_run_id'] is None
            if i==2: correct &= bool(cr and cr['claims'] and cr['knowledge_evidence'])
            if i in (3,8): correct &= bool(cr and any(r['requirement']['fact_type']=='weather.forecast' and r['usable_as_current'] for r in cr['resolved_facts']) and '预计气温' in cr['response_text'])
            if i in (4,5,8):
                hours=[r for r in cr['resolved_facts'] if r['requirement']['fact_type']=='place.opening_hours']
                correct &= bool(hours and all(r['usable_as_current'] for r in hours))
                if i==5: correct &= hours[0]['value']['closed_all_day']
            if i==6: correct &= bool(cr and not any(r['usable_as_current'] for r in cr['resolved_facts']) and '不能确认' in cr['response_text'])
            if i==7: correct &= bool(cr and not cr['resolved_facts'] and '不能确认场馆现在' in cr['response_text'])
            if i==9: correct &= bool(msg.get('planning_brief') and '南京' in json.dumps(msg['planning_brief'],ensure_ascii=False))
            row={'message':message,'correct':bool(correct),'goal':goal,'answer':msg['assistant'],'companion_result':cr,'planning_brief':msg.get('planning_brief'),'run_id':msg.get('run_id'),'error':None}
        except Exception as exc: row={'message':message,'correct':False,'error':type(exc).__name__}
        report['cases'].append(row)
        if i==8:
            report['after_companion']=asyncio.run(state());report['companion_formal_state_unchanged']=before==report['after_companion']
        Path('/tmp/opening_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(i+1,row['correct'],row['error'],flush=True)
    report['after']=asyncio.run(state());report['formal_state_unchanged']=before==report['after']
    report['planning_run_delta']=report['after']['planning_runs']['count']-report['after_companion']['planning_runs']['count']
    report['passed']=all(r['correct'] for r in report['cases']) and report['companion_formal_state_unchanged']
    report['complete']=True
    Path('/tmp/opening_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    assert report['passed']
