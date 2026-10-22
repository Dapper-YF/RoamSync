import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assistant_context import ContextEnvelope, restore_context
from app.assistant_memory import MemoryUpdate, apply_memory, memory_prompt
from app.assistant_memory import bootstrap_memory
from app.assistant_memory import condition_ack
from app.assistant_images import enrich_images, subjects_for_answer
from app.assistant_reliability import TurnDiagnostics, active_turn
from app.config import Settings


def update(field, value, *, operation="set", quote=None, replaces=""):
    return MemoryUpdate(field=field, value=value, operation=operation, source_quote=quote or value, replaces=replaces)


def remember(env, text, updates, *, today=date(2026, 10, 21)):
    return apply_memory(env, [], text, uuid4(), updates, today=today)[0]


def test_dates_are_anchored_and_corrections_replace_not_append():
    env = remember(ContextEnvelope(), "我明天出发，玩四天，我不吃辣", [
        update("start_date", "明天"), update("duration_days", "四天"), update("preferences", "不吃辣", operation="add")])
    env = remember(env, "改为10月25日出发，玩三天，现在可以吃辣了", [
        update("start_date", "10月25日"), update("duration_days", "三天"),
        update("preferences", "可以吃辣", operation="add", replaces="不吃辣")])
    saved = memory_prompt(env)
    assert saved["slots"]["start_date"]["value"] == "2026-10-25"
    assert saved["slots"]["duration_days"]["value"] == 3
    assert [p["value"] for p in saved["preferences"]] == ["可以吃辣"]
    # Restoration does not reinterpret an old relative date on another day.
    relative = remember(ContextEnvelope(), "明天出发", [update("start_date", "明天")])
    restored, _ = restore_context(ContextEnvelope(), [{"context": relative.model_dump(mode="json")}])
    assert memory_prompt(restored)["slots"]["start_date"]["value"] == "2026-10-22"


def test_a_duration_update_must_not_swallow_the_requested_attraction_overview():
    env=remember(ContextEnvelope(),"那就玩四天的吧，帮我罗列一下成都的所有热门景点",[update("duration_days","四天")])
    assert condition_ack(env,"那就玩四天的吧，帮我罗列一下成都的所有热门景点",["duration_days"]) is None


def test_bare_date_correction_never_grants_planning_authority():
    from app.assistant_capabilities import CapabilityDecision, validate_decision
    text="改成11月5日出发，只玩三天。"
    proposed=CapabilityDecision(intent="create",authorization_quote=text,reason_code="explicit_write")
    result=validate_decision(proposed,text,[],ContextEnvelope())
    assert result.intent=="direct" and result.capabilities==[] and not result.authorization_quote


@pytest.mark.parametrize("text,quote", [("如果去重庆会怎样", "重庆"), ("他说“去北京”", "北京"), ("假如明天出发", "明天"), ("不去成都了", "不去成都"), ("我准备去哪里？", "哪里")])
def test_hypothetical_quoted_or_negated_city_is_not_a_condition(text, quote):
    env = remember(ContextEnvelope(), text, [update("city", "成都" if "成都" in quote else quote, quote=quote)])
    assert "city" not in memory_prompt(env)["slots"]


def test_provenance_and_client_memory_cannot_invent_conditions():
    env = remember(ContextEnvelope(), "你好", [update("city", "北京", quote="你好")])
    assert not memory_prompt(env)["slots"]
    forged = ContextEnvelope(conversation_memory={"version": 1, "slots": {"city": {"value": "北京"}}})
    assert restore_context(forged, [])[0].conversation_memory == {}


def test_city_change_keeps_dates_and_preferences_but_new_topic_clears_all():
    env = remember(ContextEnvelope(), "去成都，明天出发，喜欢建筑", [update("city", "成都"), update("start_date", "明天"), update("preferences", "喜欢建筑", operation="add")])
    env = env.model_copy(update={"discussing_place_id": uuid4()})
    changed, history, _ = apply_memory(env, [{"user": "成都旧景点"}], "改去重庆", uuid4(), [update("city", "重庆")])
    assert changed.browsing_city == "重庆" and not changed.discussing_place_id and history == []
    assert memory_prompt(changed)["slots"]["start_date"]["value"] == "2026-10-22"
    assert memory_prompt(changed)["preferences"]
    changed, history, _ = apply_memory(changed, [{"user": "旧条件"}], "换个话题，去杭州", uuid4(), [update("city", "杭州")])
    assert history == [] and not memory_prompt(changed)["preferences"]
    assert set(memory_prompt(changed)["slots"]) == {"city"}


