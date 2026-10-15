import asyncio
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic import SecretStr

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.assistant_service import ToolDecision, get_or_create_session, send_message
from app.database import Activity, ActivityExecution, DayPlan, RouteLeg, PlanningRun, PlanRevision, TravelEvent, Trip, TripExecution, TripPreferences, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.schemas import TravelGoalRouting
from app.travel_goal_router import route_travel_goal
from evals.travel_goal_cases import TRAVEL_GOAL_CASES


def test_goal_router_benchmark_separates_the_two_routing_errors():
    assert 40 <= len(TRAVEL_GOAL_CASES) <= 60
    assert len({item["id"] for item in TRAVEL_GOAL_CASES}) == len(TRAVEL_GOAL_CASES)
    companion_to_planning = 0
    planning_to_companion = 0
    for case in TRAVEL_GOAL_CASES:
        result = route_travel_goal(case["text"], case.get("history"))
        assert isinstance(result, TravelGoalRouting)
        assert result.goal_type == case["goal"], case["id"]
        assert result.target_runtime == case["runtime"], case["id"]
        companion_to_planning += case["runtime"] == "companion" and result.target_runtime == "planning"
        planning_to_companion += case["runtime"] == "planning" and result.target_runtime == "companion"
    assert companion_to_planning == 0
    assert planning_to_companion == 0


def test_explicit_generate_from_trip_details_routes_to_planning():
    result = route_travel_goal("请根据我的旅行日期、预算和偏好生成完整行程。")
    assert result.target_runtime == "planning"
    assert result.goal_type == "trip_planning"
    assert result.mutation_requested is True


def test_companion_turns_and_execution_requests_create_no_planning_or_formal_changes():
    class ForbiddenPlanningRouter:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            raise AssertionError("non-planning goals must not invoke the planning tool router")

    async def answer(context, goal):
        assert goal.target_runtime == "companion"
        # Even a poor model response has no ability to execute this claim.
        return "已把博物馆加进行程。"

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days_before = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        started = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={})
        assert started.status_code == 200

        async def scenario():
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                # Imported historical trips can lack preference rows. Reading
                # Companion context must not invoke Planning's repair writes.
                await db.execute(delete(TripPreferences).where(TripPreferences.trip_id == DEMO_TRIP_ID))
                await db.commit()
                router = ForbiddenPlanningRouter()
                trip = await db.get(Trip, DEMO_TRIP_ID)
                before_version = trip.version
                before_activities = list((await db.execute(
                    select(Activity.id, Activity.version, Activity.scheduled_time, Activity.status)
                    .join(DayPlan)
                    .where(DayPlan.trip_id == DEMO_TRIP_ID)
                    .order_by(Activity.id)
                )).tuples().all())
                before_runs = await db.scalar(select(func.count()).select_from(PlanningRun))
                before_revisions = await db.scalar(select(func.count()).select_from(PlanRevision))
                before_events = await db.scalar(select(func.count()).select_from(TravelEvent))
                before_executions = await db.scalar(select(func.count()).select_from(TripExecution))
                async def persisted_state():
                    return [list((await db.execute(select(model.__table__).order_by(model.id))).tuples())
                            for model in (Trip, DayPlan, Activity, RouteLeg, TripExecution, ActivityExecution, TravelEvent)]
                before_state = await persisted_state()

                for text in (case["text"] for case in TRAVEL_GOAL_CASES if case["runtime"] == "companion"):
                    result = await send_message(
                        db, row.id, text, uuid.uuid4(), router=router, companion_responder=answer
                    )
                    assert result.messages[-1]["goal_routing"]["target_runtime"] == "companion"
                    assert result.messages[-1]["run_id"] is None

                execution_result = await send_message(
                    db, row.id, "我想在这里再待30分钟。", uuid.uuid4(), router=router
                )
                assert execution_result.messages[-1]["goal_routing"]["target_runtime"] == "execution"
                assert "执行卡片" in execution_result.messages[-1]["assistant"]

                trip = await db.get(Trip, DEMO_TRIP_ID)
                after_activities = list((await db.execute(
                    select(Activity.id, Activity.version, Activity.scheduled_time, Activity.status)
                    .join(DayPlan)
                    .where(DayPlan.trip_id == DEMO_TRIP_ID)
                    .order_by(Activity.id)
                )).tuples().all())
                assert trip.version == before_version
                assert after_activities == before_activities
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before_runs
                assert await db.scalar(select(func.count()).select_from(PlanRevision)) == before_revisions
                assert await db.scalar(select(func.count()).select_from(TravelEvent)) == before_events
                assert await db.scalar(select(func.count()).select_from(TripExecution)) == before_executions
                assert await persisted_state() == before_state
                assert await db.get(TripPreferences, DEMO_TRIP_ID) is None
                assert router.calls == 0

        asyncio.run(scenario())
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json() == days_before


