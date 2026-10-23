import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.destination_research import research_destination, match_place
from app.external_facts import SearchFact, ExternalFactError
from app.planning_errors import PlannerProviderError
from app.planning_graph import _collect_external_facts
from app.planning_intent_service import classify_planning_intent
from app.schemas import PlaceSearchResultResponse


def research_session():
    from unittest.mock import Mock
    db = AsyncMock()
    db.in_transaction = Mock(return_value=False)
    db.scalar.return_value = 1  # Unit projection of Trip/preferences version.
    return db


def test_first_plan_searches_without_candidates_coordinates_or_weather():
    search = AsyncMock(return_value=SearchFact("tavily", "now", "query", {"results": [{"title": "大理旅游"}]}))
    with patch("app.planning_graph.get_settings", return_value=Settings(app_env="development", tavily_api_key="test")), patch("app.planning_graph.search_tavily", search), patch("app.planning_graph.fetch_open_meteo", AsyncMock()) as weather:
        result = asyncio.run(_collect_external_facts({"trip": {"version":1,"destination": "大理市"}, "candidates": []}, "规划行程"))
    assert result["search"]["status"] == "available"
    assert "代表性热门景点" in search.call_args.kwargs["query"]
    weather.assert_not_awaited()


def test_same_day_replan_can_skip_destination_search_but_still_fetch_weather():
    search = AsyncMock()
    weather = AsyncMock(return_value=SimpleNamespace(
        provider="open-meteo", queried_at="now", latitude=30.2, longitude=120.1,
        payload={"daily": {"temperature_2m_max": [22]}},
    ))
    context = {"trip": {"version":1,"destination": "杭州市", "center_latitude": 30.2, "center_longitude": 120.1,
        "start_date": "2026-10-20", "end_date": "2026-10-20", "timezone": "Asia/Shanghai"}, "candidates": []}
    with patch("app.planning_graph.get_settings", return_value=Settings(app_env="development", tavily_api_key="test")), \
         patch("app.planning_graph.search_tavily", search), patch("app.planning_graph.fetch_open_meteo", weather):
        result = asyncio.run(_collect_external_facts(context, "请调整今天的行程，尽量少走路", include_search=False))
    search.assert_not_awaited()
    weather.assert_awaited_once()
    assert result["search"]["status"] == "not_required"
    assert result["weather"]["status"] == "available"


def test_weather_failure_does_not_discard_search():
    search = AsyncMock(return_value=SearchFact("tavily", "now", "query", {"results": [{"title": "大理旅游"}]}))
    with patch("app.planning_graph.get_settings", return_value=Settings(app_env="development", tavily_api_key="test")), patch("app.planning_graph.search_tavily", search), patch("app.planning_graph.fetch_open_meteo", AsyncMock(side_effect=ExternalFactError("forecast unavailable"))):
        result = asyncio.run(_collect_external_facts({"trip": {"version":1,"destination": "大理市", "center_latitude": 25, "center_longitude": 100, "start_date": "2027-01-01", "end_date": "2027-01-03", "timezone": "Asia/Shanghai"}}, "规划行程"))
    assert result["search"]["status"] == "available"
    assert result["weather"]["status"] == "unavailable"
    assert result["status"] == "partial"


@pytest.mark.parametrize("focused_fails", [False, True])
def test_named_places_get_focused_sources_without_losing_broad_search(focused_fails):
    common = {"title": "大理旅游", "url": "https://example.com/common"}
    focus = {"title": "磻溪S彎", "url": "https://example.com/bend"}
    search = AsyncMock(side_effect=[SearchFact("tavily", "now", "broad", {"results": [common]}),
        ExternalFactError("unavailable") if focused_fails else SearchFact("tavily", "now", "focus", {"results": [focus, common]})])
    with patch("app.planning_graph.get_settings", return_value=Settings(app_env="development", tavily_api_key="test")), patch("app.planning_graph.search_tavily", search):
        result = asyncio.run(_collect_external_facts({"trip": {"version":1,"destination": "大理市"}, "candidates": []}, "希望包含龙龛码头、最美S湾"))
    assert search.await_count == 2
    assert "最美S湾" in search.call_args_list[1].kwargs["query"]
    assert "最美S湾" not in search.call_args_list[0].kwargs["query"]
    assert result["search"]["status"] == "available"
    assert result["search"]["payload"]["results"] == ([common] if focused_fails else [focus, common])
    if focused_fails:
        assert result["search"]["focused_search_status"] == "unavailable"


