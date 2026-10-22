"""Independently scoped contracts from two rejected experiments; not model evidence."""
import asyncio
from types import SimpleNamespace

from app.assistant_context import ContextEnvelope
from app.assistant_practical import previous_reads, walking_followup, practical_next_step


def test_compound_creation_restrictions_do_not_cancel_literal_action():
    from app.assistant_capabilities import CapabilityDecision, validate_decision
    quote = "帮我形成允许留白的旅行安排建议"
    text = "就按前面的日期，" + quote + "。保留人民公园但暂不排时间，武侯祠还是备选。"
    assert validate_decision(CapabilityDecision(intent="create", authorization_quote=quote, reason_code="explicit_write"), text, [], ContextEnvelope()).intent == "create"
    text = quote + "，不要安排具体时间。"
    assert validate_decision(CapabilityDecision(intent="create", authorization_quote=quote, reason_code="explicit_write"), text, [], ContextEnvelope()).intent == "create"
    for text in ["如果" + quote + "会怎样", "先别" + quote, "他说“" + quote + "”", quote + "，先别创建", "只讨论" + quote]:
        assert validate_decision(CapabilityDecision(intent="create", authorization_quote=quote, reason_code="explicit_write"), text, [], ContextEnvelope()).intent == "direct"


def test_atomic_unverified_advice_does_not_erase_useful_differences():
    from app.companion_answer_reliability import control_model_text
    text = "火锅围锅涮食，串串通常按签或份计价。两者都可以要求清汤，所以不吃辣也放心。武侯祠看红墙，出门顺路去锦里。先向店家确认独立不辣锅底，再决定。"
    result = control_model_text(text, "不吃辣，怎么选择")
    assert "按签或份" in result.text and "确认独立不辣" in result.text
    assert "顺路" not in result.text and "都可以" not in result.text and "所以" not in result.text
    assert len(result.issues) == 2


def test_general_introduction_cannot_invent_transport_measurements():
    from app.companion_answer_reliability import control_model_text
    text = "彭镇可以了解老茶馆文化。离市区约一小时车程，适合给半天。建议给茶馆留半天，具体交通可按出发点查询。"
    result = control_model_text(text, "第一次去成都，想了解城市气质")
    assert "一小时车程" not in result.text
    assert "老茶馆文化" in result.text and "建议给茶馆留半天" in result.text
    assert result.issues == ["output_unverified_travel_measurement"]
    for claim in ("从这里步行20分钟就到。", "打车大约30分钟。", "路程约3公里。"):
        assert not control_model_text(claim, "介绍成都").text


def test_relative_day_window_is_grounded_in_explicit_creation_dates():
    from datetime import date, time
    from app.flexible_creation import CreationChoice, check_time_quote
    choice = CreationChoice(kind="free_window", label="留白", day_date=date(2026,11,3), start=time(15), end=time(16))
    check_time_quote(choice, "第二天15:00-16:00明确留白", date(2026,11,2))
    import pytest
    with pytest.raises(ValueError):
        check_time_quote(choice, "第三天15:00-16:00明确留白", date(2026,11,2))


def test_tool_decision_repairs_format_once_and_shares_budget(monkeypatch):
    import json
    from pydantic import SecretStr
    from app.assistant_service import AssistantRouter, AssistantToolError
    import app.assistant_service as service
    calls = []
    async def close(): pass
    async def generate(*args, **kwargs):
        calls.append(json.loads(kwargs["input_text"]))
        bad = {"tool":"create_trip", "reply":"生成预览", "choices":[{"kind":"selected", "label":"人民公园", "start":"10:00"}]}
        good = {"tool":"reply", "reply":"请确认缺少的时间。"}
        return SimpleNamespace(status="completed", output_text=json.dumps(bad if len(calls)==1 else good))
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(planner_api_key=SecretStr("fixture"), planner_model="fixture"))
    monkeypatch.setattr(service, "build_model_client", lambda _: SimpleNamespace(close=close))
    monkeypatch.setattr(service, "create_model_response", generate)
    async def run():
        router = AssistantRouter()
        result = await router.decide({"message":"形成预览"})
        assert result.tool == "reply" and len(calls)==2
        assert calls[1]["tool_schema_feedback"][0]["field"]==["choices",0]
        import pytest
        with pytest.raises(AssistantToolError):
            await router.decide({"message":"不能叠加重试"})
        assert len(calls)==2
    asyncio.run(run())


def test_finite_quote_recovery_keeps_negation_questions_and_ambiguity_rejected():
    from app.flexible_creation import recover_creation_quotes, CreationChoice
    decision=SimpleNamespace(choices=[CreationChoice(kind="optional",label="武侯祠",source_quote="用户想把武侯祠留作备选")])
    assert recover_creation_quotes(decision,"武侯祠还是备选。其他不定")[0].source_quote=="武侯祠还是备选"
    for text in ["不保留武侯祠","武侯祠不是备选","保留武侯祠还是不保留","武侯祠备选取消","武侯祠需要预约吗？","武侯祠先不去，武侯祠还是备选。"]:
        assert recover_creation_quotes(decision,text)[0].source_quote==decision.choices[0].source_quote


