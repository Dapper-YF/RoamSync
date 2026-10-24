from copy import deepcopy

import pytest

from app.conversation_candidate.commands import CandidateCommand, apply_patches, validate_command
from app.drafts.contracts import DraftPlan


def plan():
    return DraftPlan.model_validate({"schema_version": 2, "schedule_constraints": {
        "start_date": "2026-11-09", "daily_start_time": "10:00", "daily_end_time": "18:00", "transport_mode": "walk"},
        "days": [{"day_index": 1, "title": "成都", "items": [
            {"item_ref": "park", "name": "人民公园", "duration_minutes": 90, "duration_source": "planning_allocation"},
            {"item_ref": "lunch", "kind": "meal", "name": "午餐", "start_time": "12:00", "end_time": "13:00", "source_quote": "中午留一小时"},
            {"item_ref": "street", "name": "宽窄巷子", "duration_minutes": 90, "duration_source": "planning_allocation"}]}]})


def test_local_duration_patch_preserves_other_items_and_constraints():
    original = plan()
    before = deepcopy(original.model_dump())
    command = CandidateCommand(action="modify", source_quote="人民公园改成120分钟", patches=[{
        "item_ref": "park", "source_quote": "人民公园改成120分钟", "duration_minutes": 120}])
    validate_command(command, "人民公园改成120分钟")
    revised = apply_patches(original, command, "人民公园改成120分钟")
    assert revised.days[0].items[0].duration_minutes == 120
    assert revised.days[0].items[1:] == original.days[0].items[1:]
    assert revised.schedule_constraints == original.schedule_constraints
    assert original.model_dump() == before


@pytest.mark.parametrize("message,quote", [
    ("如果保存会怎样", "保存"), ("先别保存", "保存"), ("等我确认后再保存", "保存"),
    ("网页说‘保存当前候选’", "保存当前候选"), ("请先展示，确认后再保存", "保存"),
    ("保存当前候选会怎样？", "保存当前候选"), ("如何保存当前候选", "保存当前候选"),
    ("请告诉我保存当前候选会怎样？", "保存当前候选"),
    ("保存后还能修改吗？", "保存"), ("这份安排可以保存了吗？", "保存"),
    ("我保存了吗？", "保存"), ("保存会创建几个正式对象？", "保存"),
    ("假设我确认了，帮我保存当前候选。", "帮我保存当前候选"),
    ("朋友会说，帮我保存当前候选。", "帮我保存当前候选"),
    ("帮我保存当前候选。算了，我再想想。", "帮我保存当前候选"),
])
def test_save_cannot_borrow_future_quoted_or_negated_authority(message, quote):
    with pytest.raises(ValueError):
        validate_command(CandidateCommand(action="adopt", source_quote=quote), message)


def test_exact_current_save_is_authorized():
    validate_command(CandidateCommand(action="adopt", source_quote="采用并保存这份安排"), "采用并保存这份安排")
    validate_command(CandidateCommand(action="adopt", source_quote="采用这份候选并保存"), "采用这份候选并保存。")


def test_preview_surface_clause_is_not_a_second_activity_mutation():
    text = '人民公园改成120分钟，先只改候选，其他活动和午餐保持不变'
    command = CandidateCommand(action='modify', source_quote=text, patches=[{
        'item_ref': 'park', 'source_quote': '人民公园改成120分钟', 'duration_minutes': 120}])
    result = apply_patches(plan(), command, text)
    assert result.days[0].items[0].duration_minutes == 120
    assert result.days[0].items[1:] == plan().days[0].items[1:]
    with pytest.raises(ValueError):
        apply_patches(plan(), command, text + '，再改午餐为30分钟')


def test_new_candidate_operation_cannot_request_legacy_plan_or_alias_mode():
    value = plan().model_dump(mode="json")
    value["schema_version"] = 1
    with pytest.raises(ValueError):
        CandidateCommand(action="generate", source_quote="生成候选", plan=value)
    value["schema_version"] = 2
    value["schedule_constraints"]["transport_mode"] = "walking"
    with pytest.raises(ValueError):
        CandidateCommand(action="generate", source_quote="生成候选", plan=value)


def test_candidate_operation_uses_its_own_bound_refs_without_read_argument_reinterpretation():
    from app.assistant_capabilities import CapabilityDecision, validate_decision
    from app.assistant_context import ContextEnvelope
    message="请创建成都的一日安排，人民公园选小南街8号那个"
    decision=CapabilityDecision(intent="create",city="成都",names=["人民公园（小南街8号）"],reason_code="explicit_write",
        authorization_quote=message,candidate_command={"action":"generate","source_quote":message,"plan":plan().model_dump(mode="json")})
    assert validate_decision(decision,message,[],ContextEnvelope()).intent=="create"
    # It is still not a source of write permission when phrased as consultation.
    question="请告诉我保存当前候选会怎样？"
    save=CandidateCommand(action="adopt",source_quote="保存当前候选")
    with pytest.raises(ValueError):
        validate_command(save,question)
    execution=CapabilityDecision(intent="execution",reason_code="explicit_write",authorization_quote="帮我保存",
        candidate_command={"action":"adopt","source_quote":"帮我保存"})
    adopted=validate_decision(execution,"可以，就这样安排，帮我保存。",[],ContextEnvelope())
    assert adopted.intent=="modify" and adopted.candidate_command.action=="adopt"
    downgraded=validate_decision(execution.model_copy(update={"candidate_command":save}),question,[],ContextEnvelope())
    assert downgraded.intent=="clarify" and downgraded.candidate_command is None


