import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, func, select

from app.assistant_service import ToolDecision, get_or_create_session, send_message
from app.companion_contracts import (AgentAnswerText, CompanionAnswerDraft, CompanionContext,
    CompanionDraft, CompanionExplanation, CompanionResult, CompanionSuggestion, EntityReference,
    EvidenceApplicability, InformationNeed, KnowledgeEvidence, KnowledgeToolResult, SuggestionDraft)
from app.companion_graph import CompanionContractError
from app.companion_information import determine_information_need
from app.companion_runtime import CompanionRuntime
from app.companion_state import build_planning_brief, project_conversation, resolve_suggestions
from app.database import Activity, AssistantSession, DayPlan, PlaceCandidate, PlanningRun, PlanRevision, Trip, engine, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.travel_goal_router import route_travel_goal


class Reader:
    def __init__(self):
        self.needs = []

    async def load(self, context, need):
        self.needs.append(need)
        return context


class Provider:
    def __init__(self):
        self.contexts = []

    async def generate(self, context, need):
        self.contexts.append(context)
        return CompanionAnswerDraft(agent_claims=[AgentAnswerText(
            text="可以先比较这些旅行体验，再按自己的兴趣选择。",
            claim_type="agent_inference", applicability=EvidenceApplicability(scope="general"))], suggestions=[
            SuggestionDraft(title=name, summary="待核实的兴趣候选。", reasons=[f"{name}是这次摄影讨论的候选兴趣。"])
            for name in ("西湖", "九溪", "北山街")])


def turn(runtime, message, messages=None, *, turn_id=None):
    messages = messages or []
    turn_id = turn_id or str(uuid.uuid4())
    result = asyncio.run(runtime.run(session_id="session", turn_id=turn_id, message=message,
        goal=route_travel_goal(message, messages[-12:]), messages=messages))
    return result, {"id": turn_id, "user": message, "assistant": result.response_text,
        "goal_routing": route_travel_goal(message, messages[-12:]).model_dump(), "companion_result": result.model_dump(mode="json")}


def test_independent_graph_runtime_and_server_owned_suggestion_identity():
    provider, reader = Provider(), Reader()
    runtime = CompanionRuntime(reader, provider)
    result, message = turn(runtime, "杭州有什么适合摄影的地方？", turn_id="same-turn")
    assert len(result.suggestions) == 3
    assert len({s.suggestion_id for s in result.suggestions}) == 3
    assert all(s.suggestion_id.startswith("suggestion_") for s in result.suggestions)
    assert all(s.entity_refs[0].kind == "raw_mention" for s in result.suggestions)
    assert all(s.grounding == "unverified_proposal" for s in result.suggestions)
    assert result.planning_handoff is None
    assert "determine_information_need" in result.runtime_trace
    assert "planning_handoff_not_authorized" in result.runtime_trace
    same, _ = turn(runtime, message["user"], turn_id="same-turn")
    assert [s.suggestion_id for s in same.suggestions] == [s.suggestion_id for s in result.suggestions]
    assert reader.needs[0].preferences_required


def test_casual_destination_food_uses_model_without_knowledge_lookup():
    class FoodProvider:
        calls = 0
        async def generate(self, context, need):
            self.calls += 1
            assert need.general_knowledge_allowed and not need.knowledge_required
            return CompanionDraft(response_text="南京常见的特色小吃有鸭血粉丝汤、盐水鸭和牛肉锅贴。")

    class ForbiddenKnowledgeTool:
        async def retrieve(self, request):
            raise AssertionError("casual food chat should not search the curated corpus")

    provider = FoodProvider()
    result, _ = turn(CompanionRuntime(Reader(), provider, ForbiddenKnowledgeTool()), "南京有什么特色美食吗？")
    assert provider.calls == 1
    assert result.status == "completed"
    assert result.response_text.startswith("南京常见的特色小吃")
    assert "待核实" not in result.response_text
    assert result.grounding_limitations == ["model_general_knowledge_unverified"]
    assert not result.knowledge_evidence and not result.answer_evidence_refs


