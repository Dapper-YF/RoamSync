"""Observed task failures plus cross-target and authority boundary regressions."""
import pytest

from app.assistant_capabilities import CapabilityDecision, ReadTask, validate_decision
from app.assistant_context import ContextEnvelope
from app.assistant_operation import approved_draft
from app.assistant_memory import MemoryUpdate, apply_memory, recall_conditions


def test_literal_task_quote_retains_shared_address_in_containing_source():
    text = '比较成都人民公园和宽窄巷子，人民公园按少城路12号核对位置'
    task = ReadTask(source_quote=text, source_ref='user_0_span_0', capabilities=['poi'],
        city='成都', names=['人民公园（少城路12号）'])
    result = validate_decision(CapabilityDecision(intent='lookup', reason_code='place_identity',
        read_tasks=[task]), text, [], ContextEnvelope())
    assert result.intent == 'lookup'
    assert not result.read_tasks[0]._clarification
    assert result.read_tasks[0].source_quote == text


def test_shared_source_cannot_lend_address_to_a_different_named_place():
    text = '比较人民公园和宽窄巷子，人民公园地址少城路12号；查宽窄巷子位置'
    task = ReadTask(source_quote='查宽窄巷子位置', source_ref='user_0_span_2', capabilities=['poi'],
        names=['宽窄巷子（少城路12号）'])
    result = validate_decision(CapabilityDecision(intent='lookup',reason_code='place_identity',
        read_tasks=[task]), text, [], ContextEnvelope(browsing_city='成都'))
    assert result.intent == 'clarify'


def test_long_literal_quote_cannot_authorize_its_negated_peer_or_unbound_address():
    for text,name in [
        ('查人民公园的地址，不用查宽窄巷子的地址','宽窄巷子'),
        ('人民公园地址少城路12号；查宽窄巷子的位置','宽窄巷子（少城路12号）'),
    ]:
        task=ReadTask(source_quote=text,source_ref='user_0_span_0',capabilities=['poi'],names=[name])
        result=validate_decision(CapabilityDecision(intent='lookup',reason_code='place_identity',
            read_tasks=[task]),text,[],ContextEnvelope(browsing_city='成都'))
        assert result.intent=='clarify'


def _replacement(text, target='人民公园'):
    return CapabilityDecision(intent='modify',reason_code='explicit_write',authorization_quote=text,
        planning_draft={'primary_intent':'replace_activity','operations':[
            {'operation':'replace_activity','raw_text':text,'activity_mentions':[target]}],
            'confidence':.9,'parser':'model','parser_version':'v1'})


def test_complete_duration_value_is_attribute_change_even_if_model_says_replace():
    text = '把人民公园的停留改为60分钟，其他活动保持不变'
    draft = approved_draft(_replacement(text), text)
    assert draft.primary_intent == 'replan_trip'
    assert [op.operation for op in draft.operations] == ['replan_trip']
    assert draft.operations[0].raw_text == text


@pytest.mark.parametrize('text', [
    '如果把人民公园改为60分钟会怎样',
    '他说“把人民公园改为60分钟”',
    '不要把人民公园改为60分钟',
])
def test_duration_type_normalization_never_supplies_authority(text):
    with pytest.raises(ValueError):
        approved_draft(_replacement(text), text)


def test_duration_name_is_not_a_numeric_attribute():
    text = '把人民公园换成45分钟咖啡馆'
    draft = approved_draft(_replacement(text), text)
    assert draft.primary_intent == 'replace_activity'


def test_mixed_duration_and_venue_change_cannot_drop_unhandled_peer():
    text = '把人民公园改为60分钟，并把宽窄巷子换成杜甫草堂'
    with pytest.raises(ValueError):
        approved_draft(_replacement(text), text)


@pytest.mark.parametrize('text,target', [
    ('把人民公园改成60分钟，宽窄巷子不要动','宽窄巷子'),
    ('把人民公园改成60分钟，删除宽窄巷子','人民公园'),
])
def test_duration_normalization_requires_own_target_and_complete_operation(text,target):
    with pytest.raises(ValueError):
        approved_draft(_replacement(text,target), text)


def test_coordinated_subject_is_not_a_single_activity_duration():
    text='把人民公园和宽窄巷子改成60分钟'
    with pytest.raises(ValueError):
        approved_draft(_replacement(text,'宽窄巷子'),text)


def test_decorated_address_requires_a_relation_not_same_sentence_presence():
    from app.read_references import argument_in_read_scope
    assert not argument_in_read_scope('甲馆(乙路9号)','比较甲馆和乙馆(乙路9号)',[])
    assert argument_in_read_scope('甲馆(甲路8号)','甲馆地址甲路8号；乙馆在乙路9号',[])


def test_preview_authority_is_local_and_does_not_cancel_independent_inquiry():
    from app.conversation_candidate.commands import CandidateCommand, validate_command
    text = '先出候选，暂不写进正式行程；另外解释为什么车到门口不等于完全不用走路'
    validate_command(CandidateCommand(action='generate',source_quote='先出候选'),text)
    with pytest.raises(ValueError):
        validate_command(CandidateCommand(action='generate',source_quote='先出候选'),
            '先出候选，但现在不要生成它')


