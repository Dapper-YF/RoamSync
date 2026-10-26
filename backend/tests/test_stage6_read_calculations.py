import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest

from app.read_calculations import ReadCalculation, calculate, render_calculation
from test_formal_write_protection import sample, current

TEXT='一人预算120元，已知门票45元、午餐38元、交通22元，合计多少、还剩多少？这些只是参考价，能保证最终不超预算吗？'
DATA={'operation':'budget_balance','items':[
    {'source_quote':name,'amount_fen':amount} for name,amount in (
        ('门票45元',4500),('午餐38元',3800),('交通22元',2200))],
    'budget':{'source_quote':'预算120元','amount_fen':12000}}


def test_integer_fen_sum_balance_and_source_receipt_do_not_guarantee_a_bill():
    receipt=calculate(ReadCalculation.model_validate(DATA),TEXT)
    assert receipt['status']=='computed'
    assert receipt['sum_fen']==10500 and receipt['balance_fen']==1500
    assert receipt['inputs'][0]['source_quote']=='已知门票45元'
    text=render_calculation(receipt)
    assert '合计105元' in text and '还剩15元' in text and '不能保证' in text


def test_sum_subgoal_does_not_mistake_a_literal_budget_for_an_additional_cost():
    data=deepcopy(DATA);data['operation']='sum';data.pop('budget')
    result=calculate(ReadCalculation.model_validate(data),TEXT)
    assert result['status']=='computed' and result['sum_fen']==10500
    assert result['separate_context'][0]['role']=='budget_context_not_a_cost'


def test_a_cost_named_budget_hotel_is_not_discarded_as_budget_context():
    data=deepcopy(DATA);data['operation']='sum';data.pop('budget')
    text=TEXT.replace('一人预算120元','预算旅馆120元')
    assert calculate(ReadCalculation.model_validate(data),text)['status']=='needs_clarification'


def test_conditional_reference_price_language_cannot_guarantee_a_final_budget():
    from app.companion_answer_reliability import control_model_text
    text='不能保证最终账单。只要当日不新增第四笔消费，参考价这一层基本能兜住。请先核对完整订单和附加收费。'
    result=control_model_text(text,TEXT)
    assert '兜住' not in result.text and '核对完整订单' in result.text
    assert 'output_unverified_final_bill' in result.issues


@pytest.mark.parametrize('alteration', ['wrong_amount','omit_cost','duplicate','missing_budget','wrong_role'])
def test_unbound_incomplete_or_duplicate_inputs_cannot_become_a_computed_result(alteration):
    data=deepcopy(DATA)
    if alteration=='wrong_amount': data['items'][0]['amount_fen']=4600
    if alteration=='omit_cost': data['items'].pop()
    if alteration=='duplicate': data['items'].append(deepcopy(data['items'][0]))
    if alteration=='missing_budget': data['budget']=None
    if alteration=='wrong_role': data['budget'],data['items'][0]=data['items'][0],data['budget']
    assert calculate(ReadCalculation.model_validate(data),TEXT)['status']=='needs_clarification'


def test_decimal_amounts_are_exact_and_equal_prices_on_different_items_are_not_deduplicated():
    data={'operation':'sum','items':[{'source_quote':q,'amount_fen':n} for q,n in (
        ('门票0.10元',10),('餐费0.20元',20),('交通0.10元',10))]}
    result=calculate(ReadCalculation.model_validate(data),'门票0.10元，餐费0.20元，交通0.10元，合计多少？')
    assert result['sum_fen']==40 and '0.4元' in render_calculation(result)


@pytest.mark.parametrize('text',[
    TEXT.replace('门票45元','门票每人45元'),
    TEXT.replace('门票45元','门票45元/人'),
    TEXT.replace('门票45元','门票45元，另收10%服务费'),
    TEXT.replace('门票45元','门票45元美元'),
    TEXT.replace('门票45元','门票-45元'),
    TEXT.replace('门票45元','不要算门票45元'),
    TEXT.replace('门票45元','门票45元起'),
    TEXT.replace('门票45元','门票45元，另收五元服务费'),
    TEXT.replace('门票45元','门票45元，另收5块服务费'),
    TEXT.replace('一人预算','港币预算'),
    TEXT.replace('午餐38元','两人午餐38元'),
    TEXT.replace('门票45元','门票45元，另收五分服务费'),
])
def test_short_operand_quotes_cannot_erase_rates_foreign_currency_or_negative_values(text):
    assert calculate(ReadCalculation.model_validate(DATA),text)['status']=='needs_clarification'


