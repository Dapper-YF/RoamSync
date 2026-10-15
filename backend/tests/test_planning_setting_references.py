"""Real Demo handoff regression: settings are not protected Activity IDs."""
from app.planning_intent_service import _resolve_protected_activities, _trip_setting_kind, _build_rule_semantic_draft
from app.schemas import PlanningTimeScope


REQUEST = '请调整行程：把2026年10月10日（第二天）安排得轻松一点，减少当天活动密度。保留原有旅行日期2026年10月9日至10月11日、总预算3000元、一人出行、喜欢历史文化、老街巷和本地小吃的偏好。先输出新候选方案，不要直接保存正式行程。'


def test_real_preserved_setting_clause_does_not_invent_activities_or_budget_change():
    ambiguities = []
    assert _resolve_protected_activities(REQUEST, [], None, ambiguities) == []
    assert ambiguities == []
    draft = _build_rule_semantic_draft(REQUEST, 'modify_day', PlanningTimeScope(day_number=2))
    assert 'adjust_budget' not in [op.operation for op in draft.operations]
    assert draft.operations[0].constraints.requested_pace == 'relaxed'


def test_direct_budget_value_still_requests_budget_operation():
    draft = _build_rule_semantic_draft('请把第二天的预算设置为3000元', 'modify_day', PlanningTimeScope(day_number=2))
    assert 'adjust_budget' in [op.operation for op in draft.operations]


def test_execution_group_preservation_is_not_an_unknown_venue():
    errors = []
    assert _resolve_protected_activities('保留当前活动和已完成活动', [], None, errors) == []
    assert not errors
    _resolve_protected_activities('保留已完成博物馆', [], None, errors)
    assert errors == ['activity_not_found:已完成博物馆']
    draft = _build_rule_semantic_draft('总预算3000元', 'modify_day', PlanningTimeScope(day_number=2))
    assert 'adjust_budget' in [op.operation for op in draft.operations]


def test_labeled_party_preference_from_second_live_handoff_is_metadata():
    errors = []
    message = '请调整第二天的行程。保留用户整体偏好：一个人出行，喜欢历史文化、老街巷和本地小吃，节奏轻松，总预算3000元。'
    assert _resolve_protected_activities(message, [], None, errors) == []
    assert not errors
    assert _resolve_protected_activities('保留用户整体偏好：老门东', [], None, errors) == []
    assert errors == ['activity_not_found:用户整体偏好：老门东']


def test_real_named_and_unknown_venues_keep_strict_grounding():
    from datetime import date
    from uuid import uuid4
    from app.planning_intent_service import _ActivityEntity
    activity = uuid4()
    entities = [_ActivityEntity(activity, uuid4(), date(2026,10,10), ('老街巷',), 'culture', None)]
    errors = []
    assert _resolve_protected_activities('保留老街巷', entities, None, errors) == [activity]
    assert not errors
    assert _resolve_protected_activities('保留喜欢老门东', [], None, errors) == []
    assert errors == ['activity_not_found:喜欢老门东']
    assert _trip_setting_kind('旅行日期博物馆') is None
    assert _trip_setting_kind('总预算咖啡馆') is None
