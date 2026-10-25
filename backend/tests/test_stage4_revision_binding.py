from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assistant_context import ContextEnvelope
from app.revision_presentation import bound_adoption_context, revision_presentation_hash


def revision():
    return SimpleNamespace(id=uuid4(),planning_run_id=uuid4(),trip_id=uuid4(),reason='仅缩短目标活动',
        before_snapshot={'activities':[]},proposed_snapshot={'activities':[]},
        difference_summary={'changed':[]},validation_result={'valid':True,'errors':[],'warnings':[]})


@pytest.mark.parametrize('before', [None, {'days': [{'date': '2026-11-09', 'activities': [{'id': 'legacy'}]}]},
    {'days': None}, {'days': [{'activities': [None]}]},
    {'trip': {}, 'days': [{'date': '2026-11-09'}],
        'execution_recovery': {'frozen_activity_ids': [], 'protected_activity_ids': []}},
    {'trip': {'version': 2}, 'days': [{'date': '2026-11-09'}],
        'execution_recovery': {'frozen_activity_ids': [], 'protected_activity_ids': []}}])
def test_legacy_snapshot_can_be_read_but_cannot_present_a_complete_review(before):
    from app.revision_presentation import revision_review
    item = revision()
    item.before_snapshot = before
    review = revision_review(item)
    assert review['complete'] is False
    assert review['changes'] == []


def test_hash_normalizes_snapshot_defaults_but_binds_changes_and_risks():
    item=revision();bound=revision_presentation_hash(item)
    from app.schemas import CandidatePlanSnapshot
    item.proposed_snapshot=CandidatePlanSnapshot.model_validate(item.proposed_snapshot)
    assert revision_presentation_hash(item)==bound
    item.validation_result['warnings'].append({'code':'unverified','message':'园内步行未知'})
    assert revision_presentation_hash(item)!=bound
    copy=deepcopy(item);copy.trip_id=uuid4()
    assert revision_presentation_hash(item)!=revision_presentation_hash(copy)


@pytest.mark.parametrize('text', ['先不采用','采用会怎样？','等我确认后再采用','请把甲馆改成60分钟',
    '朋友说“采用这份方案”','采用这份方案并把甲馆改为60分钟'])
def test_displayed_reference_cannot_authorize_other_turns(text):
    env=ContextEnvelope(action_target={'trip_id':uuid4(),'expected_version':1,'operation':'plan_trip',
        'authorization_message_id':uuid4(),'revision_id':uuid4(),'revision_hash':'a'*64})
    assert bound_adoption_context(env,text).action_target.operation=='plan_trip'


def test_explicit_adoption_uses_only_current_passive_binding():
    env=ContextEnvelope(action_target={'trip_id':uuid4(),'expected_version':1,'operation':'plan_trip',
        'authorization_message_id':uuid4(),'revision_id':uuid4(),'revision_hash':'a'*64})
    result=bound_adoption_context(env,'请采用并保存当前这份候选。')
    assert result.action_target.operation=='accept_plan'
    assert result.action_target.revision_hash=='a'*64
    missing=env.model_copy(update={'action_target':env.action_target.model_copy(update={'revision_hash':None})})
    assert bound_adoption_context(missing,'请采用当前候选').action_target.operation=='plan_trip'


def test_explicit_approval_may_complete_its_same_reviewed_change_but_not_other_changes():
    from app.conversation_candidate.commands import CandidateCommand,validate_command
    text='现在确认采用当前这份修改候选，把刚才审阅的变化保存'
    validate_command(CandidateCommand(action='adopt',source_quote=text),text)
    for tail in ['把其他变化保存','把甲馆改为60分钟','等我再确认后保存']:
        bad='现在确认采用当前这份修改候选，'+tail
        with pytest.raises(ValueError):
            validate_command(CandidateCommand(action='adopt',source_quote=bad),bad)


@pytest.mark.parametrize('text',['就按这份来','就这样安排'])
def test_legacy_exact_approval_remains_server_bound(text):
    env=ContextEnvelope(action_target={'trip_id':uuid4(),'expected_version':1,'operation':'plan_trip',
        'authorization_message_id':uuid4(),'revision_id':uuid4(),'revision_hash':'a'*64})
    assert bound_adoption_context(env,text).action_target.operation=='accept_plan'


def test_review_includes_deleted_activity_and_uses_the_bound_before_values():
    from app.revision_presentation import revision_review
    item=revision()
    item.before_snapshot={'trip':{'version':4},'execution_recovery':{'frozen_activity_ids':[],'protected_activity_ids':[]},'candidates':[], 'days':[{'date':'2026-11-09','activities':[
        {'id':'deleted','place_id':'p','display_name':'旧馆','scheduled_time':'09:00:00','duration_minutes':80,
         'estimated_cost_fen':0,'schedule_locked':False,'status':'planned'}]}]}
    review=revision_review(item)
    assert review['complete'] and review['base_trip_version']==4
    assert review['changes']==[{'kind':'remove','before':{'activity_id':'deleted','place_id':'p','name':'旧馆',
        'date':'2026-11-09','time':'09:00','duration_minutes':80,'estimated_cost_fen':0,'locked':False},'after':None}]


def test_review_uses_accept_retention_rule_for_omitted_fixed_and_execution_items():
    from app.revision_presentation import revision_review
    item=revision();item.before_snapshot={'trip':{'version':1},'candidates':[],
        'execution_recovery':{'frozen_activity_ids':['paused'],'protected_activity_ids':[]},
        'days':[{'date':'2026-11-09','activities':[{'id':key,'place_id':key,'name':key,'scheduled_time':'09:00',
            'duration_minutes':30,'estimated_cost_fen':0,'schedule_locked':key=='fixed','status':'planned'}
            for key in ['fixed','paused','removed']]}]}
    review=revision_review(item)
    assert review['complete']
    assert [c['before']['name'] for c in review['changes']]==['removed']
    assert {v['name'] for v in review['preserved']}=={'fixed','paused'}