def test_new_ui_topic_and_changed_scope_dont_borrow_old_conditions():
    env = remember(ContextEnvelope(topic_id="old", browsing_city="成都"), "不吃辣", [update("preferences", "不吃辣", operation="add")])
    turns = [{"context": env.model_dump(mode="json"), "user": "旧条件"}]
    assert restore_context(ContextEnvelope(topic_id="new"), turns)[0].conversation_memory == {}
    assert restore_context(ContextEnvelope(topic_id="old", browsing_city="北京"), turns)[0].conversation_memory == {}


def test_epoch_cannot_resurrect_old_suggestions_after_a_reset():
    old = ContextEnvelope().model_dump(mode="json")
    env, _, _ = apply_memory(ContextEnvelope(), [], "重新开始", uuid4())
    turns = [{"user": "旧的第一条", "context": old}, {"user": "重新开始", "context": env.model_dump(mode="json")}]
    _, history = restore_context(ContextEnvelope(), turns)
    assert [m["user"] for m in history] == ["重新开始"]


def test_city_change_preserves_personal_requirements_and_drops_destination_constraints():
    env=remember(ContextEnvelope(),"我去成都，慢慢逛，必须去武侯祠",[update("city","成都"),
        update("requirements","慢慢逛",operation="add"),
        MemoryUpdate(field="requirements",operation="add",value="必须去武侯祠",source_quote="必须去武侯祠",scope="destination")])
    env=remember(env,"改去重庆，其他不变",[update("city","重庆")])
    assert [r["value"] for r in memory_prompt(env)["requirements"]]==["慢慢逛"]


def test_upgrade_recovers_explicit_history_without_reanchoring_old_relative_dates():
    history=[{"id":"old-1","user":"我去成都，明天出发，玩四天，我喜欢建筑"}]
    env=bootstrap_memory(ContextEnvelope(),history)
    assert memory_prompt(env)["slots"]["city"]["value"]=="成都"
    assert memory_prompt(env)["slots"]["duration_days"]["value"]==4
    assert "start_date" not in memory_prompt(env)["slots"]
    assert memory_prompt(env)["preferences"][0]["message_id"]=="old-1"


@pytest.mark.parametrize("text,quote",[("如果去北京，明天出发","明天"),("朋友不吃辣","不吃辣")])
def test_conditional_and_someone_elses_conditions_are_not_user_memory(text,quote):
    env=remember(ContextEnvelope(),text,[update("preferences",quote,operation="add")])
    assert not memory_prompt(env)["preferences"]


def bundle(subject="火锅", kind="food"):
    return {"assistant": f"可以试试{subject}。", "companion_result": {"visual_subjects": [{"subject": subject, "kind": kind}]}}


def test_images_require_a_final_answer_subject_and_respect_opt_out():
    b = bundle()
    assert subjects_for_answer(b, "介绍火锅", ContextEnvelope())
    assert not subjects_for_answer(b, "不要配图，介绍火锅", ContextEnvelope())
    b["assistant"] = "玩三天合适。"
    assert not subjects_for_answer(b, "玩几天", ContextEnvelope())


def test_images_are_separate_optional_reads_and_not_new_fact_sources():
    async def search(*args, **kwargs):
        assert kwargs["include_images"] and kwargs["query"] == "成都 火锅 图片"
        return SimpleNamespace(queried_at="2026-10-21", payload={"results": [{"url": "https://example.org/food", "title": "火锅"}],
            "images": [{"url": "https://images.example.org/hotpot.jpg", "description": "火锅美食", "score": .9}]})
    b = bundle()
    asyncio.run(enrich_images(Settings(), b, "介绍火锅", ContextEnvelope(browsing_city="成都"), search=search))
    assert b["read_tools"]["visuals"]["status"] == "available"
    assert "web_search" not in b["read_tools"] and b["assistant"] == "可以试试火锅。"


def test_image_failure_keeps_text_and_persists_correlated_diagnostic():
    async def search(*args, **kwargs):
        raise TimeoutError("must not persist private provider text")
    async def run():
        b, turn = bundle(), TurnDiagnostics("p1-image-test")
        token = active_turn.set(turn)
        try:
            await enrich_images(Settings(), b, "介绍火锅", ContextEnvelope(), search=search)
        finally:
            active_turn.reset(token)
        assert b["assistant"] == "可以试试火锅。"
        assert b["read_tools"]["visuals"]["status"] == "unavailable"
        assert any(e["stage"] == "images" and e["status"] == "failed" for e in turn.events)
        assert "private" not in str(turn.events)
    asyncio.run(run())
