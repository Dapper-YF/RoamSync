import uuid
from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app


def _create_trip(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/trips",
        json={
            "title": f"Hangzhou budget trip {uuid.uuid4()}",
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
            "total_budget_fen": 80000,
            "daily_budget_fen": 50000,
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_trip_expense_budget_and_idempotency() -> None:
    with TestClient(app) as client:
        trip = _create_trip(client)
        trip_id = trip["id"]

        fetched = client.get(f"/api/v1/trips/{trip_id}")
        assert fetched.status_code == 200
        assert fetched.json()["total_budget_fen"] == 80000

        idempotency_key = str(uuid.uuid4())
        expense_payload = {
            "idempotency_key": idempotency_key,
            "amount_fen": 4800,
            "category": "food",
            "description": "Lunch",
        }
        created = client.post(
            f"/api/v1/trips/{trip_id}/expenses", json=expense_payload
        )
        assert created.status_code == 201
        assert created.json()["duplicate"] is False

        replayed = client.post(
            f"/api/v1/trips/{trip_id}/expenses", json=expense_payload
        )
        assert replayed.status_code == 200
        assert replayed.json()["duplicate"] is True
        assert replayed.json()["id"] == created.json()["id"]

        budget = client.get(f"/api/v1/trips/{trip_id}/budget")
        assert budget.status_code == 200
        assert budget.json()["total_spent_fen"] == 4800
        assert budget.json()["total_remaining_fen"] == 75200
        assert budget.json()["today_spent_fen"] == 4800
        assert budget.json()["today_remaining_fen"] == 45200

        conflicting_payload = expense_payload | {"amount_fen": 4900}
        conflict = client.post(
            f"/api/v1/trips/{trip_id}/expenses", json=conflicting_payload
        )
        assert conflict.status_code == 409


def test_missing_trip_and_trip_validation() -> None:
    with TestClient(app) as client:
        assert client.get(f"/api/v1/trips/{uuid.uuid4()}").status_code == 404

        invalid = client.post(
            "/api/v1/trips",
            json={
                "title": "Invalid budget",
                "start_date": "2026-09-01",
                "end_date": "2026-08-31",
                "total_budget_fen": 10000,
                "daily_budget_fen": 20000,
            },
        )
        assert invalid.status_code == 422


def test_multi_city_trip_creates_days_and_appears_in_directory() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/trips",
            json={
                "title": "南昌周末之旅",
                "destination": "南昌市",
                "destination_adcode": "360100",
                "destination_citycode": "0791",
                "center_longitude": 115.857972,
                "center_latitude": 28.682976,
                "start_date": "2026-10-01",
                "end_date": "2026-10-03",
                "total_budget_fen": 300000,
                "daily_budget_fen": 100000,
            },
        )
        assert response.status_code == 201
        trip = response.json()
        assert trip["destination_adcode"] == "360100"
        assert trip["center_longitude"] == 115.857972
        days = client.get(f"/api/v1/trips/{trip['id']}/days").json()
        assert len(days) == 3
        assert [day["label"] for day in days] == ["第 1 天", "第 2 天", "第 3 天"]
        assert any(item["id"] == trip["id"] for item in client.get("/api/v1/trips").json())


def test_city_search_maps_amap_district_response(monkeypatch) -> None:
    import app.maps_service as maps_service

    monkeypatch.setattr(
        maps_service,
        "get_settings",
        lambda: SimpleNamespace(amap_rest_key="test-key"),
    )
    monkeypatch.setattr(
        maps_service,
        "_get_json",
        lambda _: {
            "status": "1",
            "districts": [
                {
                    "name": "南昌市",
                    "adcode": "360100",
                    "citycode": "0791",
                    "center": "115.857972,28.682976",
                }
            ],
        },
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/locations/cities", params={"keyword": "南昌"})
        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "南昌市",
                "adcode": "360100",
                "citycode": "0791",
                "longitude": 115.857972,
                "latitude": 28.682976,
            }
        ]


