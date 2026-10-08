"""PostgreSQL integration coverage for Phase 1C experience recovery.

The tests use the persisted demo itinerary and actual command/service paths.
They deliberately pin execution facts to the formal day so the assertions are
about the deterministic timeline policy rather than the wall-clock date.
"""
import asyncio
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.activity_experience_impact import evaluate_activity_experience_time_impact
from app.database import Activity, ActivityExecution, DayPlan, NavigationSession, PlanRevision, PlanningRun, PlaceCandidate, TravelEvent, Trip, TripDisruptionEvent, TripExecution, TripPreferences, session_factory
from app.demo_seed import DEMO_TRIP_ID
from app.experience_replanning_service import ensure_experience_recovery, refresh_experience_trigger_snapshot
from app.main import app
from app.navigation.disruption_service import record_disruption
from app.navigation.event_detector import DetectedExecutionEvent
from app.navigation.observation_ingestion import _ensure_recovery_planning_run
from app.schemas import ExtendStayRequest
from app.trip_execution_service import extend_stay
from app.plan_revision_service import validate_candidate_plan
from app.planning_run_repository import save_plan_revision
from app.planning_intent_service import resolve_planning_intent
from app.schemas import PlanningIntentParseRequest
from app.schemas import CandidateActivity, CandidatePlanSnapshot


ACTIVE = ("queued", "researching", "awaiting_clarification", "planning", "validating", "awaiting_confirmation")


def _start_current(client: TestClient) -> tuple[dict, dict]:
    client.post("/api/v1/demo/reset")
    execution = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
    current = next(item for item in execution["activities"] if item["activity_id"] == execution["current_activity_id"])
    assert client.post(
        f"/api/v1/trip-executions/{execution['id']}/actions",
        json={"action": "start_activity", "activity_id": current["activity_id"]},
    ).status_code == 200
    return execution, current


async def _pin_current_start(activity_execution_id: str) -> None:
    """Put the live fact on its formal start, making shifts deterministic."""
    async with session_factory() as session:
        row = await session.execute(
            select(ActivityExecution, Activity, DayPlan)
            .join(Activity, ActivityExecution.activity_id == Activity.id)
            .join(DayPlan, Activity.day_plan_id == DayPlan.id)
            .where(ActivityExecution.id == uuid.UUID(activity_execution_id))
        )
        item, activity, day = row.tuples().one()
        item.actual_started_at = datetime.combine(day.date, activity.scheduled_time, tzinfo=ZoneInfo("Asia/Shanghai"))
        await session.commit()


async def _set_daily_end(hour: int, minute: int) -> None:
    async with session_factory() as session:
        preferences = await session.scalar(select(TripPreferences).where(TripPreferences.trip_id == DEMO_TRIP_ID))
        assert preferences is not None
        preferences.daily_end_time = time(hour, minute)
        await session.commit()


async def _run_rows() -> list[PlanningRun]:
    async with session_factory() as session:
        return list((await session.scalars(select(PlanningRun).where(
            PlanningRun.trip_id == DEMO_TRIP_ID,
            PlanningRun.trigger_type == "experience_impact",
        ).order_by(PlanningRun.created_at))).all())


async def _impact(execution_id: str, activity_execution_id: str):
    async with session_factory() as session:
        return await evaluate_activity_experience_time_impact(session, uuid.UUID(execution_id), uuid.UUID(activity_execution_id))


def _extend(client: TestClient, activity_execution_id: str, minutes: int, action_id: uuid.UUID | None = None):
    return client.post(
        f"/api/v1/activity-executions/{activity_execution_id}/extend-stay",
        json={"client_action_id": str(action_id or uuid.uuid4()), "extension_minutes": minutes},
    )


def test_experience_recovery_policy_absorbed_at_risk_and_unavailable() -> None:
    """Only deterministic infeasibility may create an automatic run."""
    with TestClient(app) as client:
        # Unavailable before an activity has an authoritative boundary.
        client.post("/api/v1/demo/reset")
        initial = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start", json={}).json()
        current = next(item for item in initial["activities"] if item["activity_id"] == initial["current_activity_id"])
        assert asyncio.run(_impact(initial["id"], current["id"])).impact_state == "unavailable"
        assert asyncio.run(_run_rows()) == []

        execution, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        assert _extend(client, current["id"], 1).status_code == 200
        assert asyncio.run(_impact(execution["id"], current["id"])).impact_state == "absorbed"
        assert asyncio.run(_run_rows()) == []

        # The seeded first day has a schedule gap before its next activity;
        # this consumes the buffer without violating fixed/day-end constraints.
        asyncio.run(_set_daily_end(19, 29))
        assert _extend(client, current["id"], 300).status_code == 200
        assert asyncio.run(_impact(execution["id"], current["id"])).impact_state == "at_risk"
        assert asyncio.run(_run_rows()) == []