def test_multi_stop_trip_request_ignores_default_day_but_explicit_day_is_local():
    for has_plan in (False, True):
        assert classify_planning_intent("请调整行程，希望行程中可以看到苍洱大道、龙龛码头", has_activities=has_plan, has_selected_day=True) == ("replan_trip" if has_plan else "create_plan")
        assert classify_planning_intent("请调整第一天，加入龙龛码头", has_activities=has_plan, has_selected_day=True) == "modify_day"
    assert classify_planning_intent("调整一下", has_activities=False) == "modify_day"


def poi(name, identity="poi"):
    return PlaceSearchResultResponse(provider_place_id=identity, name=name, category="nature", longitude=100.1,
        latitude=25.7, suggested_duration_minutes=60, estimated_cost_fen=0, source_url="https://www.amap.com/search?id=" + identity)


def test_map_matching_does_not_pick_a_gate_or_random_first_result():
    assert match_place("龙龛码头", [poi("龙龛码头停车场"), poi("龙龛码头游客中心", "other")]) is None
    assert match_place("龍龕碼頭", [poi("其他公园"), poi("龙龛码头", "exact")]).provider_place_id == "exact"
    assert match_place("磻溪村S湾", [poi("磻溪S弯景点"), poi("S湾停车场", "parking")]).provider_place_id == "poi"
    assert match_place("独克宗古城", [poi("香格里拉市独克宗古城"), poi("香格里拉市独克宗古城-月光广场", "square"), poi("独克宗古城北门城楼", "gate")]).provider_place_id == "poi"
    assert match_place("松赞林寺", [poi("噶丹松赞林寺"), poi("松赞林寺(公交站)", "bus"), poi("噶丹松赞林寺-白塔", "tower")]).provider_place_id == "poi"
    assert match_place("古城", [poi("一号古城"), poi("二号古城", "other")]) is None
    assert match_place("梅里雪山", [poi("夜游梅里雪山")]) is None


@pytest.mark.parametrize("valid_evidence,declare_alias,extra_citation", [(True, True, False), (False, True, False), (True, False, False), (True, True, True)])
def test_requested_alias_requires_web_evidence_and_is_disclosed(valid_evidence, declare_alias, extra_citation):
    canonical = "磻溪村S弯"
    source = {"title": "最美S弯介绍", "url": "https://example.com/s-bend", "content": "最美S彎位於磻溪村S彎，適合沿湖遊覽。"}
    output = {"places": [{"name": canonical, "reason": "洱海湖岸弯道适合看风景和摄影，符合用户希望的湖边体验。", "prominence": "网页介绍的湖边游览地", "source_indices": [0]}],
              "requested_names": ["最美S湾"], "aliases": [{"requested_name": "最美S湾", "canonical_name": canonical, "source_indices": [0 if valid_evidence else 7]}]}
    if not declare_alias:
        output["aliases"] = []
    if extra_citation:
        output["aliases"][0]["source_indices"].extend([1, 7])
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(status="completed", output_text=json.dumps(output), usage=None))))
    async def search(name, city):
        return [poi("磻溪S弯景点")] if name == canonical else [poi("不相关餐馆")]
    async def scenario():
        with patch("app.destination_research.save_candidate_snapshot", AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))):
            return await research_destination(research_session(), uuid.uuid4(), context={"trip": {"version":1,"destination": "大理市"}, "days": [{"date": "2026-10-20", "activities": []}], "preferences": {"version": 1}},
                user_request="希望去最美S湾", external_facts={"search": {"payload": {"results": [source, {"title": "其他景点", "url": "https://example.com/other", "content": "大理古城"}]}}}, client=client, search=search)
    if valid_evidence:
        result = asyncio.run(scenario())
        place = next(iter(result["places"].values()))
        assert place["requested"] and "最美S湾" in place["reason"] and "磻溪村S弯" in place["reason"]
    else:
        with pytest.raises(PlannerProviderError, match="未唯一匹配"):
            asyncio.run(scenario())


