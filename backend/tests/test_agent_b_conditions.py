"""Behavioral gaps found by B's source audit, separate from frozen holdout."""
import asyncio
from datetime import date
from uuid import uuid4

from app.assistant_context import ContextEnvelope, RouteReadRequest, restore_context
from app.assistant_memory import MemoryUpdate, apply_memory, memory_prompt
from app.assistant_places import PlaceView
from app.assistant_research import LookupIntent, ResearchAnswer, research


def remember(env, text, *updates):
    return apply_memory(env, [], text, uuid4(), updates, today=date(2026, 10, 22))[0]


def test_clearing_destination_releases_place_route_and_old_trip_scope():
    env = remember(ContextEnvelope(browsing_city="柳州", read_trip_id=uuid4(), discussing_place_id=uuid4(),
        route_request=RouteReadRequest(origin_place_id=uuid4(), destination_place_id=uuid4())),
        "我去柳州", MemoryUpdate(field="city", value="柳州", source_quote="我去柳州"))
    message_id = uuid4()
    env, history, _ = apply_memory(env, [{"user": "查柳州附近", "id": "old"}], "取消目的地，日期先不定", message_id, [
        MemoryUpdate(field="city", operation="clear", source_quote="取消目的地"),
        MemoryUpdate(field="start_date", operation="clear", source_quote="日期先不定")])
    assert env.browsing_city is None and env.discussing_place_id is None and env.route_request is None
    assert env.read_trip_id is None and env.conversation_memory["detached_trip"] and history == []
    restored, history = restore_context(ContextEnvelope(), [{"user": "old", "context": ContextEnvelope().model_dump(mode="json")},
        {"user": "取消目的地，日期先不定", "context": env.model_dump(mode="json")}])
    assert restored.browsing_city is None and len(history) == 1


def test_pending_date_is_unknown_with_withdrawal_provenance():
    env = remember(ContextEnvelope(), "11月23日出发", MemoryUpdate(field="start_date", value="11月23日", source_quote="11月23日出发"))
    env = remember(env, "日期也先不定", MemoryUpdate(field="start_date", operation="clear", source_quote="日期也先不定"))
    assert "start_date" not in memory_prompt(env)["slots"]
    withdrawn = memory_prompt(env)["withdrawn"]
    assert withdrawn["start_date"]["source_quote"] == "日期也先不定"
    env = remember(env, "11月26日出发", MemoryUpdate(field="start_date", value="11月26日", source_quote="11月26日出发"))
    assert "start_date" not in memory_prompt(env)["withdrawn"]


def test_destination_scoped_conditions_expire_in_every_collection():
    env = remember(ContextEnvelope(browsing_city="柳州"), "当地只拍桥，门票预算80元", 
        MemoryUpdate(field="preferences", value="只拍桥", operation="add", source_quote="只拍桥", scope="destination"),
        MemoryUpdate(field="budget", value="80元", source_quote="门票预算80元", scope="destination"))
    env = remember(env, "改去洛阳", MemoryUpdate(field="city", value="洛阳", source_quote="改去洛阳"))
    assert not memory_prompt(env)["preferences"] and "budget" not in memory_prompt(env)["slots"]


def test_trip_constraints_are_separate_from_personal_preferences_on_new_journey():
    env = remember(ContextEnvelope(), "我一直吃素，这次两人同行", 
        MemoryUpdate(field="preferences", value="吃素", source_quote="我一直吃素", operation="add", scope="personal"),
        MemoryUpdate(field="party_size", value="两人", source_quote="这次两人同行", scope="trip"))
    env, history, _ = apply_memory(env, [{"user": "旧旅程"}], "另一次旅行，先咨询泉州", uuid4())
    assert not memory_prompt(env)["slots"] and memory_prompt(env)["preferences"][0]["value"] == "吃素"
    assert not history
    env, _, _ = apply_memory(env, [], "重新开始", uuid4())
    assert not memory_prompt(env)["preferences"]


def test_hypothetical_pending_date_never_revokes_current_date():
    env = remember(ContextEnvelope(), "11月23日出发", MemoryUpdate(field="start_date", value="11月23日", source_quote="11月23日出发"))
    env = remember(env, "朋友说“日期先不定”", MemoryUpdate(field="start_date", operation="clear", source_quote="日期先不定"))
    assert memory_prompt(env)["slots"]["start_date"]["value"] == "2026-11-23"


