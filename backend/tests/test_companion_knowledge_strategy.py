import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.companion_contracts import CompanionContext, CompanionDraft, KnowledgeToolRequest
from app.companion_evidence_quality import gate_evidence
from app.companion_information import determine_information_need
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal
from evals.companion_knowledge_strategy import CountingTool, Reader

CASES = json.loads((Path(__file__).parents[1] / "evals/fixtures/companion_knowledge_strategy_v1.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_fixed_decisions_and_planning_boundary(case):
    goal = route_travel_goal(case["text"], case.get("history", []))
    if "runtime" in case:
        assert goal.target_runtime == case["runtime"] and goal.mutation_requested
        return
    assert goal.target_runtime == "companion" and not goal.mutation_requested
    need = determine_information_need(CompanionContext(current_message=case["text"], travel_goal=goal), [])
    assert need.knowledge_decision == case["decision"]
    assert need.knowledge_reasons


class Provider:
    def __init__(self):
        self.contexts = []

    async def generate(self, context, need):
        self.contexts.append(context)
        assert need.general_knowledge_allowed
        assert not context.knowledge_context
        return CompanionDraft(response_text="可以先介绍一般背景；精确碑文释读需要具体材料确认。")


def test_optional_specialist_fallback_preserves_explicit_preference_and_has_no_citations():
    async def scenario():
        tool, provider = CountingTool(await build_reviewed_knowledge_tool()), Provider()
        text = "西湖碑刻的训诂有什么特点？"
        result = await CompanionRuntime(Reader(), provider, tool).run(session_id="policy", turn_id="next", message=text,
            goal=route_travel_goal(text), messages=[{"id":"pref", "user":"我喜欢安静的街巷", "assistant":"好"}])
        assert tool.calls == 1 and len(provider.contexts) == 1
        assert provider.contexts[0].relevant_user_preferences
        assert result.status == "completed"
        assert "quality_gate_general_fallback" in result.information_need.knowledge_reasons
        assert not result.answer_evidence_refs and not result.knowledge_evidence
        assert result.grounding_limitations == ["model_general_knowledge_unverified"]
    asyncio.run(scenario())


@pytest.mark.parametrize("corruption,code", [
    ({"source_authority":"ugc"}, "untrusted_provenance"),
    ({"reviewed_at":None}, "review_missing_or_invalid"),
    ({"scope":"semi_stable", "valid_until":None}, "expired_or_missing_validity"),
    ({"valid_until":datetime.now(UTC) - timedelta(days=1)}, "expired_or_missing_validity"),
    ({"source_reference":"https://"}, "invalid_source_reference"),
    ({"answerable_assertions":[]}, "no_direct_assertion_support"),
])
def test_nonempty_retrieval_is_not_evidence_quality(corruption, code):
    async def scenario():
        text = "西湖列入世界遗产是哪年？请给出来源。"
        context = CompanionContext(current_message=text, travel_goal=route_travel_goal(text), current_destination="杭州")
        need = determine_information_need(context, [])
        tool = await build_reviewed_knowledge_tool()
        result = await tool.retrieve(KnowledgeToolRequest(query=text, destination="杭州", knowledge_types=need.knowledge_types))
        assert result.evidence
        result = result.model_copy(update={"evidence":[e.model_copy(update=corruption) for e in result.evidence]})
        accepted, rejected = gate_evidence(result, context, need)
        assert not accepted and code in rejected
    asyncio.run(scenario())


def test_conflicting_assertion_identity_not_published():
    async def scenario():
        text = "西湖列入世界遗产是哪年？请给出来源。"
        context = CompanionContext(current_message=text, travel_goal=route_travel_goal(text), current_destination="杭州")
        need = determine_information_need(context, [])
        tool = await build_reviewed_knowledge_tool()
        result = await tool.retrieve(KnowledgeToolRequest(query=text, destination="杭州", knowledge_types=need.knowledge_types))
        original = next(e for e in result.evidence if any("heritage_inscription_year" in a.topics for a in e.answerable_assertions))
        changed = original.model_copy(update={"evidence_ref":"knowledge_conflict", "answerable_assertions":[
            a.model_copy(update={"text":"不同的年份。"}) for a in original.answerable_assertions]})
        accepted, rejected = gate_evidence(result.model_copy(update={"evidence":[original, changed]}), context, need)
        assert not accepted and "conflicting_assertion_identity" in rejected
    asyncio.run(scenario())


def test_general_model_cannot_claim_it_retrieved_an_official_source():
    async def scenario():
        class FalseCitation:
            async def generate(self, context, need):
                return CompanionDraft(response_text="资料显示，南京最适合所有人旅游。")
        text = "南京有哪些文化特色？"
        result = await CompanionRuntime(Reader(), FalseCitation()).run(session_id="citation", turn_id="now",
            message=text, goal=route_travel_goal(text), messages=[])
        assert "资料显示" not in result.response_text
        assert result.status == "needs_information" and not result.answer_evidence_refs
    asyncio.run(scenario())


@pytest.mark.parametrize("text", ["怎么把当前行程改得轻松一点？", "先别把当前行程改得轻松一点", "如果改得轻松一点会怎样？"])
def test_replanning_fix_does_not_authorize_questions_or_negation(text):
    assert route_travel_goal(text).target_runtime == "companion"


@pytest.mark.parametrize("text", ["南京到苏州交通耗时多少？", "元宵灯会举办时间和地点是什么？", "从南京到苏州开车多久？"])
def test_verifiable_transport_and_specific_festival_need_live_evidence(text):
    need = determine_information_need(CompanionContext(current_message=text, travel_goal=route_travel_goal(text)), [])
    assert need.live_fact_required and not need.general_knowledge_allowed


def test_failed_model_attempt_is_counted_without_private_error_payload(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    import httpx
    import app.companion_provider as module
    from app.planning_errors import PlannerProviderError
    class Client:
        async def close(self):
            pass
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(planner_api_key=SecretStr("test"), planner_model="test"))
    monkeypatch.setattr(module, "build_model_client", lambda settings: Client())
    async def failure(*args, **kwargs):
        raise httpx.ConnectError("private-provider-payload")
    monkeypatch.setattr(module, "create_model_response", failure)
    provider = module.ModelCompanionProvider()
    text = "南京历史是什么？"
    context = CompanionContext(current_message=text, travel_goal=route_travel_goal(text))
    with pytest.raises(PlannerProviderError):
        asyncio.run(provider.generate(context, determine_information_need(context, [])))
    assert len(provider.observations) == 1
    assert provider.observations[0]["status"] == "failed"
    assert provider.observations[0]["error_code"] == "planner_unavailable"
    assert "private-provider-payload" not in json.dumps(provider.observations)


@pytest.mark.parametrize("mode", ["general_only", "forced_rag", "selective"])
def test_dynamic_and_source_degradation_do_not_invoke_general_model(mode):
    async def scenario():
        class NoModel:
            async def generate(self, context, need):
                pytest.fail("cannot invent verified fact or missing source")
        tool = CountingTool(await build_reviewed_knowledge_tool())
        runtime = CompanionRuntime(Reader(), NoModel(), tool, knowledge_strategy=mode)
        for text in ["今年南京灯会具体举办时间和地点是什么？", "南京历史是什么？请给出来源。"]:
            result = await runtime.run(session_id="boundary", turn_id="now", message=text, goal=route_travel_goal(text), messages=[])
            assert not result.answer_evidence_refs
            assert result.information_gaps
            assert result.planning_handoff is None
    asyncio.run(scenario())