def test_temporal_personal_statements_do_not_trigger_live_state_fallback():
    from app.travel_goal_router import route_travel_goal
    from app.companion_information import determine_information_need
    from app.companion_contracts import CompanionContext
    for text in ["今天不出门，下午留空，不用给我找替代活动。","我现在改去杭州，预算还是五百","现在预算改成120，还是不吃辣","2026年11月2日出发，四天，先不形成安排。"]:
        goal=route_travel_goal(text,[])
        assert not determine_information_need(CompanionContext(current_message=text,travel_goal=goal),[]).live_fact_required
    assert route_travel_goal("西湖今天适合去吗",[]).live_fact_likely_required
    assert route_travel_goal("改成11月14日，是星期几？",[]).target_runtime=="companion"


def test_saved_route_is_not_a_flat_terrain_or_comfort_guarantee():
    reads=previous_reads([{"id":"actual","assistant":"地势平坦，轻松顺路","read_tools":{"route":{"status":"available","result":{"mode":"walk","duration_seconds":3631,"distance_meters":4100,"is_estimated_fallback":False}}}}])
    assert "平坦" not in str(reads) and "轻松顺路" not in str(reads)
    text=walking_followup(reads)
    assert "61分钟" in text and "没有计算场所内" in text and "备选" in text
    assert "路面平" not in text


def test_missing_food_evidence_still_gives_actionable_diet_and_cost_help():
    text=practical_next_step("不吃辣，人均100元，哪家合适","food")
    assert "锅底" in text and "菜单" in text and "候选" in text
    assert "供应清汤" not in text and "完全无法" not in text


def test_wrong_business_category_is_not_an_attraction_and_request_count_is_kept():
    from test_assistant_research import PLACE
    from app.assistant_research import research,LookupIntent,ResearchAnswer
    from uuid import uuid4
    class Port:
        async def search(self,**kw):
            return [PLACE.model_copy(update={"name":"街拍按摩店","category":"other"}),
                *[PLACE.model_copy(update={"name":"街道"+str(n),"place_id":uuid4(),"category":"other","provider_type":"地名地址信息;道路名"}) for n in range(3)]]
    async def judge(*args):return LookupIntent(needed=True,city="成都",query="街道",category="attraction",read_pages=False)
    async def answer(*args):return ResearchAnswer()
    result=asyncio.run(research(None,"成都街头生活只说两处",[],ContextEnvelope(),Port(),judge=judge,answer=answer))
    assert len(result["place_cards"])==2
    assert all(c["place"]["name"]!="街拍按摩店" for c in result["place_cards"])


def test_old_cards_do_not_force_a_generic_reply_into_a_place_catalog(monkeypatch):
    import json
    from pydantic import SecretStr
    from app.companion_provider import ModelCompanionProvider
    from app.companion_contracts import CompanionContext,CompanionDraft,InformationNeed
    from app.travel_goal_router import route_travel_goal
    from test_assistant_research import PLACE
    async def close():pass
    async def create(*args,**kw):
        assert kw["text_format"]["name"]=="general_knowledge_reply"
        return SimpleNamespace(status="completed",output_text=CompanionDraft(response_text="好的，先休息。").model_dump_json())
    monkeypatch.setattr("app.companion_provider.get_settings",lambda:SimpleNamespace(planner_api_key=SecretStr("fixture"),planner_model="fixture"))
    monkeypatch.setattr("app.companion_provider.build_model_client",lambda _:SimpleNamespace(close=close))
    monkeypatch.setattr("app.companion_provider.create_model_response",create)
    text="今天不出门，想休息。"
    context=CompanionContext(current_message=text,travel_goal=route_travel_goal(text,[]),assistant_context={"browsing_city":"成都"},place_context=[PLACE.model_dump(mode="json")])
    assert asyncio.run(ModelCompanionProvider().generate(context,InformationNeed(general_knowledge_allowed=True))).response_text=="好的，先休息。"


def test_selecting_a_place_does_not_swallow_the_request_to_discuss_it():
    from test_companion_runtime import Provider, Reader, turn
    from app.companion_runtime import CompanionRuntime
    provider = Provider()
    runtime = CompanionRuntime(Reader(), provider)
    _, previous = turn(runtime, "杭州有什么适合摄影的地方？")
    result, _ = turn(runtime, "第二个挺不错，先聊聊这个选择。", [previous])
    assert len(provider.contexts) == 2
    assert result.interactions[0].status == "user_liked"
    assert "可以先比较" in result.response_text
    assert not result.planning_handoff
