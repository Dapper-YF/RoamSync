import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.database import session_factory
from app.planning_intent_service import classify_planning_intent, resolve_planning_intent
from app.schemas import (
    PlanningIntentParseRequest,
    SemanticIntentDraft,
    SemanticIntentOperation,
)


INTENT_CASES = [
    ("请分析当前行程，说明每天的安排和这样游玩的理由。只回答，不要调整行程。", True, "unknown"),
    ("只分析当前安排，不要修改行程", True, "unknown"),
    ("解释安排的理由，然后请调整第一天的行程", True, "modify_day"),
    # Initial planning: the same generic planning phrases become create_plan
    # only when the trip has no formal activities.
    ("帮我规划南昌三天", False, "create_plan"),
    ("请帮我规划这次旅行", False, "create_plan"),
    ("帮我规划一个历史文化行程", False, "create_plan"),
    ("帮我规划适合亲子的路线", False, "create_plan"),
    ("生成行程", False, "create_plan"),
    ("生成行程并控制预算", False, "create_plan"),
    ("制定行程", False, "create_plan"),
    ("制定行程，节奏适中", False, "create_plan"),
    ("安排行程", False, "create_plan"),
    ("安排行程并多看博物馆", False, "create_plan"),
    ("做个行程", False, "create_plan"),
    ("做个行程，以地铁为主", False, "create_plan"),
    ("做一份行程", False, "create_plan"),
    ("规划行程", False, "create_plan"),
    ("从头规划这次旅行", False, "create_plan"),
    ("重新规划这次旅行", False, "create_plan"),
    # Existing formal activities turn full-trip planning into replan_trip.
    ("帮我规划南昌三天", True, "replan_trip"),
    ("请帮我规划这次旅行", True, "replan_trip"),
    ("生成行程", True, "replan_trip"),
    ("制定行程", True, "replan_trip"),
    ("安排行程", True, "replan_trip"),
    ("做个行程", True, "replan_trip"),
    ("做一份行程", True, "replan_trip"),
    ("规划行程", True, "replan_trip"),
    ("重新规划全部内容", True, "replan_trip"),
    ("重做整个旅行", True, "replan_trip"),
    ("重做全程安排", True, "replan_trip"),
    ("全部重排", True, "replan_trip"),
    ("整体重排一下", True, "replan_trip"),
    ("推倒重来", True, "replan_trip"),
    ("从头规划", True, "replan_trip"),
    ("重新规划，预算降低一些", True, "replan_trip"),
    # Local/day-scoped mutations.
    ("第二天下午别太满", True, "modify_day"),
    ("第一天调整一下", True, "modify_day"),
    ("首日太赶了", True, "modify_day"),
    ("2026-10-01 的活动修改一下", True, "modify_day"),
    ("10月1日调整安排", True, "modify_day"),
    ("把这个活动移到下午", True, "modify_day"),
    ("把博物馆移动到第二天", True, "modify_day"),
    ("删掉这个景点", True, "modify_day"),
    ("删除下午的活动", True, "modify_day"),
    ("把这个地方换掉", True, "modify_day"),
    ("替换上午的景点", True, "modify_day"),
    ("保留滕王阁", True, "modify_day"),
    ("滕王阁不要动", True, "modify_day"),
    ("晚上轻松一点", True, "modify_day"),
    ("下午放松一点", True, "modify_day"),
    ("这一天不要太赶", True, "modify_day"),
    ("第二天想去滕王阁", True, "modify_day"),
    ("第三天增加一个博物馆", True, "modify_day"),
    # Unsupported or conversational input stays unknown and must clarify.
    ("你好", True, "unknown"),
    ("谢谢", True, "unknown"),
    ("天气怎么样", True, "unknown"),
    ("南昌有什么好吃的", True, "unknown"),
    ("推荐一家酒店", True, "unknown"),
    ("预算是多少", True, "unknown"),
    ("为什么这样安排", True, "unknown"),
    ("给我解释一下", True, "unknown"),
    ("现在几点", True, "unknown"),
    ("帮我订票", True, "unknown"),
    ("预订酒店", True, "unknown"),
    ("查一下航班", True, "unknown"),
    ("记录这笔消费", True, "unknown"),
    ("分享给朋友", True, "unknown"),
    ("导出 PDF", True, "unknown"),
    ("随便看看", True, "unknown"),
    ("删除整个行程", True, "unknown"),
]


