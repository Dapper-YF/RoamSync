import asyncio
import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.assistant_service import (
    AssistantToolError,
    AssistantRouter,
    ToolDecision,
    _creation_clarification,
    confirm_action,
    get_or_create_session,
    reset_pre_trip_session,
    send_message,
)
from types import SimpleNamespace
from pydantic import SecretStr
from app.database import Activity, AssistantSession, DayPlan, Expense, PlanningRun, Trip, TripPreferences, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.schemas import CitySuggestionResponse


class Router:
    def __init__(self, decision):
        self.decision = decision
        self.contexts = []
    async def decide(self, context):
        self.contexts.append(context)
        return self.decision


def test_assistant_router_uses_bounded_reasoning_for_tool_selection(monkeypatch):
    import app.assistant_service as service

    calls = []

    class Client:
        async def close(self):
            pass

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        planner_api_key=SecretStr("test-key"), planner_model="test-model", intent_reasoning_effort="max"))
    monkeypatch.setattr(service, "build_model_client", lambda settings: Client())

    async def create(client, settings, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="completed", output_text='{"tool":"reply","reply":"请提供日期。"}',
            finish_reason="stop")

    monkeypatch.setattr(service, "create_model_response", create)
    decision = asyncio.run(AssistantRouter().decide({"message": "帮我安排南京一日游"}))
    assert decision.tool == "reply"
    assert calls[0]["reasoning_effort"] == "low"
    assert calls[0]["max_output_tokens"] == 8000


async def cities(keyword):
    if "深圳" in keyword:
        return [CitySuggestionResponse(name="深圳市", adcode="440300", citycode="0755", longitude=114.06, latitude=22.55)]
    return [CitySuggestionResponse(name="成都市", adcode="510100", citycode="028", longitude=104.06, latitude=30.67)]


def reset():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")


def test_home_creation_is_previewed_atomic_idempotent_and_carries_conversation():
    async def run():
        router = Router(ToolDecision(tool="create_trip", reply="已整理好旅行信息。", destination="成都", start_date=date(2027, 1, 1), end_date=date(2027, 1, 3), total_budget_fen=400000, preferences="两个人，以美食为主，不太赶；预算包含两人。"))
        async with session_factory() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row)
            await db.commit()
            before = await db.scalar(select(func.count()).select_from(Trip))
            mid = uuid.uuid4()
            row = await send_message(db, row.id, "帮我规划元旦去成都三天，两人四千元", mid, router=router, city_search=cities)
            assert await db.scalar(select(func.count()).select_from(Trip)) == before
            action = row.pending_action
            assert action["city"]["adcode"] == "510100"
            await send_message(db, row.id, "帮我规划元旦去成都三天，两人四千元", mid, router=router, city_search=cities)
            assert len(router.contexts) == 1
            await confirm_action(db, row.id, action["id"], True)
            created_id = row.trip_id
            assert created_id and row.latest_run_id
            preferences = await db.get(TripPreferences, created_id)
            assert "两个人" in preferences.free_text_requirements
            await confirm_action(db, row.id, action["id"], True)
            assert row.trip_id == created_id
            assert await db.scalar(select(func.count()).select_from(Trip)) == before + 1
            resumed = await get_or_create_session(db, created_id)
            assert resumed.id == row.id
            assert resumed.messages[0]["user"] == "帮我规划元旦去成都三天，两人四千元"
    asyncio.run(run())


def test_missing_dates_does_not_guess_or_create_and_followup_receives_history():
    async def run():
        router = Router(ToolDecision(tool="create_trip", reply="请补充日期", destination="成都", total_budget_fen=400000))
        async with session_factory() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row)
            await db.commit()
            before = await db.scalar(select(func.count()).select_from(Trip))
            await send_message(db, row.id, "帮我规划下个月去成都", uuid.uuid4(), router=router, city_search=cities)
            assert row.pending_action is None
            assert row.messages[-1]["assistant"] == "准备什么时候去，打算玩几天？"
            router.decision = ToolDecision(tool="reply", reply="好的，请再告诉我具体日期。")
            await send_message(db, row.id, "两个人", uuid.uuid4(), router=router, city_search=cities)
            assert any(m.get("user") == "帮我规划下个月去成都" for m in router.contexts[-1]["history"])
            assert await db.scalar(select(func.count()).select_from(Trip)) == before
    asyncio.run(run())


