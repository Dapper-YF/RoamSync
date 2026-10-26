import asyncio
import pytest
from app.travel_goal_router import route_travel_goal
from app.companion_contracts import CompanionAnswerDraft
from app.companion_runtime import CompanionRuntime
from app.companion_knowledge import build_reviewed_knowledge_tool

EXPLORATION = ["国庆想出去但怕一个人无聊", "玩三四天", "想出去三四天散散心", "南京怎么样", "南京适合一个人玩吗", "有三天时间能去哪", "想去一个有历史感的城市", "我可能会去南京", "南京听起来不错", "国庆一个人旅行有什么建议", "我想去深圳旅游", "南京三天", "10月2日去南京玩两天", "再去一次", "我在考虑改期"]
PLANNING = ["帮我规划南京三天", "给我做一个南京三日行程", "安排一下这三天", "那就按南京帮我安排", "把第二个安排进第二天下午", "修改第二天行程", "重新规划", "给我排一下国庆南京行程", "帮我规划一个杭州三日游", "把这个地方加进去"]

EXPLORATION += ["一个人出去有什么建议", "想找个适合慢慢逛的城市", "过几天国庆了，我想出去玩，但是怕一个人玩没意思，你有什么建议吗", "目前准备玩个三四天的样子", "你觉得南京怎么样", "南京它是一个怎样的城市呢", "跟我讲讲南京的老街巷吧"]
PLANNING += ["帮我安排杭州三日游", "给我做一个南京三天的行程", "把第二个放进第二天下午", "调整第二天行程", "听起来不错，那帮我规划南京三天吧。"]

@pytest.mark.parametrize("text", EXPLORATION)
def test_exploration_has_no_authority(text):
    goal = route_travel_goal(text)
    assert goal.target_runtime == "companion" and not goal.mutation_requested

@pytest.mark.parametrize("text", PLANNING)
def test_explicit_planning_has_authority(text):
    goal = route_travel_goal(text)
    assert goal.target_runtime == "planning" and goal.mutation_requested

@pytest.mark.parametrize("text", ["三天", "800元左右", "800左右", "预算800", "10月2号出发", "国庆第二天出发", "就第二个", "第二个", "下午吧"])
def test_clarification_inherits_only_explicit_authority(text):
    goal = route_travel_goal("帮我规划南京三天")
    history = [{"user": "帮我规划南京三天", "goal_routing": goal.model_dump(), "status": "answered"}]
    result = route_travel_goal(text, history)
    assert result.target_runtime == "planning" and not result.mutation_requested
    assert result.signals == ["planning_field_follow_up"]
    assert route_travel_goal(text, [{"user": "南京怎么样"}]).target_runtime == "companion"
    assert route_travel_goal(text, pending_action={"tool": "create_trip"}).target_runtime == "companion"
    history[-1]["status"] = "cancelled"
    assert route_travel_goal(text, history).target_runtime == "companion"

class Reader:
    async def load(self, context, need):
        return context

def test_named_subject_does_not_become_ambiguous_suggestion_pronoun():
    from app.companion_state import ConversationState, resolve_suggestions
    state = ConversationState()
    selected, gaps = resolve_suggestions("南京它是一个怎样的城市呢", state)
    assert selected == [] and gaps == []
    selected, gaps = resolve_suggestions("它是一个怎样的地方呢", state)
    assert selected == [] and gaps[0].code == "ambiguous_suggestion"

class Provider:
    async def generate(self, context, need):
        return CompanionAnswerDraft()

def test_partial_answer_keeps_material_gap_in_natural_prose():
    async def run():
        text = "根据可靠资料讲讲西湖历史和形成的确切年份"
        result = await CompanionRuntime(Reader(), Provider(), await build_reviewed_knowledge_tool()).run(
            session_id="final", turn_id="gap", message=text, goal=route_travel_goal(text), messages=[])
        assert result.claims
        assert "年份" in result.response_text and "没有足够可靠的资料确认" in result.response_text
        assert not any(t in result.response_text for t in ["资料限制", "knowledge_", "claim_type"])
    asyncio.run(run())

def test_renderer_keeps_inference_and_recommendation_voice():
    from app.companion_graph import _answer_text
    from app.companion_contracts import GroundedAnswerClaim, EvidenceApplicability
    claims = [GroundedAnswerClaim(claim_id="claim_" + "0" * 32, text="堤道可作为摄影观察线索。", claim_type=kind,
        applicability=EvidenceApplicability(scope="general"), support_status="not_applicable",
        applicability_status="not_applicable", attribution_status="not_applicable")
        for kind in ["curator_inference", "agent_inference", "recommendation"]]
    text = _answer_text(claims, [], [])
    assert "如果你喜欢" in text and "我倾向于认为" in text and "我的建议" in text
    assert "UNESCO" not in text and "推断" not in text

@pytest.mark.parametrize("text", ["根据可靠资料，西湖有哪些景观构成？", "UNESCO官方推荐西湖哪些摄影机位？请给出依据", "根据可靠资料，西湖有哪些文化景观值得观察和摄影？"])
def test_explicit_source_request_retrieves_even_without_city_name(text):
    from app.companion_contracts import CompanionContext
    from app.companion_information import determine_information_need
    need = determine_information_need(CompanionContext(current_message=text, travel_goal=route_travel_goal(text)), [])
    assert need.knowledge_required and not need.general_knowledge_allowed