@pytest.mark.parametrize(("message", "has_activities", "expected"), INTENT_CASES)
def test_rules_v1_intent_fixture(
    message: str, has_activities: bool, expected: str
) -> None:
    assert (
        classify_planning_intent(message, has_activities=has_activities) == expected
    )


def test_unknown_language_uses_structured_semantic_provider_without_authority() -> None:
    class FakeSemanticProvider:
        async def extract(self, message: str, context: dict) -> SemanticIntentDraft:
            assert context["trip"]["destination"]
            return SemanticIntentDraft(
                primary_intent="general_chat",
                operations=[
                    SemanticIntentOperation(
                        operation="general_chat",
                        raw_text=message,
                    )
                ],
                confidence=0.94,
                parser="model",
                parser_version="fake-model-v1",
            )

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

    async def resolve() -> None:
        async with session_factory() as session:
            result = await resolve_planning_intent(
                session,
                DEMO_TRIP_ID,
                PlanningIntentParseRequest(message="陪我聊聊杭州"),
                semantic_provider=FakeSemanticProvider(),
            )
        assert result.semantic_draft is not None
        assert result.semantic_draft.parser == "model"
        assert result.policy_decision is not None
        assert result.policy_decision.route == "answer"
        assert result.policy_decision.operation_mode == "answer_only"

    asyncio.run(resolve())


def test_resolve_day_pace_and_protected_activity() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/demo/reset").status_code == 200
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        protected = days[0]["activities"][0]
        response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={
                "message": f"第一天下午别太满，保留{protected['display_name']}"
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["parser_version"] == "rules-v1"
        assert payload["requires_clarification"] is False
        assert payload["request"]["target_day_id"] == days[0]["id"]
        intent = payload["request"]["intent"]
        assert intent["intent_type"] == "modify_day"
        assert intent["time_scope"] == {
            "day_number": 1,
            "day_date": days[0]["date"],
            "period": "afternoon",
        }
        assert intent["requested_pace"] == "relaxed"
        assert intent["protected_activity_ids"] == [protected["id"]]


def test_selected_activity_resolves_pronoun_and_target_day() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        selected = days[1]["activities"][0]
        response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={
                "message": "这个活动不要动",
                "entry_point": "activity_editor",
                "selected_activity_id": selected["id"],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["requires_clarification"] is False
        assert payload["request"]["target_day_id"] == days[1]["id"]
        assert payload["request"]["intent"]["protected_activity_ids"] == [selected["id"]]


def test_unknown_and_out_of_range_requests_require_clarification() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        unknown = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "给我解释一下为什么这么安排"},
        )
        assert unknown.status_code == 200
        assert unknown.json()["requires_clarification"] is False
        assert unknown.json()["policy_decision"]["route"] == "answer"
        assert unknown.json()["request"]["intent"]["intent_type"] == "unknown"

        outside = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "调整第九天的安排"},
        )
        assert outside.status_code == 200
        payload = outside.json()
        assert payload["requires_clarification"] is True
        assert "day_outside_trip" in payload["request"]["intent"]["ambiguities"]
        assert "target_day" in payload["request"]["intent"]["missing_fields"]

        unresolved_activity = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "第二天保留不存在的博物馆"},
        )
        assert unresolved_activity.status_code == 200
        unresolved_intent = unresolved_activity.json()["request"]["intent"]
        assert any(
            value.startswith("activity_not_found:")
            for value in unresolved_intent["ambiguities"]
        )