def test_explicit_planning_followup_keeps_the_existing_planning_run_boundary():
    class PlanningRouter:
        async def decide(self, context):
            return ToolDecision(
                tool="plan_trip", reply="准备候选调整。", planning_request=context["message"]
            )

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        async def scenario():
            async with session_factory() as db:
                row = await get_or_create_session(db, DEMO_TRIP_ID)
                trip = await db.get(Trip, DEMO_TRIP_ID)
                version = trip.version
                before = await db.scalar(select(func.count()).select_from(PlanningRun))
                before_revisions = await db.scalar(select(func.count()).select_from(PlanRevision))
                result = await send_message(
                    db, row.id, "把第二天的博物馆换掉。", uuid.uuid4(), router=PlanningRouter()
                )
                assert result.messages[-1]["goal_routing"]["target_runtime"] == "planning"
                assert result.latest_run_id is not None
                assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before + 1
                assert await db.scalar(select(func.count()).select_from(PlanRevision)) == before_revisions
                assert (await db.get(Trip, DEMO_TRIP_ID)).version == version

        asyncio.run(scenario())


def test_multi_turn_companion_to_planning_and_explanation_to_mutation_transitions():
    a_history = []
    scenario_a = [
        ("杭州适合我吗？", "companion"),
        ("我喜欢人文，自然也可以，不喜欢商业街。", "companion"),
        ("那就去杭州吧。", "companion"),
        ("帮我安排三天。", "planning"),
    ]
    for text, runtime in scenario_a:
        result = route_travel_goal(text, a_history)
        assert result.target_runtime == runtime
        a_history.append({"user": text, "assistant": "旅行建议。"})

    b_history = [{"user": "西湖有什么历史？", "assistant": "这里保存的推荐理由是避开午后人流。"}]
    explanation = route_travel_goal("那为什么你之前把它安排到晚上？", b_history)
    assert explanation.target_runtime == "companion"
    assert explanation.goal_type == "explanation"
    change = route_travel_goal("那改成上午吧。", [*b_history, {"user": "那为什么？", "assistant": "避开人流。"}])
    assert change.target_runtime == "planning"
    assert change.mutation_requested
    assert change.referenced_previous_decision


def test_schema_rejects_inconsistent_runtime_and_mutation_authorization():
    value = route_travel_goal("西湖有什么历史？").model_dump()
    with pytest.raises(ValidationError):
        TravelGoalRouting.model_validate({**value, "target_runtime": "planning"})
    with pytest.raises(ValidationError):
        TravelGoalRouting.model_validate({**value, "mutation_requested": True})


def test_companion_http_contract_and_message_idempotency():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        row = client.post("/api/v1/assistant/sessions", json={"trip_id": str(DEMO_TRIP_ID)}).json()
        payload = {"message": "西湖有什么历史？", "message_id": str(uuid.uuid4())}
        response = client.post(f"/api/v1/assistant/sessions/{row['id']}/messages", json=payload)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["latest_run_id"] is None
        assert result["pending_action"] is None
        assert result["messages"][-1]["goal_routing"]["target_runtime"] == "companion"
        assert result["messages"][-1]["companion_result"]["runtime_trace"][-1] == "prepare_conversation_persistence"
        assert result["messages"][-1]["assistant"]
        again = client.post(f"/api/v1/assistant/sessions/{row['id']}/messages", json=payload)
        assert again.json() == result


def test_execution_chat_cannot_create_a_run_through_direct_planning_api():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={
            "run_type": "replan", "user_request": "我想在这里再待30分钟。"})
        assert response.status_code == 422
        assert response.json()["detail"]["route"] == "execution"


def test_planning_clarification_does_not_promote_a_new_question_or_discovery():
    history = [{"user": "帮我安排杭州三天。", "assistant": "什么时候出发？",
                "goal_routing": route_travel_goal("帮我安排杭州三天。").model_dump()}]
    assert route_travel_goal("10月2日出发", history).target_runtime == "planning"
    assert route_travel_goal("两个人", history).target_runtime == "planning"
    assert route_travel_goal("还是两天", history).target_runtime == "planning"
    assert route_travel_goal("希望行程中包含龙龛码头").target_runtime == "planning"
    for text in ("我想了解去杭州旅行的利弊", "我喜欢去杭州旅游", "介绍一下杭州两天游的体验"):
        assert route_travel_goal(text).target_runtime == "companion"
    for previous in ({"user": "我喜欢去杭州旅游"}, {"user": "我喜欢去杭州旅游", "goal_routing": route_travel_goal("我喜欢去杭州旅游").model_dump()}):
        assert route_travel_goal("两个人", [previous]).target_runtime == "companion"
    assert route_travel_goal("杭州适合两个人去吗？", history).target_runtime == "companion"
    assert route_travel_goal("还没想好去哪", history).target_runtime == "companion"
    assert route_travel_goal("你好", history, pending_action={"tool": "create_trip"}).target_runtime == "companion"