def test_saved_suggestion_explanation_uses_exact_original_reasons_without_model_call():
    provider = Provider()
    runtime = CompanionRuntime(Reader(), provider)
    first, message = turn(runtime, "杭州有什么适合摄影的地方？")
    result, _ = turn(runtime, "第二个为什么值得去？", [message])
    assert result.resolved_suggestion_refs == [first.suggestions[1].suggestion_id]
    assert result.explanation.explanation_type == "original_saved_suggestion"
    assert result.explanation.reasons == first.suggestions[1].reasons
    assert result.explanation.source_turn_ref == message["id"]
    assert result.explanation.based_on_prior_decision
    assert "实时事实" in result.response_text
    assert len(provider.contexts) == 1


def test_liking_and_pronouns_survive_reload_and_more_than_twelve_turns():
    runtime = CompanionRuntime(Reader(), Provider())
    first, message = turn(runtime, "杭州有什么适合摄影的地方？")
    liked, liked_message = turn(runtime, "第二个挺不错。", [message])
    assert liked.interactions[0].status == "user_liked"
    assert liked.planning_handoff is None
    history = [message, liked_message, *[{"id": str(i), "user": "谢谢", "assistant": "收到"} for i in range(20)]]
    reloaded = CompanionRuntime(Reader(), Provider())
    followup, _ = turn(reloaded, "它为什么值得去？", history)
    assert followup.resolved_suggestion_refs == [first.suggestions[1].suggestion_id]
    projection = project_conversation(history)
    assert projection.suggestions[first.suggestions[1].suggestion_id].status == "user_liked"


@pytest.mark.parametrize("text,code", [("第九个为什么值得去？", "unknown_suggestion"),
    ("那个地方为什么值得去？", "ambiguous_suggestion"),
    ("suggestion_" + "a" * 32 + "为什么值得去？", "unknown_suggestion")])
def test_unknown_or_ambiguous_suggestions_clarify_without_guessed_identity(text, code):
    provider = Provider()
    runtime = CompanionRuntime(Reader(), provider)
    _, message = turn(runtime, "杭州有什么适合摄影的地方？")
    result, _ = turn(runtime, text, [message])
    assert result.status == "needs_clarification"
    assert result.information_gaps[0].code == code
    assert not result.resolved_suggestion_refs
    assert len(provider.contexts) == 1


def test_preference_and_destination_followup_have_conversation_continuity():
    provider = Provider()
    runtime = CompanionRuntime(Reader(), provider)
    _, first = turn(runtime, "杭州适合我吗？")
    _, second = turn(runtime, "我不喜欢商业化的地方。", [first])
    result, _ = turn(runtime, "那苏州呢？", [first, second])
    assert result.conversation_destination == "苏州"
    assert provider.contexts[-1].relevant_user_preferences[-1].text == second["user"]
    assert provider.contexts[-1].recent_turns[-1]["id"] == second["id"]
    assert result.planning_handoff is None


def test_handoff_resolves_multiple_stable_refs_without_promoting_liked_to_must_do():
    runtime = CompanionRuntime(Reader(), Provider())
    first, message = turn(runtime, "杭州有什么适合摄影的地方？")
    _, liked = turn(runtime, "第二个挺不错。", [message])
    text = "那就按第二个和第三个给我规划三天。"
    goal = route_travel_goal(text, [message, liked])
    assert goal.target_runtime == "planning"
    brief = build_planning_brief("session", "handoff", text, goal, [message, liked])
    assert brief.status == "prepared"
    assert brief.suggestion_refs == [first.suggestions[1].suggestion_id, first.suggestions[2].suggestion_id]
    assert [s.display_name for s in brief.candidate_interests] == ["九溪", "北山街"]
    assert brief.duration_days == 3
    assert not brief.must_do
    assert brief.authorization_turn_id == "handoff"
    assert message["id"] in brief.source_turn_refs
    assert build_planning_brief("s", "no-auth", liked["user"], route_travel_goal(liked["user"]), [message]) is None


def test_must_do_requires_explicit_constraint_and_model_cannot_authorize_or_invent_identity():
    runtime = CompanionRuntime(Reader(), Provider())
    first, message = turn(runtime, "杭州有什么适合摄影的地方？")
    text = "第二个一定帮我放进去。"
    brief = build_planning_brief("session", "must", text, route_travel_goal(text), [message])
    assert brief.must_do == [first.suggestions[1].suggestion_id]
    with pytest.raises(ValidationError):
        CompanionDraft.model_validate({"response_text": "完成", "planning_handoff": brief.model_dump()})
    with pytest.raises(ValidationError):
        SuggestionDraft.model_validate({"title": "九溪", "summary": "候选", "place_id": "activity_1"})