@pytest.mark.parametrize(
    ("message", "decision", "expected"),
    [
        ("帮我做一个南京两天一晚的旅游规划", ToolDecision(tool="reply", reply="模板回复", destination="南京"), "准备什么时候出发？"),
        ("10月2日去南京玩两天", ToolDecision(tool="reply", reply="模板回复", destination="南京"), None),
        ("南京两天一晚，预算1000", ToolDecision(tool="reply", reply="模板回复"), "准备什么时候出发？"),
    ],
)
def test_creation_clarification_only_asks_current_blockers(message, decision, expected):
    assert _creation_clarification(message, decision) == expected


def test_creation_clarification_uses_user_history_and_treats_unlimited_as_an_answer():
    # The old model prompt could ask “日期 + 预算” again even after both were
    # in conversation. The deterministic gate reads user turns, never its own
    # prior reply, so it also accepts an explicit “预算不限” as non-missing.
    known = "帮我做南京两天一晚的旅游规划\n10月2日出发\n预算1000"
    assert _creation_clarification(known, ToolDecision(tool="reply", reply="模板回复")) is None
    unlimited = _creation_clarification("南京两天一晚，预算不限", ToolDecision(tool="reply", reply="模板回复"))
    assert unlimited == "准备什么时候出发？"


@pytest.mark.parametrize(
    ("message", "decision", "expected_reply"),
    [
        (
            "帮我规划去深圳旅游",
            ToolDecision(tool="reply", reply="请告诉我出发和返回日期，以及总预算。", destination="深圳"),
            "准备什么时候去，打算玩几天？",
        ),
        (
            "帮我规划下周六去深圳",
            ToolDecision(tool="reply", reply="请补充日期和预算。", destination="深圳"),
            "准备玩几天，还是已经有返程日期了？",
        ),
        (
            "帮我规划深圳两天一晚",
            ToolDecision(tool="reply", reply="请补充日期和预算。", destination="深圳"),
            "准备什么时候出发？",
        ),
        (
            "帮我规划10月2日到4日去深圳",
            ToolDecision(tool="create_trip", reply="已收集信息", destination="深圳", start_date=date(2027, 10, 2), end_date=date(2027, 10, 4)),
            "请核对：深圳市，2027-10-02 至 2027-10-04，共 3 天，未设置预算上限。确认后执行。",
        ),
        (
            "帮我规划10月2日去深圳玩三天，预算1000",
            ToolDecision(tool="create_trip", reply="已收集信息", destination="深圳", start_date=date(2027, 10, 2), end_date=date(2027, 10, 4), total_budget_fen=100000),
            "请核对：深圳市，2027-10-02 至 2027-10-04，共 3 天，总预算 1000 元，每日预算 333.33 元。确认后执行。",
        ),
    ],
)
def test_send_message_applies_creation_window_policy(message, decision, expected_reply):
    async def run():
        async with session_factory() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row)
            await db.commit()
            router = Router(decision)
            result = await send_message(db, row.id, message, uuid.uuid4(), router=router, city_search=cities)
            assert result.messages[-1]["assistant"] == expected_reply
    asyncio.run(run())


def test_bad_case_records_router_path_that_previously_bypassed_gate():
    async def run():
        raw = "请告诉我出发和返回日期，以及总预算。"
        decision = ToolDecision(tool="create_trip", reply=raw, destination="深圳")
        async with session_factory() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row)
            await db.commit()
            router = Router(decision)
            result = await send_message(db, row.id, "帮我规划去深圳旅游", uuid.uuid4(), router=router, city_search=cities)
            assert row.trip_id is None
            assert router.contexts[0]["current_trip_id"] is None
            assert router.decision.tool == "create_trip"
            assert router.decision.reply == raw
            assert _creation_clarification("帮我规划去深圳旅游", decision) == "准备什么时候去，打算玩几天？"
            assert result.messages[-1]["assistant"] == "准备什么时候去，打算玩几天？"
    asyncio.run(run())


def test_current_trip_can_start_explicit_new_city_creation():
    reset()
    async def run():
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            router = Router(ToolDecision(
                tool="create_trip", reply="已收集信息", destination="深圳",
                start_date=date(2027, 10, 2), end_date=date(2027, 10, 4),
            ))
            result = await send_message(db, row.id, "帮我规划去深圳旅游，10月2日到4日", uuid.uuid4(), router=router, city_search=cities)
            assert result.messages[-1]["assistant"] == "请核对：深圳市，2027-10-02 至 2027-10-04，共 3 天，未设置预算上限。确认后执行。"
            assert result.pending_action["tool"] == "create_trip"
    asyncio.run(run())


