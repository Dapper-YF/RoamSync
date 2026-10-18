from app.candidate_decisions import compare_candidates
from tests.test_candidate_decisions import NOW, context, candidate


def test_known_route_to_later_anchor_does_not_bridge_intervening_fixed_activity():
    ctx = context()
    ctx['days'][0]['activities'] = [
        {'id': 'early', 'schedule_locked': True, 'scheduled_time': '11:00', 'duration_minutes': 120},
        {'id': 'anchor', 'schedule_locked': True, 'scheduled_time': '13:30', 'duration_minutes': 60},
    ]
    place = candidate('candidate', '馆', ['博物馆']) | {'suggested_duration_minutes': 60}
    ctx['candidate_route_facts'] = [{'candidate_id': 'candidate', 'date': '2026-10-17',
        'to_activity_id': 'anchor', 'status': 'available', 'direction': 'candidate_to_fixed_activity',
        'mode': 'walk', 'provider': 'amap', 'is_estimated': False, 'duration_minutes': 20,
        'expires_at': '2026-10-17T00:00:00Z'}]
    _, comparison = compare_candidates(ctx, [place], allowed_dates={'2026-10-17'}, now=NOW)
    fit = comparison['candidates'][0]['day_comparisons'][0]['fixed_time_fit']['before_fixed_anchor']
    assert fit['known_free_minutes'] == 30
    assert fit['status'] == 'does_not_fit_with_known_route'
