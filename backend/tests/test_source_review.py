import copy
from datetime import datetime, UTC, timedelta
import pytest
from app.travel_facts.source_review import POLICY, triage, validate_registry, revise_registry, promotion_gate
from app.travel_facts.official_collector import PROFILES
from test_official_collector import P, RAW, run, page, accepted, notice


def registry(entries=None):
    return {'policy': POLICY, 'version': 1, 'entries': [accepted()] if entries is None else entries}


def gate(result=None, reviews=None, now=None):
    result = result or run([page([RAW], 1)], reviews=[accepted()])
    return promotion_gate(P, result, result.candidates[0], target_date='2026-10-02',
                          now=now or datetime.now(UTC), registry=reviews or registry())


def test_accepted_is_not_promotable_without_complete_exception_review():
    result = run([page([RAW, notice(2, '临时闭馆', '暂停开放')], 2)], reviews=[accepted()])
    assert len(result.accepted_snapshots) == 1
    assert not gate(result)['promotable']
    assert 'exception_review_incomplete' in gate(result)['blockers']


def test_reviewed_fixture_gate_eligible_but_never_deploys_or_enables_regular():
    value = gate()
    assert value['promotable'] and not value['production_promoted']
    assert value['regular_exception_readiness'] == 'NOT READY'


@pytest.mark.parametrize('kind', ['pagination', 'schema', 'stale', 'future', 'hash', 'scope', 'url', 'range', 'status', 'parser'])
def test_gate_fails_closed_for_each_required_boundary(kind):
    result = run([page([RAW], 1)], reviews=[accepted()]); now = datetime.now(UTC)
    c = result.candidates[0]
    if kind == 'pagination': result.pagination_complete = False
    if kind == 'schema': result.schema_status = 'changed'
    if kind == 'stale': now += timedelta(hours=1)
    if kind == 'future': now -= timedelta(hours=1)
    if kind == 'hash': c['raw_notice']['introduction'] += '临时闭馆'
    if kind == 'scope': c['branch_scope'] = 'subvenue'
    if kind == 'url': c['source_api'] = 'https://example.com/api'
    if kind == 'range': c['date_scope']['effective_ranges'] = [['2026-10-03', '2026-10-07']]
    if kind == 'status': c['review_status'] = 'superseded'
    if kind == 'parser': c['raw_notice']['id'] = 999
    assert not gate(result, now=now)['promotable']


def test_auto_irrelevant_triage_cannot_certify_exception_absence():
    result = run([page([RAW, notice(2, 'x', '展览')], 2)], reviews=[accepted()])
    assert result.exception_scan_complete  # Old collector alone permits this.
    assert 'exception_review_incomplete' in gate(result)['blockers']
    report = triage(result, target_date='2026-10-02')
    assert report['counts']['obviously_irrelevant'] == 1
    assert not report['accepted_truth_changed']


def test_historical_is_triage_hint_not_out_of_scope_proof():
    raw = notice(2, '暂停开放', '旧公告'); raw['time'] = '2016-02-05'
    result = run([page([raw], 1)])
    row = triage(result, target_date='2026-10-02')['items'][0]
    assert 'historical' in row['categories'] and 'temporary_closure' in row['categories']
    assert not row['auto_out_of_scope'] and not row['auto_accepted']


def test_broken_schema_triage_retains_record():
    bad = notice(2); bad['introduction'] = None
    report = triage(run([page([bad], 1)]), target_date='2026-10-02')
    assert report['counts']['schema_broken'] == 1
    assert report['items'][0]['notice_id'] == '2'


def test_duplicate_reviews_fail_instead_of_last_write_wins():
    value = registry([accepted(), accepted()])
    with pytest.raises(ValueError, match='duplicate'): validate_registry(value, PROFILES)
    assert 'registry_invalid' in gate(reviews=value)['blockers']


@pytest.mark.parametrize('field,value', [('effective_ranges', [['2026-10-07', '2026-10-01']]),
                                        ('effective_ranges', []), ('reviewer', ''),
                                        ('content_hash', 'bad'), ('branch_scope', 'ambiguous')])
def test_invalid_registry_contract_rejected(field, value):
    r = registry(); r['entries'][0][field] = value
    with pytest.raises(ValueError): validate_registry(r, PROFILES)


def test_explicit_registry_revision_preserves_previous_and_checks_version():
    original = registry(); saved = copy.deepcopy(original); h = validate_registry(original, PROFILES)
    replacement = accepted(); replacement['reason'] = 'second explicit review'
    new = revise_registry(original, replacement, PROFILES, expected_hash=h)
    assert original == saved and new['version'] == 2 and new['previous_registry_hash'] == h
    assert len(new['entries']) == 1 and new['entries'][0]['reason'] == replacement['reason']
    with pytest.raises(ValueError, match='changed'):
        revise_registry(new, replacement, PROFILES, expected_hash=h)
