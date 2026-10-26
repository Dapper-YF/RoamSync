"""Source-bound arithmetic over listed amounts; no price or write authority."""
from decimal import Decimal
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MoneyOperand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_quote: str=Field(min_length=1,max_length=300)
    amount_fen: int=Field(ge=0,le=100_000_000,strict=True)


class ReadCalculation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation: Literal['sum','budget_balance']
    currency: Literal['CNY']='CNY'
    items: list[MoneyOperand]=Field(min_length=1,max_length=20)
    budget: MoneyOperand | None=None


MONEY=re.compile(r'(?<![\d.,])(-?\d+(?:\.\d{1,2})?)\s*元(?![\d])')


def _budget_role(clause,amount):
    return bool(re.search(r'(?:预算|限额|上限)(?:为|是|约|大约|最多|不超过|控制在)?\s*(?:人民币)?\s*$',clause[:amount.start()]))


def _basis(text):
    markers=[name for name,pattern in (
        ('per_person',r'人均|每人|每位|/人'),('per_day',r'每天|每日|/天'),
        ('per_night',r'每晚|/晚'),('per_portion',r'每份|/份'),('per_ticket',r'每张|/张'),
        ('per_item',r'每件|/件'),('total',r'总预算|总价|合计|总计|共计|小计|全程|全部费用'),
    ) if re.search(pattern,text)]
    rate_text=re.sub(r'人均|每人|每位|/人|每天|每日|/天|每晚|/晚|每份|/份|每张|/张|每件|/件','',text)
    if '每' in rate_text or '/' in rate_text:
        return None
    quantities=list(re.finditer(r'([一二三四五六七八九十百千万两零\d]+)\s*个?(人|位|份|张|晚|天|件|小时|分钟)',text))
    if quantities:
        from app.travel_language import chinese_number
        if any(not re.fullmatch(r'[1-9]\d{0,3}|[一二三四五六七八九两]|[一二三四五六七八九]?十[一二三四五六七八九]?',match[1]) for match in quantities):
            return None
        groups={f"group:{chinese_number(match[1])}:{'人' if match[2]=='位' else match[2]}" for match in quantities}
        if len(groups)!=1 or markers:
            return None
        return next(iter(groups))
    if ('每' in text or '/' in text) and not markers:
        return None
    return markers[0] if len(markers)==1 else 'listed_amounts' if not markers else None


