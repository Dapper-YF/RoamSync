import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import NavigationSession, Trip, session_factory
from app.demo_seed import DEMO_TRIP_ID, demo_uuid
from app.navigation.fake_routing_provider import FakeRouteResponse, FakeRoutingProvider
from app.navigation.providers import RoutingCoordinate, RoutingProviderError, RoutingResult
from app.navigation.session_service import (
    StaleNavigationWriteError,
    refresh_route,
    supersede_navigation_sessions_for_itinerary,
)
from app.navigation.disruption_service import record_disruption
from app.navigation.event_detector import DetectedExecutionEvent
from app.planning_run_repository import RecoveryPlanningConflictError, create_planning_run
from app.schemas import PlanningRunCreate
from app.main import app


TZ = ZoneInfo("Asia/Shanghai")


def _start_and_create_session(client: TestClient) -> dict:
    assert client.post("/api/v1/demo/reset").status_code == 200
    execution = client.post(
        f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start",
        json={"day_plan_id": str(demo_uuid("day", "day-1"))},
    ).json()
    day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
    leg = day["route_legs"][0]
    created = client.post(
        f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",
        json={
            "trip_execution_id": execution["id"],
            "from_activity_id": leg["from_activity_id"],
            "to_activity_id": leg["to_activity_id"],
        },
    )
    assert created.status_code == 201, created.text
    return {"execution": execution, "leg": leg, "session": created.json()}


def _location(sequence: int, itinerary_version: int) -> dict:
    return {
        "sequence": sequence,
        "itinerary_version": itinerary_version,
        "location": {"longitude": 120.154 + sequence / 100_000, "latitude": 30.274},
        "observed_at": "2026-09-05T09:10:00+08:00",
    }


def test_navigation_session_is_a_versioned_leg_projection_and_allows_one_live_session():
    with TestClient(app) as client:
        state = _start_and_create_session(client)
        item = state["session"]
        assert item["trip_id"] == str(DEMO_TRIP_ID)
        assert item["itinerary_version"] == 1
        assert item["formal_route_leg_id"] == state["leg"]["id"]
        assert item["from_activity_id"] == state["leg"]["from_activity_id"]
        assert item["to_activity_id"] == state["leg"]["to_activity_id"]
        duplicate = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",
            json={
                "trip_execution_id": state["execution"]["id"],
                "from_activity_id": state["leg"]["from_activity_id"],
                "to_activity_id": state["leg"]["to_activity_id"],
            },
        )
        assert duplicate.status_code == 409


def test_execution_progress_is_a_single_ui_read_model_without_frontend_slack_calculation():
    with TestClient(app) as client:
        state = _start_and_create_session(client)
        progress = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution-progress")
        assert progress.status_code == 200, progress.text
        body = progress.json()
        assert body["navigation_session"]["id"] == state["session"]["id"]
        assert isinstance(body["navigation_target_name"], str)
        assert body["risk_level"] == "normal"
        assert body["minimum_downstream_slack_minutes"] is None


def test_concurrent_session_creation_is_resolved_by_postgresql_partial_unique_index():
    with TestClient(app) as client:
        state = _start_and_create_session(client)
        # Complete the setup session, then start two independent transactions
        # which race to create the next live projection for one execution.
        assert client.post(f"/api/v1/navigation-sessions/{state['session']['id']}/actions", json={"action": "complete"}).status_code == 200

        async def create_once():
            from app.navigation.session_service import create_navigation_session, NavigationSessionConflictError
            from app.schemas import NavigationSessionCreate
            async with session_factory() as session:
                try:
                    return await create_navigation_session(session, DEMO_TRIP_ID, NavigationSessionCreate(
                        trip_execution_id=state["execution"]["id"], from_activity_id=state["leg"]["from_activity_id"], to_activity_id=state["leg"]["to_activity_id"]
                    ))
                except NavigationSessionConflictError:
                    return "conflict"
        async def race():
            return await asyncio.gather(create_once(), create_once())
        first, second = asyncio.run(race())
        assert sorted(["created" if item != "conflict" else "conflict" for item in (first, second)]) == ["conflict", "created"]


