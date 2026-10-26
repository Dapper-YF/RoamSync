import asyncio
from datetime import datetime, UTC
from uuid import uuid4

from app.assistant_context import ContextEnvelope
from app.assistant_capabilities import CapabilityDecision, validate_decision
from app.assistant_memory import MemoryUpdate, apply_memory, memory_prompt
from app.read_references import place_catalog, resolve_read_text
from app.saved_trip_reads import SavedTripReadSnapshot, render_saved_read
from app.place_content.provider import normalize_poi


def places():
    return [{'place_id': str(uuid4()), 'name': name, 'city': '扬州市', 'aliases': [],
             'source': 'https://www.amap.com', 'retrieved_at': datetime.now(UTC).isoformat()}
            for name in ['个园', '何园']]


def test_user_order_beats_search_rank_and_aliases_are_scoped():
    ps = places()
    h = [{'user': '查扬州个园和何园的地址', 'place_cards': [{'place': p} for p in reversed(ps)]}]
    cat = place_catalog(h, ContextEnvelope(browsing_city='扬州'))
    assert [p['name'] for p in cat] == ['个园', '何园']
    assert resolve_read_text('从前一个到后一个步行，再查第二个开放时间', cat) == '从个园到何园步行，再查何园开放时间'
    assert not place_catalog(h, ContextEnvelope(browsing_city='南京'))
    assert resolve_read_text('第二个建议', cat) == '第二个建议'
    h.append({'user': '查后一个地址', 'place_cards': [{'place': ps[1]}]})
    assert resolve_read_text('第一个', place_catalog(h, ContextEnvelope(browsing_city='扬州'))) == '个园'
    h.insert(1, {'user': '查前一个地址', 'place_cards': [{'place': ps[0]}]})
    assert resolve_read_text('第一个', place_catalog(h, ContextEnvelope(browsing_city='扬州'))) == '个园'


def test_compound_route_and_hours_share_verified_objects_but_not_peer_queries():
    ps = places(); history = [{'user': '扬州个园和何园', 'place_cards': [{'place': p} for p in ps]}]
    text = '从前一个到后一个查步行路线，再查后一个今天的开放时间'
    d = CapabilityDecision.model_validate({'intent': 'route', 'capabilities': ['poi', 'route', 'facts'],
        'city': '扬州', 'origin': '个园', 'destination': '何园', 'mode': 'walk', 'reason_code': 'route_requested',
        'read_tasks': [{'source_quote': '从前一个到后一个查步行路线', 'capabilities': ['poi', 'route'],
            'city': '扬州', 'origin': '个园', 'destination': '何园', 'mode': 'walk'},
            {'source_quote': '再查后一个今天的开放时间', 'capabilities': ['facts'], 'city': '扬州',
             'names': ['何园'], 'fact_kind': 'opening_hours'}]})
    valid = validate_decision(d, text, history, ContextEnvelope(browsing_city='扬州'))
    assert valid.intent == 'route' and len(valid.read_tasks) == 2
    bad = d.model_copy(deep=True)
    bad.read_tasks[1] = bad.read_tasks[1].model_copy(update={'names': ['个园'], 'capabilities': ['poi']})
    partial = validate_decision(bad, text, history, ContextEnvelope(browsing_city='扬州'))
    assert partial.intent == 'route' and partial.read_tasks[0].capabilities == ['poi','route']
    # The complete opening-hours property and a unique saved referent permit
    # correcting this read-only POI label; the route peer stays independent.
    assert partial.read_tasks[1].names == ['何园']
    assert partial.read_tasks[1].capabilities == ['facts']
    assert not partial.read_tasks[1]._clarification


