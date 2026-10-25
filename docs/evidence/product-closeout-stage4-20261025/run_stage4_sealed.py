"""Single-use sealed acceptance runner. Creation/compile is NOT execution.

Required freeze JSON keys: git_commit, app_sha256, cases_sha256,
rubric_sha256, runner_sha256. app_sha256 uses run_live.py's backend/app
Python-file digest. Only open sealed inputs AFTER all freeze checks pass.
Uses production application functions and actual providers in a new isolated
database; never seeds candidates/revisions or retries evaluator messages.
This is a service-level harness, not browser/F5 visual acceptance.
"""
import argparse
import asyncio
from datetime import UTC, date, datetime, time, timedelta
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic
from uuid import uuid4

logging.disable(logging.CRITICAL)
sys.dont_write_bytecode = True
SECRETS = []


def normalized(value):
    if hasattr(value, 'model_dump'):
        return normalized(value.model_dump(mode='json'))
    if isinstance(value, dict):
        return {str(k): ('[REDACTED]' if re.search(r'^authorization$|(?:^|_)(?:api_key|rest_key|access_token|refresh_token|password|secret)$|database_url|proxy_url', str(k), re.I)
                         else normalized(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    if isinstance(value, str):
        for secret in SECRETS:
            value = value.replace(secret, '[REDACTED]')
        return value
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)


def dump(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(normalized(value), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hash(root):
    files = {p.relative_to(root).as_posix(): sha(p) for p in sorted((root / 'backend/app').rglob('*.py'))}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def verify_freeze(args, initial=None):
    manifest = json.loads(args.freeze_manifest.read_text(encoding='utf-8-sig'))
    observed = {
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.app_root, text=True).strip(),
        'app_sha256': source_hash(args.app_root), 'cases_sha256': sha(args.cases),
        'rubric_sha256': sha(args.rubric), 'runner_sha256': sha(Path(__file__)), 'saved_fixture_sha256':sha(args.saved_fixture),
        'clone_helper_sha256':sha(Path(__file__).with_name('clone_saved_fixture.py')),
    }
    for key, actual in observed.items():
        if manifest.get(key) != actual:
            raise RuntimeError('Freeze mismatch: ' + key)
    manifest_sha = sha(args.freeze_manifest)
    if initial is not None and (manifest_sha != initial['manifest_sha256'] or observed != initial['observed']):
        raise RuntimeError('Frozen identity changed after execution started')
    return {'manifest': manifest, 'manifest_sha256': manifest_sha, 'observed': observed,
            'git_status': subprocess.check_output(['git', 'status', '--porcelain'], cwd=args.app_root, text=True)}


def error(exc):
    body = getattr(exc, 'body', None)
    detail = body.get('error', body) if isinstance(body, dict) else {}
    return {'error_type': type(exc).__name__, 'error_code': getattr(exc, 'code', None),
            'http_status': getattr(exc, 'status_code', None), 'provider_error_code': detail.get('code')}


def install_observers(sink):
    # Patch the function owner before importing consumers; all later imports
    # retain real model behavior. Never capture hidden reasoning deltas.
    module = importlib.import_module('app.model_client')
    original = module.create_model_response

    async def model(*args, **kwargs):
        event = {'kind': 'model', 'started_at': datetime.now(UTC).isoformat(),
                 'request': {k: normalized(kwargs[k]) for k in (
                     'model', 'instructions', 'input_text', 'text_format', 'reasoning_effort',
                     'max_output_tokens', 'temperature') if k in kwargs}}
        sink.append(event)
        started = monotonic()
        try:
            result = await original(*args, **kwargs)
            event.update(status=result.status, visible_output=result.output_text,
                         usage=normalized(getattr(result, 'usage', None)))
            return result
        except BaseException as exc:
            event.update(error(exc))
            raise
        finally:
            event['seconds'] = round(monotonic() - started, 3)
    module.create_model_response = model

    def wrap(fn, name, method=False):
        async def observed(*args, **kwargs):
            event = {'kind': 'tool', 'tool': name, 'args': normalized(args[1:] if method else args),
                     'kwargs': normalized(kwargs), 'started_at': datetime.now(UTC).isoformat()}
            sink.append(event)
            started = monotonic()
            try:
                result = await fn(*args, **kwargs)
                event['result'] = normalized(result)
                return result
            except BaseException as exc:
                event.update(error(exc))
                raise
            finally:
                event['seconds'] = round(monotonic() - started, 3)
        return observed

    from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
    transport=importlib.import_module('app.map_transport')
    original_map=transport.get_json
    def observed_map(url,**kwargs):
        parsed=urlsplit(url)
        safe=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode([(k,v) for k,v in parse_qsl(parsed.query) if k.lower() not in {'key','sig','token'}]),''))
        event={'kind':'amap_wire','url':safe};sink.append(event)
        try:
            result=original_map(url,**kwargs);event['result']=normalized(result);return result
        except Exception as exc:
            event.update(error(exc));raise
    transport.get_json=observed_map

    for module_name, cls_name, methods in (
        ('app.place_content.provider', 'AMapContentProvider', ('search', 'detail', 'route')),
        ('app.place_content.service', 'PlaceContentService', ('search', 'get_place', 'query_route')),
    ):
        cls = getattr(importlib.import_module(module_name), cls_name)
        for name in methods:
            setattr(cls, name, wrap(getattr(cls, name), cls_name + '.' + name, method=True))
    for module_name, names in (
        ('app.assistant_search', ('search_tavily',)),
        ('app.external_facts', ('search_tavily', 'extract_tavily')),
    ):
        module = importlib.import_module(module_name)
        for name in names:
            setattr(module, name, wrap(getattr(module, name), module_name + '.' + name))



async def run(args, settings, cases, rubric, report):
    from sqlalchemy import create_engine, select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.database import (Base, AssistantSession, Trip, DayPlan, Activity, SourceRecord, PlaceCandidate,
                              TripArrangementItem, TripPreferences, RouteLeg, PlanningRun, PlanRevision)
    from app.place_content.repository import ContentRepository, metadata as content_metadata
    from app.drafts.repository import DraftRepository, metadata as draft_metadata, drafts
    from app.draft_promotion.repository import metadata as promotion_metadata, prepared_plans, promotions
    from app.place_content.provider import AMapContentProvider
    from app.place_content.service import PlaceContentService
    from app.assistant_places import ContentServicePlaces
    from app.assistant_service import send_message
    from app.assistant_capabilities import select_capabilities
    from app.agent_worker import claim_next_run, execute_claimed_run
    from app.conversation_candidate.commands import CandidateCommand, validate_command
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    sync = create_engine(settings.database_url, poolclass=NullPool)
    for metadata in (Base.metadata, content_metadata, draft_metadata, promotion_metadata):
        metadata.create_all(sync)
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_database_url) as saver:
        await saver.setup()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    formal = (Trip, DayPlan, Activity, TripPreferences, TripArrangementItem, RouteLeg, PlanningRun, PlanRevision)

    async def state():
        async with sessions() as db:
            result = {}
            for model in formal:
                rows = [dict(r) for r in (await db.execute(select(model.__table__))).mappings()]
                rows.sort(key=lambda r: str(r.get('id', r.get('trip_id'))))
                result[model.__name__] = {'count': len(rows), 'sha256': hashlib.sha256(
                    json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest(), 'rows': normalized(rows)}
            return result

    async def session_state(sid):
        async with sessions() as db:
            row = await db.get(AssistantSession, sid)
            data = {'id': str(sid), 'trip_id': str(row.trip_id) if row.trip_id else None,
                    'latest_run_id': str(row.latest_run_id) if row.latest_run_id else None,
                    'messages': row.messages, 'pending_action': row.pending_action, 'applied_actions': row.applied_actions}
            data['durable_candidate_tables'] = {}
            for table in (drafts, prepared_plans, promotions):
                records = [dict(r) for r in (await db.execute(select(table))).mappings()]
                data['durable_candidate_tables'][table.name] = normalized(records)
            return normalized(data)

    # Record actual formal writer entry points, including no-value-change calls.
    import app.plan_revision_service as revision_service
    original_accept=revision_service.accept_plan_revision
    async def observed_accept(*a,**kw):
        event={'kind':'formal_write_call','writer':'accept_plan_revision','revision_id':str(a[1]) if len(a)>1 else None}
        report['_event_sink'].append(event)
        try:
            value=await original_accept(*a,**kw)
            event['status']='returned'
            return value
        except Exception as exc:
            event.update(error(exc))
            raise
    revision_service.accept_plan_revision=observed_accept
    for loaded in list(sys.modules.values()):
        if getattr(loaded,'__name__','').startswith('app.'):
            for key,value in list(vars(loaded).items()):
                if value is original_accept:
                    setattr(loaded,key,observed_accept)
    # SQL entry tracing also sees formal no-op writes and internal writers;
    # parameters are retained only in the private synthetic evidence package.
    from sqlalchemy import event
    formal_names=('trips','day_plans','activities','trip_preferences','trip_arrangement_items','route_legs')
    def sql_write(conn,cursor,statement,parameters,context,executemany):
        if re.search(r'^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:"?public"?\.)?"?(?:'+ '|'.join(formal_names)+r')"?\b',statement,re.I):
            report['_event_sink'].append({'kind':'formal_sql_call','statement':statement,'parameters':normalized(parameters),'executemany':executemany})
    from sqlalchemy.engine import Engine
    event.listen(Engine,'before_cursor_execute',sql_write)
    case_sessions = {}
    report['fixture_setup'] = []
    async with sessions() as db:
        for index, case in enumerate(cases):
            trip_id = None
            # Group association is positional in the sealed evaluation contract;
            # all fixture values are read from sealed rubric only at execution.
            if index == 4:
                from clone_saved_fixture import clone
                trip_id, clone_receipt=await clone(db,args.saved_fixture,report['freeze_before']['manifest']['saved_fixture_snapshot_sha256'])
                report['fixture_setup'].append({'case_id':case['id'],'trip_id':str(trip_id),**clone_receipt})
            row = AssistantSession(trip_id=trip_id, messages=[], applied_actions={})
            db.add(row)
            await db.flush()
            case_sessions[case['id']] = row.id
        await db.commit()
    report['before'] = await state()
    report['schema_setup'] = 'Base/content/draft/promotion metadata create_all and checkpoint setup on new test DB; not migration acceptance'
    dump(args.output, report)
    seen_messages = set()
    displayed_revisions = {}

    try:
        for case in cases:
            sid = case_sessions[case['id']]
            for turn_index, message in enumerate(case['messages'], 1):
                freeze_before = verify_freeze(args, report['freeze_before'])
                key = (case['id'], turn_index)
                if key in seen_messages:
                    raise RuntimeError('Duplicate evaluator message blocked')
                seen_messages.add(key)
                mid = uuid4()
                record = {'case_id': case['id'], 'case_turn': turn_index, 'turn': len(report['records']) + 1,
                          'user': message, 'message_id': str(mid), 'session_id': str(sid),
                          'attempt': 1, 'started_at': datetime.now(UTC).isoformat(), 'events': [],
                          'before_state': await state(), 'session_before': await session_state(sid),
                          'source_before': freeze_before['observed']}
                report['records'].append(record)
                report['_active_events'] = record['events']
                # The observer sink is shared, then partitioned at turn boundaries.
                offset = len(report['_event_sink'])
                ctx = {'topic_id': case['id'], 'prefer_flexible': True}
                async with sessions() as db:
                    current = await db.get(AssistantSession, sid)
                    if current.trip_id:
                        trip = await db.get(Trip, current.trip_id)
                        ctx.update(surface='trip', read_trip_id=str(trip.id), action_target={
                            'trip_id': str(trip.id), 'expected_version': trip.version, 'operation': 'plan_trip',
                            'authorization_message_id': str(mid)})
                        shown=displayed_revisions.get(case['id'])
                        if shown:
                            ctx['action_target'].update(revision_id=shown['revision_id'],revision_hash=shown['presentation_hash'])
                            record['displayed_binding']=shown
                record['request_context'] = ctx
                dump(args.output, {k: v for k, v in report.items() if not k.startswith('_')})
                started = monotonic()
                choices = []

                async def selector(*a):
                    selected = await select_capabilities(*a)
                    choices.append(selected.model_dump(mode='json'))
                    return selected

                port = ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),
                    ContentRepository(sync)), DraftRepository(sync), owner='sealed-stage4-synthetic')
                try:
                    async with sessions() as db:
                        row = await asyncio.wait_for(send_message(db, sid, message, mid, context=ctx,
                            place_port=port, capability_selector=selector), timeout=args.turn_timeout)
                        record.update(raw=row.messages[-1] if row.messages else None,
                                      pending_action=row.pending_action, latest_run_id=str(row.latest_run_id) if row.latest_run_id else None)
                        next_run = row.latest_run_id
                    if next_run:
                        async with sessions() as db:
                            current_run = await db.get(PlanningRun, next_run)
                            queued = current_run is not None and current_run.status == 'queued'
                            outstanding = list((await db.scalars(select(PlanningRun.id).where(
                                PlanningRun.status.in_(['queued', 'researching', 'planning', 'validating'])))).all())
                        if queued:
                            if outstanding != [next_run]:
                                raise RuntimeError('Unexpected outstanding run: refusing to execute another case')
                            claim = await claim_next_run()
                            if claim is None or claim.run_id != next_run:
                                raise RuntimeError('Actual Worker claim mismatch')
                            record['worker_claim'] = {'run_id': str(claim.run_id), 'matches_requested': True}
                            await asyncio.wait_for(execute_claimed_run(claim), timeout=args.worker_timeout)
                        async with sessions() as db:
                            run_row = (await db.execute(select(PlanningRun.__table__).where(PlanningRun.id == next_run))).mappings().one()
                            record['worker_terminal'] = normalized(dict(run_row))
                            revisions = [dict(r) for r in (await db.execute(select(PlanRevision.__table__).where(
                                PlanRevision.planning_run_id == next_run))).mappings()]
                            record['revisions_after_worker'] = normalized(revisions)
                            pending = [r for r in revisions if r['status'] == 'pending']
                            if len(pending) == 1:
                                trip = await db.get(Trip, pending[0]['trip_id'])
                                # Record the same server candidate payload a client would display;
                                # an adoption context can only bind this prior returned object.
                                displayed_revisions[case['id']] = {'revision_id': str(pending[0]['id']),
                                    'run_id': str(next_run), 'trip_id': str(trip.id), 'trip_version': trip.version,
                                    'displayed_after_message_id': str(mid), 'snapshot': normalized(pending[0]),
                                    'presentation_hash': __import__('app.revision_presentation',fromlist=['revision_presentation_hash']).revision_presentation_hash(await db.get(PlanRevision,pending[0]['id']))}
                                record['candidate_readback'] = displayed_revisions[case['id']]
                except Exception as exc:
                    record.update(error(exc))
                finally:
                    record.update(seconds=round(monotonic() - started, 3), choices=choices,
                                  events=report['_event_sink'][offset:], after_state=await state(),
                                  session_after=await session_state(sid))
                    record['formal_diff'] = {name: {'before': record['before_state'][name]['sha256'],
                        'after': record['after_state'][name]['sha256'],
                        'changed': record['before_state'][name]['sha256'] != record['after_state'][name]['sha256']}
                        for name in record['before_state']}
                    record['source_after'] = verify_freeze(args, report['freeze_before'])['observed']
                    dump(args.output, {k: v for k, v in report.items() if not k.startswith('_')})
                    print(json.dumps({'turn': record['turn'], 'seconds': record['seconds'],
                                      'error_type': record.get('error_type')}, ensure_ascii=True), flush=True)
        report.update(completed_turns=len(seen_messages), after=await state(), freeze_after=verify_freeze(args, report['freeze_before']),
                      completed_at=datetime.now(UTC).isoformat(), execution_status='completed_once')
    finally:
        report.pop('_active_events', None)
        report.pop('_event_sink', None)
        try:
            report['freeze_finally'] = verify_freeze(args, report['freeze_before'])
        except Exception as exc:
            report['source_integrity_failure'] = error(exc)
            report['execution_status'] = 'invalid_source_changed'
        dump(args.output, report)
        await engine.dispose()
        sync.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, required=True)
    parser.add_argument('--settings-source', type=Path, required=True)
    parser.add_argument('--database-name', required=True)
    parser.add_argument('--freeze-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', type=Path, default=Path(__file__).parent / 'private-final/cases.json')
    parser.add_argument('--rubric', type=Path, default=Path(__file__).parent / 'private-final/rubric.json')
    parser.add_argument('--saved-fixture',type=Path,required=True)
    parser.add_argument('--turn-timeout', type=int, default=120)
    parser.add_argument('--worker-timeout', type=int, default=420)
    args = parser.parse_args()
    args.app_root = args.app_root.resolve()
    if args.app_root == Path('E:/Study/RoamSync').resolve():
        raise SystemExit('Official source refused')
    if not re.fullmatch(r'roamsync_agent_b3_stage4_sealed_[a-z0-9_]+_test', args.database_name):
        raise SystemExit('Exclusive stage3 sealed test database name required')
    if args.output.exists():
        raise SystemExit('Refusing to overwrite evidence')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frozen = verify_freeze(args)
    # No provider or DB call occurs before the freeze gate and strict input check.
    cases = json.loads(args.cases.read_text(encoding='utf-8-sig'))
    rubric = args.rubric.read_text(encoding='utf-8-sig')
    if (len(cases) != 5 or len({c['id'] for c in cases}) != 5
            or any(len(c['messages']) != 4 or len(c['criteria']) != 4 for c in cases)):
        raise SystemExit('Expected exactly five groups of four original messages')
    sys.path.insert(0, str(args.app_root / 'backend'))
    from app.config import Settings, get_settings
    configured = Settings(_env_file=args.settings_source)
    for name in ('planner_provider', 'planner_api_key', 'planner_model', 'planner_base_url', 'planner_proxy_url',
                 'planner_max_output_tokens', 'planner_timeout_seconds', 'planner_max_candidates',
                 'intent_reasoning_effort', 'research_reasoning_effort', 'amap_rest_key', 'tavily_api_key',
                 'roamsync_tavily_api_key', 'tavily_base_url', 'tavily_proxy_url'):
        value = getattr(configured, name)
        value = value.get_secret_value() if hasattr(value, 'get_secret_value') else str(value)
        if ('key' in name or 'proxy_url' in name) and len(value) >= 6:
            SECRETS.append(value)
        os.environ[name.upper()] = value.replace('host.docker.internal', '127.0.0.1')
    if not os.environ.get('PLANNER_PROXY_URL'):
        from dotenv import dotenv_values
        values = dotenv_values(args.settings_source)
        os.environ['PLANNER_PROXY_URL'] = (values.get('HTTP_PROXY') or '').replace('host.docker.internal', '127.0.0.1')
    url = 'postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/' + args.database_name
    os.environ.update(APP_ENV='test', DATABASE_URL=url, LANGGRAPH_DATABASE_URL=url.replace('+psycopg', ''),
                      PLANNER_REASONING_EFFORT='high', PLANNER_MAX_RETRIES='0', ALLOW_MAP_ESTIMATES='false')
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.planner_model or not settings.planner_api_key.get_secret_value() or not settings.amap_rest_key:
        raise SystemExit('Real model and AMap configuration required')
    config = {k: str(getattr(settings, k)) for k in ('planner_provider', 'planner_model', 'planner_base_url',
        'planner_reasoning_effort', 'planner_max_output_tokens', 'planner_timeout_seconds', 'planner_max_retries',
        'intent_reasoning_effort', 'research_reasoning_effort', 'allow_map_estimates', 'agent_run_timeout_seconds')}
    lock = args.cases.parent / 'execution_started.json'
    with lock.open('x', encoding='utf-8') as handle:
        json.dump({'started_at': datetime.now(UTC).isoformat(), 'output': str(args.output),
                   'database_name': args.database_name, 'freeze': frozen['observed']}, handle, indent=2)
    report = {'evaluation': 'stage4-sealed-single-sample', 'execution_status': 'started', 'freeze_before': frozen,
              'configuration': config, 'config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
              'database_name': args.database_name, 'records': [], 'provider_execution': 'real',
              'browser_visual_acceptance': 'not_exercised_service_level_runner',
              'evaluator_reruns': 0, 'expected_turns': 20, '_event_sink': []}
    dump(args.output, {k: v for k, v in report.items() if not k.startswith('_')})
    import psycopg
    from psycopg import sql
    with psycopg.connect('postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/postgres', autocommit=True) as conn:
        if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (args.database_name,)).fetchone():
            raise SystemExit('Test database already exists; refusing to reuse')
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(args.database_name)))
    install_observers(report['_event_sink'])
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args, settings, cases, rubric, report))


if __name__ == '__main__':
    main()