def test_infeasible_experience_creates_fingerprinted_recovery_snapshot() -> None:
    with TestClient(app) as client:
        execution, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        response = _extend(client, current["id"], 480)
        assert response.status_code == 200
        assert response.json()["replanning_status"] == "queued"
        [run] = asyncio.run(_run_rows())
        snapshot = run.trigger_snapshot
        assert run.trigger_type == "experience_impact"
        assert run.trigger_key == f"experience:{execution['id']}:{run.base_trip_version}:{current['id']}"
        assert run.trigger_fingerprint and run.trigger_fingerprint == snapshot["fingerprint"]
        assert run.base_trip_version == 1
        assert snapshot["activity_execution_id"] == current["id"]
        assert snapshot["formal_itinerary_version"] == run.base_trip_version
        assert snapshot["impact"]["time_shift_minutes"] == 480
        assert snapshot["impact"]["minimum_downstream_slack_minutes"] is not None
        assert snapshot["impact"]["fixed_window_feasible"] is not None
        assert snapshot["impact"]["day_end_feasible"] is False


def test_exact_replay_does_not_duplicate_event_or_recovery() -> None:
    with TestClient(app) as client:
        _, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        action = uuid.uuid4()
        assert _extend(client, current["id"], 480, action).status_code == 200
        first_fingerprint = asyncio.run(_run_rows())[0].trigger_fingerprint
        replay = _extend(client, current["id"], 480, action)
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        rows = asyncio.run(_run_rows())
        assert len(rows) == 1 and rows[0].trigger_fingerprint == first_fingerprint

        async def counts() -> tuple[int, int]:
            async with session_factory() as session:
                events = await session.scalar(select(func.count(TravelEvent.id)).where(TravelEvent.activity_execution_id == uuid.UUID(current["id"])))
                active = await session.scalar(select(func.count(PlanningRun.id)).where(PlanningRun.trip_id == DEMO_TRIP_ID, PlanningRun.status.in_(ACTIVE)))
                return events or 0, active or 0
        assert asyncio.run(counts()) == (2, 1)  # activity_started + one extend fact


def test_real_second_extend_leaves_one_active_run_for_f2_worker_refresh() -> None:
    with TestClient(app) as client:
        _, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        assert _extend(client, current["id"], 480).status_code == 200
        first_fingerprint = asyncio.run(_run_rows())[0].trigger_fingerprint
        second = _extend(client, current["id"], 30)
        assert second.status_code == 200
        [latest] = asyncio.run(_run_rows())
        assert latest.trigger_fingerprint == first_fingerprint

        async def refresh() -> dict:
            async with session_factory() as session:
                run = await session.get(PlanningRun, latest.id)
                assert run is not None
                snapshot = await refresh_experience_trigger_snapshot(session, run)
                await session.commit()
                return snapshot
        fresh = asyncio.run(refresh())
        assert fresh["fingerprint"] != first_fingerprint
        assert fresh["impact"]["time_shift_minutes"] == 510


def test_rejected_fingerprint_is_suppressed_but_changed_facts_retrigger() -> None:
    with TestClient(app) as client:
        execution, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        assert _extend(client, current["id"], 480).status_code == 200
        [first] = asyncio.run(_run_rows())

        async def reject_and_recheck() -> None:
            async with session_factory() as session:
                run = await session.get(PlanningRun, first.id)
                assert run is not None
                run.status = "rejected"
                await session.commit()
            async with session_factory() as session:
                assert await ensure_experience_recovery(session, uuid.UUID(current["id"])) is None
        asyncio.run(reject_and_recheck())
        assert len(asyncio.run(_run_rows())) == 1

        assert _extend(client, current["id"], 30).status_code == 200
        rows = asyncio.run(_run_rows())
        assert len(rows) == 2
        assert rows[-1].trigger_fingerprint != first.trigger_fingerprint
        assert rows[-1].base_trip_version == 1
        assert asyncio.run(_impact(execution["id"], current["id"])).impact_state == "infeasible"


