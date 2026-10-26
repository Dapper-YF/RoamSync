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


@pytest.mark.parametrize("field,value,text", [
    ("duration_days", "3天", "这次不玩三天"),
    ("duration_days", "4天", "这次不是改为四天"),
    ("party_size", "2人", "这次不是两个人同行"),
    ("start_date", "2026-10-23", "不是明天出发"),
])
def test_negated_scalar_cannot_become_an_affirmative_effective_condition(field, value, text):
    env, accepted, _ = remember(text, MemoryUpdate(field=field, value=value, source_quote=text, scope="trip"))
    assert accepted == [] and field not in memory_prompt(env)["slots"]
    assert memory_prompt(env)["diagnostics"][-1]["reason"] in {"unverified_numeric_value", "unverified_date_value"}


def test_literal_quote_cropping_cannot_hide_scalar_negation():
    env, accepted, _ = remember("这次不玩三天", MemoryUpdate(field="duration_days", value="3天", source_quote="玩三天", scope="trip"))
    assert accepted == [] and "duration_days" not in memory_prompt(env)["slots"]


@pytest.mark.parametrize("field,value,text,want", [
    ("duration_days", "4天", "这次不玩三天，改玩四天", 4),
    ("duration_days", "4天", "不玩三天改四天", 4),
    ("party_size", "3人", "这次不是两个人同行，改为三个人同行", 3),
    ("start_date", "2026-10-24", "不是明天出发，改为后天出发", "2026-10-24"),
])
def test_affirmative_scalar_correction_keeps_only_the_approved_value(field, value, text, want):
    env, accepted, _ = remember(text, MemoryUpdate(field=field, value=value, source_quote=text, scope="trip"))
    assert accepted == [field]
    assert memory_prompt(env)["slots"][field]["value"] == want


def test_continuous_walking_withdrawal_only_applies_to_explicit_matching_subject():
    scope = {"kind": "trip", "trip_id": "trip"}
    records = capture_explicit_requirements([], "妈妈连续步行不超过20分钟，孩子连续步行不超过10分钟", scope=scope, source_ref="first")
    records = capture_explicit_requirements(records, "撤销妈妈连续步行上限", scope=scope, source_ref="withdraw")
    assert [(r["key"], r["text"]) for r in project_requirements(records, trip_id="trip")] == [
        ("user_requirement", "孩子连续步行不超过10分钟")]


def test_ambiguous_continuous_walking_withdrawal_preserves_different_subjects():
    scope = {"kind": "trip", "trip_id": "trip"}
    records = capture_explicit_requirements([], "妈妈连续步行不超过20分钟，孩子连续步行不超过10分钟", scope=scope, source_ref="first")
    records = capture_explicit_requirements(records, "撤销连续步行上限", scope=scope, source_ref="withdraw")
    assert [r["text"] for r in project_requirements(records, trip_id="trip")] == [
        "妈妈连续步行不超过20分钟", "孩子连续步行不超过10分钟"]


@pytest.mark.parametrize("lower", ["至少5分钟", "超过5分钟", "不少于5分钟"])
def test_walking_upper_limit_withdrawal_cannot_revoke_a_lower_bound_predicate(lower):
    scope = {"kind": "trip", "trip_id": "trip"}
    lower_text = "妈妈连续步行" + lower
    records = capture_explicit_requirements([], "妈妈连续步行不超过20分钟，" + lower_text, scope=scope, source_ref="first")
    records = capture_explicit_requirements(records, "撤销妈妈连续步行上限", scope=scope, source_ref="withdraw")
    assert [r["text"] for r in project_requirements(records, trip_id="trip")] == [lower_text]