def test_creation_without_budget_previews_and_persists_unconstrained_trip():
    async def run():
        async with session_factory() as db:
            row = await get_or_create_session(db, None)
            router = Router(ToolDecision(
                tool="create_trip", reply="核对", destination="成都",
                start_date=date(2027, 1, 1), end_date=date(2027, 1, 2),
            ))
            result = await send_message(db, row.id, "帮我规划2027年1月1日去成都玩两天，预算不限", uuid.uuid4(), router=router, city_search=cities)
            assert result.pending_action["total_budget_fen"] is None
            assert "未设置预算上限" in result.messages[-1]["assistant"]
            await confirm_action(db, row.id, result.pending_action["id"], True)
            trip = await db.get(Trip, row.trip_id)
            assert trip.total_budget_fen is None and trip.daily_budget_fen is None
    asyncio.run(run())


def test_existing_trip_state_never_gets_home_creation_clarification():
    reset()

    async def run():
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            router = Router(ToolDecision(tool="plan_trip", reply="准备调整", planning_request="请重新规划完整行程"))
            result = await send_message(db, row.id, "帮我重新规划", uuid.uuid4(), router=router)
            assert result.messages[-1]["assistant"] == "我会按这次要求准备候选调整，并说明修改理由。"
            assert result.latest_run_id is not None

    asyncio.run(run())


def test_reschedule_moves_day_ids_without_losing_activities_or_expenses():
    reset()
    async def run():
        router = Router(ToolDecision(tool="reschedule_trip", reply="将整趟旅行改期", start_date=date(2027, 2, 1), end_date=date(2027, 2, 2)))
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            before_days = list((await db.scalars(select(DayPlan).where(DayPlan.trip_id == DEMO_TRIP_ID).order_by(DayPlan.position))).all())
            ids = [d.id for d in before_days]
            acts = list((await db.scalars(select(Activity).join(DayPlan).where(DayPlan.trip_id == DEMO_TRIP_ID))).all())
            activity_ids = {a.id for a in acts}
            await send_message(db, row.id, "将这趟旅行改到2027年2月1日至2日", uuid.uuid4(), router=router)
            action = row.pending_action
            assert (await db.get(Trip, DEMO_TRIP_ID)).start_date.year == 2026
            await confirm_action(db, row.id, action["id"], True)
            assert (await db.get(Trip, DEMO_TRIP_ID)).status == "upcoming"
            assert [d.id for d in before_days] == ids
            assert before_days[0].date == date(2027, 2, 1)
            after = set((await db.scalars(select(Activity.id).join(DayPlan).where(DayPlan.trip_id == DEMO_TRIP_ID))).all())
            assert after == activity_ids
    asyncio.run(run())


def test_reuse_keeps_old_records_and_resets_completion_on_the_new_trip():
    reset()
    async def run():
        router = Router(ToolDecision(tool="reuse_trip", reply="参考旧行程再去一次", start_date=date(2027, 3, 1), end_date=date(2027, 3, 2)))
        async with session_factory() as db:
            old = await db.get(Trip, DEMO_TRIP_ID)
            old_start = old.start_date
            activity = await db.scalar(select(Activity).join(DayPlan).where(DayPlan.trip_id == old.id))
            activity.status, activity.schedule_locked = "completed", True
            db.add(Expense(trip_id=old.id, idempotency_key=uuid.uuid4(), amount_fen=16800, category="food", description="已经吃过的午饭", spent_at=datetime.now(UTC)))
            await db.commit()
            row = await get_or_create_session(db, old.id)
            await send_message(db, row.id, "参考这趟旅行明年再去一次", uuid.uuid4(), router=router)
            await confirm_action(db, row.id, row.pending_action["id"], True)
            assert row.trip_id != old.id
            assert old.start_date == old_start and activity.status == "completed"
            old_session = await get_or_create_session(db, old.id)
            assert old_session.id != row.id and old_session.pending_action is None
            assert old_session.messages[0]["user"] == "参考这趟旅行明年再去一次"
            assert "原旅行记录保留" in old_session.messages[-1]["assistant"]
            assert await db.scalar(select(func.count()).select_from(Expense).where(Expense.trip_id == row.trip_id)) == 0
            copied = list((await db.scalars(select(Activity).join(DayPlan).where(DayPlan.trip_id == row.trip_id))).all())
            assert copied and all(a.status == "planned" and not a.schedule_locked for a in copied)
    asyncio.run(run())