@pytest.mark.parametrize("text", ["西湖今天几点关门？", "杭州最近天气怎么样？", "西湖今天适合去吗？"])
def test_missing_live_facts_bypass_even_an_unsafe_provider(text):
    class UnsafeProvider:
        async def generate(self, context, need):
            raise AssertionError("no model may invent live facts")
    result, _ = turn(CompanionRuntime(Reader(), UnsafeProvider()), text)
    assert result.information_need.live_fact_required
    assert "无法核实" in result.response_text
    assert any(g.code == "live_fact_unavailable" for g in result.information_gaps)
    assert not result.suggestions


def test_missing_original_planner_rationale_cannot_be_reconstructed_as_original():
    provider = Provider()
    runtime = CompanionRuntime(Reader(), provider)
    _, suggestion_message = turn(runtime, "杭州有什么适合摄影的地方？")
    result, _ = turn(runtime, "为什么你之前把西湖放在晚上？", [suggestion_message])
    assert result.explanation.explanation_type == "rationale_unavailable"
    assert not result.explanation.based_on_prior_decision
    assert len(provider.contexts) == 1
    with pytest.raises(ValidationError):
        CompanionExplanation(explanation_type="original_validated_decision", reasons=["模型猜测"])
    with pytest.raises(ValidationError):
        CompanionExplanation(explanation_type="current_reconstruction", based_on_prior_decision=True)


def test_unavailable_knowledge_is_explicit_and_tool_port_is_used_only_when_needed():
    class Tool:
        calls = []
        async def retrieve(self, request):
            self.calls.append(request)
            return KnowledgeToolResult(status="available", evidence=[KnowledgeEvidence(evidence_ref="fixture:history",
                text="测试历史证据", source_reference="fixture://history", knowledge_type="history_culture")])
    provider, tool = Provider(), Tool()
    runtime = CompanionRuntime(Reader(), provider, tool)
    result, message = turn(runtime, "西湖有什么历史？请给出来源。")
    assert tool.calls[0].knowledge_types == ["history_culture"]
    assert not provider.contexts  # exact factual answers are server-rendered from reviewed assertions
    assert not any(g.code == "knowledge_unavailable" for g in result.information_gaps)
    turn(runtime, "你好", [message])
    assert len(tool.calls) == 1
    unavailable, _ = turn(CompanionRuntime(Reader(), provider), "西湖有什么历史？请给出来源。")
    assert "现有来源不足" in unavailable.response_text
    assert any(g.code == "knowledge_unavailable" for g in unavailable.information_gaps)


def test_unknown_evidence_and_wrong_runtime_are_rejected():
    class BadEvidence:
        async def generate(self, context, need):
            return CompanionDraft(response_text="证据已确认", evidence_refs=["invented"])
    with pytest.raises(CompanionContractError, match="unknown evidence"):
        turn(CompanionRuntime(Reader(), BadEvidence()), "杭州适合我吗？")
    with pytest.raises(CompanionContractError, match="Planning or Execution"):
        asyncio.run(CompanionRuntime(Reader(), Provider()).run(session_id="s", turn_id="t", message="帮我安排三天",
            goal=route_travel_goal("帮我安排三天"), messages=[]))


def test_unresolved_conversation_reference_requests_information_without_model_call():
    provider, reader = Provider(), Reader()
    result, _ = turn(CompanionRuntime(reader, provider), "那呢？")
    assert result.status == "needs_clarification"
    assert "哪个目的地" in result.response_text
    assert not provider.contexts
    assert not reader.needs


def test_context_policy_uses_no_planning_or_execution_queries_for_history_and_preferences():
    from sqlalchemy.engine import Engine
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        async def scenario():
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                statements = []
                def capture(conn, cursor, statement, parameters, context, executemany):
                    statements.append(statement.lower())
                # Saved reads use an independent bounded read channel. Observe
                # all engines so the policy still checks the actual queries.
                event.listen(Engine, "before_cursor_execute", capture)
                try:
                    await send_message(db, row.id, "西湖有什么历史？", uuid.uuid4(), companion_provider=Provider())
                    assert all("planning_runs" not in s and "trip_executions" not in s and "route_legs" not in s
                               and "activities" not in s and "trip_preferences" not in s for s in statements)
                    statements.clear()
                    await send_message(db, row.id, "杭州适合我吗？", uuid.uuid4(), companion_provider=Provider())
                    assert any("trip_preferences" in s for s in statements)
                    assert all("planning_runs" not in s and "activities" not in s and "route_legs" not in s
                               and "trip_executions" not in s for s in statements)
                    statements.clear()
                    await send_message(db, row.id, "为什么你之前把西湖安排到晚上？", uuid.uuid4(), companion_provider=Provider())
                    assert any("activities" in s for s in statements)
                    assert all("route_legs" not in s and "trip_executions" not in s for s in statements)
                finally:
                    event.remove(Engine, "before_cursor_execute", capture)
        asyncio.run(scenario())