def test_worker_refresh_reads_latest_persisted_experience_facts() -> None:
    with TestClient(app) as client:
        _, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        assert _extend(client, current["id"], 480).status_code == 200
        [first] = asyncio.run(_run_rows())
        assert _extend(client, current["id"], 30).status_code == 200

        async def refresh() -> dict:
            async with session_factory() as session:
                run = await session.get(PlanningRun, first.id)
                assert run is not None
                snapshot = await refresh_experience_trigger_snapshot(session, run)
                await session.commit()
                return snapshot
        fresh = asyncio.run(refresh())
        assert fresh["fingerprint"] != first.trigger_fingerprint
        assert fresh["impact"]["time_shift_minutes"] == 510
        assert fresh["impact"]["day_end_feasible"] is False


def test_stale_experience_facts_fence_accept_and_new_facts_supersede_revision() -> None:
    """F2 fences A independently of Trip.version; the product state is superseded."""
    with TestClient(app) as client:
        _, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        assert _extend(client, current["id"], 480).status_code == 200
        [run] = asyncio.run(_run_rows())

        async def prepare() -> tuple[uuid.UUID, int]:
            async with session_factory() as session:
                live = await session.get(PlanningRun, run.id)
                assert live is not None
                live.status = "awaiting_confirmation"
                revision = PlanRevision(planning_run_id=live.id, trip_id=DEMO_TRIP_ID, revision_number=1,
                                        reason="test", before_snapshot={}, proposed_snapshot={})
                session.add(revision)
                trip = await session.get(Trip, DEMO_TRIP_ID)
                assert trip is not None
                await session.commit()
                return revision.id, trip.version
        revision_id, version = asyncio.run(prepare())

        # Direct command records F2 but intentionally does not run supersede;
        # acceptance must therefore fail specifically on its fingerprint fence.
        async def record_f2() -> None:
            async with session_factory() as session:
                await extend_stay(session, uuid.UUID(current["id"]), ExtendStayRequest(client_action_id=uuid.uuid4(), extension_minutes=30))
        asyncio.run(record_f2())
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()["version"] == version
        assert client.post(f"/api/v1/plan-revisions/{revision_id}/accept").status_code == 409

        # Calling the automatic policy with the same F2 gives the old pending
        # proposal a visible superseded state, never a user rejection.
        async def supersede() -> tuple[str, str]:
            async with session_factory() as session:
                latest = await ensure_experience_recovery(session, uuid.UUID(current["id"]))
                old = await session.get(PlanRevision, revision_id)
                assert latest is not None and old is not None
                return old.status, latest.status
        old_status, latest_status = asyncio.run(supersede())
        assert old_status == "superseded"
        assert latest_status == "queued"
        assert client.post(f"/api/v1/plan-revisions/{revision_id}/accept").status_code == 409


@pytest.mark.parametrize("mutation", ["shorten", "replace", "move"])
def test_current_experience_activity_cannot_be_redefined(mutation: str) -> None:
    """A deterministic recovery validator preserves present execution reality."""
    with TestClient(app) as client:
        _, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        assert _extend(client, current["id"], 30).status_code == 200

        async def validate() -> list[str]:
            async with session_factory() as session:
                row = await session.execute(select(Activity, DayPlan, PlaceCandidate).join(DayPlan, Activity.day_plan_id == DayPlan.id).join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id).where(Activity.id == uuid.UUID(current["activity_id"])))
                activity, day, place = row.tuples().one()
                other = await session.scalar(select(PlaceCandidate).where(PlaceCandidate.trip_id == DEMO_TRIP_ID, PlaceCandidate.id != place.id).limit(1))
                assert other is not None
                candidate = CandidateActivity(candidate_id="illegal-current", day_date=day.date,
                    place_candidate_id=other.id if mutation == "replace" else place.id,
                    planned_start_time=time(11, 0) if mutation == "move" else activity.scheduled_time,
                    duration_minutes=30 if mutation == "shorten" else activity.duration_minutes,
                    estimated_cost_fen=other.estimated_cost_fen if mutation == "replace" else activity.estimated_cost_fen,
                    transport_mode_to_here="walk", source_ids=[other.source_record_id if mutation == "replace" else place.source_record_id], replaces_activity_id=activity.id)
                result = await validate_candidate_plan(session, DEMO_TRIP_ID, CandidatePlanSnapshot(activities=[candidate]), enforce_execution_invariants=True)
                return [error.code for error in result.errors]
        assert "execution_activity_changed" in asyncio.run(validate())


