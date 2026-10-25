import pytest
from app.assistant_capabilities import CapabilityDecision, validate_decision
from app.assistant_context import ContextEnvelope
from app.assistant_operation import approved_draft


def decision(text):
    return CapabilityDecision(intent='modify', reason_code='explicit_write', response_purpose='conditions_only',
        planning_draft={'primary_intent':'replan_trip','operations':[{'operation':'replan_trip',
            'raw_text':text,'activity_mentions':['人民公园'],'place_mentions':[]}],
            'confidence':.95,'parser':'model','parser_version':'v1'})


def test_operation_literal_source_can_supply_omitted_duplicate_preview_quote():
    text='请把第一天人民公园的停留改为60分钟，午餐与其他活动保持不变。先给修改候选，等我明确采用再保存。'
    result=validate_decision(decision(text),text,[],ContextEnvelope())
    assert result.intent=='modify' and result.authorization_quote==text
    assert approved_draft(result,text).primary_intent=='replan_trip'


@pytest.mark.parametrize('text', ['如果把人民公园改为60分钟会怎样', '朋友说“把人民公园改为60分钟”',
    '不要把人民公园改为60分钟', '把人民公园改为60分钟会怎样？'])
def test_missing_duplicate_quote_never_restores_unauthorized_operation(text):
    assert validate_decision(decision(text),text,[],ContextEnvelope()).intent!='modify'


@pytest.mark.parametrize('text', ['请把人民公园改为60分钟，宽窄巷子保持不变', '请调整人民公园，别动宽窄巷子'])
def test_missing_quote_cannot_borrow_change_from_a_preserved_peer(text):
    proposal=decision(text)
    proposal.planning_draft.operations[0].activity_mentions=['宽窄巷子']
    assert validate_decision(proposal,text,[],ContextEnvelope()).intent!='modify'


@pytest.mark.parametrize('kind', ['unsupported','query_trip','general_chat','search_places'])
def test_missing_duplicate_never_promotes_a_non_modification_operation(kind):
    from app.assistant_operation import normalize_modification_evidence
    text='请把人民公园改为60分钟'
    proposal=decision(text)
    proposal.planning_draft.operations[0].operation=kind
    assert not normalize_modification_evidence(proposal,text).authorization_quote