def recall_fixture():
    text = "我去汕头，11月23日出发，玩三天，我们两个人同行，晚餐人均最多70元，我不吃辣，爸爸连续步行不超过15分钟，不喜欢挨个拍照打卡"
    updates = [
        MemoryUpdate(field="city", value="汕头", source_quote="我去汕头", scope="trip"),
        MemoryUpdate(field="start_date", value="2026-11-23", source_quote="11月23日出发", scope="trip"),
        MemoryUpdate(field="duration_days", value="3天", source_quote="玩三天", scope="trip"),
        MemoryUpdate(field="party_size", value="2人", source_quote="我们两个人同行", scope="trip"),
        MemoryUpdate(field="budget", value="晚餐人均最多70元", source_quote="晚餐人均最多70元", scope="trip"),
        MemoryUpdate(field="preferences", operation="add", value="不吃辣", source_quote="我不吃辣", scope="personal"),
        MemoryUpdate(field="requirements", operation="add", value="爸爸连续步行不超过15分钟", source_quote="爸爸连续步行不超过15分钟", scope="trip"),
        MemoryUpdate(field="preferences", operation="add", value="不喜欢挨个拍照打卡", source_quote="不喜欢挨个拍照打卡", scope="trip"),
    ]
    return apply_memory(ContextEnvelope(), [], text, "recall-source", updates, today=date(2026, 10, 22))[0]


def test_deterministic_recall_keeps_budget_and_continuous_parent_walking_together():
    from app.assistant_memory import recall_conditions
    result = recall_conditions(recall_fixture())
    assert isinstance(result, str)
    for condition in ("目的地：汕头", "出发日期：2026-11-23", "游玩天数：3天", "同行人数：2人",
                      "预算：晚餐人均最多70元", "我不吃辣", "爸爸连续步行不超过15分钟", "不喜欢挨个拍照打卡"):
        assert condition in result
    assert "保证" not in result and "满足你的全部条件" not in result


def test_deterministic_recall_exposes_budget_withdrawal_and_pending_date_without_old_values():
    from app.assistant_memory import recall_conditions
    env = apply_memory(recall_fixture(), [], "取消晚餐预算，日期待定", "withdraw-source", [
        MemoryUpdate(field="budget", operation="clear", source_quote="取消晚餐预算", scope="trip"),
        MemoryUpdate(field="start_date", operation="clear", source_quote="日期待定", scope="trip"),
    ])[0]
    result = recall_conditions(env)
    assert "预算：已撤销" in result and "出发日期：待定" in result
    assert "70元" not in result and "2026-11-23" not in result
    assert "爸爸连续步行不超过15分钟" in result and "我不吃辣" in result


def test_deterministic_recall_leaves_unknown_values_unknown_and_ignores_rejected_hypothesis():
    from app.assistant_memory import recall_conditions
    env, accepted, _ = remember("假如明天出发", MemoryUpdate(field="start_date", value="2026-10-23", source_quote="明天出发"))
    assert accepted == []
    result = recall_conditions(env)
    for condition in ("目的地：未确定", "出发日期：未确定", "游玩天数：未确定", "同行人数：未确定", "预算：未确定"):
        assert condition in result
    assert "2026-10-23" not in result and "假如明天出发" not in result


def test_deterministic_recall_does_not_invent_destination_from_a_browsing_city():
    from app.assistant_memory import recall_conditions
    result = recall_conditions(ContextEnvelope(browsing_city="洛阳"))
    assert "目的地：未确定" in result and "洛阳" not in result


def test_deterministic_recall_does_not_restore_removed_preference_from_withdrawal_provenance():
    from app.assistant_memory import recall_conditions
    env = apply_memory(recall_fixture(), [], "不再要求不吃辣", "diet-withdrawal", [
        MemoryUpdate(field="preferences", operation="remove", value="不吃辣", source_quote="不再要求不吃辣", scope="personal"),
    ])[0]
    result = recall_conditions(env)
    # Withdrawn provenance is now explicitly separated from effective values.
    active=result.split('已撤销条件：')[0]
    assert "我不吃辣" not in active and "不再要求不吃辣" not in active
    assert '已撤销条件：我不吃辣' in result
    assert "不喜欢挨个拍照打卡" in result and "爸爸连续步行不超过15分钟" in result
