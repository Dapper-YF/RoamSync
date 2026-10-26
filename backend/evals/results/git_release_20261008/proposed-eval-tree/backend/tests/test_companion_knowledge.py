"""Real retrieval integration; generation is controlled unless explicitly live-evaluated."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, func, select

from app.assistant_service import get_or_create_session, send_message, ToolDecision
from app.companion_contracts import (AgentAnswerText, CompanionAnswerDraft, CompanionDraft,
    EvidenceApplicability, KnowledgeToolRequest, KnowledgeToolResult, SuggestionDraft)
from app.companion_graph import CompanionContractError
from app.companion_knowledge import build_reviewed_knowledge_tool, load_reviewed_documents
from app.companion_runtime import CompanionRuntime
from app.companion_state import build_planning_brief
from app.database import Activity, DayPlan, PlanningRun, PlanRevision, Trip, TripExecution, TravelEvent, engine, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.tourism_knowledge_adapter import TourismKnowledgeToolAdapter
from app.travel_goal_router import route_travel_goal


class Reader:
    async def load(self, context, need):
        return context


class CountingTool:
    def __init__(self, tool):
        self.tool, self.calls, self.results = tool, [], []

    async def retrieve(self, request):
        self.calls.append(request)
        result = await self.tool.retrieve(request)
        self.results.append(result)
        return result


class ControlledProvider:
    def __init__(self):
        self.contexts = []

    async def generate(self, context, need):
        self.contexts.append(context)
        if not context.knowledge_context:
            return CompanionAnswerDraft(agent_claims=[AgentAnswerText(
                text="可以先从你的兴趣和节奏出发，逐步比较旅行体验。",
                claim_type="agent_inference", applicability=EvidenceApplicability(scope="general"))])
        evidence = context.knowledge_context[0]
        if "摄影" in context.current_message:
            return CompanionAnswerDraft(agent_claims=[AgentAnswerText(
                text="可以把景观要素当作观察线索，再按自己的兴趣选拍摄主题。",
                claim_type="recommendation",
                applicability=EvidenceApplicability(scope="place", target="西湖"),
                evidence_refs=[evidence.evidence_ref])],
                suggestions=[SuggestionDraft(suggestion_type="experience", title=title,
                    summary="可以作为待核实的摄影体验方向。",
                    reasons=["这是助手提出的观察建议，不是来源事实。"], evidence_refs=[evidence.evidence_ref])
                    for title in ("西湖湖面", "西湖堤道", "西湖亭台")])
        return CompanionAnswerDraft(agent_claims=[AgentAnswerText(
            text="可以结合同行者的体力和兴趣调整节奏，具体选择由你来定。",
            claim_type="recommendation",
            applicability=EvidenceApplicability(scope="audience", target="senior"),
            evidence_refs=[evidence.evidence_ref])])


async def invoke(runtime, text, history=None):
    history = history or []
    # These tests exercise explicit evidence requests, rather than ordinary
    # conversation (covered by test_companion_conversation_policy.py).
    if not history and text not in {"谢谢。", "你好。", "第二个不错。"}:
        text += "请给出来源。"
    tid = str(uuid.uuid4())
    result = await runtime.run(session_id="integration", turn_id=tid, message=text,
        goal=route_travel_goal(text, history[-12:]), messages=history)
    return result, {"id": tid, "user": text, "assistant": result.response_text, "companion_result": result.model_dump(mode="json"),
        "goal_routing": route_travel_goal(text, history[-12:]).model_dump()}


@pytest.mark.parametrize("text,types,season,audience", [
    ("西湖有什么历史？", ["history_culture"], [], []),
    ("杭州有什么当地生活体验？", ["local_lifestyle"], [], []),
    ("秋天去杭州有什么特点？", ["seasonal_experience"], ["autumn"], []),
    ("带父母去杭州怎么玩轻松？", ["audience_strategy", "travel_strategy"], [], ["senior"]),
])
def test_real_curated_ingestion_retrieval_and_valid_citations(text, types, season, audience):
    async def scenario():
        tool = CountingTool(await build_reviewed_knowledge_tool())
        provider = ControlledProvider()
        result, _ = await invoke(CompanionRuntime(Reader(), provider, tool), text)
        assert len(tool.calls) == 1
        assert tool.calls[0].knowledge_types == types
        assert tool.calls[0].season_tags == season and tool.calls[0].audience_tags == audience
        assert result.grounding_status == "citations_validated"
        assert result.answer_evidence_refs and result.knowledge_evidence
        assert set(result.answer_evidence_refs) <= {e.evidence_ref for e in result.knowledge_evidence}
        assert result.knowledge_retrieval.retrieval_mode == "lexical"
        for e in result.knowledge_evidence:
            assert e.chunk_id and e.document_id and e.source_reference.startswith("https://")
            assert e.source_type == "web" and e.reviewed_at
        assert result.planning_handoff is None
    asyncio.run(scenario())


@pytest.mark.parametrize("text", ["谢谢。", "你好。", "第二个不错。"])
def test_acknowledgments_do_not_query_knowledge(text):
    async def scenario():
        tool = CountingTool(await build_reviewed_knowledge_tool())
        await invoke(CompanionRuntime(Reader(), ControlledProvider(), tool), text)
        assert not tool.calls
    asyncio.run(scenario())


@pytest.mark.parametrize("text", ["西湖今天几点关门？", "明天杭州下雨吗？", "我今天已经玩多久了？", "西湖门票价格多少？"])
def test_live_traps_do_not_use_stable_knowledge_or_model(text):
    async def scenario():
        tool, provider = CountingTool(await build_reviewed_knowledge_tool()), ControlledProvider()
        result, _ = await invoke(CompanionRuntime(Reader(), provider, tool), text)
        assert result.information_need.live_fact_required
        assert result.grounding_status == "live_verification_required"
        assert "无法核实" in result.response_text
        assert not tool.calls and not provider.contexts and not result.answer_evidence_refs
    asyncio.run(scenario())


def test_tool_retrieval_boundary_advisory_blocks_background_hits():
    async def scenario():
        actual = await build_reviewed_knowledge_tool()
        class BoundaryRetriever:
            async def retrieve_tourism_knowledge(self, request):
                # Use real hits but simulate a conservative retriever backstop.
                result = await actual.retriever.retrieve_tourism_knowledge(request)
                return result.model_copy(update={"advisory": result.advisory.model_copy(update={
                    "knowledge_sufficient": False, "live_fact_verification_required": True,
                    "planning_decision_context_required": True})})
        provider = ControlledProvider()
        result, _ = await invoke(CompanionRuntime(Reader(), provider, TourismKnowledgeToolAdapter(BoundaryRetriever())), "西湖有什么历史？")
        assert result.explanation.explanation_type == "rationale_unavailable"
        assert result.information_need.live_fact_required and result.information_need.decision_history_required
        assert not result.knowledge_evidence and not result.answer_evidence_refs and not provider.contexts
        assert result.knowledge_retrieval.retrieved_document_refs
    asyncio.run(scenario())


@pytest.mark.parametrize("text,outcome,gap", [("苏州有什么历史？", "unsupported_query", "knowledge_unsupported_query"),
    ("春天去杭州有什么特点？", "no_results", "knowledge_no_results")])
def test_failure_outcomes_have_distinct_safe_messages(text, outcome, gap):
    async def scenario():
        result, _ = await invoke(CompanionRuntime(Reader(), ControlledProvider(), await build_reviewed_knowledge_tool()), text)
        assert result.knowledge_retrieval.outcome == outcome
        assert any(g.code == gap for g in result.information_gaps)
        assert not result.answer_evidence_refs
    asyncio.run(scenario())


def test_retriever_unavailable_and_insufficient_are_distinct():
    async def scenario():
        tool = await build_reviewed_knowledge_tool()
        class Unavailable:
            async def retrieve_tourism_knowledge(self, request):
                raise RuntimeError("private upstream error must not be surfaced")
        result = await TourismKnowledgeToolAdapter(Unavailable()).retrieve(KnowledgeToolRequest(query="西湖历史"))
        assert result.outcome == "retriever_unavailable" and not result.evidence
        class Insufficient:
            async def retrieve_tourism_knowledge(self, request):
                result = await tool.retriever.retrieve_tourism_knowledge(request)
                return result.model_copy(update={"advisory": result.advisory.model_copy(update={"knowledge_sufficient": False})})
        runtime = CompanionRuntime(Reader(), ControlledProvider(), TourismKnowledgeToolAdapter(Insufficient()))
        result, _ = await invoke(runtime, "西湖有什么历史？")
        assert result.knowledge_retrieval.outcome == "knowledge_insufficient"
        assert any(g.code == "knowledge_insufficient" for g in result.information_gaps)
        assert not result.answer_evidence_refs
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["invented_structured_ref", "invented_visible_ref"])
def test_grounding_ref_validation_does_not_silently_strip_invalid_refs(mode):
    class BadProvider:
        async def generate(self, context, need):
            ref = context.knowledge_context[0].evidence_ref
            if mode == "invented_visible_ref":
                return CompanionAnswerDraft(suggestions=[SuggestionDraft(suggestion_type="experience",
                    title="西湖观察建议", summary="讨论方向 [knowledge_99]", reasons=["个人建议。"])])
            return CompanionAnswerDraft(agent_claims=[AgentAnswerText(
                text="可以从景观线索开始探索。",
                claim_type="recommendation", applicability=EvidenceApplicability(scope="place", target="西湖"),
                evidence_refs=["knowledge_99" if mode == "invented_structured_ref" else ref])])
    async def scenario():
        runtime = CompanionRuntime(Reader(), BadProvider(), await build_reviewed_knowledge_tool())
        with pytest.raises(CompanionContractError, match="unknown evidence"):
            await invoke(runtime, "西湖有什么历史？请给我一个观察历史景观的建议。")
    asyncio.run(scenario())


def test_valid_citation_does_not_claim_sentence_entailment():
    class UnsupportedClaim:
        async def generate(self, context, need):
            return CompanionAnswerDraft(agent_claims=[AgentAnswerText(text="西湖在公元9999年形成。",
                claim_type="agent_inference", applicability=EvidenceApplicability(scope="place", target="西湖"),
                evidence_refs=[context.knowledge_context[0].evidence_ref])])
    async def scenario():
        result, _ = await invoke(CompanionRuntime(Reader(), UnsupportedClaim(), await build_reviewed_knowledge_tool()),
            "西湖有什么历史？请给我一个观察历史景观的建议。")
        assert result.grounding_status == "citations_validated"
        assert "claim_entailment_not_verified" in result.grounding_limitations
        assert "9999" not in result.response_text
        assert "unsupported_factual_background_in_advice" in result.claim_validation_issues


def test_missing_exact_fact_does_not_invoke_model_for_background_fill():
    class ForbiddenProvider:
        calls = 0
        async def generate(self, context, need):
            self.calls += 1
            raise AssertionError("an uncovered exact fact must not be filled from model memory")
    async def scenario():
        provider = ForbiddenProvider()
        result, _ = await invoke(CompanionRuntime(Reader(), provider, await build_reviewed_knowledge_tool()), "西湖是哪一年形成的？")
        assert result.grounding_status == "insufficient_evidence"
        assert provider.calls == 0
        assert "9999" not in result.response_text and not result.answer_evidence_refs
    asyncio.run(scenario())
    asyncio.run(scenario())


def test_timing_explanation_cannot_become_original_reason_from_rag():
    async def scenario():
        tool, provider = CountingTool(await build_reviewed_knowledge_tool()), ControlledProvider()
        result, _ = await invoke(CompanionRuntime(Reader(), provider, tool), "为什么你推荐18点去西湖？")
        assert result.explanation.explanation_type == "rationale_unavailable"
        assert result.information_need.live_fact_required and "timing_conditions" in result.information_need.fact_types
        assert not tool.calls and not provider.contexts and not result.answer_evidence_refs
    asyncio.run(scenario())


def test_grounded_suggestion_reload_explanation_and_brief_preserve_identity_domains():
    async def scenario():
        tool = CountingTool(await build_reviewed_knowledge_tool())
        runtime = CompanionRuntime(Reader(), ControlledProvider(), tool)
        first, turn1 = await invoke(runtime, "杭州有哪些适合摄影的地方？")
        liked, turn2 = await invoke(runtime, "第二个不错。", [turn1])
        explanation, _ = await invoke(runtime, "第二个为什么适合我？", [turn1, turn2])
        assert len(tool.calls) == 1
        assert liked.interactions[0].status == "user_liked"
        assert explanation.explanation.subject_ref.value == first.suggestions[1].suggestion_id
        assert explanation.knowledge_evidence[0].document_id == first.knowledge_evidence[0].document_id
        text = "那把第二个安排进第二天下午。"
        brief = build_planning_brief("integration", "explicit", text, route_travel_goal(text), [turn1, turn2])
        assert brief.suggestion_refs == [first.suggestions[1].suggestion_id] and not brief.must_do
        assert all(e.kind == "raw_mention" for interest in brief.candidate_interests for e in interest.entity_refs)
        assert not any(e.kind == "formal_activity" for s in first.suggestions for e in s.entity_refs)
        assert first.knowledge_evidence[0].external_place_ref.startswith("tourism_corpus:")
    asyncio.run(scenario())


def test_real_adapter_service_persistence_minimal_sql_and_explicit_planning_transition():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        async def scenario():
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                provider = ControlledProvider()
                before = {model.__name__: await db.scalar(select(func.count()).select_from(model))
                    for model in (PlanningRun, PlanRevision, TravelEvent, TripExecution)}
                trip = await db.get(Trip, DEMO_TRIP_ID)
                version = trip.version
                activities = list((await db.execute(select(Activity.__table__).order_by(Activity.id))).tuples())
                statements = []
                def capture(conn, cursor, statement, parameters, context, executemany):
                    statements.append(statement.lower())
                event.listen(engine.sync_engine, "before_cursor_execute", capture)
                try:
                    row = await send_message(db, row.id, "西湖有什么历史？请给出来源。", uuid.uuid4(), companion_provider=provider)
                finally:
                    event.remove(engine.sync_engine, "before_cursor_execute", capture)
                assert all(not any(table in s for table in ("planning_runs", "trip_executions", "route_legs", "activities", "trip_preferences")) for s in statements)
                result = row.messages[-1]["companion_result"]
                assert result["answer_evidence_refs"] and result["knowledge_evidence"][0]["chunk_id"]
                await send_message(db, row.id, "杭州有哪些适合摄影的地方？请给出来源。", uuid.uuid4(), companion_provider=provider)
                refs = [s["suggestion_id"] for s in row.messages[-1]["companion_result"]["suggestions"]]
                await send_message(db, row.id, "第二个不错。", uuid.uuid4(), companion_provider=provider)
                assert trip.version == version
                assert list((await db.execute(select(Activity.__table__).order_by(Activity.id))).tuples()) == activities
                for model in (PlanningRun, PlanRevision, TravelEvent, TripExecution):
                    assert await db.scalar(select(func.count()).select_from(model)) == before[model.__name__]
                class Router:
                    calls = []
                    async def decide(self, context):
                        self.calls.append(context)
                        return ToolDecision(tool="plan_trip", planning_request="把第二天下午的节奏调整得更轻松。", reply="准备候选")
                router = Router()
                mid = uuid.uuid4()
                row = await send_message(db, row.id, "那把第二个安排进第二天下午。", mid, router=router)
                assert router.calls[0]["planning_brief"]["suggestion_refs"] == [refs[1]]
                assert all("companion_result" not in m and "planning_brief" not in m for m in router.calls[0]["history"])
                assert row.latest_run_id
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before["PlanningRun"] + 1
                assert not any(e["kind"] == "formal_activity" for i in router.calls[0]["planning_brief"]["candidate_interests"] for e in i["entity_refs"])
        asyncio.run(scenario())


def test_reviewed_corpus_is_small_and_excludes_operational_values():
    documents = load_reviewed_documents()
    assert len(documents) == 7 and {d.destination for d in documents} == {"杭州"}
    assert len({d.source.source_reference for d in documents}) == 4
    assert all(d.source.source_type != "fixture" and d.reviewed_at for d in documents)
    assert all("excluded" in d.metadata for d in documents)


def test_adapter_maps_explicit_filters_without_inferring_them_from_query():
    async def scenario():
        actual = await build_reviewed_knowledge_tool()
        class Spy:
            calls = []
            async def retrieve_tourism_knowledge(self, request):
                self.calls.append(request)
                return await actual.retriever.retrieve_tourism_knowledge(request)
        spy = Spy()
        await TourismKnowledgeToolAdapter(spy).retrieve(KnowledgeToolRequest(query="秋天带父母去杭州", max_results=2))
        request = spy.calls[0]
        assert request.audience_tags == () and request.season_tags == () and request.destination is None
        assert request.top_k == 2 and request.retrieval_mode == "lexical" and not request.include_fixtures
    asyncio.run(scenario())


@pytest.mark.parametrize("corruption", ["fixture", "wrong_destination", "expired", "oversized_identity"])
def test_adapter_rejects_faulty_upstream_provenance(corruption):
    async def scenario():
        actual = await build_reviewed_knowledge_tool()
        class Corrupt:
            async def retrieve_tourism_knowledge(self, request):
                result = await actual.retriever.retrieve_tourism_knowledge(request)
                hit = result.hits[0]
                changes = {"source":hit.chunk.source.model_copy(update={"source_type":"fixture"})} if corruption == "fixture" else {
                    "destination":"苏州"} if corruption == "wrong_destination" else {
                    "valid_until":datetime.now(UTC)-timedelta(days=1)} if corruption == "expired" else {"id":"x"*1000}
                return result.model_copy(update={"hits":(hit.model_copy(update={"chunk":hit.chunk.model_copy(update=changes)}),)})
        result = await TourismKnowledgeToolAdapter(Corrupt()).retrieve(KnowledgeToolRequest(query="西湖历史", destination="杭州"))
        assert result.outcome == "retriever_unavailable" and not result.evidence
    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["live_verification_required", "decision_context_required"])
def test_contradictory_knowledge_outcome_cannot_bypass_advisory(outcome):
    with pytest.raises(ValidationError):
        KnowledgeToolResult(status="unavailable", outcome=outcome)


def test_general_senior_guidance_cannot_assert_destination_suitability():
    class TooBroad:
        async def generate(self, context, need):
            return CompanionDraft(response_text="总体来说杭州适合带父母。", evidence_refs=[context.knowledge_context[0].evidence_ref])
    async def scenario():
        result, _ = await invoke(CompanionRuntime(Reader(), TooBroad(), await build_reviewed_knowledge_tool()), "杭州适合带父母玩吗？")
        assert "杭州适合带父母" not in result.response_text
        assert any("不能据此确认" in gap.message for gap in result.information_gaps)
        assert any(g.code == "knowledge_insufficient" for g in result.information_gaps)
        assert all(e.applicability in {"general_strategy", "audience"} for e in result.knowledge_evidence)
        assert result.answer_evidence_refs
    asyncio.run(scenario())
