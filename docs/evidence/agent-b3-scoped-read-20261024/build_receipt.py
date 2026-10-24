"""Validate captured artifacts and publish author review; no model/DB rerun.

Review labels below are an explicit reading of the entire visible replies and
fixture requirements. They are not a hidden automated judge or a blind score.
"""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REVIEW = {
    'public-before.json': [False, False, False, False, True, False],
    'public-after.json': [True, True, True, False, True, True],
    'public-after-final.json': [True]*6,
    'public-after-pool-final.json': [True, False, True, True, True, True],
}
REASONS = [
    'Only day3 five saved activities, optional tea and lunch free window; no live venue claim.',
    'Selected day3 a13, saved60 minutes; not day1 same-name a03 or suggested visit duration.',
    'No verified original rationale is saved; honestly unavailable, no invented original reason.',
    'Day1 a03 saved45 minutes, no inherited page selection or day3 date.',
    'Only day2 five activities after explicit topic redirection, no day3 leakage.',
    'Selected day3 date and60 minutes; formal state unchanged, no pending write/Run.',
]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    fixture = ROOT/'backend/evals/fixtures/b3_scoped_read_public.json'
    required = json.loads(fixture.read_text(encoding='utf-8'))
    summary = {'reviewer': 'B code author; not blind/independent/heldout',
        'criteria': 'All material fixture must observations, no unsupported fact or unauthorized formal write.',
        'split': 'repeated public-development', 'fixture_sha256': sha(fixture), 'runs': []}
    rendered = ['# Full public development replies\n',
        'All four captures retained. Ratings are B author review, not independent or heldout.\n']
    config = None
    for name, passes in REVIEW.items():
        run = json.loads((HERE/name).read_text(encoding='utf-8'))
        assert len(run['records']) == 6 and run['fixture_sha256'] == sha(fixture)
        assert run['source_unchanged'] and run['formal_state_unchanged']
        assert config is None or config == run['config_fingerprint']
        config = run['config_fingerprint']
        rendered.append(f"## {name} ({sum(passes)}/6)\n")
        judgments = []
        for record, turn, passed, reason in zip(run['records'], required['turns'], passes, REASONS):
            assert record['user'] == turn['user'] and not record.get('error_type')
            assert record['formal_state'] == run['before']
            assert not record['pending_action'] and not record['latest_run_id']
            raw = record['raw']; reply = raw['assistant']
            diagnosis = reason if passed else ('Selector emitted forbidden extra trip field; schema rejected it and returned generic retry; no requested saved value.'
                if name=='public-after-pool-final.json' else
                'Generic clarification asks for already available read target; material user goal not answered.')
            judgments.append({'turn': record['turn'], 'all_material_must_satisfied': passed,
                'reason': diagnosis, 'seconds': record['seconds'],
                'formal_unchanged': True, 'no_pending_or_run': True,
                'tool_calls': len(record['calls']), 'visible_model_calls': len(record['model_outputs'])})
            rendered.extend([f"### Turn {record['turn']} — {'PASS' if passed else 'FAIL'}\n",
                f"User: {record['user']}\n", f"Reply:\n\n{reply}\n",
                f"Review: {diagnosis}\n", f"Time: {record['seconds']}s; tools={len(record['calls'])}; "
                f"visible model calls={len(record['model_outputs'])}. Full trace: {name}, records[{record['turn']-1}].\n"])
        summary['runs'].append({'artifact': name, 'sha256': sha(HERE/name),
            'source_commit': run['source_commit'], 'app_sha256': run['app_sha256_before'],
            'config_fingerprint': config, 'score': f'{sum(passes)}/6',
            'median_seconds': statistics.median(r['seconds'] for r in run['records']),
            'mean_seconds': statistics.mean(r['seconds'] for r in run['records']), 'judgments': judgments})
    regression = json.loads((HERE/'final-regression-source.json').read_text(encoding='utf-8'))
    current = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT/'backend/app').rglob('*.py'))}
    aggregate = hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()
    assert regression['source_unchanged'] and regression['exit_code']==0
    assert current == regression['before'] == regression['after']
    assert aggregate == summary['runs'][-1]['app_sha256']
    suite = ET.parse(HERE/'final-regression.xml').getroot().find('testsuite')
    assert suite is not None and all(suite.get(k)=='0' for k in ['errors','failures','skipped'])
    summary.update(final_regression=dict(suite.attrib), final_product_commit=summary['runs'][-1]['source_commit'],
        final_source_matches_regression_and_real_capture=True,
        historical_independent_result='C2 strict2/20 (valid2/19); not rerun; no new independent holdout on this product')
    (HERE/'review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (HERE/'PUBLIC_RESPONSES.md').write_text('\n'.join(rendered),encoding='utf-8')
    artifacts = {p.relative_to(HERE).as_posix():sha(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json'}
    manifest={'final_product_commit':summary['final_product_commit'],'base_sha':'89b81e8d6cf5561f2bbab1a9ac437aa9dde88fb9',
        'files':artifacts,'all_raw_captures_preserved':True,'artifact_checks_passed':True,
        'limitations':['Author public-development score, not independent holdout.',
            'No new browser, real venue/provider advice, formal candidate/Accept or production deployment proof.',
            'Historical failed red test, zero-test command, first after failure and superseded source runs retained.']}
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'scores':[r['score'] for r in summary['runs']], 'tests':suite.get('tests'),
        'final_source_matches':True,'artifacts':len(artifacts)}))


if __name__=='__main__':main()