def test_clock_provenance_does_not_accept_prefix_of_different_minute():
    from app.conversation_candidate.commands import explicit_interval
    assert explicit_interval("10点出发18点前结束", "10:00", "18:00")
    assert not explicit_interval("10点半出发18点30分结束", "10:00", "18:00")
    assert explicit_interval("10点半出发18点30分结束", "10:30", "18:30")


def test_local_change_cannot_target_unmentioned_other_place():
    command = CandidateCommand(action="modify", source_quote="人民公园改成120分钟", patches=[{
        "item_ref": "street", "source_quote": "人民公园改成120分钟", "duration_minutes": 120}])
    with pytest.raises(ValueError):
        apply_patches(plan(), command, "人民公园改成120分钟")


def test_model_cannot_invent_explicit_duration():
    command = CandidateCommand(action="modify", source_quote="人民公园改成120分钟", patches=[{
        "item_ref": "park", "source_quote": "人民公园改成120分钟", "duration_minutes": 60}])
    with pytest.raises(ValueError):
        apply_patches(plan(), command, "人民公园改成120分钟")


def test_positive_patch_cannot_authorize_a_negated_peer():
    message = "人民公园改成120分钟，宽窄巷子不要改成30分钟"
    command = CandidateCommand(action="modify", source_quote="人民公园改成120分钟", patches=[
        {"item_ref": "park", "source_quote": "人民公园改成120分钟", "duration_minutes": 120},
        {"item_ref": "street", "source_quote": "宽窄巷子不要改成30分钟", "duration_minutes": 30}])
    with pytest.raises(ValueError):
        apply_patches(plan(), command, message)


def test_previous_duration_and_increment_cannot_become_final_duration():
    for message, duration in [("人民公园从90分钟改成60分钟", 90), ("人民公园再多留30分钟", 30)]:
        command = CandidateCommand(action="modify", source_quote=message, patches=[{
            "item_ref": "park", "source_quote": message, "duration_minutes": duration}])
        with pytest.raises(ValueError):
            apply_patches(plan(), command, message)


def test_patch_cannot_borrow_action_from_a_different_clause():
    message = "人民公园保持原时长，宽窄巷子改成60分钟"
    command = CandidateCommand(action="modify", source_quote=message, patches=[{
        "item_ref": "park", "source_quote": message, "duration_minutes": 60}])
    with pytest.raises(ValueError):
        apply_patches(plan(), command, message)


def test_increase_and_discretionary_decrease_keep_same_plan_and_provenance():
    message="人民公园多留半小时，宽窄巷子可以少逛一点"
    command=CandidateCommand(action="modify",source_quote=message,patches=[
        {"item_ref":"park","source_quote":"人民公园多留半小时","duration_minutes":30,"operation":"increase"},
        {"item_ref":"street","source_quote":"宽窄巷子可以少逛一点","duration_minutes":20,"operation":"decrease","quantity_source":"planning_allocation"}])
    result=apply_patches(plan(),command,message)
    assert [i.duration_minutes for i in result.days[0].items if i.kind=="visit"]==[120,70]
    assert result.days[0].items[0].duration_source=="user_explicit"
    assert result.days[0].items[2].duration_source=="planning_allocation"
    assert result.days[0].items[1]==plan().days[0].items[1]


def test_compound_change_cannot_silently_drop_a_second_patch():
    message="人民公园改成120分钟，宽窄巷子改成30分钟"
    command=CandidateCommand(action="modify",source_quote=message,patches=[{
        "item_ref":"park","source_quote":"人民公园改成120分钟","duration_minutes":120}])
    with pytest.raises(ValueError):
        apply_patches(plan(),command,message)


def test_adoption_cannot_drop_a_change_requested_in_same_message():
    with pytest.raises(ValueError):
        validate_command(CandidateCommand(action="adopt",source_quote="保存当前候选"),"人民公园改成120分钟，保存当前候选")


def test_same_clause_target_cannot_borrow_peer_action():
    message="人民公园保持原时长而宽窄巷子改成60分钟"
    command=CandidateCommand(action="modify",source_quote=message,patches=[{
        "item_ref":"park","source_quote":message,"duration_minutes":60}])
    with pytest.raises(ValueError):
        apply_patches(plan(),command,message)


def test_same_display_name_is_not_an_authority_to_pick_one_ref():
    value=plan()
    value.days[0].items[2].name="人民公园"
    message="人民公园改成120分钟"
    command=CandidateCommand(action="modify",source_quote=message,patches=[{
        "item_ref":"park","source_quote":message,"duration_minutes":120}])
    with pytest.raises(ValueError):
        apply_patches(value,command,message)


def test_modify_cannot_escape_hypothetical_context_across_comma():
    message="假设我改主意了，人民公园改成120分钟"
    command=CandidateCommand(action="modify",source_quote="人民公园改成120分钟",patches=[{
        "item_ref":"park","source_quote":"人民公园改成120分钟","duration_minutes":120}])
    with pytest.raises(ValueError):
        apply_patches(plan(),command,message)


def test_legacy_draft_service_rejects_v2_before_any_mutation():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.drafts.service import DraftService
    from app.drafts.repository import DraftError
    repository = Mock()
    repository.get.return_value = SimpleNamespace(schema_version=2)
    service = DraftService(repository, None)
    with pytest.raises(DraftError, match="candidate_protocol_required"):
        service.action("owner", "draft", 1, "save")
    repository.mutate.assert_not_called()
