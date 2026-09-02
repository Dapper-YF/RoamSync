import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.demo_seed import DEMO_TRIP_ID
from app.main import app


def _reset(client: TestClient) -> list[dict]:
    reset = client.post("/api/v1/demo/reset")
    assert reset.status_code == 200
    assert reset.json()["trip_id"] == str(DEMO_TRIP_ID)
    days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days")
    assert days.status_code == 200
    return days.json()


def test_persisted_planner_crud_order_and_budget() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        assert len(days) == 2
        assert [len(day["activities"]) for day in days] == [3, 2]

        candidates = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates")
        assert candidates.status_code == 200
        leifeng = next(item for item in candidates.json() if item["name"] == "雷峰塔")

        created = client.post(
            f"/api/v1/day-plans/{days[0]['id']}/activities",
            json={"place_id": leifeng["id"]},
        )
        assert created.status_code == 201
        assert created.json()["name"] == "雷峰塔"
        assert created.json()["position"] == 3

        duplicate = client.post(
            f"/api/v1/day-plans/{days[1]['id']}/activities",
            json={"place_id": leifeng["id"]},
        )
        assert duplicate.status_code == 409

        updated_days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        activity_ids = [item["id"] for item in updated_days[0]["activities"]]
        reordered = client.put(
            f"/api/v1/day-plans/{days[0]['id']}/activity-order",
            json={"activity_ids": list(reversed(activity_ids))},
        )
        assert reordered.status_code == 200
        assert [item["id"] for item in reordered.json()["activities"]] == list(
            reversed(activity_ids)
        )

        budget = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-budget")
        assert budget.status_code == 200
        assert budget.json()["total_planned_fen"] == 22_500
        assert budget.json()["days"][0]["planned_fen"] == 12_000

        removed = client.delete(f"/api/v1/activities/{created.json()['id']}")
        assert removed.status_code == 204
        candidates_after_delete = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/candidates"
        ).json()
        assert any(item["id"] == leifeng["id"] for item in candidates_after_delete)


def test_planner_validation_and_not_found_responses() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        activity_ids = [item["id"] for item in days[0]["activities"]]

        missing = client.put(
            f"/api/v1/day-plans/{days[0]['id']}/activity-order",
            json={"activity_ids": activity_ids[:-1]},
        )
        assert missing.status_code == 422

        duplicate = client.put(
            f"/api/v1/day-plans/{days[0]['id']}/activity-order",
            json={"activity_ids": [activity_ids[0]] * len(activity_ids)},
        )
        assert duplicate.status_code == 422

        cross_day = client.put(
            f"/api/v1/day-plans/{days[0]['id']}/activity-order",
            json={"activity_ids": activity_ids[:-1] + [days[1]["activities"][0]["id"]]},
        )
        assert cross_day.status_code == 422

        unknown = uuid.uuid4()
        assert client.get(f"/api/v1/trips/{unknown}/days").status_code == 404
        assert client.delete(f"/api/v1/activities/{unknown}").status_code == 404


def test_demo_reset_restores_only_demo_state() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        removed_id = days[0]["activities"][0]["id"]
        assert client.delete(f"/api/v1/activities/{removed_id}").status_code == 204
        assert len(client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]["activities"]) == 2

        restored = _reset(client)
        assert len(restored[0]["activities"]) == 3


def test_place_search_route_modes_and_schedule_recalculation() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        first_day = days[0]
        assert len(first_day["route_legs"]) == 2
        assert all(leg["is_estimated"] for leg in first_day["route_legs"])

        recalculated = client.post(
            f"/api/v1/day-plans/{first_day['id']}/route",
            json={"mode": "driving"},
        )
        assert recalculated.status_code == 200
        payload = recalculated.json()
        assert len(payload["route_legs"]) == 2
        assert all(leg["mode"] == "driving" for leg in payload["route_legs"])
        assert all(leg["provider"] == "RoamSync Estimate" for leg in payload["route_legs"])
        assert [item["scheduled_time"] for item in payload["activities"]] == sorted(
            item["scheduled_time"] for item in payload["activities"]
        )


def test_amap_poi_search_is_transient_until_activity_confirmation(monkeypatch) -> None:
    import app.maps_service as maps_service

    monkeypatch.setattr(
        maps_service,
        "get_settings",
        lambda: SimpleNamespace(
            amap_rest_key="test-key",
            route_cache_ttl_seconds=60,
            allow_map_estimates=True,
        ),
    )
    monkeypatch.setattr(
        maps_service,
        "_get_json",
        lambda _: {
            "status": "1",
            "pois": [
                {
                    "id": "B_TEST_MUSEUM",
                    "name": "杭州博物馆",
                    "location": "120.169000,30.240000",
                    "type": "科教文化服务;博物馆",
                    "address": "粮道山 18 号",
                    "adname": "上城区",
                    "biz_ext": {"rating": "4.7"},
                    "photos": [],
                }
            ],
        },
    )
    with TestClient(app) as client:
        days = _reset(client)
        candidates_before = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/candidates"
        ).json()
        response = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/places/search",
            params={"q": "杭州博物馆"},
        )
        assert response.status_code == 200
        result = response.json()[0]
        assert result["name"] == "杭州博物馆"
        assert result["provider_place_id"] == "B_TEST_MUSEUM"
        assert result["provider"] == "amap"
        assert client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/candidates"
        ).json() == candidates_before

        created = client.post(
            f"/api/v1/day-plans/{days[0]['id']}/activities",
            json={"place_snapshot": result},
        )
        assert created.status_code == 201
        assert created.json()["name"] == "杭州博物馆"

        duplicate = client.post(
            f"/api/v1/day-plans/{days[1]['id']}/activities",
            json={"place_snapshot": result},
        )
        assert duplicate.status_code == 409

        assert client.delete(f"/api/v1/activities/{created.json()['id']}").status_code == 204
        candidates = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()
        assert any(item["name"] == "杭州博物馆" for item in candidates)