def test_place_query_is_a_hint_not_a_persisted_place() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "第二天想去滕王阁"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["requires_clarification"] is True
        assert payload["request"]["target_day_id"] == days[1]["id"]
        assert payload["request"]["intent"]["requested_place_queries"] == ["滕王阁"]
        assert payload["grounded_intent"]["unresolved_place_mentions"] == ["滕王阁"]


def test_compound_request_produces_grounded_envelope_and_risk_decision() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        target = days[1]["activities"][1]
        candidates = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()
        replacement = next(item for item in candidates if item["name"] == "小河公园")
        response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={
                "message": (
                    f"把第二天下午的{target['display_name']}换成小河公园，"
                    "预算不要增加"
                )
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["requires_clarification"] is False
        assert payload["semantic_draft"]["primary_intent"] == "replace_activity"
        assert set(payload["grounded_intent"]["operation_types"]) == {
            "replace_activity",
            "adjust_budget",
        }
        assert payload["grounded_intent"]["target_day_ids"] == [days[1]["id"]]
        assert payload["grounded_intent"]["target_activity_ids"] == [target["id"]]
        assert payload["grounded_intent"]["candidate_place_ids"] == [replacement["id"]]
        assert payload["grounded_intent"]["constraints"]["budget_must_not_increase"] is True
        assert payload["policy_decision"] == {
            "operation_mode": "preview_change",
            "risk_level": "high",
            "requires_confirmation": True,
            "reasons": ["destructive_or_financial_change"],
            "route": "plan_preview",
        }


def test_multiple_places_and_protected_activities_are_resolved_separately() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "第二天下午保留灵隐和龙井，增加茶博和小河公园"},
        )
        assert response.status_code == 200
        intent = response.json()["request"]["intent"]
        assert len(intent["protected_activity_ids"]) == 2
        assert intent["requested_place_queries"] == ["茶博", "小河公园"]
        assert intent["time_scope"]["period"] == "afternoon"


def test_invalid_ui_context_is_rejected_without_guessing() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        response = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "调整这一天", "selected_day_id": str(uuid.uuid4())},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "selected_day_not_in_trip"
        invalid_activity = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={
                "message": "这个活动不要动",
                "selected_activity_id": str(uuid.uuid4()),
            },
        )
        assert invalid_activity.status_code == 422
        assert (
            invalid_activity.json()["detail"]["code"]
            == "selected_activity_not_in_trip"
        )
        missing_trip = client.post(
            f"/api/v1/trips/{uuid.uuid4()}/planning-intent/resolve",
            json={"message": "帮我规划行程"},
        )
        assert missing_trip.status_code == 404


def test_blank_message_and_extra_fields_are_rejected() -> None:
    with TestClient(app) as client:
        blank = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "   "},
        )
        assert blank.status_code == 422
        extra = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve",
            json={"message": "帮我规划行程", "allow_write": True},
        )
        assert extra.status_code == 422