def test_explicit_delete_of_current_activity_is_rejected_without_mutating_facts() -> None:
    """Delta omission becomes deletion only when the real intent says remove."""
    with TestClient(app) as client:
        _, current = _start_current(client)

        async def validate_delete() -> tuple[list[str], tuple]:
            async with session_factory() as session:
                state = await session.get(ActivityExecution, uuid.UUID(current["id"]))
                activity = await session.get(Activity, uuid.UUID(current["activity_id"]))
                assert state is not None and activity is not None
                before = (activity.id, activity.scheduled_time, state.id, state.status,
                          state.actual_started_at, state.actual_ended_at)
                intent = await resolve_planning_intent(session, DEMO_TRIP_ID, PlanningIntentParseRequest(
                    message="删除这个活动", selected_activity_id=activity.id,
                ))
                result = await validate_candidate_plan(session, DEMO_TRIP_ID, CandidatePlanSnapshot(activities=[]),
                    intent_resolution=intent, enforce_execution_invariants=True)
                await session.refresh(activity)
                await session.refresh(state)
                after = (activity.id, activity.scheduled_time, state.id, state.status,
                         state.actual_started_at, state.actual_ended_at)
                return [item.code for item in result.errors], (before, after)
        errors, facts = asyncio.run(validate_delete())
        assert "execution_activity_changed" in errors
        assert facts[0] == facts[1]


def test_delta_omission_of_current_activity_is_not_misread_as_delete() -> None:
    with TestClient(app) as client:
        _, current = _start_current(client)

        async def validate_delta() -> list[str]:
            async with session_factory() as session:
                result = await validate_candidate_plan(session, DEMO_TRIP_ID, CandidatePlanSnapshot(activities=[]),
                    enforce_execution_invariants=True)
                return [item.code for item in result.errors]
        assert "execution_activity_changed" not in asyncio.run(validate_delta())


def test_navigation_eta_replaces_historical_experience_boundary_without_double_count() -> None:
    """A live observation owns the timeline; prior dwell facts remain history."""
    with TestClient(app) as client:
        execution, current = _start_current(client)

        async def prepare() -> None:
            async with session_factory() as session:
                row = await session.execute(select(ActivityExecution, Activity, DayPlan)
                    .join(Activity, ActivityExecution.activity_id == Activity.id)
                    .join(DayPlan, Activity.day_plan_id == DayPlan.id)
                    .where(ActivityExecution.id == uuid.UUID(current["id"])))
                state, activity, day = row.tuples().one()
                activity.duration_minutes = 120
                state.actual_started_at = datetime.combine(day.date, time(10, 8), tzinfo=ZoneInfo("Asia/Shanghai"))
                await session.commit()
        asyncio.run(prepare())
        assert _extend(client, current["id"], 60).status_code == 200
        before = asyncio.run(_impact(execution["id"], current["id"]))
        assert before.impact_state != "unavailable" and before.time_shift_minutes > 60

        # Completion preserves the experience fact, then real navigation owns A→B.
        assert client.post(f"/api/v1/trip-executions/{execution['id']}/actions",
            json={"action": "complete", "activity_id": current["activity_id"]}).status_code == 200
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        leg = days[0]["route_legs"][0]
        nav_response = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions", json={
            "trip_execution_id": execution["id"], "from_activity_id": leg["from_activity_id"], "to_activity_id": leg["to_activity_id"],
        })
        assert nav_response.status_code == 201, nav_response.text
        navigation = nav_response.json()
        eta = datetime.fromisoformat(navigation["planned_arrival_at"]) + timedelta(minutes=20)
        observation = client.post("/api/v1/navigation-observations", json={
            "session_id": navigation["id"], "itinerary_version": navigation["itinerary_version"], "sequence": 1,
            "observed_at": "2026-09-05T13:20:00+08:00", "position": {"longitude": 120.154, "latitude": 30.274},
            "coordinate_system": navigation["coordinate_system"], "location_accuracy_meters": 8.5,
            "remaining_distance_meters": 1500, "remaining_duration_seconds": 1200, "eta": eta.isoformat(),
            "route_revision": navigation["route_revision"], "navigation_status": "navigating", "source": "simulation",
        })
        assert observation.status_code == 200, observation.text
        assert datetime.fromisoformat(observation.json()["current_eta"]) == eta
        progress = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution-progress")
        assert progress.status_code == 200
        body = progress.json()
        assert body["navigation_session"]["id"] == navigation["id"]
        assert datetime.fromisoformat(body["navigation_session"]["current_eta"].replace("Z", "+00:00")) == eta
        assert body["experience_impact"] is None

        async def history() -> int:
            async with session_factory() as session:
                return int(await session.scalar(select(func.count(TravelEvent.id)).where(
                    TravelEvent.activity_execution_id == uuid.UUID(current["id"]),
                    TravelEvent.event_type == "user_extend_stay",
                )) or 0)
        assert asyncio.run(history()) == 1


