from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

from app.planning_intent_service import _ground_semantic_intent
from app.planning_intent_service import _decide_intent_policy
from app.schemas import SemanticIntentDraft, SemanticIntentOperation
from app.assistant_capabilities import CapabilityDecision, validate_decision, affirmative_action_source
from app.assistant_context import ContextEnvelope
from app.revision_presentation import explicit_revision_adoption


def entities():
    day=SimpleNamespace(id=uuid4(),date=date(2026,11,9),position=0)
    rows=[SimpleNamespace(id=uuid4(),day_id=day.id,day_date=day.date,aliases=(name,),category='sight',
        scheduled_time=time(10+i*3),position=i,duration_minutes=60 if i==0 else 90,
        version=2,schedule_locked=False) for i,name in enumerate(('甲园','乙馆'))]
    return day, rows


def ground(day, rows, operations, selected=None):
    draft=SemanticIntentDraft(primary_intent='replan_trip',operations=[
        SemanticIntentOperation(operation='replan_trip',raw_text=raw,activity_mentions=[mention])
        for raw,mention in operations],confidence=1,parser_version='stage6-fixture')
    return _ground_semantic_intent(draft,trip_id=uuid4(),target_day=day,selected_activity_id=selected,
        protected_activity_ids=[],entities=rows,candidates=[],inherited_missing_fields=[],inherited_ambiguities=[])


def test_explicit_named_target_does_not_union_unrelated_ui_selection():
    day,rows=entities()
    result=ground(day,rows,[('把乙馆停留时长改为80分钟','乙馆')],selected=rows[0].id)
    assert result.target_activity_ids==[rows[1].id]


def test_saved_ordinal_and_increment_keep_server_target_and_delta():
    day,rows=entities()
    result=ground(day,rows,[('第一天第一项活动增加15分钟','第一天第一项活动')])
    assert result.target_activity_ids==[rows[0].id]
    change=result.duration_changes[0]
    assert change.activity_id==rows[0].id and change.before_minutes==60 and change.after_minutes==75
    assert change.operator=='add' and change.minutes==15 and change.activity_version==2


def test_two_operations_do_not_cross_product_targets_and_amounts():
    day,rows=entities()
    result=ground(day,rows,[('甲园增加15分钟','甲园'),('乙馆减少10分钟','乙馆')])
    assert [(v.activity_id,v.after_minutes) for v in result.duration_changes]==[(rows[0].id,75),(rows[1].id,80)]


def test_named_target_is_scoped_to_requested_day():
    day,rows=entities()
    other=SimpleNamespace(**{**vars(rows[1]),'id':uuid4(),'day_id':uuid4()})
    result=ground(day,[*rows,other],[('乙馆增加15分钟','乙馆')])
    assert result.target_activity_ids==[rows[1].id]


def test_wrong_subject_or_missing_sibling_cannot_form_partial_preview():
    day,rows=entities()
    for operations in [
        [('甲园附近的乙馆增加15分钟','甲园')],
        [('甲园增加15分钟','甲园'),('不存在馆减少10分钟','不存在馆')],
        [('甲园增加一刻钟','甲园')],
        [('甲园增加15.5分钟','甲园')],
        [('甲园增加15','甲园')],
        [('甲园增加一小时半','甲园')],
        [('甲园增加一小时 半','甲园')],
        [('甲园增加十半分钟','甲园')],
        [('甲园增加一点休息时间，乙馆增加15分钟','甲园')],
        [('甲园增加一点休息时间再让乙馆增加15分钟','甲园')],
        [('甲园增加15分钟','甲园'),('甲园减少10分钟','甲园')],
    ]:
        assert _decide_intent_policy(ground(day,rows,operations)).route=='clarify'
    result=ground(day,rows,[('甲园增加半小时','甲园')])
    assert result.duration_changes[0].after_minutes==90
    result=ground(day,rows,[('甲园增加15分钟','甲园'),('乙馆再待10分钟','乙馆')])
    assert [(v.activity_id,v.after_minutes) for v in result.duration_changes]==[(rows[0].id,75),(rows[1].id,100)]


def test_duration_and_other_operation_are_not_silently_partially_applied():
    day,rows=entities()
    draft=SemanticIntentDraft(primary_intent='replan_trip',operations=[
        SemanticIntentOperation(operation='replan_trip',raw_text='甲园增加15分钟',activity_mentions=['甲园']),
        SemanticIntentOperation(operation='remove_activity',raw_text='删除乙馆',activity_mentions=['乙馆'])],
        confidence=1,parser_version='fixture')
    result=_ground_semantic_intent(draft,trip_id=uuid4(),target_day=day,selected_activity_id=None,
        protected_activity_ids=[],entities=rows,candidates=[],inherited_missing_fields=[],inherited_ambiguities=[])
    assert _decide_intent_policy(result).route=='clarify'


def test_saved_baseline_is_not_an_adoption_action_and_denial_scopes_stay_separate():
    quote='请以当前保存版本为基线，把第一天第一项活动的停留时长增加15分钟'
    choice=CapabilityDecision(intent='modify',reason_code='explicit_write',authorization_quote=quote)
    envelope=ContextEnvelope(browsing_city='南京')
    assert validate_decision(choice,quote+'。先只预览修改，暂不采用。',[],envelope).intent=='modify'
    assert validate_decision(choice,quote+'。暂不修改。',[],envelope).intent=='direct'
    full=quote+'。先只预览修改，暂不采用。'
    assert validate_decision(choice.model_copy(update={'authorization_quote':full}),full,[],envelope).intent=='modify'
    assert not affirmative_action_source('甲园增加15分钟，先别修改甲园','甲园增加15分钟','增加')
    assert affirmative_action_source('甲园增加15分钟，先别修改乙馆','甲园增加15分钟','增加')


def test_explicit_adoption_wording_reuses_bound_adoption_not_new_planning():
    assert explicit_revision_adoption('明确采用当前这份修改候选并保存。')
    for text in ('是否明确采用当前这份修改候选？','解释明确采用当前这份修改候选是什么意思','等我确认后明确采用当前这份修改候选','不要明确采用当前这份修改候选'):
        assert not explicit_revision_adoption(text)