def test_confirmation_detects_activity_changes_even_without_trip_version_change():
    reset()
    async def run():
        router = Router(ToolDecision(tool="reschedule_trip", reply="准备改期", start_date=date(2027, 4, 1), end_date=date(2027, 4, 2)))
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            await send_message(db, row.id, "改期到明年四月", uuid.uuid4(), router=router)
            activity = await db.scalar(select(Activity).join(DayPlan).where(DayPlan.trip_id == DEMO_TRIP_ID))
            activity.duration_minutes += 15
            await db.commit()
            with pytest.raises(AssistantToolError, match="新修改"):
                await confirm_action(db, row.id, row.pending_action["id"], True)
    asyncio.run(run())


def test_shrinking_populated_days_requires_resolution_and_cancel_is_read_only():
    reset()
    async def run():
        router = Router(ToolDecision(tool="reschedule_trip", reply="准备改期", start_date=date(2027, 4, 1), end_date=date(2027, 4, 1)))
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            await send_message(db, row.id, "缩短为一天", uuid.uuid4(), router=router)
            assert row.pending_action is None
            assert "已有活动" in row.messages[-1]["assistant"]
            router.decision = router.decision.model_copy(update={"end_date": date(2027, 4, 2)})
            await send_message(db, row.id, "还是两天", uuid.uuid4(), router=router)
            await confirm_action(db, row.id, row.pending_action["id"], False)
            assert row.pending_action is None
            assert (await db.get(Trip, DEMO_TRIP_ID)).start_date.year == 2026
    asyncio.run(run())