def test_research_grounds_named_choices_and_rejects_fabricated_citations():
    output = {"places": [
        {"name": "龙龛码头", "reason": "这里能体验洱海湖岸风光，符合用户的摄影兴趣。", "prominence": "来源介绍了当地湖岸体验", "source_indices": [0, 7]},
        {"name": "随机公园", "reason": "这个地方据说很受欢迎，应当安排在第一天。", "prominence": "模型捏造的名气", "source_indices": [0]},
    ], "requested_names": ["龙龛码头"]}
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(status="completed", output_text=json.dumps(output), usage=SimpleNamespace(total_tokens=10)))))
    source = {"title": "龙龛码头旅行", "url": "https://example.com/guide", "content": "龙龛码头可以欣赏湖岸风光。"}
    facts = {"search": {"payload": {"results": [source]}, "queried_at": "now"}}
    search = AsyncMock(return_value=[poi("随机公园"), poi("龙龛码头", "requested")])
    db, saved_id = research_session(), uuid.uuid4()
    with patch("app.destination_research.save_candidate_snapshot", AsyncMock(return_value=SimpleNamespace(id=saved_id))) as save:
        result = asyncio.run(research_destination(db, uuid.uuid4(), context={"trip": {"version":1,"destination": "大理市"}, "days": [{"date": "2026-10-20", "activities": []}, {"date": "2026-10-21", "activities": []}], "preferences": {"version": 1}}, user_request="我想去龙龛码头", external_facts=facts, client=client, search=search))
    search.assert_awaited_once_with("龙龛码头", "大理市")
    assert save.call_args.args[2].provider_place_id == "requested"
    assert result["places"][str(saved_id)]["requested"] is True
    assert result["places"][str(saved_id)]["sources"][0]["url"] == source["url"]
    assert len(result["places"][str(saved_id)]["sources"]) == 1


def test_descriptive_alias_does_not_choose_between_two_sourced_places():
    names = ["磻溪S弯", "另一村S弯"]
    output = {"places": [{"name": name, "reason": "网页介绍的湖岸弯道，符合用户的摄影兴趣。", "prominence": "本地湖岸体验", "source_indices": [0]} for name in names],
              "requested_names": ["最美S湾"], "aliases": []}
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(status="completed", output_text=json.dumps(output), usage=None))))
    source = {"title": "两处S弯", "url": "https://example.com/bends", "content": "、".join(names)}
    search = AsyncMock(return_value=[])
    with patch("app.destination_research.asyncio.sleep", AsyncMock()), patch("app.destination_research.save_candidate_snapshot", AsyncMock()) as save:
        with pytest.raises(PlannerProviderError, match="未唯一匹配"):
            asyncio.run(research_destination(research_session(), uuid.uuid4(), context={"trip": {"version":1,"destination": "大理市"}, "days": [{"date": "2026-10-20", "activities": []}], "preferences": {"version": 1}},
                user_request="想去最美S湾", external_facts={"search": {"payload": {"results": [source]}}}, client=client, search=search))
    assert search.call_args_list[0].args[0] == "最美S湾"
    save.assert_not_awaited()


def test_no_web_evidence_fails_without_random_map_fallback():
    search = AsyncMock()
    with pytest.raises(PlannerProviderError, match="网页检索"):
        asyncio.run(research_destination(research_session(), uuid.uuid4(), context={}, user_request="规划行程", external_facts={}, search=search))
    search.assert_not_awaited()


