"""A duration value is an activity attribute, never a venue replacement."""
import pytest

from app.planning_intent_service import _build_rule_semantic_draft, classify_planning_intent


@pytest.mark.parametrize("message", [
    "把它改成45分钟，其他日期不要动",
    "把这个活动改成1小时",
    "把第2天河坊街改成一个半小时",
])
def test_complete_duration_change_does_not_create_place_query(message):
    intent = classify_planning_intent(message, has_activities=True, has_selected_activity=True)
    assert intent == "modify_day"
    semantic = _build_rule_semantic_draft(message, intent, None)
    assert semantic.primary_intent == "replan_trip"
    assert [op.operation for op in semantic.operations] == ["replan_trip"]
    assert semantic.operations[0].activity_mentions
    assert not semantic.operations[0].place_mentions


def test_number_in_real_venue_name_still_requires_exact_place_grounding():
    message = "把它改成45分钟咖啡馆"
    semantic = _build_rule_semantic_draft(message, "modify_day", None)
    assert semantic.primary_intent == "replace_activity"
    assert semantic.operations[0].place_mentions == ["45分钟咖啡馆"]