def test_trip_update_duplicate_archive_and_safe_delete() -> None:
    with TestClient(app) as client:
        trip = _create_trip(client)
        trip_id = trip["id"]
        updated = client.put(
            f"/api/v1/trips/{trip_id}",
            json={
                "version": trip["version"],
                "title": "Updated trip",
                "end_date": "2030-09-03",
                "start_date": "2030-09-01",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == trip["version"] + 1
        assert len(client.get(f"/api/v1/trips/{trip_id}/days").json()) == 3
        stale = client.put(
            f"/api/v1/trips/{trip_id}",
            json={"version": trip["version"], "title": "Stale"},
        )
        assert stale.status_code == 409

        duplicated = client.post(f"/api/v1/trips/{trip_id}/duplicate")
        assert duplicated.status_code == 201
        duplicate_id = duplicated.json()["id"]
        assert duplicated.json()["title"].endswith("（副本）")

        archived = client.post(f"/api/v1/trips/{trip_id}/archive")
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"

        preview = client.get(f"/api/v1/trips/{duplicate_id}/deletion-preview")
        assert preview.status_code == 200
        assert preview.json()["day_plans"] == 3
        assert client.delete(f"/api/v1/trips/{duplicate_id}").status_code == 400
        assert client.delete(f"/api/v1/trips/{duplicate_id}?confirm=true").status_code == 204
        assert client.get(f"/api/v1/trips/{duplicate_id}").status_code == 404


def test_accommodation_search_maps_amap_pois(monkeypatch) -> None:
    import app.maps_service as maps_service

    monkeypatch.setattr(maps_service, "get_settings", lambda: SimpleNamespace(amap_rest_key="test-key"))
    monkeypatch.setattr(
        maps_service,
        "_get_json",
        lambda _: {
            "status": "1",
            "pois": [{
                "id": "B_NANCHANG_HOTEL",
                "name": "南昌中心酒店",
                "address": "红谷滩新区测试路 1 号",
                "adname": "红谷滩区",
                "location": "115.858000,28.683000",
                "type": "住宿服务;宾馆酒店",
                "biz_ext": {"rating": "4.6"},
            }],
        },
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/locations/pois",
            params={"keyword": "酒店", "city": "360100", "accommodation_only": "true"},
        )
        assert response.status_code == 200
        assert response.json()[0] == {
            "poi_id": "B_NANCHANG_HOTEL",
            "name": "南昌中心酒店",
            "address": "红谷滩新区测试路 1 号",
            "district": "红谷滩区",
            "longitude": 115.858,
            "latitude": 28.683,
            "type_name": "住宿服务;宾馆酒店",
            "rating": 4.6,
        }


def test_trip_preferences_and_planning_context() -> None:
    with TestClient(app) as client:
        trip = _create_trip(client)
        trip_id = trip["id"]

        defaults = client.get(f"/api/v1/trips/{trip_id}/preferences")
        assert defaults.status_code == 200
        assert defaults.json()["pace"] == "balanced"
        assert defaults.json()["transport_modes"] == ["walk", "transit"]
        assert defaults.json()["daily_start_time"] == "09:00:00"

        payload = {
            "version": defaults.json()["version"],
            "pace": "relaxed",
            "interest_categories": ["history", "food", "photography"],
            "transport_modes": ["walk", "transit"],
            "daily_start_time": "09:30:00",
            "daily_end_time": "20:30:00",
            "meal_preferences": "Local food, no spicy dishes",
            "avoid_categories": ["crowded theme parks"],
            "max_walking_minutes": 45,
            "free_text_requirements": "Keep one unplanned hour each afternoon.",
        }
        updated = client.put(f"/api/v1/trips/{trip_id}/preferences", json=payload)
        assert updated.status_code == 200
        assert updated.json()["version"] == defaults.json()["version"] + 1
        assert updated.json()["interest_categories"] == ["history", "food", "photography"]

        stale = client.put(f"/api/v1/trips/{trip_id}/preferences", json=payload)
        assert stale.status_code == 409

        context = client.get(f"/api/v1/trips/{trip_id}/planning-context")
        assert context.status_code == 200
        body = context.json()
        assert body["trip"]["id"] == trip_id
        assert body["preferences"]["pace"] == "relaxed"
        assert len(body["days"]) == 1
        assert body["actual_budget"]["total_remaining_fen"] == 80000
        assert body["planning_budget"]["total_planned_fen"] == 0
        assert body["generated_at"]


def test_trip_preferences_validation_and_missing_trip() -> None:
    with TestClient(app) as client:
        trip = _create_trip(client)
        trip_id = trip["id"]
        version = client.get(f"/api/v1/trips/{trip_id}/preferences").json()["version"]
        invalid = client.put(
            f"/api/v1/trips/{trip_id}/preferences",
            json={
                "version": version,
                "pace": "intensive",
                "interest_categories": ["history", "history"],
                "transport_modes": ["walk"],
                "daily_start_time": "21:00:00",
                "daily_end_time": "09:00:00",
                "max_walking_minutes": 60,
            },
        )
        assert invalid.status_code == 422
        missing_id = uuid.uuid4()
        assert client.get(f"/api/v1/trips/{missing_id}/preferences").status_code == 404
        assert client.get(f"/api/v1/trips/{missing_id}/planning-context").status_code == 404
