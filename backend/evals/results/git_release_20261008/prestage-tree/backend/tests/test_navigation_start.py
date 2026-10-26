import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import RouteLeg, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.main import app
from app.navigation.start_navigation import start_navigation
from app.schemas import NavigationStartRequest


def start(client: TestClient, version: int = 1):
    return client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/navigation/start", json={"expected_itinerary_version": version})


def test_start_navigation_creates_execution_and_first_formal_leg_atomically():
    with TestClient(app) as client:
        assert client.post("/api/v1/demo/reset").status_code == 200
        response = start(client)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["resumed"] is False
        assert body["execution"]["status"] == "in_progress"
        assert body["navigation_session"]["status"] == "active"
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        assert body["navigation_session"]["from_activity_id"] == day["route_legs"][0]["from_activity_id"]
        assert body["navigation_session"]["to_activity_id"] == day["route_legs"][0]["to_activity_id"]


def test_start_navigation_resumes_one_live_session_and_cancel_allows_new_one():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        first = start(client).json()
        duplicate = start(client)
        assert duplicate.status_code == 200
        assert duplicate.json()["resumed"] is True
        assert duplicate.json()["navigation_session"]["id"] == first["navigation_session"]["id"]
        assert client.post(f"/api/v1/navigation-sessions/{first['navigation_session']['id']}/actions", json={"action": "cancel"}).status_code == 200
        replacement = start(client)
        assert replacement.status_code == 200
        assert replacement.json()["navigation_session"]["id"] != first["navigation_session"]["id"]


def test_start_navigation_rejects_stale_itinerary_and_no_formal_leg():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        assert start(client, 99).status_code == 409
        async def remove_legs():
            async with session_factory() as db:
                await db.execute(delete(RouteLeg))
                await db.commit()
        asyncio.run(remove_legs())
        failed = start(client)
        assert failed.status_code == 409
        assert "没有可执行的正式路线" in failed.json()["detail"]


def test_start_navigation_uses_completed_predecessor_as_incoming_leg():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        initial = start(client).json()
        execution_id = initial["execution"]["id"]
        first_activity_id = initial["execution"]["current_activity_id"]
        assert client.post(f"/api/v1/navigation-sessions/{initial['navigation_session']['id']}/actions", json={"action": "complete"}).status_code == 200
        assert client.post(f"/api/v1/trip-executions/{execution_id}/actions", json={"action": "skip", "activity_id": first_activity_id}).status_code == 200
        resumed = start(client).json()["navigation_session"]
        assert resumed["from_activity_id"] == first_activity_id
        assert resumed["to_activity_id"] != first_activity_id


def test_completed_execution_cannot_start_navigation_again():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        initial = start(client).json()
        execution_id = initial["execution"]["id"]
        assert client.post(f"/api/v1/navigation-sessions/{initial['navigation_session']['id']}/actions", json={"action": "cancel"}).status_code == 200
        execution = initial["execution"]
        while execution["current_activity_id"]:
            execution = client.post(f"/api/v1/trip-executions/{execution_id}/actions", json={"action": "skip", "activity_id": execution["current_activity_id"]}).json()
        assert client.post(f"/api/v1/trip-executions/{execution_id}/actions", json={"action": "finish"}).status_code == 200
        assert start(client).status_code == 409


def test_concurrent_atomic_starts_converge_to_one_live_session():
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")

        async def once():
            async with session_factory() as db:
                result = await start_navigation(db, DEMO_TRIP_ID, NavigationStartRequest(expected_itinerary_version=1))
                return result.navigation_session.id

        async def race():
            return await asyncio.gather(once(), once())
        first, second = asyncio.run(race())
        assert first == second
