"""Finite real-service probes and isolated PG wait sampling; no mock providers."""
import json
import os
from pathlib import Path
from threading import Event, Thread
from time import perf_counter
from datetime import datetime, UTC
from uuid import uuid4

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/evidence/natural-closure-20261020'
OUT.mkdir(exist_ok=True)
assert os.environ.get('ROAMSYNC_TASK_PG_PORT', '').isdigit()
port = os.environ['ROAMSYNC_TASK_PG_PORT']
report = {'kind': 'real model/API; deterministic commands explicitly distinguished; synthetic data', 'cases': [], 'locks': []}
OUTPUT = OUT / f'finite-live-{uuid4()}.json'
stop = Event()


def sample_locks():
    with psycopg.connect(f'postgresql://write_test:write_test_only@127.0.0.1:{port}/roamsync_natural_live_test', autocommit=True) as db:
        while not stop.wait(1):
            row = db.execute("SELECT count(*) FILTER (WHERE wait_event_type='Lock'), coalesce(max(extract(epoch from now()-xact_start)) FILTER (WHERE state='active'),0) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()").fetchone()
            report['locks'].append({'at': datetime.now(UTC).isoformat(), 'waiting_for_lock': row[0], 'max_active_transaction_age_seconds': float(row[1])})


thread = Thread(target=sample_locks, daemon=True)
thread.start()
with httpx.Client(base_url='http://127.0.0.1:18019', timeout=180, trust_env=False) as c:
    def run_case(name, sid, message, context, check, *, expected_path):
        start = perf_counter()
        mid = str(uuid4())
        context = json.loads(json.dumps(context))
        if 'action_target' in context:
            context['action_target']['authorization_message_id'] = mid
        response = c.post(f'/api/v1/assistant/sessions/{sid}/messages', json={'message': message, 'message_id': mid, 'context': context})
        try:
            body = response.json()
        except ValueError:
            body = {'non_json_response':response.text[:500]}
        item = {'name': name, 'input': message, 'context': context, 'status': response.status_code,
            'elapsed_ms': round((perf_counter()-start)*1000), 'expected_path': expected_path, 'body': body}
        item['telemetry'] = c.get(f'/api/v1/agent-monitor/sessions/{sid}/messages/{mid}').json()
        try:
            response.raise_for_status()
            check(body)
            item['verdict'] = 'PASS'
        except Exception as error:
            item['verdict'] = 'FAIL'
            item['failure'] = str(error)
        report['cases'].append(item)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(name, item['verdict'], flush=True)
        return body

    sid = c.post('/api/v1/assistant/sessions', json={}).json()['id']
    context = {'version': 'assistant-context-v1', 'topic_id': 'finite-consult', 'surface': 'assistant', 'prefer_flexible': True}
    before = c.get('/api/v1/trips').json()
    def consultation(body):
        assert body['trip_id'] is None and body['pending_action'] is None and body['latest_run_id'] is None
        assert c.get('/api/v1/trips').json() == before
        assert body['messages'][-1]['assistant'].strip()
    run_case('culture-consultation', sid, '南京有哪些历史文化特点？先了解，不规划旅行。', context, consultation, expected_path='real Companion model, no formal writes')
    run_case('place-comparison', sid, '南京博物院与玄武湖适合怎样不同的体验？先不安排。', context, consultation, expected_path='real Companion model, no Planner')
    run_case('interest-is-not-adoption', sid, '南京博物院听起来不错，我感兴趣，但还没决定出行。', context, consultation, expected_path='real model or bounded reply; no adoption')

    # Existing one-Trip browser success supplies actual IDs, never a production trip.
    paths = sorted((ROOT/'docs/evidence/natural-assistant').glob('web-live-2026-10-20*.json'))
    successful = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    seed = next(p for p in reversed(successful) if str(p.get('result','')).startswith('PASS'))
    tid = next(s['trip_id'] for s in seed['steps'] if s['step']=='page-plus-chat-readback')
    sid = c.post('/api/v1/assistant/sessions', json={'trip_id':tid}).json()['id']
    def current():
        return c.get(f'/api/v1/trips/{tid}/arrangement-items').json()
    def bound(operation='plan_trip'):
        return {'version':'assistant-context-v1','topic_id':'finite-bound','surface':'trip','prefer_flexible':True,
            'read_trip_id':tid, 'action_target':{'trip_id':tid,'expected_version':current()['version'],'operation':operation}}
    def simple(body):
        assert body['messages'][-1]['run_id'] is None  # latest_run_id may retain an older accepted run.
        assert body['messages'][-1]['tool'] == 'arrangement_edit'
    state = current()
    result = run_case('simple-duration-no-graph', sid, '请把南京博物院的停留时长改为20分钟，其他日期保持不变。', bound(), simple, expected_path='deterministic existing update_activity, no model')
    after = current()
    report['cases'][-1]['saved_result'] = after
    assert state['days'][0] == after['days'][0]
    run_case('explicit-cancellation', sid, '取消玄武湖', bound('edit_arrangement'), simple, expected_path='deterministic choice command; not a global dislike')
    report['cases'][-1]['saved_result'] = current()
    assert next(i for i in current()['items'] if '玄武湖' in i['label'])['kind']=='cancelled'
    state = current()
    def ambiguous(body):
        assert not body['messages'][-1].get('run_id')
        assert current() == state
    run_case('ambiguous-user-reference', sid, '刚才说的那个不去了。', bound(), ambiguous, expected_path='real routing; clarify or safe answer, no guessed cancellation')
    report['cases'][-1]['saved_result'] = current()
    stop.set()
    thread.join(timeout=3)
    report['summary'] = {v:sum(case['verdict']==v for case in report['cases']) for v in ['PASS','FAIL']}
    report['measurement_limits'] = '1-second samples are not a deadlock proof; model counts from telemetry stages are observed lower bounds. No hard walking-limit guarantee tested.'
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(report['summary'], OUTPUT, flush=True)