def test_greeting_attached_to_trip_uses_minimal_companion_path(monkeypatch):
    import app.assistant_service as assistant_service

    class GreetingProvider:
        def __init__(self):
            self.calls = 0
            self.need = None

        async def generate(self, context, need):
            self.calls += 1
            self.need = need
            return CompanionDraft(response_text="你好！今天想聊点什么？")

    async def corpus_must_stay_lazy():
        raise AssertionError("greeting must not initialize or retrieve tourism knowledge")

    monkeypatch.setattr(assistant_service, "get_default_knowledge_tool", corpus_must_stay_lazy)
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        async def scenario():
            provider = GreetingProvider()
            async with session_factory() as db:
                row = AssistantSession(trip_id=DEMO_TRIP_ID, messages=[], applied_actions={})
                db.add(row)
                await db.commit()
                before_runs = await db.scalar(select(func.count()).select_from(PlanningRun))
                before_revisions = await db.scalar(select(func.count()).select_from(PlanRevision))
                statements = []

                def capture(conn, cursor, statement, parameters, context, executemany):
                    statements.append(statement.lower())

                event.listen(engine.sync_engine, "before_cursor_execute", capture)
                try:
                    row = await send_message(db, row.id, "你好", uuid.uuid4(), companion_provider=provider)
                finally:
                    event.remove(engine.sync_engine, "before_cursor_execute", capture)

                assert provider.calls == 1
                assert provider.need is not None
                assert provider.need.answer_mode == "advisory"
                assert provider.need.knowledge_required is False
                assert provider.need.trip_context_required is False
                assert provider.need.itinerary_required is False
                assert provider.need.live_fact_required is False
                assert all(not any(table in statement for table in (
                    " from trips", " from planning_runs", " from plan_revisions", " from trip_preferences",
                    " from day_plans", " from activities", " from route_legs", " from trip_executions",
                )) for statement in statements)
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before_runs
                assert await db.scalar(select(func.count()).select_from(PlanRevision)) == before_revisions
                assert "goal_routing" in row.messages[-1]
                assert row.messages[-1]["goal_routing"]["target_runtime"] == "companion"
                assert row.messages[-1]["run_id"] is None
                assert row.messages[-1]["companion_result"]["knowledge_retrieval"] is None

        asyncio.run(scenario())


@pytest.mark.parametrize("message", [
    "国庆想出去玩，但是怕一个人玩没意思，你有什么建议？",
    "一个人出去怕无聊怎么办？",
])
def test_destination_discovery_and_solo_concern_do_not_request_planning_slots(message):
    goal = route_travel_goal(message)
    context = CompanionContext(current_message=message, travel_goal=goal)
    need = determine_information_need(context, [])
    assert goal.target_runtime == "companion"
    assert goal.mutation_requested is False
    assert need.trip_context_required is False
    assert need.itinerary_required is False
    assert need.live_fact_required is False
    assert need.knowledge_required is False


def test_companion_preserves_pending_action_without_confirming_or_cancelling_it():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        async def scenario():
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                row.pending_action = {"id": "preview", "tool": "create_trip"}
                await db.commit()
                before = await db.scalar(select(func.count()).select_from(PlanningRun))
                row = await send_message(db, row.id, "杭州适合我吗？", uuid.uuid4(), companion_provider=Provider())
                assert row.pending_action == {"id": "preview", "tool": "create_trip"}
                assert row.latest_run_id is None
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before
        asyncio.run(scenario())


@pytest.mark.parametrize("ledger_status,stale,expected", [("validated", False, "original_validated_decision"),
    ("invalid", False, "rationale_unavailable"), ("unavailable", False, "rationale_unavailable"),
    ("validated", True, "rationale_unavailable")])
