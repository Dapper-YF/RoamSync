import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.assistant_capabilities import CapabilityDecision, CapabilityContractError, select_capabilities
from app.assistant_context import ContextEnvelope
from app.assistant_selection_contract import scope_candidate_schema,validate_wire_selection
from app.assistant_selection_repair import representation_repair
from test_candidate_commands import plan

TEXT='请生成成都11月9日一日候选，人民公园和宽窄巷子，10:00到18:00游玩，中午留一小时午餐，步行为主。不要保存。'


def invalid_proposal():
    proposal=plan().model_dump(mode='json')
    proposal['days'][0]['items'][2].update(start_time='13:00',end_time='18:00')
    proposal['days'].append({'day_index':1,'title':'占位','items':[]})
    return {'intent':'create','reason_code':'explicit_write','city':'成都',
        'authorization_quote':'请生成成都11月9日一日候选',
        'candidate_command':{'action':'generate','source_quote':'请生成成都11月9日一日候选','plan':proposal}}


def errors(raw):
    with pytest.raises(ValidationError) as error:
        CapabilityDecision.model_validate(raw)
    return error.value.errors(include_input=False,include_context=False,include_url=False)


def test_read_task_field_name_used_as_intent_has_only_exact_read_container_repair():
    raw={'intent':'read_tasks','reason_code':'stable_knowledge',
        'read_tasks':[{'source_quote':'查个园位置','capabilities':['poi'],'names':['个园']}]}
    expected,kind,_=representation_repair(raw,errors(raw),'查个园位置',ContextEnvelope())
    assert kind=='read_container_namespace' and expected=={**raw,'intent':'lookup'}
    unsafe={**raw,'authorization_quote':'查个园位置'}
    assert representation_repair(unsafe,errors(unsafe),'查个园位置',ContextEnvelope()) is None


def test_numeric_memory_value_is_an_explicit_representation_repair_only():
    raw={'intent':'direct','reason_code':'explicit_write','response_purpose':'conditions_only',
        'memory_updates':[{'field':'party_size','value':1,'source_quote':'我一个人去','scope':'trip'}]}
    expected,kind,_=representation_repair(raw,errors(raw),'我一个人去',ContextEnvelope())
    assert kind=='memory_scalar_representation'
    assert expected['memory_updates']==[{**raw['memory_updates'][0],'value':'1'}]


def test_duplicate_day_in_explicit_inherited_request_uses_scoped_literal_day_count():
    raw=invalid_proposal()
    expected,_,_=representation_repair(raw,errors(raw),'按刚才全部要求重新生成候选',ContextEnvelope(),[{'user':TEXT}])
    assert len(expected['candidate_command']['plan']['days'])==1
    assert representation_repair(raw,errors(raw),'重新生成候选',ContextEnvelope(),[{'user':TEXT}]) is None


def test_only_two_exact_redundant_envelope_clocks_can_be_explicitly_repaired():
    raw=invalid_proposal();raw['candidate_command'].update(start_time='10:00',end_time='18:00')
    raw['candidate_command']['plan']['days'][0]['items'][2].pop('start_time')
    raw['candidate_command']['plan']['days'][0]['items'][2].pop('end_time')
    schema=CapabilityDecision.model_json_schema();scope_candidate_schema(schema,None)
    with pytest.raises(ValidationError) as error:
        validate_wire_selection(raw,schema)
    expected,kind,_=representation_repair(raw,error.value.errors(include_input=False,include_context=False,include_url=False),TEXT,ContextEnvelope())
    assert kind=='redundant_candidate_clock_representation'
    assert 'start_time' not in expected['candidate_command'] and 'end_time' not in expected['candidate_command']
    assert len(expected['candidate_command']['plan']['days'])==1
    raw['candidate_command']['start_time']='09:00'
    assert representation_repair(raw,error.value.errors(include_input=False,include_context=False,include_url=False),TEXT,ContextEnvelope()) is None


def test_day_count_withdrawal_or_unrelated_inheritance_does_not_revive_history():
    from app.assistant_selection_contract import known_day_count
    env=ContextEnvelope(conversation_memory={'slots':{},'withdrawn':{'duration_days':{'state':'unknown'}}})
    assert known_day_count('按刚才全部要求生成候选',env,[{'user':'请安排两天'}]) is None
    assert known_day_count('沿用刚才的地点，天数还没定',ContextEnvelope(),[{'user':'安排两天'}]) is None
    assert known_day_count('不玩两天，天数还没定',ContextEnvelope(),[]) is None
    assert known_day_count('沿用刚才地点',ContextEnvelope(),[{'user':'安排两天'}]) is None


def test_daily_window_source_cannot_borrow_independent_venue_times_or_cancelled_window():
    from app.conversation_candidate.schedule_evidence import daily_window_source
    from datetime import time
    assert daily_window_source('10:00到18:00游玩',time(10),time(18))
    assert daily_window_source('每天9点出发，18点结束',time(9),time(18))
    assert not daily_window_source('甲馆9点预约，乙馆18点闭馆',time(9),time(18))
    assert not daily_window_source('按刚才全部要求生成候选',time(10),time(18),
        [{'user':'10点到18点游玩'},{'user':'取消游玩时间窗口'}])
    assert not daily_window_source('如果10点到18点游玩',time(10),time(18))
    assert not daily_window_source('不要9点到18点游玩，请生成候选',time(9),time(18))
    assert not daily_window_source('沿用刚才时间要求',time(9),time(18),[
        {'user':'9点到18点游玩'},{'user':'每天10点出发，17点结束'}])
    assert daily_window_source('09:00出发18:00前结束',time(9),time(18))