@pytest.mark.parametrize('action,quote,text', [
    ('modify','把人民公园改成60分钟','把人民公园改成60分钟会怎样？'),
    ('generate','生成候选','生成候选会怎样？'),
    ('generate','先出一份候选','先出一份候选，先不要出一份候选'),
    ('modify','把人民公园改成60分钟','把人民公园改成60分钟，会怎样？'),
])
def test_truncated_questions_and_same_action_revocation_never_authorize(action,quote,text):
    from app.conversation_candidate.commands import CandidateCommand,validate_command
    with pytest.raises(ValueError):
        validate_command(CandidateCommand(action=action,source_quote=quote),text)


def test_enumerated_party_count_and_unqualified_groups_stay_distinct():
    env, _, _ = apply_memory(ContextEnvelope(), [], '表哥和我一起去', 'm1', [
        MemoryUpdate(field='party_size',value='表哥和我一起去',source_quote='表哥和我一起去',scope='trip')])
    assert env.conversation_memory['slots']['party_size']['value'] == 2
    env, _, _ = apply_memory(env, [], '全家和我一起去', 'm2', [
        MemoryUpdate(field='party_size',value='2',source_quote='全家和我一起去',scope='trip')])
    assert env.conversation_memory['slots']['party_size']['value'] == 2
    assert env.conversation_memory['latest_receipt']['updates'][0]['status'] == 'rejected'


def test_lookup_denial_does_not_cancel_an_independent_explanation():
    from app.read_references import argument_in_read_scope
    text='介绍甲馆和乙馆，乙馆地址不要查'
    assert not argument_in_read_scope('乙馆',text,[],capabilities=['poi'])
    assert argument_in_read_scope('乙馆',text,[],capabilities=[])


def test_query_only_lookup_cannot_borrow_an_introduction_to_avoid_denial():
    text='介绍甲馆和乙馆，乙馆地址不要查'
    decision=CapabilityDecision(intent='lookup',reason_code='place_identity',read_tasks=[
        ReadTask(source_quote=text,capabilities=['poi'],query='乙馆')])
    result=validate_decision(decision,text,[],ContextEnvelope(browsing_city='扬州'))
    assert result.intent=='clarify'


def test_date_revocation_and_solo_value_are_normalized_from_full_user_evidence():
    env, _, _ = apply_memory(ContextEnvelope(), [], '2026年12月19日出发', 'm1', [
        MemoryUpdate(field='start_date',value='2026年12月19日',source_quote='2026年12月19日出发')])
    text = '出发日期先撤销，这趟就我独自出发'
    env, _, _ = apply_memory(env, [], text, 'm2', [
        MemoryUpdate(field='start_date',operation='clear',source_quote='出发日期先撤销'),
        MemoryUpdate(field='party_size',value='独自出发',source_quote='这趟就我独自出发',scope='trip')])
    assert 'start_date' not in env.conversation_memory['slots']
    assert env.conversation_memory['slots']['party_size']['value'] == 1
    assert '待定' in recall_conditions(env)


def test_unresolved_first_subject_does_not_renumber_resolved_second():
    from app.read_references import place_catalog, resolve_read_text
    history = [{'user':'比较天津的意式风情区和古文化街',
        'read_tools':{'tasks':[
            {'validated_arguments':{'names':['意式风情区'],'city':'天津'}},
            {'validated_arguments':{'names':['古文化街'],'city':'天津'}}]},
        'place_cards':[{'place':{'place_id':'00000000-0000-0000-0000-000000000002',
            'name':'古文化街','city':'天津'}}]}]
    refs = place_catalog(history,ContextEnvelope(browsing_city='天津'))
    assert resolve_read_text('第一个和第二个',refs) == '意式风情区和古文化街'
    assert refs[0].get('place_id') is None
    assert refs[1]['place_id']


def test_ambiguous_provider_results_cannot_upgrade_raw_comparison_member():
    from app.read_references import place_catalog
    peer={'name':'乙园','city':'扬州','place_id':'00000000-0000-0000-0000-000000000003'}
    first={'user':'比较甲馆和乙园','read_tools':{'tasks':[
        {'validated_arguments':{'names':['甲馆','乙园'],'city':'扬州'}}]},'place_cards':[{'place':peer}]}
    again={'user':'查甲馆的位置','place_cards':[{'place':{'name':'甲馆','city':'扬州',
        'place_id':'00000000-0000-0000-0000-00000000000'+str(i)}} for i in [1,2]]}
    refs=place_catalog([first,again],ContextEnvelope(browsing_city='扬州'))
    assert len(refs)==2 and refs[0]['name']=='甲馆' and refs[0]['place_id'] is None
    assert refs[1]['place_id']==peer['place_id']


def test_verified_identity_is_never_replaced_by_a_same_name_search_result():
    from app.read_references import place_catalog
    first={'user':'比较甲馆和乙园','place_cards':[{'place':{'name':n,'city':'扬州',
        'place_id':'00000000-0000-0000-0000-00000000000'+str(i)}} for n,i in [('甲馆',1),('乙园',3)]]}
    again={'user':'查甲馆的位置','place_cards':[{'place':{'name':'甲馆','city':'扬州',
        'place_id':'00000000-0000-0000-0000-000000000002'}}]}
    refs=place_catalog([first,again],ContextEnvelope(browsing_city='扬州'))
    assert refs[0]['place_id'].endswith('1') and len(refs)==2