def test_map_quota_error_has_stable_machine_code(monkeypatch) -> None:
    import app.maps_service as maps_service

    monkeypatch.setattr(
        maps_service,
        "get_settings",
        lambda: SimpleNamespace(
            amap_rest_key="test-key",
            route_cache_ttl_seconds=60,
            allow_map_estimates=False,
        ),
    )
    monkeypatch.setattr(
        maps_service,
        "_get_json",
        lambda _: {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10044"},
    )
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/places/search",
            params={"q": "博物馆"},
        )
        assert response.status_code == 429
        assert response.json()["detail"] == {
            "code": "map_quota_exceeded",
            "message": "高德免费配额或并发额度已用尽，请稍后重试或检查控制台配额",
            "provider": "amap",
            "provider_code": "10044",
        }


def test_amap_route_parser_selects_shortest_path_and_keeps_alternatives(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import app.maps_service as maps_service

    monkeypatch.setattr(
        maps_service,
        "get_settings",
        lambda: SimpleNamespace(amap_rest_key="test-key"),
    )
    monkeypatch.setattr(
        maps_service,
        "_get_json",
        lambda url: {
            "status": "1",
            "route": {
                "paths": [
                    {
                        "distance": "1900",
                        "cost": {"duration": "900"},
                        "steps": [{"polyline": "120.1,30.1;120.2,30.2"}],
                    },
                    {
                        "distance": "1200",
                        "cost": {"duration": "720"},
                        "steps": [
                            {"polyline": "120.1,30.1;120.15,30.12"},
                            {"polyline": "120.15,30.12;120.2,30.2"},
                        ],
                    },
                ]
            },
        },
    )
    origin = SimpleNamespace(longitude=120.1, latitude=30.1)
    destination = SimpleNamespace(longitude=120.2, latitude=30.2)

    result = asyncio.run(
        maps_service._fetch_amap_route(origin, destination, "walk", "0571")
    )

    assert result[0:2] == (1200, 12)
    assert result[4] == [[120.1, 30.1], [120.15, 30.12], [120.2, 30.2]]
    assert result[5][0]["distance_meters"] == 1900


def test_amap_route_parser_collects_nested_transit_geometry() -> None:
    from app.maps_service import _parse_route_path

    parsed = _parse_route_path(
        {
            "distance": "3200",
            "cost": {"duration": "1080"},
            "segments": [
                {"walking": {"steps": [{"polyline": "120.1,30.1;120.11,30.11"}]}},
                {"bus": {"buslines": [{"polyline": "120.11,30.11;120.2,30.2"}]}},
            ],
        },
        {},
    )

    assert parsed == (
        3200,
        18,
        [[120.1, 30.1], [120.11, 30.11], [120.2, 30.2]],
    )


def test_activity_create_requires_one_place_source() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        response = client.post(
            f"/api/v1/day-plans/{days[0]['id']}/activities",
            json={},
        )
        assert response.status_code == 422


def test_activity_editing_versioning_and_budget_recalculation() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        activity = days[0]["activities"][0]
        initial_budget = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-budget"
        ).json()

        updated = client.put(
            f"/api/v1/activities/{activity['id']}",
            json={
                "version": activity["version"],
                "custom_name": "  西湖晨间散步  ",
                "scheduled_time": "10:15",
                "duration_minutes": 150,
                "estimated_cost_fen": 12_345,
                "status": "planned",
                "note": "  从北山街入口进入  ",
                "schedule_locked": True,
            },
        )
        assert updated.status_code == 200
        payload = updated.json()
        assert payload["name"] == "西湖·断桥"
        assert payload["custom_name"] == "西湖晨间散步"
        assert payload["display_name"] == "西湖晨间散步"
        assert payload["scheduled_time"] == "10:15:00"
        assert payload["duration_minutes"] == 150
        assert payload["estimated_cost_fen"] == 12_345
        assert payload["note"] == "从北山街入口进入"
        assert payload["schedule_locked"] is True
        assert payload["version"] == activity["version"] + 1
        assert payload["updated_at"]

        refreshed_days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        assert refreshed_days[0]["activities"][0]["display_name"] == "西湖晨间散步"
        assert refreshed_days[0]["activities"][0]["scheduled_time"] == "10:15:00"
        budget = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-budget"
        ).json()
        assert budget["total_planned_fen"] == (
            initial_budget["total_planned_fen"]
            - activity["estimated_cost_fen"]
            + 12_345
        )

        stale = client.put(
            f"/api/v1/activities/{activity['id']}",
            json={"version": activity["version"], "note": "stale update"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "activity_version_conflict"

        skipped = client.put(
            f"/api/v1/activities/{activity['id']}",
            json={"version": payload["version"], "status": "skipped"},
        )
        assert skipped.status_code == 200
        skipped_budget = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-budget"
        ).json()
        assert skipped_budget["total_planned_fen"] == budget["total_planned_fen"] - 12_345


def test_activity_editing_validation_and_not_found() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        activity = days[0]["activities"][0]
        invalid_duration = client.put(
            f"/api/v1/activities/{activity['id']}",
            json={"version": activity["version"], "duration_minutes": 4},
        )
        assert invalid_duration.status_code == 422
        no_edit = client.put(
            f"/api/v1/activities/{activity['id']}",
            json={"version": activity["version"]},
        )
        assert no_edit.status_code == 422
        unknown = client.put(
            f"/api/v1/activities/{uuid.uuid4()}",
            json={"version": 1, "note": "missing"},
        )
        assert unknown.status_code == 404


def test_activity_moves_between_days_and_reorders_transactionally() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        source = days[0]
        target = days[1]
        activity = source["activities"][0]
        budget_before = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-budget"
        ).json()["total_planned_fen"]

        moved = client.post(
            f"/api/v1/activities/{activity['id']}/move",
            json={
                "version": activity["version"],
                "target_day_plan_id": target["id"],
                "target_position": 1,
            },
        )
        assert moved.status_code == 200
        payload = moved.json()
        assert payload["activity_id"] == activity["id"]
        assert activity["id"] not in [item["id"] for item in payload["source_day"]["activities"]]
        assert payload["target_day"]["activities"][1]["id"] == activity["id"]
        assert payload["target_day"]["activities"][1]["version"] == activity["version"] + 1
        assert len(payload["source_day"]["route_legs"]) == len(payload["source_day"]["activities"]) - 1
        assert len(payload["target_day"]["route_legs"]) == len(payload["target_day"]["activities"]) - 1
        assert client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-budget"
        ).json()["total_planned_fen"] == budget_before

        stale = client.post(
            f"/api/v1/activities/{activity['id']}/move",
            json={
                "version": activity["version"],
                "target_day_plan_id": source["id"],
                "target_position": 0,
            },
        )
        assert stale.status_code == 409

        refreshed = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        moved_activity = next(
            item for item in refreshed[1]["activities"] if item["id"] == activity["id"]
        )
        reordered = client.post(
            f"/api/v1/activities/{activity['id']}/move",
            json={
                "version": moved_activity["version"],
                "target_day_plan_id": target["id"],
                "target_position": 0,
            },
        )
        assert reordered.status_code == 200
        assert reordered.json()["target_day"]["activities"][0]["id"] == activity["id"]


