"""Run inside deployed API: separate synthetic session, no reset/approval."""
import asyncio,hashlib,json,uuid,urllib.request
from pathlib import Path
from sqlalchemy import text
from app.database import AssistantSession,session_factory

async def state():
    async with session_factory() as db:
        result={n:(await db.execute(text('SELECT count(*) FROM '+n))).scalar_one() for n in ['trips','planning_runs','plan_revisions']}
        result['trip_versions']=[{'id':str(r.id),'version':r.version} for r in (await db.execute(text('SELECT id,version FROM trips ORDER BY id'))).all()]
        result['formal_rows_sha256']={}
        for n in ['trips','day_plans','activities','plan_revisions']:
            rows=(await db.execute(text(f'SELECT row_to_json(t)::text FROM "{n}" t ORDER BY row_to_json(t)::text'))).scalars().all()
            result['formal_rows_sha256'][n]=hashlib.sha256(json.dumps(rows).encode()).hexdigest()
        return result
async def session():
    async with session_factory() as db:
        row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit();return str(row.id)

manifest=json.loads(Path('/tmp/forecast_source.json').read_text())
checks={n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest()==sha for n,sha in manifest['files'].items() if not n.startswith('tests/') and n!='Dockerfile'}
assert all(checks.values())
before=asyncio.run(state());sid=asyncio.run(session())
report={'source_sha256':manifest['sha256'],'runtime_files_verified':len(checks),'synthetic_session_id':sid,'before':before,'cases':[],'passed':False}
texts=['你好','南京怎么样','根据可靠资料讲讲西湖历史','杭州明天下午天气怎么样','西湖有什么历史，明天下午天气怎么样','杭州现在多少度','帮我规划南京三天']
for i,message in enumerate(texts):
    req=urllib.request.Request('http://127.0.0.1:8000/api/v1/assistant/sessions/'+sid+'/messages',data=json.dumps({'message':message,'message_id':str(uuid.uuid4())},ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=120) as response: data=json.load(response)
        msg=data['messages'][-1];cr=msg.get('companion_result');goal=msg['goal_routing']
        correct=goal['target_runtime']==('planning' if i==6 else 'companion') and goal['mutation_requested']==(i==6)
        if i<6: correct &= msg.get('run_id') is None and data['latest_run_id'] is None
        if i==2: correct &= bool(cr and cr['knowledge_evidence'] and cr['claims'] and not cr['resolved_facts'])
        if i in [3,4]:
            correct &= bool(cr and cr['resolved_facts'] and all(r['usable_as_current'] and r['freshness_status']=='fresh' and r['selected_fact']['nature']=='provider_prediction' for r in cr['resolved_facts']) and 'Open-Meteo' in cr['response_text'] and '预计气温' in cr['response_text'])
        if i==4: correct &= bool(cr['claims'] and cr['knowledge_evidence'])
        if i==5: correct &= bool(cr and not cr['resolved_facts'] and '不能核实当前实测' in cr['response_text'])
        row={'message':message,'correct':bool(correct),'goal':goal,'answer':msg['assistant'],'companion_result':cr,'planning_brief':msg.get('planning_brief'),'run_id':msg.get('run_id'),'error':None}
    except Exception as exc: row={'message':message,'correct':False,'error':type(exc).__name__}
    report['cases'].append(row)
    if i==5:
        report['after_fact_knowledge']=asyncio.run(state())
        report['weather_knowledge_formal_state_unchanged']=before==report['after_fact_knowledge']
    Path('/tmp/forecast_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(i+1,row['correct'],row['error'],flush=True)
report['after']=asyncio.run(state())
report['explicit_planning_run_delta']=report['after']['planning_runs']-report['after_fact_knowledge']['planning_runs']
report['formal_state_unchanged']=before==report['after']
report['passed']=all(r['correct'] for r in report['cases']) and report['weather_knowledge_formal_state_unchanged']
report['complete']=True
Path('/tmp/forecast_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
assert report['passed']