def test_repeated_macro_disruption_updates_one_active_row_and_version_is_part_of_its_identity():
    with TestClient(app) as client:
        state = _start_and_create_session(client)
        session_id = state["session"]["id"]

        async def persist():
            async with session_factory() as db:
                one = await record_disruption(db, session_id, DetectedExecutionEvent("itinerary_infeasible", "disruption", datetime(2026, 9, 5, 9, tzinfo=TZ), "appointment", {"minimum_slack_minutes": -5}))
            async with session_factory() as db:
                two = await record_disruption(db, session_id, DetectedExecutionEvent("itinerary_infeasible", "disruption", datetime(2026, 9, 5, 9, 2, tzinfo=TZ), "appointment", {"minimum_slack_minutes": -12}))
                from app.database import TripDisruptionEvent
                count = len(list((await db.scalars(select(TripDisruptionEvent))).all()))
                return one.id, two.id, two.impact_snapshot, count
        first_id, second_id, snapshot, count = asyncio.run(persist())
        assert first_id == second_id
        assert snapshot["minimum_slack_minutes"] == -12
        assert count == 1


def test_same_active_disruption_has_one_active_recovery_run_and_rejection_does_not_resolve_it():
    with TestClient(app) as client:
        state = _start_and_create_session(client)
        async def create_recovery():
            async with session_factory() as db:
                disruption = await record_disruption(db, state["session"]["id"], DetectedExecutionEvent(
                    "itinerary_infeasible", "disruption", datetime(2026, 9, 5, 9, tzinfo=TZ), "appointment", {"minimum_slack_minutes": -20}
                ))
            async with session_factory() as db:
                first = await create_planning_run(db, DEMO_TRIP_ID, PlanningRunCreate(
                    run_type="replan", user_request="行程已延误，请调整后续安排", disruption_event_id=disruption.id
                ))
            async with session_factory() as db:
                try:
                    await create_planning_run(db, DEMO_TRIP_ID, PlanningRunCreate(
                        run_type="replan", user_request="行程已延误，请调整后续安排", disruption_event_id=disruption.id
                    ))
                except RecoveryPlanningConflictError:
                    pass
                else:
                    raise AssertionError("active disruption must not own two active runs")
                from app.database import TripDisruptionEvent
                event = await db.get(TripDisruptionEvent, disruption.id)
                return first, event.status
        run, event_status = asyncio.run(create_recovery())
        assert run.disruption_event_id is not None
        assert event_status == "active"


def test_location_sequence_is_a_database_compare_and_set_and_terminal_sessions_reject_writes():
    with TestClient(app) as client:
        state = _start_and_create_session(client)
        session_id = state["session"]["id"]
        version = state["session"]["itinerary_version"]
        for sequence in (10, 12):
            response = client.post(
                f"/api/v1/navigation-sessions/{session_id}/location-updates",
                json=_location(sequence, version),
            )
            assert response.status_code == 200
        # Re-delivery after a client timeout is idempotent; a lower sequence is
        # still rejected and cannot overwrite the acknowledged value.
        assert client.post(
            f"/api/v1/navigation-sessions/{session_id}/location-updates", json=_location(12, version)
        ).status_code == 200
        stale = client.post(
            f"/api/v1/navigation-sessions/{session_id}/location-updates", json=_location(11, version)
        )
        assert stale.status_code == 409
        assert client.get(f"/api/v1/navigation-sessions/{session_id}").json()["last_location_sequence"] == 12

        complete = client.post(f"/api/v1/navigation-sessions/{session_id}/actions", json={"action": "complete"})
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed"
        assert client.post(
            f"/api/v1/navigation-sessions/{session_id}/location-updates", json=_location(13, version)
        ).status_code == 409

        replacement = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",
            json={
                "trip_execution_id": state["execution"]["id"],
                "from_activity_id": state["leg"]["from_activity_id"],
                "to_activity_id": state["leg"]["to_activity_id"],
            },
        ).json()
        cancelled = client.post(
            f"/api/v1/navigation-sessions/{replacement['id']}/actions", json={"action": "cancel"}
        )
        assert cancelled.status_code == 200
        assert client.post(
            f"/api/v1/navigation-sessions/{replacement['id']}/location-updates",
            json=_location(1, replacement["itinerary_version"]),
        ).status_code == 409


