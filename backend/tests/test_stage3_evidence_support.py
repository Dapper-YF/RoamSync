from datetime import UTC, datetime, timedelta
import pytest
from app.requirement_support import assess_support
from app.companion_answer_reliability import unsupported_advice, control_model_text


@pytest.mark.parametrize('text', [
    '车能到门口，所以长辈完全不用走路',
    '餐馆有清汤，这一餐肯定都不辣',
    '参考人均80元，最后账单一定不超过80元',
    '店在地铁旁，所以门口离出口很近',
    '票价50元并不代表实际花费。',
    '清汤只说明这家店有一款不辣的锅底。',
])
def test_partial_data_cannot_become_complete_guarantee(text):
    assert unsupported_advice(text) or control_model_text(text, '').issues


@pytest.mark.parametrize('text', [
    '车到门口不代表完全不用走路。请问场馆入口到展厅有无台阶、能否借轮椅。',
    '有清汤不能证明这一餐都不辣。点餐前逐道确认调料和辣椒处理。',
    '参考价不足以说明账单一定不超过80元。请先汇总完整订单和服务费。',
    '请确认汤底是否独立熬制，微辣和清油锅都不能算不辣。',
])
def test_direct_negative_inference_and_concrete_verification_survive(text):
    assert not unsupported_advice(text)
    assert control_model_text(text, '').text == text


def test_support_is_bound_to_exact_identity_time_and_scope():
    now = datetime.now(UTC)
    route = {'kind':'route','message_id':'tool_1','places':[{'place_id':'a'},{'place_id':'b'}],
        'binding':{'place_ids':['a','b'],'mode':'walk'},
        'result':{'mode':'walk','duration_seconds':600,'source':{'freshness':'fresh',
            'expires_at':(now+timedelta(minutes=5)).isoformat()}}}
    result = assess_support('这两处路线距离多少？', {}, [route], ['a','b'], now=now, expected_route=route['binding'])
    assert result['assessments'][0]['status'] == 'supported'
    effort = assess_support('这就证明长辈完全不用走路？', {}, [route], ['a','b'], now=now)
    assert effort['assessments'][0]['status'] == 'insufficient_or_stale'
    mismatch = assess_support('这两处路线距离多少？', {}, [route], ['a','c'], now=now)
    assert mismatch['assessments'][0]['observations'] == []
    stale = assess_support('这两处路线距离多少？', {}, [route], ['a','b'], now=now+timedelta(minutes=6))
    assert stale['assessments'][0]['status'] == 'insufficient_or_stale'
    assert not assess_support('路线多长', {}, [route], [], now=now)['assessments'][0]['observations']
    for binding in ({'place_ids':['b','a'],'mode':'walk'}, {'place_ids':['a','b'],'mode':'driving'},
        {'place_ids':['a'],'mode':'walk'}):
        result = assess_support('驾车路线多长', {}, [route], binding['place_ids'], now=now, expected_route=binding)
        assert result['assessments'][0]['status'] != 'supported'


def test_requested_and_related_are_distinct_from_satisfied():
    now = datetime.now(UTC)
    memory = {'requirements':[{'value':'长辈需要省力','message_id':'u1','scope':'this_trip'}]}
    assert assess_support('介绍一下', memory, [])['assessments'][0]['status'] == 'requested'
    related = {'kind':'source','places':[{'place_id':'a'}],'expires_at':(now+timedelta(minutes=5)).isoformat()}
    value = assess_support('介绍一下', memory, [related], ['a'], now=now)['assessments'][0]
    assert value['status'] == 'related_information' and value['missing_link']