def calculate(proposal: ReadCalculation, source: str):
    """Verify every amount and its basis before computing integer-fen results.

    The model proposes operand roles; it cannot invent amounts, omit a quoted
    cost, convert a rate, multiply party size or upgrade reference prices.
    """
    receipt={'version':1,'status':'needs_clarification','operation':proposal.operation,
        'currency':'CNY','basis':None,'inputs':[],'source_quote':source,
        'semantics':'listed_inputs_only_not_a_complete_or_guaranteed_bill'}
    def gap(reason):
        return {**receipt,'reason':reason}
    if re.search(r'美元|欧元|港元|日元|USD|EUR|JPY|HKD|(?<!人民)币|[$£€]|[%％]|折扣|打折|汇率',source,re.I):
        return gap('currency_or_rate_requires_confirmation')
    # Every currency unit must belong to a supported literal amount. Chinese
    # amounts, 块/角/毛 and malformed numeric units cannot silently disappear.
    covered_units={match.end()-1 for match in MONEY.finditer(source)}
    mentions=re.finditer(r'[一二三四五六七八九十百千万两零\d]+(?:[.点][一二三四五六七八九十零\d]+)?\s*(元|块|角|毛|分)(?!钟)',source)
    if {match.start(1) for match in mentions}!=covered_units or re.search(r'￥|¥',source):
        return gap('unsupported_or_unaccounted_currency_amount')
    if (proposal.operation=='budget_balance')!=(proposal.budget is not None):
        return gap('budget_role_missing_or_unexpected')
    operands=[*proposal.items,*([proposal.budget] if proposal.budget else [])]
    used=set();bases=[]
    for index,operand in enumerate(operands):
        quote=operand.source_quote
        if source.count(quote)!=1:
            return gap('operand_source_not_unique')
        start=source.index(quote)
        clause=next((part for part in re.finditer(r'[^，,。；;、!?！？\n]+',source)
            if part.start()<=start and start+len(quote)<=part.end()),None)
        if clause is None:
            return gap('operand_crosses_source_clauses')
        # Bind the entire literal item, including any rate/currency qualifier
        # that the proposed shorter quote omitted.
        quote=clause[0]
        amounts=list(MONEY.finditer(quote))
        if len(amounts)!=1 or Decimal(amounts[0][1])<0 or int(Decimal(amounts[0][1])*100)!=operand.amount_fen:
            return gap('amount_not_equal_to_literal')
        # Do not interpret the tail of malformed/foreign/rate amounts as yuan.
        if re.search(r'[\d.,-]$',quote[:amounts[0].start()]):
            return gap('unsupported_amount_format')
        is_budget=proposal.budget is not None and index==len(proposal.items)
        if _budget_role(quote,amounts[0])!=is_budget:
            return gap('budget_role_not_bound')
        if (not re.fullmatch(r'\s*(?:/人|/天|/份)?\s*',quote[amounts[0].end():])
            or re.search(r'不|别|未|除|仅|只|优惠|抵扣|免|包含|其中|已含|至少|至多|大约|约',quote[:amounts[0].start()])):
            return gap('unsupported_cost_relation_or_qualification')
        position=clause.start()+amounts[0].start()
        if position in used:
            return gap('duplicate_operand')
        used.add(position)
        basis=_basis(quote)
        if basis=='total' and is_budget:
            basis='listed_amounts'
        elif basis=='total':
            return gap('aggregate_cost_cannot_also_be_an_item')
        if basis is None:
            return gap('mixed_price_basis')
        bases.append(basis)
        receipt['inputs'].append({'source_quote':quote,'amount_fen':operand.amount_fen,
            'role':'budget' if is_budget else 'listed_cost','basis':basis})
    ignored_budget=[]
    if proposal.operation=='sum':
        for clause in re.finditer(r'[^，,。；;、!?！？\n]+',source):
            amounts=list(MONEY.finditer(clause[0]))
            if len(amounts)==1 and _budget_role(clause[0],amounts[0]):
                position=clause.start()+amounts[0].start()
                ignored_budget.append({'position':position,'source_quote':clause[0],'role':'budget_context_not_a_cost'})
    if used|{item['position'] for item in ignored_budget}!={match.start() for match in MONEY.finditer(source)}:
        return gap('unaccounted_amounts_in_task')
    if set(bases)<= {'listed_amounts','group:1:人'} and 'group:1:人' in bases:
        # A single traveller introduces no multiplication. Multi-person or
        # rate inputs must each carry the same explicit basis instead.
        bases=['group:1:人']*len(bases)
    if len(set(bases))!=1:
        return gap('incompatible_price_basis')
    total=sum(item.amount_fen for item in proposal.items)
    return {**receipt,'status':'computed','reason':'all_literal_operands_same_currency_and_basis',
        'basis':bases[0],'sum_fen':total,
        'separate_context':ignored_budget,
        'budget_fen':proposal.budget.amount_fen if proposal.budget else None,
        'balance_fen':proposal.budget.amount_fen-total if proposal.budget else None}


def render_calculation(receipt):
    if receipt['status']!='computed':
        return '这部分金额计算还缺少一致的输入：请确认所列费用、预算的币种和计价单位，并逐项给出金额；其他查询可以继续。'
    def yuan(value):
        return format(Decimal(value)/100,'f').rstrip('0').rstrip('.') if value%100 else str(value//100)
    text=f"所列项目合计{yuan(receipt['sum_fen'])}元。"
    if receipt['balance_fen'] is not None:
        balance=receipt['balance_fen']
        text+=f"按预算{yuan(receipt['budget_fen'])}元计算，"+(f"还剩{yuan(balance)}元。" if balance>=0 else f"超出{yuan(-balance)}元。")
    labels={'listed_amounts':'按所列金额原样相加，未乘人数或天数',
        'per_person':'按每人金额计算','per_day':'按每天金额计算','per_night':'按每晚金额计算',
        'per_portion':'按每份金额计算','per_ticket':'按每张金额计算','per_item':'按每件金额计算','total':'按明确总额计算'}
    basis=receipt['basis']
    label=('按每组'+basis.split(':')[1]+basis.split(':')[2]+'所列金额计算，未作数量换算') if basis.startswith('group:') else labels[basis]
    return text+label+'。这只覆盖列出的项目，参考价不能保证最终账单；还需核对未列费用、附加收费和实际结算。'