def test_fake_provider_results_are_fenced_by_monotonic_route_revision():
    with TestClient(app) as client:
        navigation_session_id = _start_and_create_session(client)["session"]["id"]

        async def run() -> tuple[object, object, dict]:
            base = datetime(2026, 9, 5, 9, tzinfo=TZ)
            provider = FakeRoutingProvider([
                FakeRouteResponse(result=RoutingResult(3000, 30, base + timedelta(minutes=30), "fake", {"call": 5}), delay_seconds=0.04),
                FakeRouteResponse(result=RoutingResult(1200, 12, base + timedelta(minutes=12), "fake", {"call": 6})),
            ])
            old = asyncio.create_task(refresh_route(session_factory, navigation_session_id, provider))
            await asyncio.sleep(0.005)
            newest = asyncio.create_task(refresh_route(session_factory, navigation_session_id, provider))
            old_result, newest_result = await asyncio.gather(old, newest, return_exceptions=True)
            async with session_factory() as session:
                item = await session.get(NavigationSession, navigation_session_id)
                return old_result, newest_result, {
                    "route_revision": item.route_revision,
                    "distance": item.remaining_distance_meters,
                    "metadata": item.provider_metadata,
                    "status": item.status,
                }

        old, newest, stored = asyncio.run(run())
        assert isinstance(old, StaleNavigationWriteError)
        assert not isinstance(newest, Exception)
        assert stored == {"route_revision": 2, "distance": 1200, "metadata": {"call": 6}, "status": "active"}


def test_provider_response_after_itinerary_change_is_rejected_and_session_stays_superseded():
    with TestClient(app) as client:
        navigation_session_id = _start_and_create_session(client)["session"]["id"]

        async def run() -> tuple[object, str, int]:
            base = datetime(2026, 9, 5, 9, tzinfo=TZ)
            provider = FakeRoutingProvider([
                FakeRouteResponse(result=RoutingResult(900, 9, base + timedelta(minutes=9), "fake"), delay_seconds=0.04)
            ])
            pending = asyncio.create_task(refresh_route(session_factory, navigation_session_id, provider))
            await asyncio.sleep(0.005)
            async with session_factory() as session:
                trip = await session.scalar(select(Trip).where(Trip.id == DEMO_TRIP_ID).with_for_update())
                await supersede_navigation_sessions_for_itinerary(session, trip.id, trip.version)
                trip.version += 1
                await session.commit()
            result = await pending
            async with session_factory() as session:
                item = await session.get(NavigationSession, navigation_session_id)
                return result, item.status, item.itinerary_version

        try:
            asyncio.run(run())
        except StaleNavigationWriteError:
            async def read() -> tuple[str, int]:
                async with session_factory() as session:
                    item = await session.get(NavigationSession, navigation_session_id)
                    return item.status, item.itinerary_version
            assert asyncio.run(read()) == ("superseded", 1)
        else:
            raise AssertionError("a provider response for an old itinerary must be rejected")


def test_fake_provider_failure_does_not_leave_the_latest_session_stuck_rerouting():
    with TestClient(app) as client:
        navigation_session_id = _start_and_create_session(client)["session"]["id"]

        async def run() -> str:
            provider = FakeRoutingProvider([
                FakeRouteResponse(error=RoutingProviderError("fake unavailable", code="fake_down"))
            ])
            try:
                await refresh_route(session_factory, navigation_session_id, provider)
            except RoutingProviderError as error:
                assert error.code == "fake_down"
            async with session_factory() as session:
                return (await session.get(NavigationSession, navigation_session_id)).status

        assert asyncio.run(run()) == "active"
