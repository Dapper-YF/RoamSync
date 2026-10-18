"""Background assertions never become travel goals; genuine constraints survive."""
from copy import deepcopy

import pytest

from app.requirements import add_requirement, capture_explicit_requirements, project_requirements

SCOPE = {"kind": "draft", "draft_id": "background-boundary", "city": "杭州"}


@pytest.mark.parametrize("text", [
    "仅用于软件验收", "本次行程只是用于系统测试", "未实际到访", "我之前没有去过",
    "仅用于软件验收/未实际到访", "仅用于软件验收（未实际到访）",
])
def test_explicit_field_does_not_turn_provenance_into_requirements(text):
    assert capture_explicit_requirements([], text, scope=SCOPE, source_ref="u", force=True) == []


@pytest.mark.parametrize("text", [
    "不要自动确认到访", "软件验收期间不要安排购物", "必须带婴儿推车",
    "不要安排夜间活动", "未实际到访的地点不要标记已到达", "请安排软件博物馆",
    "我有哮喘，需要避免爬坡", "仅用于软件验收但不要安排夜间活动",
])
def test_actual_travel_or_execution_constraints_are_preserved(text):
    records = capture_explicit_requirements([], text, scope=SCOPE, source_ref="u", force=True)
    assert records
    assert project_requirements(records, draft_id=SCOPE["draft_id"], city="杭州")


def test_mixed_context_and_requirements_do_not_contaminate_each_day():
    records = capture_explicit_requirements([], "仅用于软件验收，未实际到访，希望少走路，第2天不要安排夜间活动",
                                            scope=SCOPE, source_ref="u", force=True)
    assert [(r["key"], r["scope"]["day_index"]) for r in records] == [
        ("walking_preference", None), ("user_requirement", 2)]
    assert [r["key"] for r in project_requirements(records, draft_id=SCOPE["draft_id"], city="杭州", day_index=1)] == ["walking_preference"]


def test_question_and_background_do_not_discard_separate_explicit_instruction():
    records = capture_explicit_requirements([], "未实际到访，希望少走路，那里开放吗？", scope=SCOPE, source_ref="u")
    assert [(r["key"], r["value"]) for r in records] == [("walking_preference", "minimal")]


def test_legacy_background_is_excluded_from_projection_without_rewriting_source():
    records = add_requirement([], text="仅用于软件验收", scope=SCOPE, source_ref="legacy")
    records = add_requirement(records, text="不要自动确认到访", scope=SCOPE, source_ref="real")
    before = deepcopy(records)
    projected = project_requirements(records, draft_id=SCOPE["draft_id"], city="杭州", day_index=2)
    assert [r["text"] for r in projected] == ["不要自动确认到访"]
    assert records == before and records[0]["status"] == "active"


def test_multi_turn_scope_and_revoked_numeric_reference_remain_separate():
    records = capture_explicit_requirements([], "步行上限30分钟，喜欢拍照", scope=SCOPE, source_ref="u1")
    records = capture_explicit_requirements(records, "撤销第2天步行上限", scope=SCOPE, source_ref="u2")
    records = capture_explicit_requirements(records,
        "仅用于软件验收，未实际到访，不要恢复第2天已撤销的30分钟步行要求，第2天不要安排夜间活动",
        scope=SCOPE, source_ref="u3", force=True)
    day1 = project_requirements(records, draft_id=SCOPE["draft_id"], city="杭州", day_index=1)
    day2 = project_requirements(records, draft_id=SCOPE["draft_id"], city="杭州", day_index=2)
    assert {r["key"] for r in day1} == {"max_walking_minutes", "interest"}
    assert {r["key"] for r in day2} == {"interest", "user_requirement"}