def test_formal_rationale_requires_accepted_validated_identity_and_current_version(ledger_status, stale, expected):
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        async def scenario():
            async with session_factory() as db:
                trip = await db.get(Trip, DEMO_TRIP_ID)
                trip.version = 3 if stale else 2
                activity, place = (await db.execute(select(Activity, PlaceCandidate)
                    .join(DayPlan, DayPlan.id == Activity.day_plan_id)
                    .join(PlaceCandidate, PlaceCandidate.id == Activity.place_candidate_id)
                    .where(DayPlan.trip_id == trip.id).order_by(DayPlan.position, Activity.position).limit(1))).first()
                run = PlanningRun(trip_id=trip.id, run_type="replan", status="accepted", user_request="测试历史记录", base_trip_version=1)
                db.add(run)
                await db.flush()
                revision = PlanRevision(trip_id=trip.id, planning_run_id=run.id, revision_number=1,
                    status="accepted", before_snapshot={}, proposed_snapshot={}, validation_result={"valid": True},
                    difference_summary={"decision_summary": {"status": ledger_status, "error_codes": [], "entries": [{
                        "target_activity_id": str(activity.id), "evidence_status": "validated", "reason": "保留你标记为必去的活动",
                        "after": {"start_time": str(activity.scheduled_time)[:5]}}]}})
                db.add(revision)
                await db.commit()
                row = await get_or_create_session(db, trip.id)
                name = activity.custom_name or place.name
                row = await send_message(db, row.id, f"为什么你之前把{name}安排到晚上？请提供原始保存理由。", uuid.uuid4(), companion_provider=Provider())
                explanation = row.messages[-1]["companion_result"]["explanation"]
                assert explanation["explanation_type"] == expected
                if expected == "original_validated_decision":
                    assert explanation["source_decision_ref"] == f"revision:{revision.id}"
                    assert explanation["subject_ref"]["value"] == str(activity.id)
                    assert explanation["reasons"] == ["保留你标记为必去的活动"]
                assert trip.version == (3 if stale else 2)
        asyncio.run(scenario())


def test_persisted_runtime_result_handoff_and_idempotency_across_database_sessions():
    class Router:
        contexts = []
        async def decide(self, context):
            self.contexts.append(context)
            return ToolDecision(tool="plan_trip", reply="候选讨论", planning_request="请调整第二天的行程，让节奏轻松一些。")
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        async def scenario():
            provider, router = Provider(), Router()
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                session_id, turn_id = row.id, uuid.uuid4()
                before = await db.scalar(select(func.count()).select_from(PlanningRun))
                row = await send_message(db, session_id, "杭州有什么适合摄影的地方？", turn_id, companion_provider=provider)
                saved = row.messages[-1]["companion_result"]
                assert saved["runtime_trace"][-1] == "prepare_conversation_persistence"
                again = await send_message(db, session_id, "杭州有什么适合摄影的地方？", turn_id, companion_provider=provider)
                assert again.messages[-1]["companion_result"] == saved
                assert len(provider.contexts) == 1
            async with session_factory() as db:
                row = await send_message(db, session_id, "第二个挺不错。", uuid.uuid4(), companion_provider=provider)
                assert row.messages[-1]["companion_result"]["interactions"][0]["status"] == "user_liked"
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before
                row = await send_message(db, session_id, "那就按第二个帮我安排两天。", uuid.uuid4(), router=router)
                brief = row.messages[-1]["planning_brief"]
                assert brief["suggestion_refs"] == [saved["suggestions"][1]["suggestion_id"]]
                assert brief["candidate_interests"][0]["display_name"] == "九溪"
                assert not brief["must_do"]
                assert router.contexts[-1]["planning_brief"] == brief
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before + 1
        asyncio.run(scenario())


def test_ambiguous_planning_handoff_cannot_call_planning_router():
    class ForbiddenRouter:
        async def decide(self, context):
            raise AssertionError("unknown suggestion cannot hand off")
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        async def scenario():
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                before = await db.scalar(select(func.count()).select_from(PlanningRun))
                row = await send_message(db, row.id, "那按第二个帮我规划两天。", uuid.uuid4(), router=ForbiddenRouter())
                assert row.messages[-1]["planning_brief"]["status"] == "needs_clarification"
                assert row.latest_run_id is None
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before
        asyncio.run(scenario())
