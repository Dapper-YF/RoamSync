"""Development counterexamples for source-bound effective conditions (not holdout)."""
from datetime import date
from uuid import uuid4

import pytest

from app.assistant_context import ContextEnvelope, capture_effective_requirements, capture_requirements
from app.assistant_memory import MemoryUpdate, apply_memory, memory_prompt
from app.requirements import capture_explicit_requirements, project_requirements


def remember(text, update, *, env=None):
    message_id = uuid4()
    env, _, accepted = apply_memory(env or ContextEnvelope(), [], text, message_id, [update], today=date(2026, 10, 22))
    return env, accepted, str(message_id)


@pytest.mark.parametrize("field,value,quote,want", [
    ("duration_days", "3天", "这次玩三天", 3),
    ("party_size", "2人", "我们两个人同行", 2),
])
def test_equivalent_numeric_value_uses_literal_user_evidence(field, value, quote, want):
    env, accepted, message_id = remember(quote, MemoryUpdate(field=field, value=value, source_quote=quote, scope="trip"))
    assert accepted == [field]
    assert memory_prompt(env)["slots"][field] == {
        "value": want, "source_quote": quote, "message_id": message_id, "scope": "trip", "scope_version": 2}


@pytest.mark.parametrize("field,value,quote", [
    ("duration_days", "5天", "玩三天"),
    ("party_size", "2人", "我们三个人同行"),
    ("duration_days", "3天", "住两晚"),
    ("party_size", "3人", "我们两位成人一个孩子"),
])
def test_unprovable_numeric_equivalence_is_rejected_with_evidence(field, value, quote):
    env, accepted, _ = remember(quote, MemoryUpdate(field=field, value=value, source_quote=quote, scope="trip"))
    assert accepted == [] and field not in memory_prompt(env)["slots"]
    assert memory_prompt(env)["diagnostics"][-1]["reason"] == "unverified_numeric_value"


@pytest.mark.parametrize("field,quote,paraphrase", [
    ("preferences", "不喜欢挨个拍照打卡", "避免打卡式旅行"),
    ("requirements", "妈妈连续走路不能超过20分钟", "步行上限20分钟"),
])
def test_unverifiable_paraphrase_preserves_exact_current_user_condition(field, quote, paraphrase):
    env, accepted, message_id = remember(quote, MemoryUpdate(field=field, operation="add", value=paraphrase, source_quote=quote, scope="trip"))
    assert accepted == [field]
    assert memory_prompt(env)[field][0] == {
        "value": quote, "source_quote": quote, "message_id": message_id, "scope": "trip", "scope_version": 2}


@pytest.mark.parametrize("value,quote,want", [
    ("2026-11-23", "11月23日出发", "2026-11-23"),
    ("2026-10-23", "明天出发", "2026-10-23"),
])
def test_normalized_departure_must_be_provable_from_quote(value, quote, want):
    env, accepted, _ = remember(quote, MemoryUpdate(field="start_date", value=value, source_quote=quote, scope="trip"))
    assert accepted == ["start_date"]
    assert memory_prompt(env)["slots"]["start_date"]["value"] == want


@pytest.mark.parametrize("value,quote", [("2026-11-23", "下个月出发"), ("2026-11-24", "11月23日出发")])
def test_date_normalization_cannot_invent_precision_or_change_explicit_date(value, quote):
    env, accepted, _ = remember(quote, MemoryUpdate(field="start_date", value=value, source_quote=quote))
    assert accepted == [] and "start_date" not in memory_prompt(env)["slots"]


@pytest.mark.parametrize("text", ["如果去旅行，喜欢拍照", "朋友说喜欢拍照", "攻略说“喜欢拍照”"])
def test_non_user_statements_cannot_poison_any_requirement_projection(text):
    env = capture_effective_requirements(ContextEnvelope(), text, message_id=uuid4())
    assert project_requirements(env.requirement_records, topic_id="main") == []
    env = capture_requirements(ContextEnvelope(), text.replace("喜欢拍照", "预算300元"))
    assert env.requirements is None