def test_two_places_do_not_require_repeating_their_canonical_names():
    ps = places(); history = [{'user': '扬州个园和何园', 'place_cards': [{'place': p} for p in ps]}]
    text = '说说两个地方的位置'
    d = CapabilityDecision.model_validate({'intent': 'lookup', 'capabilities': ['poi'], 'city': '扬州',
        'names': ['个园', '何园'], 'reason_code': 'place_identity', 'read_tasks': [
            {'source_quote': text, 'capabilities': ['poi'], 'city': '扬州', 'names': ['个园', '何园']}]})
    assert validate_decision(d, text, history, ContextEnvelope(browsing_city='扬州')).intent == 'lookup'
    # The root capabilities member is optional; validated tasks supply its union.
    assert validate_decision(d.model_copy(update={'capabilities': []}), text, history,
        ContextEnvelope(browsing_city='扬州')).intent == 'lookup'


def test_reviewed_alias_does_not_bind_same_named_branch_or_wrong_coordinates():
    p = {'id': 'B0253016EC', 'name': '泉州大开元寺', 'cityname': '泉州市', 'location': '118.585519,24.914168', 'typecode': '110000'}
    assert '开元寺' in normalize_poi(p).aliases
    assert '开元寺' not in normalize_poi({**p, 'id': 'other'}).aliases
    assert '开元寺' not in normalize_poi({**p, 'location': '119,25'}).aliases


def test_departing_friend_removes_only_their_requirement_and_solo_is_one():
    env = ContextEnvelope()
    for text, update in [('我不喝酒', MemoryUpdate(field='preferences', value='不喝酒', source_quote='我不喝酒')),
        ('朋友连续步行最多15分钟', MemoryUpdate(field='requirements', value='朋友连续步行最多15分钟',
            source_quote='朋友连续步行最多15分钟', subject='朋友', scope='trip'))]:
        env, _, _ = apply_memory(env, [], text, uuid4(), [update])
    text = '朋友不去了，我一个人去'
    env, _, _ = apply_memory(env, [], text, uuid4(), [
        MemoryUpdate(field='party_size', value='我一个人去', source_quote='我一个人去', scope='trip'),
        MemoryUpdate(field='requirements', operation='remove', value='朋友连续步行最多15分钟', subject='朋友', source_quote='朋友不去了')])
    current = memory_prompt(env)
    assert current['slots']['party_size']['value'] == 1
    assert not current['requirements'] and current['preferences'][0]['value'] == '不喝酒'


def test_cancelling_one_venue_does_not_withdraw_a_participant_requirement():
    env, _, _ = apply_memory(ContextEnvelope(), [], '朋友少走路', uuid4(), [
        MemoryUpdate(field='requirements', value='朋友少走路', source_quote='朋友少走路', subject='朋友')])
    env, _, _ = apply_memory(env, [], '朋友不去夜市了', uuid4(), [
        MemoryUpdate(field='requirements', operation='remove', value='朋友少走路', source_quote='朋友不去夜市了', subject='朋友')])
    assert memory_prompt(env)['requirements'][0]['value'] == '朋友少走路'
    assert not env.conversation_memory.get('withdrawn')


def test_first_item_and_total_days_from_one_saved_snapshot():
    rows = tuple({'activity_id': str(uuid4()), 'day_id': 'd'+str(i//2), 'date': f'2026-11-{10+i//2}',
        'name': '合成活动'+str(i), 'position': i % 2, 'time': '09:00', 'duration_minutes': 45,
        'schedule_locked': False, 'status': 'planned'} for i in range(6))
    snap = SavedTripReadSnapshot(trip={'id': str(uuid4()), 'version': 1},
        days=tuple({'day_id': 'd'+str(i), 'date': f'2026-11-{10+i}', 'position': i} for i in range(3)),
        activities=rows, items=(), counts_by_date={f'2026-11-{10+i}': 2 for i in range(3)}, item_count=0,
        captured_at=datetime.now(UTC).isoformat())
    first = snap.project('第一天第一项活动，它保存了多久')
    assert first['coverage']['complete'] and [r['name'] for r in first['activities']] == ['合成活动0']
    answer = render_saved_read(snap.project('总共几天'), '总共几天')
    assert '共3天' in answer and '合成活动' not in answer