def test_proposed_clock_and_empty_duplicate_need_explicit_exact_repair():
    raw=invalid_proposal();before=deepcopy(raw)
    result=representation_repair(raw,errors(raw),TEXT,ContextEnvelope())
    expected,kind,_=result
    assert raw==before and kind=='candidate_representation'
    assert len(expected['candidate_command']['plan']['days'])==1
    item=expected['candidate_command']['plan']['days'][0]['items'][2]
    assert 'start_time' not in item and 'end_time' not in item
    assert item['duration_minutes']==90
    assert expected['authorization_quote']==raw['authorization_quote']
    CapabilityDecision.model_validate(expected)


@pytest.mark.parametrize('case',['user_duration','user_window','user_start','mislabeled_user_duration','meal','unknown','nonempty_duplicate','adopt'])
def test_representation_repair_cannot_drop_user_or_unknown_semantics(case):
    raw=invalid_proposal();item=raw['candidate_command']['plan']['days'][0]['items'][2]
    text=TEXT
    if case=='user_duration':
        item.update(duration_source='user_explicit',source_quote='宽窄巷子90分钟')
    if case=='user_window':
        text+='宽窄巷子13:00到18:00。'
    if case=='user_start':
        text+='13点到宽窄巷子。'
    if case=='mislabeled_user_duration':
        text+='宽窄巷子停留60分钟。'
    if case=='meal':
        item.update(kind='meal',name='午餐')
    if case=='unknown':
        raw['candidate_command_note']='下午必须保留用户额外限制'
    if case=='nonempty_duplicate':
        raw['candidate_command']['plan']['days'][1]['items']=[deepcopy(item)]
    if case=='adopt':
        raw['candidate_command']['action']='adopt'
    assert representation_repair(raw,errors(raw),text,ContextEnvelope()) is None


def test_historical_target_timing_also_disqualifies_clock_repair():
    raw=invalid_proposal()
    assert representation_repair(raw,errors(raw),TEXT,ContextEnvelope(),
        [{'user':'宽窄巷子13点到15点预约'}]) is None


def test_allocation_label_cannot_erase_literal_user_duration():
    from app.conversation_candidate.service import resolve_plan
    text='请生成一日候选，人民公园参观70分钟，宽窄巷子停留90分钟，中午留一小时午餐'
    proposal=plan().model_copy(deep=True)
    proposal.days[0].items[0].source_quote='人民公园'
    with pytest.raises(ValueError,match='本次明确要求'):
        asyncio.run(resolve_plan(proposal,'成都',None,[],text))


def test_virtual_lunch_window_label_preserves_requested_meal_duration():
    from app.conversation_candidate.service import resolve_plan
    proposal=plan().model_copy(deep=True)
    item=proposal.days[0].items[1]
    item.kind='free_window';item.name='午餐窗口';item.source_quote='中午留一小时午餐';item.duration_minutes=60
    proposal.days[0].items=[item]
    result=asyncio.run(resolve_plan(proposal,'成都',None,[],'中午留一小时午餐'))
    assert result.days[0].items[0].duration_minutes==60


def test_action_specific_wire_fields_reject_even_empty_unavailable_wrappers():
    schema=CapabilityDecision.model_json_schema();scope_candidate_schema(schema,{'candidate':{}})
    for action,extra in [('modify',{'source_refs':{}}),('adopt',{'plan':None}),('discard',{'patches':[]})]:
        raw={'intent':'modify','reason_code':'explicit_write','candidate_command':{
            'action':action,'source_quote':'本次原文',**({'patches':[]} if action=='modify' else {}),**extra}}
        with pytest.raises(ValidationError):
            validate_wire_selection(raw,schema)


def test_new_trip_wire_cannot_adopt_or_accept_a_missing_plan():
    schema=CapabilityDecision.model_json_schema();scope_candidate_schema(schema,None)
    for command in [{'action':'adopt','source_quote':'保存'},{'action':'generate','source_quote':'生成','plan':None}]:
        with pytest.raises(ValidationError):
            validate_wire_selection({'intent':'create','reason_code':'explicit_write','candidate_command':command},schema)


@pytest.mark.parametrize('alter_quantity',[False,True])
def test_one_model_repair_revalidates_exact_allowed_changes(monkeypatch,alter_quantity):
    import app.assistant_capabilities as module
    from app.config import Settings
    raw=invalid_proposal()
    expected=representation_repair(raw,errors(raw),TEXT,ContextEnvelope())[0]
    if alter_quantity:
        expected['candidate_command']['plan']['days'][0]['items'][0]['duration_minutes']=130
    calls=[]
    class Client:
        async def close(self):
            pass
    monkeypatch.setattr(module,'build_model_client',lambda settings:Client())
    async def respond(*args,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status='completed',output_text=json.dumps(raw if len(calls)==1 else expected))
    monkeypatch.setattr(module,'create_model_response',respond)
    async def run():
        return await select_capabilities(Settings(_env_file=None),TEXT,[],ContextEnvelope())
    if alter_quantity:
        with pytest.raises(CapabilityContractError,match='selection_repair_changed_decision'):
            asyncio.run(run())
    else:
        decision=asyncio.run(run())
        assert decision.candidate_command and len(decision.candidate_command.plan.days)==1
    assert len(calls)==2
    assert json.loads(calls[1]['input_text'])['invalid_selection']==raw