def test_current_research_excludes_old_candidates_and_requires_requested_stop():
    from test_openai_planner import _state, _settings, FakeClient
    from app.openai_planner import build_planner_input, OpenAIResponsesPlanner
    state, candidate_id, _ = _state()
    state["planning_context"]["destination_research"] = {"places": {candidate_id: {"name": "指定地点", "requested": True}}}
    old = {**state["planning_context"]["candidates"][0], "id": str(uuid.uuid4()), "rating": 5}
    state["planning_context"]["candidates"].append(old)
    prompt, allowed, _ = build_planner_input(state, max_candidates=1)
    assert uuid.UUID(candidate_id) in allowed and uuid.UUID(old["id"]) not in allowed
    assert prompt["destination_research"]["places"][candidate_id]["requested"]
    client = FakeClient({"activities": []})
    from app.planning_errors import PlannerConstraintsUnsatisfiedError
    with pytest.raises(PlannerConstraintsUnsatisfiedError, match="requested_places_missing"):
        asyncio.run(OpenAIResponsesPlanner(_settings(), client=client).generate(state))
    assert "未安排用户指定地点" in json.loads(client.responses.request["input"])["output_error"]


def test_rejection_clears_approval_and_next_request_uses_empty_formal_plan():
    from fastapi.testclient import TestClient
    from langgraph.checkpoint.memory import InMemorySaver
    from app.main import app
    from app.database import session_factory, PlanningRun
    from app.planning_graph import build_planning_graph
    from app.planning_graph_runtime import invoke_compiled_graph
    from app.planning_run_repository import reject_revision
    from app.assistant_service import get_or_create_session, send_message, ToolDecision
    from test_planning_graph import _create_trip_and_run, _get_run, EmptyDraftProvider
    from test_assistant_tools import Router

    with TestClient(app) as client:
        trip, created = _create_trip_and_run(client, "请重新规划完整行程")
        async def scenario():
            graph = build_planning_graph(InMemorySaver(), EmptyDraftProvider())
            result = await invoke_compiled_graph(graph, await _get_run(created["id"]))
            async with session_factory() as db:
                old = await db.get(PlanningRun, uuid.UUID(created["id"]))
                old.pending_interrupt = result.pending_interrupt
                old.response_text = "沿用旧候选只修改第一天"
                row = await get_or_create_session(db, uuid.UUID(trip["id"]))
                row.messages = [{"id": str(uuid.uuid4()), "user": "规划", "assistant": old.response_text, "run_id": str(old.id)}]
                await db.commit()
                await reject_revision(db, uuid.UUID(result.pending_interrupt["revision_id"]))
                assert old.pending_interrupt is None
                router = Router(ToolDecision(tool="plan_trip", reply="重新规划", planning_request="请重新规划完整行程，希望包含龙龛码头"))
                await send_message(db, row.id, "希望行程中包含龙龛码头", uuid.uuid4(), router=router)
                assert all(not d["activities"] for d in router.contexts[0]["current_plan"])
                assert "沿用旧候选" not in json.dumps(router.contexts[0], ensure_ascii=False)
                new = await db.get(PlanningRun, row.latest_run_id)
                assert new.id != old.id and new.run_type == "initial_plan"
                assert not new.intent_resolution["grounded_intent"]["target_day_ids"]
        asyncio.run(scenario())


def test_existing_formal_place_is_grounded_before_map_research():
    activity_id, place_id = str(uuid.uuid4()), str(uuid.uuid4())
    output = {"places": [{"name":"杭州大剧院", "reason":"用户希望保留既有演出体验，并留出充分停留时间。", "prominence":"来源提到的文化场馆", "source_indices":[0]}], "requested_names":["杭州大剧院"]}
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(status="completed",output_text=json.dumps(output),usage=None))))
    source = {"title":"杭州大剧院", "content":"杭州大剧院的文化活动", "url":"https://example.com/theater"}
    search=AsyncMock()
    db=research_session()
    context={"preferences": {"version": 1}, "trip":{"version":1,"destination":"杭州"}, "days":[{"id":"day-1", "date":"2026-10-20", "activities":[{"id":activity_id,"place_id":place_id,"display_name":"杭州大剧院演出"}]}],"candidates":[{"id":place_id,"name":"杭州大剧院"}],"research_target_day_ids":["day-1"]}
    with patch("app.destination_research.save_candidate_snapshot",AsyncMock()) as save:
        result=asyncio.run(research_destination(db,uuid.uuid4(),context=context,user_request="请保留杭州大剧院",external_facts={"search":{"payload":{"results":[source]}}},client=client,search=search))
    assert result["places"][place_id]["existing_activity_id"]==activity_id
    search.assert_not_called()
    save.assert_not_called()