def test_all_explicit_per_person_inputs_keep_their_basis():
    text='每人预算120元，门票每人45元、午餐每人38元、交通每人22元，合计及余量？'
    data=deepcopy(DATA)
    for item in data['items']:
        item['source_quote']=item['source_quote'].replace('45','每人45').replace('38','每人38').replace('22','每人22')
    result=calculate(ReadCalculation.model_validate(data),text)
    assert result['status']=='computed' and result['basis']=='per_person'


@pytest.mark.parametrize('kind',['direct','task','truncated_task'])
def test_read_calculation_completes_without_answer_provider_or_formal_mutation(sample,monkeypatch,kind):
    from app.assistant_capabilities import CapabilityDecision
    from app.assistant_service import send_message
    async def selector(*_):
        if kind=='direct':
            return CapabilityDecision(intent='direct',reason_code='stable_knowledge',calculation=DATA)
        data=deepcopy(DATA)
        quote=TEXT
        if kind=='truncated_task':
            data['items'].pop();quote='一人预算120元，已知门票45元、午餐38元'
        return CapabilityDecision(intent='direct',reason_code='stable_knowledge',read_tasks=[{
            'source_quote':quote,'capabilities':[],'calculation':data}])
    async def forbidden(*_args,**_kwargs):
        raise AssertionError('Deterministic calculation must not call answer provider')
    monkeypatch.setattr('app.companion_provider.ModelCompanionProvider.generate',forbidden)
    async def run():
        from app.database import AssistantSession
        before=await current(sample)
        async with sample.sessions() as db:
            row=AssistantSession(trip_id=sample.trip_id,messages=[],applied_actions={})
            db.add(row);await db.commit();sid=row.id
        async with sample.sessions() as db:
            row=await send_message(db,sid,TEXT,uuid4(),context={'surface':'trip','read_trip_id':str(sample.trip_id)},capability_selector=selector)
            turn=row.messages[-1]
            if kind=='truncated_task':
                assert '合计83元' not in turn['assistant']
                assert turn['read_tools']['calculation']['status']=='needs_clarification'
            else:
                assert '合计105元' in turn['assistant'] and '还剩15元' in turn['assistant']
                assert turn['read_tools']['calculation']['status']=='computed'
        assert await current(sample)==before
    asyncio.run(run())


def test_total_and_its_components_are_not_four_independent_costs():
    source='总计105元，门票45元，午餐38元，交通22元'
    data={'operation':'sum','items':[{'source_quote':q,'amount_fen':n} for q,n in (
        ('总计105元',10500),('门票45元',4500),('午餐38元',3800),('交通22元',2200))]}
    assert calculate(ReadCalculation.model_validate(data),source)['status']=='needs_clarification'


def test_unknown_or_mixed_rate_cannot_be_assumed_to_be_a_listed_total():
    for text in ('住宿每晚100元，餐费30元','住宿每小时100元，餐费30元','住宿每晚每小时100元，餐费30元'):
        data={'operation':'sum','items':[{'source_quote':q,'amount_fen':n} for q,n in (
            (text.split('，')[0],10000),('餐费30元',3000))]}
        assert calculate(ReadCalculation.model_validate(data),text)['status']=='needs_clarification'


def test_unsupported_group_numerals_do_not_collapse_to_a_shared_zero_basis():
    text='一百人预算120元，二百人门票45元'
    data={'operation':'budget_balance','budget':{'source_quote':'一百人预算120元','amount_fen':12000},
        'items':[{'source_quote':'二百人门票45元','amount_fen':4500}]}
    assert calculate(ReadCalculation.model_validate(data),text)['status']=='needs_clarification'
