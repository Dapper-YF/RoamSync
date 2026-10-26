import asyncio

import pytest

from app.companion_contracts import CompanionDraft, SuggestionDraft
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal


class Reader:
    async def load(self, context, need):
        return context


@pytest.mark.parametrize("text", [
    "西湖有哪些历史文化特色？",
    "我想在杭州找一些适合摄影的活动，请给我两个有文化特色的建议。",
    "南京有什么历史文化特色？", "带父母去苏州怎么玩轻松？",
    "秋天去杭州有什么特点？", "你好",
])
def test_stable_conversation_generates_final_answer_without_corpus_gate(text):
    class Tool:
        async def retrieve(self, request):
            pytest.fail("ordinary conversation must not require sparse corpus retrieval")

    class Provider:
        async def generate(self, context, need):
            assert need.general_knowledge_allowed and not need.knowledge_required
            return CompanionDraft(response_text="1. 北山街人文摄影：拍摄近代建筑与湖景。\n2. 龙井村茶文化摄影：记录茶园与乡村生活。",
                suggestions=[SuggestionDraft(title="北山街", summary="人文摄影", reasons=["近代建筑与湖景"]),
                             SuggestionDraft(title="龙井村", summary="茶文化摄影", reasons=["茶园与乡村生活"])])

    result = asyncio.run(CompanionRuntime(Reader(), Provider(), Tool()).run(
        session_id="policy", turn_id="turn", message=text, goal=route_travel_goal(text), messages=[]))
    assert result.status == "completed"
    assert result.response_text.count("北山街") == 1
    assert len(result.suggestions) == 2
    assert result.grounding_limitations == ["model_general_knowledge_unverified"]
    assert not result.answer_evidence_refs and not result.knowledge_evidence
    assert result.planning_handoff is None
    assert all(label not in result.response_text for label in ("资料支持", "knowledge_", "资料限制", "助手的推断"))


@pytest.mark.parametrize("text", ["西湖有什么历史？请给出来源", "今天西湖门票多少钱？", "为什么行程安排在18点？"])
def test_source_live_and_original_decision_requests_keep_evidence_boundary(text):
    from app.companion_contracts import CompanionContext
    from app.companion_information import determine_information_need
    need = determine_information_need(CompanionContext(current_message=text, travel_goal=route_travel_goal(text)), [])
    assert not need.general_knowledge_allowed
    assert need.knowledge_required or need.live_fact_required or need.decision_history_required