def test_multi_turn_runtime_handoff_occurs_only_on_explicit_request():
    class Router:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            assert context["history"]
            return ToolDecision(tool="plan_trip", reply="准备候选。",
                planning_request="请调整第二天的行程，让节奏轻松一些。")

    async def answer(context, goal):
        return "旅行建议，不是已保存的规划决定。"

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        async def scenario():
            async with session_factory() as db:
                for texts in (
                    ["杭州适合我吗？", "我喜欢人文，自然也可以，不喜欢商业街。", "那就去杭州吧。", "帮我安排三天。"],
                    ["西湖有什么历史？", "那为什么你之前把它安排到晚上？", "那改成上午吧。"],
                ):
                    row = await get_or_create_session(db, DEMO_TRIP_ID)
                    router = Router()
                    before = await db.scalar(select(func.count()).select_from(PlanningRun))
                    for index, text in enumerate(texts):
                        row = await send_message(db, row.id, text, uuid.uuid4(), router=router, companion_responder=answer)
                        last = index == len(texts) - 1
                        assert row.messages[-1]["goal_routing"]["target_runtime"] == ("planning" if last else "companion")
                        assert await db.scalar(select(func.count()).select_from(PlanningRun)) == before + int(last)
                    assert router.calls == 1

        asyncio.run(scenario())


def test_companion_provider_uses_bounded_draft_schema_without_tools(monkeypatch):
    import app.companion_provider as service
    from app.companion_contracts import CompanionContext, InformationNeed
    calls = []

    class Client:
        closed = False

        async def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        planner_api_key=SecretStr("test-key"), planner_model="test-model", intent_reasoning_effort="low"))
    monkeypatch.setattr(service, "build_model_client", lambda settings: client)

    async def create(client, settings, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="completed", output_text='{"agent_claims":[{"text":"可以按兴趣与节奏逐项比较。","claim_type":"agent_inference","applicability":{"scope":"general"},"evidence_refs":[]}]}')

    monkeypatch.setattr(service, "create_model_response", create)
    answer = asyncio.run(service.ModelCompanionProvider().generate(CompanionContext(
        current_message="杭州和苏州哪个更适合慢游？", travel_goal=route_travel_goal("杭州和苏州哪个更适合慢游？")), InformationNeed()))
    assert answer.agent_claims[0].text == "可以按兴趣与节奏逐项比较。"
    assert "tools" not in calls[0]
    schema = calls[0]["text_format"]["schema"]
    assert set(schema["properties"]) == {"analysis_summary", "agent_claims", "suggestions", "comparison"}
    assert schema["additionalProperties"] is False
    assert client.closed


def test_companion_provider_general_food_reply_uses_plain_answer_schema(monkeypatch):
    import app.companion_provider as service
    from app.companion_contracts import CompanionContext, InformationNeed
    calls = []

    class Client:
        async def close(self):
            pass

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        planner_api_key=SecretStr("test-key"), planner_model="test-model"))
    monkeypatch.setattr(service, "build_model_client", lambda settings: Client())

    async def create(client, settings, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="completed", output_text='{"response_text":"南京常见小吃有鸭血粉丝汤。"}',
            model="test-model", usage=None, finish_reason="stop")

    monkeypatch.setattr(service, "create_model_response", create)
    text = "南京有什么特色美食吗？"
    result = asyncio.run(service.ModelCompanionProvider().generate(
        CompanionContext(current_message=text, travel_goal=route_travel_goal(text)),
        InformationNeed(general_knowledge_allowed=True)))
    assert result.response_text == "南京常见小吃有鸭血粉丝汤。"
    assert set(calls[0]["text_format"]["schema"]["properties"]) == {"analysis_summary", "response_text", "suggestions", "comparison", "evidence_refs"}
    assert calls[0]["instructions"].startswith(service.GENERAL_KNOWLEDGE_INSTRUCTIONS)
    assert "public summary" in calls[0]["instructions"]