def test_activity_move_rejects_cross_trip_and_invalid_position() -> None:
    with TestClient(app) as client:
        days = _reset(client)
        other = client.post(
            "/api/v1/trips",
            json={
                "title": "Other trip",
                "destination": "南昌市",
                "start_date": "2030-09-01",
                "end_date": "2030-09-01",
                "total_budget_fen": 100_000,
                "daily_budget_fen": 100_000,
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
            },
        )
        assert other.status_code == 201
        other_days = client.get(f"/api/v1/trips/{other.json()['id']}/days").json()
        activity = days[0]["activities"][0]
        cross_trip = client.post(
            f"/api/v1/activities/{activity['id']}/move",
            json={"version": activity["version"], "target_day_plan_id": other_days[0]["id"], "target_position": 0},
        )
        assert cross_trip.status_code == 422
        invalid_position = client.post(
            f"/api/v1/activities/{activity['id']}/move",
            json={"version": activity["version"], "target_day_plan_id": days[1]["id"], "target_position": 99},
        )
        assert invalid_position.status_code == 422
        assert client.delete(f"/api/v1/trips/{other.json()['id']}?confirm=true").status_code == 204


def test_activity_move_rolls_back_when_route_recalculation_fails(monkeypatch) -> None:
    import app.planner_repository as planner_repository
    from app.maps_service import MapProviderError

    async def fail_route(*_args, **_kwargs):
        raise MapProviderError("route failure")

    with TestClient(app) as client:
        days = _reset(client)
        activity = days[0]["activities"][0]
        monkeypatch.setattr(planner_repository, "recalculate_day_route", fail_route)
        response = client.post(
            f"/api/v1/activities/{activity['id']}/move",
            json={"version": activity["version"], "target_day_plan_id": days[1]["id"], "target_position": 0},
        )
        assert response.status_code == 503
        refreshed = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        assert refreshed[0]["activities"][0]["id"] == activity["id"]
