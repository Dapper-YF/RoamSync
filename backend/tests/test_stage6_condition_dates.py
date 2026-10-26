from datetime import date

import pytest

from app.assistant_context import ContextEnvelope
from app.assistant_memory import (
    MemoryUpdate, anchored_date, apply_memory, recall_conditions, scalar_tokens, literal_conditions,
)
from app.assistant_operation import _quoted_dates


@pytest.mark.parametrize('literal,expected', [
    ('21/11/2026','2026-11-21'), ('2026/11/21','2026-11-21'),
    ('11/21/2026','2026-11-21'), ('2026-1-9','2026-01-09'),
])
def test_unambiguous_calendar_literal_uses_one_grammar(literal, expected):
    today=date(2026,10,25)
    assert anchored_date(literal,today)==expected
    assert [m[0] for m in scalar_tokens('start_date', '出发日期为'+literal)]==[literal]
    assert _quoted_dates('出发日期为'+literal,today)==[date.fromisoformat(expected)]
    env,_,_=apply_memory(ContextEnvelope(),[],'出发日期为'+literal,'date',[
        MemoryUpdate(field='start_date',value=expected,source_quote='出发日期为'+literal,scope='trip')],today=today)
    assert env.conversation_memory['slots']['start_date']['value']==expected


@pytest.mark.parametrize('literal',['03/04/2027','31/02/2027','2026/13/21','2026年2月30日'])
def test_ambiguous_or_invalid_calendar_never_confirms_a_guessed_date(literal):
    today=date(2026,10,25)
    assert anchored_date(literal,today) is None
    assert _quoted_dates(literal,today)==[]


def test_invalid_same_month_range_is_a_gap_not_an_exception():
    assert _quoted_dates('2027年2月30日至31日',date(2026,10,25))==[]


def test_literal_departure_uses_shared_slash_token_without_a_model_patch():
    text='21/11/2026出发'
    env,_,_=apply_memory(ContextEnvelope(),[],text,'literal',literal_conditions(text),today=date(2026,10,25))
    assert env.conversation_memory['slots']['start_date']['value']=='2026-11-21'


def test_ambiguous_date_rejection_does_not_discard_other_valid_updates():
    text='03/04/2027出发，我一个人去'
    env,_,_=apply_memory(ContextEnvelope(),[],text,'ambiguous',[
        MemoryUpdate(field='start_date',value='2027-04-03',source_quote='03/04/2027出发',scope='trip'),
        MemoryUpdate(field='party_size',value='1',source_quote='我一个人去',scope='trip')])
    assert 'start_date' not in env.conversation_memory['slots']
    assert env.conversation_memory['slots']['party_size']['value']==1


@pytest.mark.parametrize('literal',['03/04/2027','2027年2月30日','2027年4月3日','2026-11-21.5'])
def test_current_unresolved_date_cannot_fall_back_to_a_prior_valid_trip_date(literal):
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_operation import CreationProposal, approved_tool_decision
    env,_,_=apply_memory(ContextEnvelope(),[],'2026年11月21日出发，玩3天','old',[
        MemoryUpdate(field='start_date',value='2026-11-21',source_quote='2026年11月21日出发',scope='trip'),
        MemoryUpdate(field='duration_days',value='3',source_quote='玩3天',scope='trip')])
    text='请生成南京'+literal+'的3天候选'
    decision=CapabilityDecision(intent='create',authorization_quote=text,reason_code='explicit_write',
        creation=CreationProposal(destination='南京'))
    result=approved_tool_decision(decision,text,env,today=date(2026,10,25))
    assert result.tool=='reply' and '日期' in result.reply


@pytest.mark.parametrize('suffix',['','。另外介绍南京博物院。'])
@pytest.mark.parametrize('new_date',['03/04/2027','2027年4月3日'])
def test_date_outside_the_action_quote_still_blocks_stale_creation_fallback(suffix,new_date):
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_operation import CreationProposal, approved_tool_decision
    env,_,_=apply_memory(ContextEnvelope(),[],'2026年11月21日出发，玩3天','old',[
        MemoryUpdate(field='start_date',value='2026-11-21',source_quote='2026年11月21日出发',scope='trip'),
        MemoryUpdate(field='duration_days',value='3',source_quote='玩3天',scope='trip')])
    message='请生成南京候选。出发日期'+new_date+'，玩3天'+suffix
    decision=CapabilityDecision(intent='create',authorization_quote='请生成南京候选',reason_code='explicit_write',
        creation=CreationProposal(destination='南京'))
    assert approved_tool_decision(decision,message,env,today=date(2026,10,25)).tool=='reply'


def test_period_punctuation_does_not_hide_an_explicit_calendar_token():
    assert [m[0] for m in scalar_tokens('start_date','21/11/2026.')]==['21/11/2026']


def test_clear_then_readd_one_condition_keeps_other_withdrawal_provenance():
    env,_,_=apply_memory(ContextEnvelope(),[],'我不吃辣，我不喝酒','add',[
        MemoryUpdate(field='preferences',operation='add',value='不吃辣',source_quote='我不吃辣'),
        MemoryUpdate(field='preferences',operation='add',value='不喝酒',source_quote='我不喝酒')])
    env,_,_=apply_memory(env,[],'清除个人偏好','clear',[
        MemoryUpdate(field='preferences',operation='clear',source_quote='清除个人偏好')])
    env,_,_=apply_memory(env,[],'我不吃辣','again',[
        MemoryUpdate(field='preferences',operation='add',value='不吃辣',source_quote='我不吃辣')])
    answer=recall_conditions(env)
    assert '偏好：我不吃辣' in answer and '已撤销条件：我不喝酒' in answer
    assert '已撤销条件：我不吃辣' not in answer


def test_condition_read_explains_the_exact_withdrawal_and_keeps_personal_preference():
    env=ContextEnvelope(topic_id='condition-review')
    text='我不喝酒，朋友这次连续步行不能超过15分钟'
    env,_,_=apply_memory(env,[],text,'first',[
        MemoryUpdate(field='preferences',operation='add',value='不喝酒',source_quote='我不喝酒'),
        MemoryUpdate(field='requirements',operation='add',value='连续步行不能超过15分钟',
            source_quote='朋友这次连续步行不能超过15分钟',subject='朋友')])
    env,_,_=apply_memory(env,[],'朋友不去了，我一个人去','second',[
        MemoryUpdate(field='party_size',value='1',source_quote='我一个人去',scope='trip')])
    # Re-read a serialized session, rather than depending on its latest answer.
    env=ContextEnvelope.model_validate_json(env.model_dump_json())
    answer=recall_conditions(env)
    assert '同行人数：1人' in answer and '我不喝酒' in answer
    assert '朋友' in answer and '15分钟' in answer and '撤销' in answer
    env,_,_=apply_memory(env,[],'朋友这次连续步行不能超过15分钟','return',[
        MemoryUpdate(field='requirements',operation='add',value='连续步行不能超过15分钟',
            source_quote='朋友这次连续步行不能超过15分钟',subject='朋友')])
    assert '已撤销条件：朋友' not in recall_conditions(env)