def test_negative_photography_keeps_source_clause_without_positive_interest():
    text = "第2天不喜欢挨个拍照打卡"
    records = capture_explicit_requirements([], text, scope={"kind": "trip", "trip_id": "trip"}, source_ref="negative")
    assert project_requirements(records, trip_id="trip", day_index=1) == []
    day2 = project_requirements(records, trip_id="trip", day_index=2)
    assert [(r["key"], r["text"]) for r in day2] == [("user_requirement", text)]


def test_continuous_internal_walking_is_not_a_transit_walking_hard_max():
    text = "妈妈在景区内连续走路不超过20分钟"
    records = capture_explicit_requirements([], text, scope={"kind": "trip", "trip_id": "trip"}, source_ref="walking", force=True)
    effective = project_requirements(records, trip_id="trip")
    assert [(r["key"], r["text"]) for r in effective] == [("user_requirement", text)]
    assert effective[0]["strength"] == "hard"


@pytest.mark.parametrize("quote,value", [
    ("不喜欢挨个拍照打卡", "拍照"),
    ("妈妈在景区内连续走路不超过20分钟", "走路不超过20分钟"),
])
def test_literal_fragment_cannot_drop_condition_polarity_or_subject_scope(quote, value):
    env, accepted, _ = remember(quote, MemoryUpdate(field="preferences", value=value, source_quote=quote, scope="trip"))
    assert accepted == ["preferences"]
    assert memory_prompt(env)["preferences"][0]["value"] == quote


def test_negative_pace_does_not_become_an_intensive_preference():
    text = "我不喜欢紧凑的行程"
    records = capture_explicit_requirements([], text, scope={"kind": "topic", "topic_id": "main"}, source_ref="pace")
    assert [(r["key"], r["text"]) for r in project_requirements(records, topic_id="main")] == [("user_requirement", text)]


def test_global_declaration_cannot_promote_later_trip_constraint():
    env = capture_effective_requirements(ContextEnvelope(), "我一直喜欢拍照，这次不要购物", message_id=uuid4())
    assert [(r["key"], r["value"]) for r in project_requirements(env.requirement_records, topic_id="other")] == [("interest", "photography")]
    assert {(r["key"], r["value"]) for r in project_requirements(env.requirement_records, topic_id="main")} == {
        ("interest", "photography"), ("avoid_category", "shopping")}


def test_withdrawing_photography_keeps_day_scope_and_does_not_restore_interest():
    scope = {"kind": "trip", "trip_id": "trip"}
    records = capture_explicit_requirements([], "喜欢拍照", scope=scope, source_ref="first")
    records = capture_explicit_requirements(records, "第2天不再喜欢拍照", scope=scope, source_ref="withdraw")
    assert [(r["key"], r["value"]) for r in project_requirements(records, trip_id="trip", day_index=1)] == [("interest", "photography")]
    assert project_requirements(records, trip_id="trip", day_index=2) == []


def test_withdrawing_continuous_walking_cannot_revoke_transit_walking_cap():
    scope = {"kind": "trip", "trip_id": "trip"}
    records = capture_explicit_requirements([], "步行上限30分钟，连续步行不超过20分钟", scope=scope, source_ref="first")
    records = capture_explicit_requirements(records, "撤销第2天连续步行上限", scope=scope, source_ref="withdraw")
    day2 = project_requirements(records, trip_id="trip", day_index=2)
    assert [(r["key"], r["value"]) for r in day2] == [("max_walking_minutes", 30)]
    day1 = project_requirements(records, trip_id="trip", day_index=1)
    assert {r["key"] for r in day1} == {"max_walking_minutes", "user_requirement"}


def test_third_party_whole_clause_is_not_effective_user_memory():
    text = "我朋友喜欢拍照"
    env, accepted, _ = remember(text, MemoryUpdate(field="preferences", value="喜欢拍照", source_quote=text))
    assert accepted == [] and not memory_prompt(env)["preferences"]
    env = capture_effective_requirements(ContextEnvelope(), text, message_id=uuid4())
    assert project_requirements(env.requirement_records, topic_id="main") == []


def test_continuous_parent_walking_condition_survives_normal_chat_capture():
    text = "妈妈连续走路不能超过20分钟"
    env = capture_effective_requirements(ContextEnvelope(), text, message_id="walking-source")
    effective = project_requirements(env.requirement_records, topic_id="main")
    assert [(r["key"], r["text"], r["source"]["ref"]) for r in effective] == [("user_requirement", text, "walking-source")]
