import asyncio
import uuid
from datetime import date, datetime, timedelta, UTC
from fastapi.testclient import TestClient
from app.main import app
from app.database import AssistantSession, PlanningRun, session_factory
from app.assistant_service import ToolDecision, send_message
from app.travel_language import trip_duration, is_generic_place_quantity
from app.demo_seed import DEMO_TRIP_ID
from app.planning_progress import active_run, report_progress, pulse
from test_assistant_tools import Router, cities


def test_days_are_inclusive_and_calendar_dates_are_not_durations():
    assert trip_duration("三天两晚") == 3
    assert trip_duration("不是两天一晚，改成四天三晚") == 4
    assert trip_duration("第十二天去公园") is None
    assert trip_duration("2027年1月13日") is None
    assert trip_duration("三天两晚\n改成2027-01-01至2027-01-04") is None
    assert is_generic_place_quantity("再加1个景点")
    for phrase in ["1个景点", "2个景点", "一两个小景点", "每天2-3个景点", "两个景区"]:
        assert is_generic_place_quantity(phrase)
    for name in ["三坊七巷", "五一广场", "二郎山", "普达措国家公园"]:
        assert not is_generic_place_quantity(name)


def test_creation_corrects_model_nights_and_ignores_invented_daily_budget():
    async def scenario():
        async with session_factory() as db:
            row = AssistantSession(messages=[{"id": str(uuid.uuid4()), "user": "帮我创建成都三天两晚行程", "assistant": "哪天出发？"}], applied_actions={})
            db.add(row)
            await db.commit()
            router = Router(ToolDecision(tool="create_trip", reply="两天行程每天一千元", destination="成都",
                start_date=date(2027, 1, 1), end_date=date(2027, 1, 2), total_budget_fen=200000, daily_budget_fen=100000))
            result = await send_message(db, row.id, "1月1日出发，总预算两千元，每天2个景点", uuid.uuid4(), router=router, city_search=cities)
            assert result.pending_action["end_date"] == "2027-01-03"
            assert result.pending_action["daily_budget_fen"] == 66666
            assert "共 3 天" in result.messages[-1]["assistant"]
            assert "两天行程" not in result.messages[-1]["assistant"]
            await db.delete(row)
            await db.commit()
    asyncio.run(scenario())


def test_explicit_daily_budget_is_preserved():
    async def scenario():
        async with session_factory() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row)
            await db.commit()
            router = Router(ToolDecision(tool="create_trip", reply="核对", destination="成都",
                start_date=date(2027, 1, 1), end_date=date(2027, 1, 3), total_budget_fen=200000, daily_budget_fen=50000))
            result = await send_message(db, row.id, "帮我规划2027年1月1日去成都三天两晚，总预算2000元，每天预算500元", uuid.uuid4(), router=router, city_search=cities)
            assert result.pending_action["daily_budget_fen"] == 50000
            await db.delete(row)
            await db.commit()
    asyncio.run(scenario())


def test_quantity_request_changes_whole_trip_without_searching_for_numbered_places():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        for message in [
            "我希望每天可以再加一两个景点游玩，比如普达措国家公园比较大。就可以再加一个景点，无底湖观赏时间短，可以再加两个景点",
            "请调整：香格里拉3日行程（9.11-9.13），希望每天安排2-3个景点游览。9.11普达措国家公园空间大，可在此基础上增加1个景点；9.13无底湖观赏时间短，可在此基础上增加2个景点；其它日期也按每天2-3个景点合理补充。",
        ]:
            response = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve", json={"message": message, "selected_day_id": days[0]["id"]})
            assert response.status_code == 200
            result = response.json()
            assert not result["requires_clarification"], result
            assert result["grounded_intent"]["unresolved_place_mentions"] == []
            assert result["grounded_intent"]["target_day_ids"] == []
        named = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve", json={"message": "第一天增加不存在的真实景点"}).json()
        assert named["requires_clarification"]


def test_progress_milestones_are_persisted_and_heartbeat_does_not_fake_advancement():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        created = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={"run_type": "replan", "user_request": "请重新规划完整行程"}).json()
        async def scenario():
            run_id = uuid.UUID(created["id"])
            async with session_factory() as db:
                run = await db.get(PlanningRun, run_id)
                run.worker_id = "test-worker"
                run.worker_lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
                await db.commit()
            token = active_run.set(run_id)
            from app.planning_claim import PlanningClaim, active_claim
            claim_token = active_claim.set(PlanningClaim(run_id, DEMO_TRIP_ID, "test-worker"))
            try:
                await report_progress("research_model", "已取得8条资料，等待模型返回")
                await pulse(run_id)
            finally:
                active_run.reset(token)
                active_claim.reset(claim_token)
            async with session_factory() as db:
                run = await db.get(PlanningRun, run_id)
                assert run.progress["stage"] == "research_model"
                assert run.heartbeat_at is not None
                assert run.worker_lease_expires_at > datetime.now(UTC)
                run.status = "failed"
                await db.commit()
            token = active_run.set(run_id)
            try:
                await report_progress("planning", "不可覆盖已结束任务")
            finally:
                active_run.reset(token)
        asyncio.run(scenario())
        response = client.get(f"/api/v1/planning-runs/{created['id']}").json()
        assert response["progress"]["stage"] == "research_model"
        assert response["heartbeat_at"]


def test_missing_route_gets_one_model_correction_with_the_actual_segment():
    from unittest.mock import AsyncMock, patch
    from langgraph.checkpoint.memory import InMemorySaver
    from app.maps_service import MapProviderError
    from app.planning_graph import build_planning_graph
    from app.planning_graph_runtime import invoke_compiled_graph
    from app.schemas import CandidatePlanSnapshot
    from test_planning_graph import _create_trip_and_run, _get_run, EmptyDraftProvider
    with TestClient(app) as client:
        _, created = _create_trip_and_run(client, "请重新规划完整行程")
        error = MapProviderError("公园 → 古城没有公共交通路线", code="map_route_unavailable")
        error.route_details = {"from_place": "公园", "to_place": "古城", "mode": "transit"}
        async def scenario():
            provider = EmptyDraftProvider()
            provider.generate = AsyncMock(wraps=provider.generate)
            with patch("app.planning_graph.enrich_candidate_routes", AsyncMock(side_effect=[error, CandidatePlanSnapshot(activities=[])])):
                result = await invoke_compiled_graph(build_planning_graph(InMemorySaver(), provider), await _get_run(created["id"]))
            assert result.pending_interrupt["kind"] == "approval"
            assert provider.generate.await_count == 2
            correction = provider.generate.call_args_list[1].args[0]["validation_result"]["errors"][0]
            assert correction["code"] == "route_unavailable"
            assert correction["details"]["mode"] == "transit"
        asyncio.run(scenario())
