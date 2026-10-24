import pytest
from app.assistant_capabilities import affirmative_action_source
from app.conversation_candidate.commands import CandidateCommand, validate_command
from app.conversation_candidate.sources import source_registry
from app.read_references import literal_search_subject


@pytest.mark.parametrize('text,quote,action', [
    ('请先给我看一份候选，先别保存', '请先给我看一份候选', 'generate'),
    ('请生成候选，但不要保存', '请生成候选', 'generate'),
    ('人民公园改为90分钟，仍不要保存', '人民公园改为90分钟', 'modify'),
    ('请采用并保存当前这份候选', '请采用并保存当前这份候选', 'adopt'),
    ('确认采用当前这份修改候选', '确认采用当前这份修改候选', 'adopt'),
])
def test_preview_modify_and_adopt_have_distinct_action_scopes(text, quote, action):
    validate_command(CandidateCommand(action=action, source_quote=quote), text)


def test_explicit_revocation_still_blocks_same_action():
    with pytest.raises(ValueError):
        validate_command(CandidateCommand(action='generate', source_quote='生成候选'), '生成候选，先别生成了')
    assert not affirmative_action_source('请修改行程，先别修改了', '请修改行程', '修改')
    assert not affirmative_action_source('甲园多留20分钟，先别修改了', '甲园多留20分钟', '多留')
    assert not affirmative_action_source('甲园改成20分钟，先别修改它', '甲园改成20分钟', '改成')


def test_source_fragments_are_literal_and_decorations_do_not_invent_addresses():
    text = '人民公园选小南街8号那个，午餐留一小时'
    spans = source_registry([], text)
    assert all(q in text for q in spans.values())
    assert literal_search_subject('人民公园（小南街8号）', text)
    assert not literal_search_subject('人民公园（另一条路）', text)
    with pytest.raises(ValueError):
        validate_command(CandidateCommand(action='adopt', source_quote='保存当前候选',
            source_refs={'new_item': 'user_0'}), '保存当前候选')


def test_save_denial_is_workflow_control_not_a_changed_travel_requirement():
    from app.requirements import capture_explicit_requirements
    assert not capture_explicit_requirements([], '仍不要保存', scope={'kind':'topic', 'topic_id':'test'}, source_ref='current')
    assert capture_explicit_requirements([], '不要安排购物', scope={'kind':'topic', 'topic_id':'test'}, source_ref='current')


def test_candidate_format_repair_never_discards_unknown_constraints_or_approval():
    from app.assistant_capabilities import _repairable_candidate_format
    err = [{'type':'extra_forbidden', 'loc':('unknown',)}]
    raw = {'candidate_command':{'action':'generate'}, 'unknown':None}
    assert _repairable_candidate_format(raw, err)
    assert not _repairable_candidate_format({**raw, 'unknown':'必须保留步行限制'}, err)
    assert not _repairable_candidate_format({**raw, 'candidate_command':{'action':'adopt'}}, err)


def test_source_ref_cannot_borrow_another_activity_quantity_or_invent_a_meal():
    import asyncio
    from test_candidate_commands import plan
    from app.drafts.contracts import DraftPlan
    from app.conversation_candidate.service import resolve_plan
    p = plan().model_dump(mode='json')
    p['days'][0]['items'] = [{**p['days'][0]['items'][0], 'name':'甲园',
        'duration_minutes':120, 'duration_source':'user_explicit', 'source_quote':'乙馆120分钟'}]
    with pytest.raises(ValueError, match='时长'):
        asyncio.run(resolve_plan(DraftPlan.model_validate(p), '合成城', None, [],
            '甲园60分钟，乙馆120分钟', {'park':'user_0_span_0'}))
    p['days'][0]['items'][0].update(name='午餐', kind='meal', duration_minutes=60)
    with pytest.raises(ValueError, match='类型'):
        asyncio.run(resolve_plan(DraftPlan.model_validate(p), '合成城', None, [],
            '甲园60分钟，乙馆120分钟', {'park':'user_0_span_0'}))