def test_initial_plan_requires_a_real_destination() -> None:
    with TestClient(app) as client:
        trip = client.post(
            "/api/v1/trips",
            json={
                "title": "待补充目的地的旅行",
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "total_budget_fen": 100000,
                "daily_budget_fen": 50000,
            },
        )
        assert trip.status_code == 201
        response = client.post(
            f"/api/v1/trips/{trip.json()['id']}/planning-intent/resolve",
            json={"message": "帮我规划行程"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["request"]["intent"]["intent_type"] == "create_plan"
        assert payload["request"]["intent"]["missing_fields"] == ["destination"]
        assert payload["requires_clarification"] is True


def test_full_plan_is_not_limited_by_the_default_selected_day() -> None:
    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={
            "title": "Full scope check", "destination": "杭州",
            "start_date": "2026-11-01", "end_date": "2026-11-03",
            "total_budget_fen": 90000, "daily_budget_fen": 30000,
        }).json()
        days = client.get(f"/api/v1/trips/{trip['id']}/days").json()
        result = client.post(f"/api/v1/trips/{trip['id']}/planning-intent/resolve", json={
            "message": "生成三天完整行程，每天留足休息时间", "selected_day_id": days[0]["id"],
        }).json()
        assert result["request"]["intent"]["intent_type"] == "create_plan"
        assert result["request"]["target_day_id"] is None
        assert result["grounded_intent"]["target_day_ids"] == []
        ranged = client.post(f"/api/v1/trips/{trip['id']}/planning-intent/resolve", json={
            "message": "请为11月1日至11月3日生成三天完整行程", "selected_day_id": days[0]["id"],
        }).json()
        assert ranged["request"]["intent"]["intent_type"] == "create_plan"
        assert ranged["request"]["target_day_id"] is None
        local = client.post(f"/api/v1/trips/{trip['id']}/planning-intent/resolve", json={
            "message": "重新规划第二天", "selected_day_id": days[0]["id"],
        }).json()
        assert local["request"]["target_day_id"] == days[1]["id"]


def test_generic_route_preferences_are_not_resolved_as_activity_names() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        for preference in ["相邻地点", "邻近的景点", "足够休息时间", "交通时间"]:
            result = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve", json={
                "message": f"重新规划第一天，优先保留{preference}", "selected_day_id": days[0]["id"],
            }).json()
            assert not result["requires_clarification"], result
            assert not result["request"]["intent"]["protected_activity_ids"]
        missing = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve", json={
            "message": "第一天保留不存在的星月寺",
        }).json()
        assert missing["requires_clarification"]


@pytest.mark.parametrize("date_context", ["", "（2026-09-10 至 2026-09-12）", "（9月10日至9月12日）"])
def test_dali_landmark_request_covers_the_trip_and_keeps_explicit_local_targets(date_context):
    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={
            "title": "大理三天两晚", "destination": "大理",
            "start_date": "2026-09-10", "end_date": "2026-09-12",
            "total_budget_fen": 200000, "daily_budget_fen": 66666,
        }).json()
        days = client.get(f"/api/v1/trips/{trip['id']}/days").json()
        message = f"请调整大理三天两晚{date_context}的行程，确保包含苍洱大道、龙龛码头、最美S湾等著名景点。"
        result = client.post(f"/api/v1/trips/{trip['id']}/planning-intent/resolve", json={
            "message": message, "selected_day_id": days[0]["id"],
        }).json()
        assert not result["requires_clarification"], result
        assert result["request"]["target_day_id"] is None
        assert result["request"]["intent"]["intent_type"] == "create_plan"
        assert result["grounded_intent"]["target_day_ids"] == []
        for target in ["第二天", "2026-09-11"]:
            local = client.post(f"/api/v1/trips/{trip['id']}/planning-intent/resolve", json={
                "message": f"大理三天两晚{date_context}的行程，只调整{target}，其他天保持不变。",
                "selected_day_id": days[0]["id"],
            }).json()
            assert not local["requires_clarification"], local
            assert local["grounded_intent"]["target_day_ids"] == [days[1]["id"]]


@pytest.mark.parametrize("preserve", [
    "保留原有日期、目的地与预算不变",
    "保留原来的出发日期和返程日期、目的地、总预算",
    "原有日期不要动，目的地别动，每日预算不变",
    "保持已保存的总预算不变",
])
def test_trip_settings_are_constraints_not_missing_activities(preserve):
    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={
            "title": "大理三天两晚", "destination": "大理",
            "start_date": "2026-09-10", "end_date": "2026-09-12",
            "total_budget_fen": 200000, "daily_budget_fen": 66666,
        }).json()
        days = client.get(f"/api/v1/trips/{trip['id']}/days").json()
        message = f"请调整大理三天两晚（2026-09-10 至 2026-09-12）的行程，确保包含苍洱大道、龙龛码头、最美S湾等著名景点，{preserve}。"
        result = client.post(f"/api/v1/trips/{trip['id']}/planning-intent/resolve", json={
            "message": message, "selected_day_id": days[0]["id"],
        }).json()
        assert not result["requires_clarification"], result
        assert result["clarification_questions"] == []
        assert result["grounded_intent"]["target_day_ids"] == []
        assert result["grounded_intent"]["operation_types"] == ["create_plan"]
        assert not result["grounded_intent"]["constraints"]["budget_must_not_increase"]
        saved = client.get(f"/api/v1/trips/{trip['id']}").json()
        assert saved["total_budget_fen"] == 200000