def test_exploration_session_has_zero_runs_until_explicit_transition():
    import uuid
    from fastapi.testclient import TestClient
    from sqlalchemy import select, func
    from app.main import app
    from app.database import PlanningRun, Trip, session_factory
    from app.demo_seed import DEMO_TRIP_ID
    from app.assistant_service import get_or_create_session, send_message, ToolDecision
    from app.companion_contracts import CompanionDraft
    class GeneralProvider:
        async def generate(self, context, need):
            return CompanionDraft(response_text="可以继续聊城市文化与旅行兴趣。")
    class Router:
        calls = []
        async def decide(self, context):
            self.calls.append(context)
            assert context["planning_brief"]["duration_days"] == 3
            assert context["planning_brief"]["destination"] == "南京"
            return ToolDecision(tool="plan_trip", planning_request=context["message"], reply="准备候选行程。")
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        async def run():
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                before = await db.scalar(select(func.count()).select_from(PlanningRun))
                version = (await db.get(Trip, DEMO_TRIP_ID)).version
                router = Router()
                for text in ["你好", "国庆想出去但怕一个人无聊", "玩三四天", "南京怎么样", "南京是怎样的城市", "讲讲南京老街巷"]:
                    row = await send_message(db, row.id, text, uuid.uuid4(), router=router, companion_provider=GeneralProvider())
                    assert row.messages[-1]["goal_routing"]["target_runtime"] == "companion"
                    assert not row.messages[-1]["goal_routing"]["mutation_requested"]
                    assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before
                assert not router.calls
                row = await send_message(db, row.id, "那帮我规划南京三天吧。", uuid.uuid4(), router=router)
                assert row.latest_run_id and router.calls
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before + 1
                assert (await db.get(Trip, DEMO_TRIP_ID)).version == version
        asyncio.run(run())

@pytest.mark.parametrize("text", ["今年满觉陇的桂花季几点开始？", "今年满觉陇的桂花节几点开始？", "杭州秋季赏桂文化是什么，出发那天花况如何？"])
def test_future_flower_condition_needs_live_verification(text):
    from app.companion_contracts import CompanionContext
    from app.companion_information import determine_information_need
    need = determine_information_need(CompanionContext(current_message=text, travel_goal=route_travel_goal(text)), [])
    assert need.live_fact_required and not need.general_knowledge_allowed

def test_source_scope_proof_question_is_factual_not_advice():
    from app.companion_contracts import CompanionContext
    from app.companion_information import determine_information_need
    text = "通用老年旅游规范能证明杭州一定适合我父母吗？请给出来源"
    need = determine_information_need(CompanionContext(current_message=text, travel_goal=route_travel_goal(text)), [])
    assert need.answer_mode == "factual" and need.knowledge_required

@pytest.mark.parametrize("repair_valid", [True, False])
def test_provider_repairs_malformed_json_once_without_relaxing_schema(monkeypatch, repair_valid):
    from types import SimpleNamespace
    from pydantic import SecretStr
    import app.companion_provider as module
    from app.companion_contracts import CompanionContext, InformationNeed
    class Client:
        async def close(self): pass
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(planner_api_key=SecretStr("test"), planner_model="test"))
    monkeypatch.setattr(module, "build_model_client", lambda settings: Client())
    calls=[]
    async def respond(client, settings, **kwargs):
        calls.append(kwargs)
        text = '{"response_text":"可以继续探索城市文化。"}'
        if len(calls)==1 or not repair_valid: text += " extra output"
        return SimpleNamespace(status="completed",output_text=text,usage=None,finish_reason="stop",model="test")
    monkeypatch.setattr(module, "create_model_response", respond)
    provider=module.ModelCompanionProvider()
    context=CompanionContext(current_message="南京怎么样",travel_goal=route_travel_goal("南京怎么样"))
    need=InformationNeed(general_knowledge_allowed=True)
    if repair_valid:
        result=asyncio.run(provider.generate(context,need))
        assert result.response_text=="可以继续探索城市文化。"
    else:
        from app.planning_errors import PlannerProviderError
        with pytest.raises(PlannerProviderError): asyncio.run(provider.generate(context,need))
    assert len(calls)==2 and calls[0]["text_format"]==calls[1]["text_format"]
    assert len(provider.observations)==2

def test_renderer_cleans_internal_topics_without_rewriting_claim_metadata():
    from app.companion_graph import _answer_text
    from app.companion_contracts import GroundedAnswerClaim, EvidenceApplicability
    claim=GroundedAnswerClaim(claim_id="claim_"+"1"*32,text="现有资料没有覆盖最佳拍摄时段（photography_time）。",
        claim_type="agent_inference",applicability=EvidenceApplicability(scope="place",target="西湖"),
        support_status="not_applicable",applicability_status="not_applicable",attribution_status="not_applicable")
    assert "photography_time" not in _answer_text([claim],[],[])
    assert "photography_time" in claim.text

def test_provider_normalizes_raw_linebreaks_preserving_string_content(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    import app.companion_provider as module
    from app.companion_contracts import CompanionContext, InformationNeed
    class Client:
        async def close(self): pass
    monkeypatch.setattr(module,"get_settings",lambda:SimpleNamespace(planner_api_key=SecretStr("test"),planner_model="test"))
    monkeypatch.setattr(module,"build_model_client",lambda settings:Client())
    async def respond(client,settings,**kwargs):
        return SimpleNamespace(status="completed",output_text='{"response_text":"第一行'+chr(10)+'第二行"}',usage=None,model="test",finish_reason="stop")
    monkeypatch.setattr(module,"create_model_response",respond)
    provider=module.ModelCompanionProvider()
    context=CompanionContext(current_message="南京怎么样",travel_goal=route_travel_goal("南京怎么样"))
    result=asyncio.run(provider.generate(context,InformationNeed(general_knowledge_allowed=True)))
    assert result.response_text=="第一行\n第二行" and len(provider.observations)==1
