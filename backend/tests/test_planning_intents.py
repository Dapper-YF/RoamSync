import uuid

import pytest
from fastapi.testclient import TestClient

from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.planning_intent_service import classify_planning_intent


INTENT_CASES = [
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
        assert unknown.json()["requires_clarification"] is True
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
        assert payload["requires_clarification"] is False
        assert payload["request"]["target_day_id"] == days[1]["id"]
        assert payload["request"]["intent"]["requested_place_queries"] == ["滕王阁"]


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