def test_downstream_candidate_respects_persisted_authoritative_experience_boundary() -> None:
    """Identity retention is insufficient: future timing must respect real dwell."""
    with TestClient(app) as client:
        _, current = _start_current(client)

        async def set_facts_and_validate() -> tuple[datetime, list[str]]:
            async with session_factory() as session:
                row = await session.execute(select(ActivityExecution, Activity, DayPlan, PlaceCandidate).join(Activity, ActivityExecution.activity_id == Activity.id).join(DayPlan, Activity.day_plan_id == DayPlan.id).join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id).where(ActivityExecution.id == uuid.UUID(current["id"])))
                state, first, day, first_place = row.tuples().one()
                first.duration_minutes = 120
                state.actual_started_at = datetime.combine(day.date, time(10, 8), tzinfo=ZoneInfo("Asia/Shanghai"))
                await session.commit()
            assert _extend(client, current["id"], 60).status_code == 200
            async with session_factory() as session:
                rows = list((await session.execute(select(Activity, DayPlan, PlaceCandidate).join(DayPlan, Activity.day_plan_id == DayPlan.id).join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id).where(Activity.day_plan_id == day.id).order_by(Activity.position))).tuples())
                first, _, first_place = rows[0]
                second, second_day, second_place = rows[1]
                snapshot = CandidatePlanSnapshot(activities=[
                    CandidateActivity(candidate_id="keep-current", day_date=day.date, place_candidate_id=first_place.id, planned_start_time=first.scheduled_time, duration_minutes=first.duration_minutes, estimated_cost_fen=first.estimated_cost_fen, transport_mode_to_here="walk", source_ids=[first_place.source_record_id], replaces_activity_id=first.id),
                    CandidateActivity(candidate_id="too-early", day_date=second_day.date, place_candidate_id=second_place.id, planned_start_time=time(12, 30), duration_minutes=second.duration_minutes, estimated_cost_fen=second.estimated_cost_fen, transport_mode_to_here="walk", source_ids=[second_place.source_record_id], replaces_activity_id=second.id),
                ])
                result = await validate_candidate_plan(session, DEMO_TRIP_ID, snapshot, enforce_execution_invariants=True)
                state = await session.get(ActivityExecution, uuid.UUID(current["id"]))
                assert state is not None and state.actual_started_at is not None
                return state.actual_started_at + timedelta(minutes=180), [item.code for item in result.errors]
        boundary, errors = asyncio.run(set_facts_and_validate())
        local_boundary = boundary.astimezone(ZoneInfo("Asia/Shanghai"))
        assert local_boundary.hour == 13 and local_boundary.minute == 8
        assert "execution_authoritative_boundary_conflict" in errors
        assert "execution_activity_changed" not in errors