def test_creation_failure_rolls_back_trip_and_keeps_confirmable_preview(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("queue unavailable")
    async def run():
        router = Router(ToolDecision(tool="create_trip", reply="准备创建", destination="成都", start_date=date(2027, 5, 1), end_date=date(2027, 5, 2), total_budget_fen=200000))
        async with session_factory() as db:
            row = await get_or_create_session(db, None)
            await send_message(db, row.id, "帮我规划五月去成都", uuid.uuid4(), router=router, city_search=cities)
            session_id, action_id = row.id, row.pending_action["id"]
            before = await db.scalar(select(func.count()).select_from(Trip))
        monkeypatch.setattr("app.assistant_service.create_planning_run", fail)
        with pytest.raises(RuntimeError, match="queue unavailable"):
            async with session_factory() as db:
                await confirm_action(db, session_id, action_id, True)
        async with session_factory() as db:
            row = await db.get(AssistantSession, session_id)
            assert row.trip_id is None and row.pending_action["id"] == action_id
            assert await db.scalar(select(func.count()).select_from(Trip)) == before
    asyncio.run(run())


def test_followup_passes_prior_answer_and_keeps_explicit_day_scope():
    reset()
    async def run():
        async with session_factory() as db:
            trip = await db.get(Trip, DEMO_TRIP_ID)
            db.add(PlanningRun(trip_id=trip.id, run_type="replan", status="answered", user_request="第二天怎样更轻松？", response_text="建议一：减少景点。建议二：第二天午后晚一小时出发，保留餐厅。", base_trip_version=trip.version))
            await db.commit()
            day = await db.scalar(select(DayPlan).where(DayPlan.trip_id == trip.id, DayPlan.position == 1))
            row = await get_or_create_session(db, trip.id)
            expanded = "请调整第二天的行程：午后晚一小时出发，保留餐厅，其他日期保持不变。"
            router = Router(ToolDecision(tool="plan_trip", reply="按第二个建议准备局部调整。", planning_request=expanded))
            await send_message(db, row.id, "按第二个建议，但保留餐厅", uuid.uuid4(), router=router, selected_day_id=day.id)
            assert "建议二" in str(router.contexts[0]["history"])
            assert router.contexts[0]["selected_day_id"] == str(day.id)
            run = await db.get(PlanningRun, row.latest_run_id)
            assert run.user_request == expanded and run.selected_day_id == day.id
            assert run.intent_resolution["policy_decision"]["route"] in {"plan_preview", "clarify"}
    asyncio.run(run())


def test_router_cannot_publish_competing_suggestions_and_followup_uses_actual_answer():
    reset()
    async def run():
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            router = Router(ToolDecision(tool="query_trip", reply="调度层自行编造的第二个建议", planning_request="目前行程怎么走？"))
            async def companion_answer(context, goal):
                from app.companion_contracts import CompanionDraft, SuggestionDraft
                return CompanionDraft(response_text="建议一保留原安排；建议二午后增加茶园。", suggestions=[
                    SuggestionDraft(suggestion_type="strategy", title="保留原安排", summary="保留现有内容。"),
                    SuggestionDraft(suggestion_type="experience", title="午后增加茶园", summary="作为候选兴趣讨论。")])
            await send_message(db, row.id, "目前行程怎么走？", uuid.uuid4(), router=router, companion_responder=companion_answer)
            assert "编造" not in row.messages[-1]["assistant"]
            assert row.messages[-1]["goal_routing"]["target_runtime"] == "companion"
            assert row.latest_run_id is None
            assert router.contexts == []
            router.decision = ToolDecision(
                tool="plan_trip", reply="按第二个建议准备调整。",
                planning_request="请调整第二天的行程：午后增加茶园，其他日期保持不变。",
            )
            await send_message(db, row.id, "按第二个建议，但保留餐厅", uuid.uuid4(), router=router)
            history = str(router.contexts[-1]["history"])
            assert "午后增加茶园" in history and "调度层自行编造" not in history
            assert router.contexts[-1]["history"][-1]["assistant"] == "建议一保留原安排；建议二午后增加茶园。"
            assert router.contexts[-1]["planning_brief"]["candidate_interests"][0]["display_name"] == "午后增加茶园"
            assert not router.contexts[-1]["planning_brief"]["must_do"]
    asyncio.run(run())


def test_reply_cannot_claim_a_nonexistent_candidate_is_ready():
    reset()
    async def run():
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            router = Router(ToolDecision(tool="reply", reply="候选方案已准备就绪，请点击确认按钮。"))
            with pytest.raises(AssistantToolError, match="状态核对"):
                await send_message(db, row.id, "请调整第二天", uuid.uuid4(), router=router)
            assert len(router.contexts) == 2 and "tool_validation_error" in router.contexts[1]
            assert not row.messages
    asyncio.run(run())


def test_pre_trip_reset_persists_empty_context_and_invalidates_old_preview():
    async def run():
        async with session_factory() as db:
            row = AssistantSession(messages=[{"id": str(uuid.uuid4()), "user": "旧城市", "assistant": "旧回复", "companion_result": {"suggestions": [{"id": "old-suggestion"}]}}],
                pending_action={"id": str(uuid.uuid4()), "tool": "create_trip"}, applied_actions={"old": "discarded"})
            db.add(row)
            await db.commit()
            old_id, old_action = row.id, row.pending_action["id"]
            before = await db.scalar(select(func.count()).select_from(Trip))
            fresh = await reset_pre_trip_session(db, old_id)
            assert fresh.id != old_id
            assert fresh.messages == [] and fresh.pending_action is None
            assert fresh.applied_actions == {} and fresh.latest_run_id is None and fresh.trip_id is None
            assert await db.get(AssistantSession, old_id) is None
            assert await db.scalar(select(func.count()).select_from(Trip)) == before
            with pytest.raises(AssistantToolError, match="对话不存在"):
                await confirm_action(db, old_id, old_action, True)
            fresh_id = fresh.id
            await db.rollback()
        async with session_factory() as db:
            restored = await get_or_create_session(db, None)
            assert restored.id == fresh_id and restored.messages == []
    asyncio.run(run())


def test_reset_refuses_saved_trip_history():
    reset()
    async def run():
        async with session_factory() as db:
            row = await get_or_create_session(db, DEMO_TRIP_ID)
            row.messages = [{"id": "saved", "user": "已保存的问题", "assistant": "已保存的回答"}]
            await db.commit()
            row_id = row.id
            with pytest.raises(AssistantToolError, match="已保存旅行"):
                await reset_pre_trip_session(db, row_id)
            await db.rollback()
            saved = await db.get(AssistantSession, row_id)
            assert len(saved.messages) == 1 and saved.trip_id == DEMO_TRIP_ID
    asyncio.run(run())