def test_preserving_settings_does_not_hide_real_or_missing_activity_references():
    from datetime import date
    from app.planning_intent_service import _ActivityEntity, _resolve_protected_activities
    activity_id, day_id = uuid.uuid4(), uuid.uuid4()
    entities = [_ActivityEntity(activity_id, day_id, date(2026, 9, 10), ("大理古城",))]
    ambiguities = []
    kept = _resolve_protected_activities("保留原有日期、目的地、预算和大理古城不变", entities, None, ambiguities)
    assert kept == [activity_id] and ambiguities == []
    _resolve_protected_activities("保留不存在的星月寺和日期咖啡馆", entities, None, ambiguities)
    assert ambiguities == ["activity_not_found:不存在的星月寺", "activity_not_found:日期咖啡馆"]


def test_soft_preservation_is_a_goal_not_a_hard_protected_activity():
    from datetime import date
    from app.planning_intent_service import _ActivityEntity, _resolve_protected_activities

    activity_id, day_id = uuid.uuid4(), uuid.uuid4()
    entities = [_ActivityEntity(activity_id, day_id, date(2026, 10, 20), ("中国美术学院美术馆",))]
    assert _resolve_protected_activities(
        "尽量保留现有活动（中国美术学院美术馆）不做大改", entities, None, []
    ) == []
    assert _resolve_protected_activities(
        "保留中国美术学院美术馆", entities, None, []
    ) == [activity_id]


def test_generic_soft_preservation_clause_does_not_become_a_missing_activity():
    from datetime import date
    from app.planning_intent_service import _ActivityEntity, _resolve_protected_activities

    entities = [_ActivityEntity(uuid.uuid4(), uuid.uuid4(), date(2026, 10, 20), ("中国美术学院美术馆",))]
    ambiguities = []
    assert _resolve_protected_activities(
        "在当前正式行程基础上小幅微调，保留现有活动尽量不要大改", entities, None, ambiguities
    ) == []
    assert ambiguities == []
    assert _resolve_protected_activities(
        "可在保留原活动的基础上微调顺序、时长与交通衔接", entities, None, ambiguities
    ) == []
    assert ambiguities == []
    assert _resolve_protected_activities(
        "在保留主体的前提下优化顺序与交通衔接", entities, None, ambiguities
    ) == []
    assert ambiguities == []
    assert _resolve_protected_activities(
        "在保留主体框架的前提下仅做必要微调", entities, None, ambiguities
    ) == []
    assert ambiguities == []
    assert _resolve_protected_activities(
        "此前被拒绝的候选方案不作为参考，不继承其内容或保留要求", entities, None, ambiguities
    ) == []
    assert ambiguities == []
    _resolve_protected_activities("保留不存在的星月寺", entities, None, ambiguities)
    assert ambiguities == ["activity_not_found:不存在的星月寺"]


def test_enriching_the_trip_does_not_inherit_the_current_day_or_activity_scope() -> None:
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        result = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve", json={
            "message": "我希望这次旅行可以丰富一些", "selected_day_id": days[0]["id"],
            "selected_activity_id": days[0]["activities"][0]["id"],
        }).json()
        assert not result["requires_clarification"]
        assert result["grounded_intent"]["target_day_ids"] == []
        assert result["grounded_intent"]["target_activity_ids"] == []