def test_accepted_experience_recovery_rebases_execution_without_rebuilding_facts() -> None:
    """Accepting a legal recovery changes the formal plan, not lived reality."""
    with TestClient(app) as client:
        execution, current = _start_current(client)

        async def prepare_facts() -> None:
            async with session_factory() as session:
                row = await session.execute(
                    select(ActivityExecution, Activity, DayPlan)
                    .join(Activity, ActivityExecution.activity_id == Activity.id)
                    .join(DayPlan, Activity.day_plan_id == DayPlan.id)
                    .where(ActivityExecution.id == uuid.UUID(current["id"]))
                )
                state, activity, day = row.tuples().one()
                # A non-formal start plus a long dwell makes the persisted impact
                # infeasible while leaving a legal, later recovery schedule.
                activity.duration_minutes = 120
                state.actual_arrived_at = datetime.combine(day.date, time(10, 8), tzinfo=ZoneInfo("Asia/Shanghai"))
                state.actual_started_at = state.actual_arrived_at
                await session.commit()

        asyncio.run(prepare_facts())
        assert _extend(client, current["id"], 480).status_code == 200
        [run] = asyncio.run(_run_rows())
        assert asyncio.run(_impact(execution["id"], current["id"])).impact_state == "infeasible"

        async def save_legal_revision() -> uuid.UUID:
            async with session_factory() as session:
                rows = list((await session.execute(
                    select(Activity, DayPlan, PlaceCandidate)
                    .join(DayPlan, Activity.day_plan_id == DayPlan.id)
                    .join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
                    .where(Activity.day_plan_id == (await session.get(Activity, uuid.UUID(current["activity_id"]))).day_plan_id)
                    .order_by(Activity.position)
                )).tuples())
                current_row = next(item for item in rows if str(item[0].id) == current["activity_id"])
                activity, day, place = current_row
                # The recovery legally retains the protected present activity.
                # Deferring the remaining stops is valid, and makes the formal
                # itinerary genuinely change without rewriting lived facts.
                candidates = [CandidateActivity(
                    candidate_id=f"rebase-{activity.id}", day_date=day.date,
                    place_candidate_id=place.id, planned_start_time=activity.scheduled_time,
                    duration_minutes=activity.duration_minutes,
                    estimated_cost_fen=activity.estimated_cost_fen,
                    transport_mode_to_here="walk", source_ids=[place.source_record_id],
                    replaces_activity_id=activity.id,
                )]
                revision = await save_plan_revision(
                    session, run.id, before_snapshot={},
                    proposed_snapshot=CandidatePlanSnapshot(activities=candidates),
                    reason="legal experience recovery", difference_summary={},
                    validation_result={}, source_ids=[],
                )
                return revision.id

        revision_id = asyncio.run(save_legal_revision())

        async def facts_before() -> dict:
            async with session_factory() as session:
                trip = await session.get(Trip, DEMO_TRIP_ID)
                state = await session.get(ActivityExecution, uuid.UUID(current["id"]))
                assert trip is not None and state is not None
                completed = list((await session.scalars(
                    select(ActivityExecution).where(
                        ActivityExecution.trip_execution_id == uuid.UUID(execution["id"]),
                        ActivityExecution.status == "completed",
                    )
                )).all())
                events = list((await session.scalars(
                    select(TravelEvent).where(TravelEvent.trip_execution_id == uuid.UUID(execution["id"])).order_by(TravelEvent.occurred_at, TravelEvent.id)
                )).all())
                return {
                    "trip_version": trip.version,
                    "state": (state.id, state.status, state.actual_arrived_at, state.actual_started_at, state.actual_ended_at),
                    "events": [(item.id, item.event_type, item.details) for item in events],
                    "completed": [(item.id, item.activity_id, item.status, item.actual_ended_at) for item in completed],
                }

        before = asyncio.run(facts_before())
        accepted = client.post(f"/api/v1/plan-revisions/{revision_id}/accept")
        assert accepted.status_code == 200, accepted.text

        async def facts_after() -> dict:
            async with session_factory() as session:
                trip = await session.get(Trip, DEMO_TRIP_ID)
                state = await session.get(ActivityExecution, uuid.UUID(current["id"]))
                live_execution = await session.get(TripExecution, uuid.UUID(execution["id"]))
                revision = await session.get(PlanRevision, revision_id)
                assert trip is not None and state is not None and live_execution is not None and revision is not None
                completed = list((await session.scalars(select(ActivityExecution).where(
                    ActivityExecution.trip_execution_id == live_execution.id,
                    ActivityExecution.status == "completed",
                ))).all())
                events = list((await session.scalars(select(TravelEvent).where(
                    TravelEvent.trip_execution_id == live_execution.id,
                ).order_by(TravelEvent.occurred_at, TravelEvent.id))).all())
                impact = await evaluate_activity_experience_time_impact(session, live_execution.id, state.id)
                return {
                    "trip_version": trip.version, "revision": revision.status,
                    "execution_version": live_execution.itinerary_version,
                    "state": (state.id, state.status, state.actual_arrived_at, state.actual_started_at, state.actual_ended_at),
                    "events": [(item.id, item.event_type, item.details) for item in events],
                    "completed": [(item.id, item.activity_id, item.status, item.actual_ended_at) for item in completed],
                    "impact_state": impact.impact_state,
                }

        after = asyncio.run(facts_after())
        assert after["trip_version"] == before["trip_version"] + 1
        assert after["revision"] == "accepted"
        assert after["execution_version"] == after["trip_version"]
        assert after["state"] == before["state"]
        assert after["events"] == before["events"]
        assert after["completed"] == before["completed"]
        assert after["impact_state"] != "unavailable"
        progress = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/execution-progress")
        assert progress.status_code == 200
        assert progress.json()["recovery_planning"] is None