def test_literal_withdrawal_is_not_misread_as_an_affirmative_old_city():
    from app.assistant_memory import literal_conditions
    env = remember(ContextEnvelope(), "我去洛阳", MemoryUpdate(field="city", value="洛阳", source_quote="我去洛阳"))
    text = "取消目的地，日期也先不定，原来的洛阳先放下。"
    env = remember(env, text, *literal_conditions(text))
    assert not env.browsing_city and "city" not in memory_prompt(env)["slots"]


def food_env(budget="晚餐人均最多60元"):
    return remember(ContextEnvelope(browsing_city="柳州"), "我完全不吃辣，" + budget,
        MemoryUpdate(field="preferences", value="完全不吃辣", operation="add", source_quote="我完全不吃辣"),
        MemoryUpdate(field="budget", value=budget, source_quote=budget))


def places():
    return [PlaceView(place_id=uuid4(), name=name, city="柳州", category="food", source="https://example.org/synthetic",
        retrieved_at="2026-10-22T08:00:00Z", reference_cost_yuan=cost)
        for name, cost in (("甲餐厅", 95), ("乙餐厅", 42), ("丙餐厅", None))]


def test_research_receives_effective_conditions_after_history_window_and_cost_tradeoff():
    from app.external_facts import SearchFact
    observed = []
    async def answer(settings, schema, instructions, value):
        observed.append(value)
        return ResearchAnswer()
    class Port:
        async def research_search(self, **kwargs): return places()
    async def judge(*args): return LookupIntent(needed=True, query="餐厅", category="food", read_pages=True)
    async def search(*args, **kwargs):
        return SearchFact("fixture", "2026-10-22", "synthetic", {"results": [{"url": "https://example.org/synthetic", "title": "甲餐厅 乙餐厅 丙餐厅", "content": "甲餐厅 乙餐厅 丙餐厅，仅为合成测试证据。"}]})
    async def extract(*args, **kwargs): return {"results": []}
    result = asyncio.run(research(None, "按我的条件选晚饭", [{"user": "聊历史"} for _ in range(10)], food_env(), Port(), judge=judge, answer=answer, search=search, extract=extract))
    assert observed[0]["effective_conditions"]["preferences"][0]["value"] == "完全不吃辣"
    support = result["read_tools"]["decision_support"]
    assert [i["budget_relation"] for i in support["candidates"]] == ["above_reference_limit", "within_reference_limit", "unknown"]
    assert support["budget"]["amount_yuan"] == 60
    assert "35" in result["assistant"] and "18" in result["assistant"]
    assert "无法判断" in result["assistant"] and "不吃辣" in result["assistant"]


def test_reference_only_food_decision_avoids_a_model_call_and_keeps_unknown_equal():
    class Port:
        async def research_search(self, **kwargs): return places()
    async def judge(*args): return LookupIntent(needed=True, query="餐厅", category="food", read_pages=False)
    async def forbidden(*args): raise AssertionError("reference arithmetic and unknown diet need no model call")
    env = remember(food_env(), "取消晚餐预算", MemoryUpdate(field="budget", operation="clear", source_quote="取消晚餐预算"))
    result = asyncio.run(research(None, "按我的条件比较", [], env, Port(), judge=judge, answer=forbidden))
    assert len(result["place_cards"]) == 3 and "先降低优先级" not in result["assistant"]
    assert "丙餐厅" in result["assistant"] and "不吃辣" in result["assistant"]
    assert result["read_tools"]["decision_support"]["reference_only_answer"]
    assert result["read_tools"]["web_search"]["answer_validation"] == []


def test_trip_total_and_per_day_budget_are_not_compared_to_restaurant_per_person_cost():
    from app.assistant_practical import research_decision_support
    for value in ("总预算600元", "每天人均60元", "人均住宿60元"):
        result = research_decision_support(food_env(value), places(), "food")
        assert result["budget"] is None
        assert all(i["budget_relation"] == "not_comparable" for i in result["candidates"])


def test_revoked_budget_never_reappears_from_old_user_history():
    from app.assistant_practical import research_decision_support
    env = remember(food_env(), "取消晚餐预算", MemoryUpdate(field="budget", operation="clear", source_quote="取消晚餐预算"))
    result = research_decision_support(env, places(), "food")
    assert result["budget"] is None
    assert result["conditions"]["withdrawn"]["budget"]["source_quote"] == "取消晚餐预算"
    assert all(i["budget_relation"] == "not_comparable" for i in result["candidates"])