@pytest.mark.parametrize("reference", ["餐厅", "原有两个用餐点", "原来的午餐和晚餐", "原有的午餐马旺子·川小馆和晚餐天府掌柜"])
def test_meal_group_references_preserve_actual_activities_only_in_the_requested_day(reference):
    from datetime import date, time
    from app.planning_intent_service import _ActivityEntity, _resolve_protected_activities
    first, second = uuid.uuid4(), uuid.uuid4()
    lunch, dinner, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entities = [
        _ActivityEntity(lunch, second, date(2027, 1, 2), ("马旺子·川小馆",), "food", time(11, 30)),
        _ActivityEntity(dinner, second, date(2027, 1, 2), ("天府掌柜",), "food", time(17)),
        _ActivityEntity(other, first, date(2027, 1, 1), ("第一天的餐厅",), "food", time(12)),
    ]
    ambiguities = []
    protected = _resolve_protected_activities(f"请调整第二天，保留{reference}", entities, None, ambiguities, target_day_id=second)
    assert set(protected) == {lunch, dinner} and not ambiguities
    assert _resolve_protected_activities("保留不存在的星月餐厅", entities, None, ambiguities, target_day_id=second) == []
    assert ambiguities


@pytest.mark.parametrize("message", ["请调整2026年9月6日的行程，第一天保持不变。", "保持2026年9月5日的行程不变，请调整第二天。"])
def test_unchanged_day_references_do_not_conflict_with_the_target_date(message):
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        result = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-intent/resolve", json={"message": message}).json()
        assert not result["requires_clarification"], result
        assert result["request"]["target_day_id"] == days[1]["id"]
        assert result["grounded_intent"]["target_day_ids"] == [days[1]["id"]]


def test_grounded_target_day_clears_resolved_relative_date_ambiguity():
    from app.planning_intent_service import _reconcile_grounded_ambiguities
    from app.schemas import GroundedIntent

    intent = GroundedIntent(
        trip_id=uuid.uuid4(), primary_intent="replan_trip", operation_types=["replan_trip"],
        target_day_ids=[uuid.uuid4()], ambiguities=["relative_date_reference_missing"],
    )
    reconciled = _reconcile_grounded_ambiguities(intent)
    assert reconciled.ambiguities == []


def test_unresolved_relative_date_ambiguity_survives_without_target_day():
    from app.planning_intent_service import _reconcile_grounded_ambiguities
    from app.schemas import GroundedIntent

    intent = GroundedIntent(
        trip_id=uuid.uuid4(), primary_intent="replan_trip", operation_types=["replan_trip"],
        ambiguities=["relative_date_reference_missing"],
    )
    assert _reconcile_grounded_ambiguities(intent).ambiguities == ["relative_date_reference_missing"]


def test_place_mention_prefers_unique_scoped_formal_activity_and_clarifies_ambiguity():
    from datetime import date
    from types import SimpleNamespace
    from app.planning_intent_service import _ActivityEntity, _ground_semantic_intent
    trip_id, day_id, activity_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entity=_ActivityEntity(id=activity_id,day_id=day_id,day_date=date(2026,10,20),category="culture",scheduled_time=None,aliases=("杭州大剧院演出","杭州大剧院"))
    draft=SemanticIntentDraft(primary_intent="add_activity",confidence=1,parser_version="test",operations=[SemanticIntentOperation(operation="add_activity",raw_text="加入杭州大剧院",place_mentions=["杭州大剧院"])])
    def ground(entities):
        return _ground_semantic_intent(draft,trip_id=trip_id,target_day=SimpleNamespace(id=day_id),selected_activity_id=None,protected_activity_ids=[],entities=entities,candidates=[],inherited_missing_fields=[],inherited_ambiguities=[])
    result=ground([entity])
    assert result.target_activity_ids==[activity_id]
    assert result.candidate_place_ids==[] and result.unresolved_place_mentions==[]
    assert "place_to_add" not in result.missing_fields
    duplicate=_ActivityEntity(id=uuid.uuid4(),day_id=day_id,day_date=date(2026,10,20),category="culture",scheduled_time=None,aliases=("杭州大剧院",))
    result=ground([entity,duplicate])
    assert "activity_not_unique:杭州大剧院" in result.ambiguities
    assert result.candidate_place_ids==[]