def test_experience_recovery_serializes_later_navigation_disruption() -> None:
    """Navigation persists its fact but must not replace an active experience owner."""
    with TestClient(app) as client:
        execution, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        assert _extend(client, current["id"], 480).status_code == 200
        [experience_run] = asyncio.run(_run_rows())
        assert experience_run.status == "queued"

        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        leg = days[0]["route_legs"][0]
        navigation = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",
            json={"trip_execution_id": execution["id"], "from_activity_id": leg["from_activity_id"], "to_activity_id": leg["to_activity_id"]},
        )
        assert navigation.status_code == 201, navigation.text
        state = navigation.json()
        planned_eta = datetime.fromisoformat(state["planned_arrival_at"])
        for sequence in (1, 2, 3):
            observed = datetime.fromisoformat("2026-09-05T10:00:00+08:00") + timedelta(minutes=sequence)
            response = client.post("/api/v1/navigation-observations", json={
                "session_id": state["id"], "itinerary_version": state["itinerary_version"],
                "sequence": sequence, "observed_at": observed.isoformat(),
                "position": {"longitude": 120.154 + sequence / 100_000, "latitude": 30.274},
                "coordinate_system": state["coordinate_system"], "location_accuracy_meters": 8.5,
                "remaining_distance_meters": 1500, "remaining_duration_seconds": 1200,
                "eta": (planned_eta + timedelta(hours=12, minutes=sequence)).isoformat(),
                "route_revision": state["route_revision"], "navigation_status": "navigating", "source": "simulation",
            })
            assert response.status_code == 200, response.text

        async def persisted() -> tuple[PlanningRun, int]:
            async with session_factory() as session:
                active = list((await session.scalars(select(PlanningRun).where(
                    PlanningRun.trip_id == DEMO_TRIP_ID,
                    PlanningRun.trigger_type.in_(("experience_impact", "navigation_disruption")),
                    PlanningRun.status.in_(ACTIVE),
                ))).all())
                disruptions = await session.scalar(select(func.count()).select_from(TripDisruptionEvent).where(
                    TripDisruptionEvent.navigation_session_id == uuid.UUID(state["id"]),
                    TripDisruptionEvent.status == "active",
                ))
                assert len(active) == 1
                return active[0], int(disruptions or 0)

        owner, disruption_count = asyncio.run(persisted())
        assert owner.id == experience_run.id
        assert owner.trigger_type == "experience_impact"
        assert disruption_count == 1


def test_navigation_recovery_serializes_later_experience_impact() -> None:
    """Experience facts remain true even when navigation already owns recovery."""
    with TestClient(app) as client:
        execution, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        leg = days[0]["route_legs"][0]
        created = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",
            json={"trip_execution_id": execution["id"], "from_activity_id": leg["from_activity_id"], "to_activity_id": leg["to_activity_id"]},
        )
        assert created.status_code == 201, created.text
        navigation = created.json()
        planned_eta = datetime.fromisoformat(navigation["planned_arrival_at"])
        for sequence in (1, 2, 3):
            observed = datetime.fromisoformat("2026-09-05T10:00:00+08:00") + timedelta(minutes=sequence)
            response = client.post("/api/v1/navigation-observations", json={
                "session_id": navigation["id"], "itinerary_version": navigation["itinerary_version"],
                "sequence": sequence, "observed_at": observed.isoformat(),
                "position": {"longitude": 120.154 + sequence / 100_000, "latitude": 30.274},
                "coordinate_system": navigation["coordinate_system"], "location_accuracy_meters": 8.5,
                "remaining_distance_meters": 1500, "remaining_duration_seconds": 1200,
                "eta": (planned_eta + timedelta(hours=12, minutes=sequence)).isoformat(),
                "route_revision": navigation["route_revision"], "navigation_status": "navigating", "source": "simulation",
            })
            assert response.status_code == 200, response.text

        assert _extend(client, current["id"], 480).status_code == 200

        async def persisted() -> tuple[PlanningRun, int, str]:
            async with session_factory() as session:
                active = list((await session.scalars(select(PlanningRun).where(
                    PlanningRun.trip_id == DEMO_TRIP_ID,
                    PlanningRun.trigger_type.in_(("experience_impact", "navigation_disruption")),
                    PlanningRun.status.in_(ACTIVE),
                ))).all())
                event_count = await session.scalar(select(func.count(TravelEvent.id)).where(
                    TravelEvent.activity_execution_id == uuid.UUID(current["id"]),
                    TravelEvent.event_type == "user_extend_stay",
                ))
                impact = await evaluate_activity_experience_time_impact(
                    session, uuid.UUID(execution["id"]), uuid.UUID(current["id"])
                )
                assert len(active) == 1
                return active[0], int(event_count or 0), impact.impact_state

        owner, event_count, impact_state = asyncio.run(persisted())
        assert owner.trigger_type == "navigation_disruption"
        assert event_count == 1
        assert impact_state == "infeasible"


