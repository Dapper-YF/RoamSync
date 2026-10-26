import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.database import (
    Activity,
    NavigationDetectionState,
    NavigationSession,
    PlanningRun,
    TripDisruptionEvent,
    session_factory,
)
from app.demo_seed import DEMO_TRIP_ID, demo_uuid
from app.main import app
from app.navigation.event_detector import EventPolicy
from app.navigation.observation_ingestion import ingest_navigation_observation
from app.schemas import NavigationObservation


def _start_session(client: TestClient) -> dict:
    assert client.post("/api/v1/demo/reset").status_code == 200
    execution = client.post(
        f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start",
        json={"day_plan_id": str(demo_uuid("day", "day-1"))},
    ).json()
    leg = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]["route_legs"][0]
    response = client.post(
        f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",
        json={
            "trip_execution_id": execution["id"],
            "from_activity_id": leg["from_activity_id"],
            "to_activity_id": leg["to_activity_id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _facts(
    navigation: dict,
    sequence: int,
    eta: datetime,
    *,
    distance: int = 1_500,
) -> dict:
    observed = datetime.fromisoformat("2026-09-05T10:00:00+08:00") + timedelta(minutes=sequence)
    return {
        "session_id": navigation["id"],
        "itinerary_version": navigation["itinerary_version"],
        "sequence": sequence,
        "observed_at": observed.isoformat(),
        "position": {
            "longitude": 120.154 + sequence / 100_000,
            "latitude": 30.274,
        },
        "coordinate_system": navigation["coordinate_system"],
        "location_accuracy_meters": 8.5,
        "remaining_distance_meters": distance,
        "remaining_duration_seconds": 1_200,
        "eta": eta.isoformat(),
        "route_revision": navigation["route_revision"],
        "navigation_status": "navigating",
        "source": "simulation",
    }


def _planned_eta(navigation: dict, delay_minutes: int = 0) -> datetime:
    return datetime.fromisoformat(navigation["planned_arrival_at"]) + timedelta(minutes=delay_minutes)


def _severe_eta(sequence: int = 0) -> datetime:
    return datetime.fromisoformat("2026-09-05T23:00:00+08:00") + timedelta(minutes=sequence)


def _counts(session_id: str) -> tuple[int, int]:
    async def read() -> tuple[int, int]:
        async with session_factory() as db:
            disruption_count = await db.scalar(
                select(func.count(TripDisruptionEvent.id)).where(
                    TripDisruptionEvent.navigation_session_id == uuid.UUID(session_id)
                )
            )
            run_count = await db.scalar(
                select(func.count(PlanningRun.id))
                .join(TripDisruptionEvent, PlanningRun.disruption_event_id == TripDisruptionEvent.id)
                .where(TripDisruptionEvent.navigation_session_id == uuid.UUID(session_id))
            )
            return int(disruption_count or 0), int(run_count or 0)

    return asyncio.run(read())


def _active_disruption_snapshot(session_id: str) -> dict:
    async def read() -> dict:
        async with session_factory() as db:
            event = await db.scalar(
                select(TripDisruptionEvent).where(
                    TripDisruptionEvent.navigation_session_id == uuid.UUID(session_id),
                    TripDisruptionEvent.status == "active",
                )
            )
            return event.impact_snapshot

    return asyncio.run(read())


def test_delay_absorbed_updates_runtime_facts_without_disruption_or_planning_run():
    with TestClient(app) as client:
        navigation = _start_session(client)
        response = client.post(
            "/api/v1/navigation-observations",
            json=_facts(navigation, 1, _planned_eta(navigation, 10)),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["accepted_sequence"] == 1
        assert body["current_eta"] is not None
        assert body["active_disruption"] is None
        assert body["recovery_planning"] is None
        assert body["minimum_downstream_slack_minutes"] > 0
        assert body["remaining_duration_seconds"] == 1_200
        persisted = client.get(
            f"/api/v1/navigation-sessions/{navigation['id']}"
        ).json()
        assert persisted["remaining_duration_seconds"] == 1_200
        assert persisted["observation_source"] == "simulation"
        execution_progress = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/execution-progress"
        ).json()
        assert (
            execution_progress["minimum_downstream_slack_minutes"]
            == body["minimum_downstream_slack_minutes"]
        )
        assert _counts(navigation["id"]) == (0, 0)


def test_temporary_negative_slack_recovers_before_confirmation():
    with TestClient(app) as client:
        navigation = _start_session(client)
        first = client.post(
            "/api/v1/navigation-observations",
            json=_facts(navigation, 1, _severe_eta(1)),
        )
        assert first.status_code == 200, first.text
        assert first.json()["risk_level"] == "infeasible"
        recovered = client.post(
            "/api/v1/navigation-observations",
            json=_facts(navigation, 2, _planned_eta(navigation, 5)),
        )
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["active_disruption"] is None
        assert _counts(navigation["id"]) == (0, 0)


def test_confirmed_negative_slack_queues_once_and_worsening_updates_same_disruption():
    with TestClient(app) as client:
        navigation = _start_session(client)
        for sequence in (1, 2, 3):
            response = client.post(
                "/api/v1/navigation-observations",
                json=_facts(navigation, sequence, _severe_eta(sequence)),
            )
            assert response.status_code == 200, response.text
        confirmed = response.json()
        assert confirmed["active_disruption"]["event_type"] == "itinerary_infeasible"
        assert confirmed["recovery_planning"]["status"] == "queued"
        disruption_id = confirmed["active_disruption"]["id"]
        run_id = confirmed["recovery_planning"]["id"]
        first_snapshot = _active_disruption_snapshot(navigation["id"])

        worse = client.post(
            "/api/v1/navigation-observations",
            json=_facts(navigation, 4, _severe_eta(20)),
        )
        assert worse.status_code == 200, worse.text
        assert worse.json()["active_disruption"]["id"] == disruption_id
        assert worse.json()["recovery_planning"]["id"] == run_id
        assert (
            _active_disruption_snapshot(navigation["id"])["minimum_slack_minutes"]
            < first_snapshot["minimum_slack_minutes"]
        )
        assert _counts(navigation["id"]) == (1, 1)


def test_hard_missed_window_bypasses_debounce_and_queues_recovery():
    with TestClient(app) as client:
        navigation = _start_session(client)

        async def lock_target() -> None:
            async with session_factory() as db:
                await db.execute(
                    update(Activity)
                    .where(Activity.id == uuid.UUID(navigation["to_activity_id"]))
                    .values(schedule_locked=True)
                )
                await db.commit()

        asyncio.run(lock_target())
        response = client.post(
            "/api/v1/navigation-observations",
            json=_facts(
                navigation,
                1,
                datetime.fromisoformat("2026-09-05T14:00:00+08:00"),
            ),
        )
        assert response.status_code == 200, response.text
        assert response.json()["active_disruption"]["event_type"] == "missed_time_window"
        assert response.json()["recovery_planning"]["status"] == "queued"
        assert _counts(navigation["id"]) == (1, 1)


def test_exact_retry_is_safe_but_conflicting_duplicate_and_old_writes_are_rejected():
    with TestClient(app) as client:
        navigation = _start_session(client)
        payload = _facts(navigation, 2, _planned_eta(navigation, 5))
        accepted = client.post("/api/v1/navigation-observations", json=payload)
        assert accepted.status_code == 200, accepted.text
        replay = client.post("/api/v1/navigation-observations", json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True

        conflicting = dict(payload)
        conflicting["remaining_distance_meters"] = 999
        assert client.post("/api/v1/navigation-observations", json=conflicting).status_code == 409
        assert client.post(
            "/api/v1/navigation-observations",
            json=_facts(navigation, 1, _planned_eta(navigation, 5)),
        ).status_code == 409
        old_version = _facts(navigation, 3, _planned_eta(navigation, 5))
        old_version["itinerary_version"] += 1
        assert client.post("/api/v1/navigation-observations", json=old_version).status_code == 409
        old_route = _facts(navigation, 3, _planned_eta(navigation, 5))
        old_route["route_revision"] += 1
        assert client.post("/api/v1/navigation-observations", json=old_route).status_code == 409
        stale_time = _facts(navigation, 3, _planned_eta(navigation, 5))
        stale_time["observed_at"] = "2026-09-05T09:59:00+08:00"
        assert client.post("/api/v1/navigation-observations", json=stale_time).status_code == 409


def test_superseded_session_rejects_observation_instead_of_reactivating():
    with TestClient(app) as client:
        navigation = _start_session(client)

        async def supersede() -> None:
            async with session_factory() as db:
                await db.execute(
                    update(NavigationSession)
                    .where(NavigationSession.id == uuid.UUID(navigation["id"]))
                    .values(status="superseded")
                )
                await db.commit()

        asyncio.run(supersede())
        response = client.post(
            "/api/v1/navigation-observations",
            json=_facts(navigation, 1, _planned_eta(navigation, 5)),
        )
        assert response.status_code == 409
        assert client.get(
            f"/api/v1/navigation-sessions/{navigation['id']}"
        ).json()["status"] == "superseded"


def test_persisted_detector_state_survives_new_service_sessions():
    with TestClient(app) as client:
        navigation = _start_session(client)

        async def across_workers():
            policy = EventPolicy(consecutive_observations=2)
            first = NavigationObservation.model_validate(
                _facts(navigation, 1, _severe_eta(1))
            )
            second = NavigationObservation.model_validate(
                _facts(navigation, 2, _severe_eta(2))
            )
            async with session_factory() as worker_one:
                one = await ingest_navigation_observation(worker_one, first, policy=policy)
            async with session_factory() as worker_two:
                two = await ingest_navigation_observation(worker_two, second, policy=policy)
            async with session_factory() as reader:
                state = await reader.get(
                    NavigationDetectionState,
                    uuid.UUID(navigation["id"]),
                )
                return one, two, state.consecutive_risk_count

        first, second, count = asyncio.run(across_workers())
        assert first.active_disruption is None
        assert second.active_disruption is not None
        assert second.recovery_planning.status == "queued"
        assert count == 2


def test_concurrent_confirmation_is_idempotent_and_does_not_wait_for_worker():
    with TestClient(app) as client:
        navigation = _start_session(client)
        for sequence in (1, 2):
            response = client.post(
                "/api/v1/navigation-observations",
                json=_facts(navigation, sequence, _severe_eta(sequence)),
            )
            assert response.status_code == 200, response.text

        payload = NavigationObservation.model_validate(
            _facts(navigation, 3, _severe_eta(3))
        )

        async def race():
            async def ingest_once():
                async with session_factory() as db:
                    return await ingest_navigation_observation(db, payload)

            return await asyncio.gather(ingest_once(), ingest_once())

        one, two = asyncio.run(race())
        assert sorted([one.replayed, two.replayed]) == [False, True]
        assert one.recovery_planning.status == "queued"
        assert two.recovery_planning.id == one.recovery_planning.id
        assert _counts(navigation["id"]) == (1, 1)