def test_concurrent_cross_source_recovery_collision_returns_one_usable_owner() -> None:
    """Two real sessions race; PostgreSQL picks one automatic recovery owner."""
    with TestClient(app) as client:
        execution, current = _start_current(client)
        asyncio.run(_pin_current_start(current["id"]))

        async def record_experience_fact() -> None:
            async with session_factory() as session:
                await extend_stay(session, uuid.UUID(current["id"]), ExtendStayRequest(
                    client_action_id=uuid.uuid4(), extension_minutes=480,
                ))
        asyncio.run(record_experience_fact())

        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        leg = days[0]["route_legs"][0]
        response = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions", json={
            "trip_execution_id": execution["id"], "from_activity_id": leg["from_activity_id"], "to_activity_id": leg["to_activity_id"],
        })
        assert response.status_code == 201, response.text
        navigation_id = uuid.UUID(response.json()["id"])

        async def create_disruption() -> uuid.UUID:
            async with session_factory() as session:
                event = await record_disruption(session, navigation_id, DetectedExecutionEvent(
                    "itinerary_infeasible", "disruption", datetime(2026, 9, 5, 12, tzinfo=ZoneInfo("Asia/Shanghai")),
                    "concurrent-test", {"minimum_slack_minutes": -30},
                ))
                assert event is not None
                return event.id
        disruption_id = asyncio.run(create_disruption())

        async def race() -> tuple[uuid.UUID, uuid.UUID, int, int]:
            ready = asyncio.Event()
            entered = 0
            entered_lock = asyncio.Lock()

            async def gate() -> None:
                nonlocal entered
                async with entered_lock:
                    entered += 1
                    if entered == 2:
                        ready.set()
                await ready.wait()

            async def experience_worker() -> tuple[uuid.UUID, int]:
                async with session_factory() as session:
                    await gate()
                    owner = await ensure_experience_recovery(session, uuid.UUID(current["id"]))
                    assert owner is not None
                    # This SELECT must work even if this session lost the
                    # unique-index race and recovered from its rollback.
                    count = await session.scalar(select(func.count(PlanningRun.id)).where(PlanningRun.trip_id == DEMO_TRIP_ID))
                    return owner.id, int(count or 0)

            async def navigation_worker() -> tuple[uuid.UUID, int]:
                async with session_factory() as session:
                    navigation = await session.get(NavigationSession, navigation_id)
                    disruption = await session.get(TripDisruptionEvent, disruption_id)
                    assert navigation is not None and disruption is not None
                    await gate()
                    owner = await _ensure_recovery_planning_run(session, navigation, disruption)
                    await session.commit()
                    count = await session.scalar(select(func.count(PlanningRun.id)).where(PlanningRun.trip_id == DEMO_TRIP_ID))
                    return owner.id, int(count or 0)

            (experience_owner, experience_count), (navigation_owner, navigation_count) = await asyncio.gather(
                experience_worker(), navigation_worker()
            )
            return experience_owner, navigation_owner, experience_count, navigation_count

        experience_owner, navigation_owner, experience_count, navigation_count = asyncio.run(race())
        assert experience_owner == navigation_owner
        assert experience_count >= 1 and navigation_count >= 1

        async def final_count() -> int:
            async with session_factory() as session:
                return int(await session.scalar(select(func.count(PlanningRun.id)).where(
                    PlanningRun.trip_id == DEMO_TRIP_ID,
                    PlanningRun.trigger_type.in_(("experience_impact", "navigation_disruption")),
                    PlanningRun.status.in_(ACTIVE),
                )) or 0)
        assert asyncio.run(final_count()) == 1
