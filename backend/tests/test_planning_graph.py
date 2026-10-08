import asyncio
import uuid

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.main import app
from app.planning_graph import DraftGeneration, PlanningGraphState, build_planning_graph, should_research_destinations
from app.planning_graph_runtime import execute_planning_run, invoke_compiled_graph
from app.schemas import CandidateActivity, CandidatePlanSnapshot, GroundedIntent, PlanningIntent


def test_existing_itinerary_replan_skips_destination_research_without_place_requests() -> None:
    trip_id = uuid.uuid4()
    intent = PlanningIntent(
        intent_type="modify_day", source_text="请调整当天行程，尽量保留现有活动。",
    )
    grounded = GroundedIntent(
        trip_id=trip_id, primary_intent="replan_trip", operation_types=["replan_trip"],
        target_day_ids=[uuid.uuid4()],
    )
    assert not should_research_destinations({"replan_trip"}, intent, grounded)
    intent.requested_place_queries = ["加入西湖附近的茶馆"]
    assert should_research_destinations({"replan_trip"}, intent, grounded)
    intent.requested_place_queries = []
    assert should_research_destinations({"add_activity"}, intent, grounded)


def test_run_deadline_marks_a_stalled_execution_failed(monkeypatch) -> None:
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    import app.planning_graph_runtime as runtime

    settings = get_settings().model_copy(update={"agent_run_timeout_seconds": 0.01})
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)

    @asynccontextmanager
    async def no_progress_tracking(_run_id):
        yield

    async def stalled_run(*_args, **_kwargs):
        await asyncio.sleep(1)

    failed = AsyncMock()
    monkeypatch.setattr(runtime, "track_progress", no_progress_tracking)
    monkeypatch.setattr(runtime, "_execute_planning_run", stalled_run)
    monkeypatch.setattr(runtime, "_mark_failed", failed)

    result = asyncio.run(runtime.execute_planning_run(uuid.uuid4()))

    assert result.pending_interrupt is None
    failed.assert_awaited_once()
    assert failed.await_args.args[1] == "planning_run_timeout"
    assert failed.await_args.args[3]["timeout_seconds"] == 0.01


class EmptyDraftProvider:
    async def generate(self, state: PlanningGraphState) -> DraftGeneration:
        return DraftGeneration(
            snapshot=CandidatePlanSnapshot(activities=[]),
            provider="test",
            model="deterministic-empty",
            token_usage=0,
        )


class ProvenanceDraftProvider:
    def __init__(self, *, valid: bool) -> None:
        self.valid = valid

    async def generate(self, state: PlanningGraphState) -> DraftGeneration:
        return DraftGeneration(
            snapshot=CandidatePlanSnapshot(
                activities=[], decision_ledger=[] if self.valid else None,
                provenance_parse_errors=[] if self.valid else ["decision_ledger_output_invalid"],
            ), provider="test", model="provenance-matrix", token_usage=1,
        )


async def _setup_test_checkpoints() -> None:
    async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as checkpointer:
        await checkpointer.setup()


def test_shadow_separates_candidate_and_provenance_validation() -> None:
    # A replan of an empty trip is a legal empty candidate; an initial plan is not.
    asyncio.run(_setup_test_checkpoints())
    for candidate_valid in (True, False):
        for ledger_valid in (True, False):
            with TestClient(app) as client:
                trip = client.post("/api/v1/trips", json={
                    "title": "Shadow validation matrix", "destination": "杭州",
                    "start_date": "2026-11-01", "end_date": "2026-11-02",
                    "total_budget_fen": 60000, "daily_budget_fen": 30000,
                }).json()
                run = client.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={
                    "run_type": "replan" if candidate_valid else "initial_plan",
                    "user_request": "重新规划全程" if candidate_valid else "生成完整行程",
                }).json()
                asyncio.run(execute_planning_run(uuid.UUID(run["id"]), provider=ProvenanceDraftProvider(valid=ledger_valid)))
                result = client.get(f"/api/v1/planning-runs/{run['id']}").json()
                response = client.get(f"/api/v1/planning-runs/{run['id']}/revision")
                if candidate_valid:
                    assert result["status"] == "awaiting_confirmation"
                    assert response.status_code == 200
                    summary = response.json()["difference_summary"]
                    assert summary["decision_ledger_status"] == ("validated" if ledger_valid else "invalid")
                    assert summary["decision_summary"]["entries"] == []
                    if not ledger_valid:
                        assert summary["decision_ledger_errors"] == ["decision_ledger_output_invalid"]
                else:
                    assert result["status"] == "failed"
                    assert response.status_code == 404
                    assert "missing_plan_days" in {item["code"] for item in result["error_details"]["validation_errors"]}


def test_enforced_mode_still_blocks_invalid_ledger(monkeypatch) -> None:
    import app.planning_graph as graph_module
    settings = get_settings().model_copy(update={"decision_ledger_validation_mode": "enforced"})
    monkeypatch.setattr(graph_module, "get_settings", lambda: settings)
    asyncio.run(_setup_test_checkpoints())
    with TestClient(app) as client:
        _, run = _create_trip_and_run(client, "重新规划全程")
        asyncio.run(execute_planning_run(uuid.UUID(run["id"]), provider=ProvenanceDraftProvider(valid=False)))
        result = client.get(f"/api/v1/planning-runs/{run['id']}").json()
        assert result["status"] == "failed"
        assert "decision_ledger_output_invalid" in {item["code"] for item in result["error_details"]["validation_errors"]}
        assert client.get(f"/api/v1/planning-runs/{run['id']}/revision").status_code == 404


class CorrectingDraftProvider:
    def __init__(self, place_id: str, source_id: str, day_date: str, cost: int) -> None:
        self.place_id = uuid.UUID(place_id)
        self.source_id = uuid.UUID(source_id)
        self.day_date = day_date
        self.cost = cost
        self.calls = 0

    async def generate(self, state: PlanningGraphState) -> DraftGeneration:
        self.calls += 1
        start_time = "23:30:00" if self.calls == 1 else "10:00:00"
        snapshot = CandidatePlanSnapshot(
            activities=[
                CandidateActivity(
                    candidate_id="review-target",
                    day_date=self.day_date,
                    place_candidate_id=self.place_id,
                    planned_start_time=start_time,
                    duration_minutes=60,
                    estimated_cost_fen=self.cost,
                    transport_mode_to_here="walk",
                    source_ids=[self.source_id],
                )
            ]
        )
        return DraftGeneration(
            snapshot=snapshot,
            provider="test",
            model="correcting-provider",
            token_usage=5,
        )


class NeverCorrectingDraftProvider(CorrectingDraftProvider):
    async def generate(self, state: PlanningGraphState) -> DraftGeneration:
        self.calls += 1
        snapshot = CandidatePlanSnapshot(
            activities=[
                CandidateActivity(
                    candidate_id="invalid-after-review",
                    day_date=self.day_date,
                    place_candidate_id=self.place_id,
                    planned_start_time="23:30:00",
                    duration_minutes=60,
                    estimated_cost_fen=self.cost,
                    transport_mode_to_here="walk",
                    source_ids=[self.source_id],
                )
            ]
        )
        return DraftGeneration(
            snapshot=snapshot,
            provider="test",
            model="never-correcting-provider",
            token_usage=5,
        )


def _create_trip_and_run(client: TestClient, request: str) -> tuple[dict, dict]:
    trip_response = client.post(
        "/api/v1/trips",
        json={
            "title": "LangGraph recovery trip",
            "destination": "南昌市",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "total_budget_fen": 60000,
            "daily_budget_fen": 30000,
        },
    )
    assert trip_response.status_code == 201
    trip = trip_response.json()
    run_response = client.post(
        f"/api/v1/trips/{trip['id']}/planning-runs",
        # EmptyDraftProvider tests checkpoint/approval mechanics using an empty
        # replan. A real initial plan now has to cover its requested dates.
        json={"run_type": "replan", "user_request": request},
    )
    assert run_response.status_code == 201
    return trip, run_response.json()


async def _get_run(run_id: str) -> PlanningRun:
    async with session_factory() as session:
        run = await session.get(PlanningRun, uuid.UUID(run_id))
        assert run is not None
        return run


def test_graph_clarifies_before_drafting() -> None:
    with TestClient(app) as client:
        _, created = _create_trip_and_run(client, "调整一下")

        async def scenario() -> None:
            graph = build_planning_graph(InMemorySaver(), EmptyDraftProvider())
            run = await _get_run(created["id"])
            first = await invoke_compiled_graph(graph, run)
            assert first.pending_interrupt is not None
            assert first.pending_interrupt["kind"] == "clarification"

            resumed = await invoke_compiled_graph(
                graph,
                run,
                resume={"decision": "clarify", "answer": "调整第一天"},
            )
            assert resumed.pending_interrupt is not None
            assert resumed.pending_interrupt["kind"] == "approval"

        asyncio.run(scenario())
        fetched = client.get(f"/api/v1/planning-runs/{created['id']}")
        assert fetched.json()["status"] == "awaiting_confirmation"


def test_postgres_checkpoint_recovers_through_decision_api() -> None:
    with TestClient(app) as client:
        _, created = _create_trip_and_run(client, "帮我规划行程")

        async def pause_with_first_connection() -> dict:
            settings = get_settings()
            async with AsyncPostgresSaver.from_conn_string(
                settings.checkpoint_database_url
            ) as checkpointer:
                await checkpointer.setup()
                graph = build_planning_graph(checkpointer, EmptyDraftProvider())
                run = await _get_run(created["id"])
                result = await invoke_compiled_graph(graph, run)
                assert result.pending_interrupt is not None
                return result.pending_interrupt

        pending = asyncio.run(pause_with_first_connection())
        assert pending["kind"] == "approval"

        # The endpoint opens a new PostgreSQL saver connection and resumes the graph.
        accepted = client.post(
            f"/api/v1/planning-runs/{created['id']}/decision",
            json={"decision": "accept"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["run"]["status"] == "accepted"
        assert accepted.json()["pending_interrupt"] is None


def test_decision_rejects_the_wrong_resume_kind() -> None:
    with TestClient(app) as client:
        _, created = _create_trip_and_run(client, "帮我规划行程")
        response = client.post(
            f"/api/v1/planning-runs/{created['id']}/decision",
            json={"decision": "accept"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "planning run is not waiting for a decision"


def test_graph_allows_one_bounded_correction_after_validation_failure() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        assert client.post("/api/v1/demo/reset").status_code == 200
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        candidate = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/candidates"
        ).json()[0]
        created = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"run_type": "replan", "user_request": "重新规划全程"},
        ).json()
        provider = CorrectingDraftProvider(
            candidate["id"],
            candidate["source"]["id"],
            day["date"],
            candidate["estimated_cost_fen"],
        )

        async def scenario() -> dict:
            graph = build_planning_graph(InMemorySaver(), provider)
            run = await _get_run(created["id"])
            result = await invoke_compiled_graph(graph, run)
            assert result.pending_interrupt is not None
            return result.pending_interrupt

        pending = asyncio.run(scenario())
        assert pending["kind"] == "approval"
        assert provider.calls == 2
        run = client.get(f"/api/v1/planning-runs/{created['id']}").json()
        assert run["status"] == "awaiting_confirmation"
        assert run["token_usage"] == 10
        revision = client.get(
            f"/api/v1/planning-runs/{created['id']}/revision"
        ).json()
        assert revision["difference_summary"]["review_count"] == 1


def test_graph_stops_after_the_single_correction_budget() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        assert client.post("/api/v1/demo/reset").status_code == 200
        day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]
        candidate = client.get(
            f"/api/v1/trips/{DEMO_TRIP_ID}/candidates"
        ).json()[0]
        created = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"run_type": "replan", "user_request": "重新规划全程"},
        ).json()
        provider = NeverCorrectingDraftProvider(
            candidate["id"],
            candidate["source"]["id"],
            day["date"],
            candidate["estimated_cost_fen"],
        )

        async def scenario() -> None:
            settings = get_settings()
            async with AsyncPostgresSaver.from_conn_string(
                settings.checkpoint_database_url
            ) as checkpointer:
                await checkpointer.setup()
            await execute_planning_run(uuid.UUID(created["id"]), provider=provider)

        asyncio.run(scenario())
        run = client.get(f"/api/v1/planning-runs/{created['id']}").json()
        assert provider.calls == 2
        assert run["status"] == "failed"
        assert run["error_code"] == "planner_constraints_unsatisfied"
        assert run["error_details"]["validation_errors"]
        assert run["error_details"]["validation_errors"][0]["message"]
        assert client.get(
            f"/api/v1/planning-runs/{created['id']}/revision"
        ).status_code == 404


def test_rejection_preserves_the_formal_plan() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        assert client.post("/api/v1/demo/reset").status_code == 200
        before = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        created = client.post(
            f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",
            json={"run_type": "replan", "user_request": "重新规划全程"},
        ).json()

        async def scenario() -> None:
            graph = build_planning_graph(InMemorySaver(), EmptyDraftProvider())
            run = await _get_run(created["id"])
            first = await invoke_compiled_graph(graph, run)
            assert first.pending_interrupt is not None
            assert first.pending_interrupt["kind"] == "approval"
            resumed = await invoke_compiled_graph(
                graph, run, resume={"decision": "reject"}
            )
            assert resumed.pending_interrupt is None

        asyncio.run(scenario())
        run = client.get(f"/api/v1/planning-runs/{created['id']}").json()
        after = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        assert run["status"] == "rejected"
        assert after == before


def test_graph_repairs_travel_time_before_requesting_another_model_draft() -> None:
    from app.demo_seed import DEMO_TRIP_ID

    class OverlappingProvider:
        calls = 0

        async def generate(self, state):
            self.calls += 1
            return DraftGeneration(
                snapshot=CandidatePlanSnapshot(activities=[CandidateActivity(
                    candidate_id=f"stop-{index}", day_date=day_date,
                    place_candidate_id=place["id"], planned_start_time=start,
                    duration_minutes=60, estimated_cost_fen=place["estimated_cost_fen"],
                    transport_mode_to_here="walk", source_ids=[place["source"]["id"]],
                ) for index, (place, start) in enumerate(zip(candidates, ["09:00", "10:00"], strict=True))]),
                provider="test", model="overlapping", token_usage=1,
            )

    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        before = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        candidates = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/candidates").json()[:2]
        day_date = before[0]["date"]
        run = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs", json={"run_type": "replan", "user_request": "重新规划完整行程"}).json()
        provider = OverlappingProvider()
        asyncio.run(execute_planning_run(uuid.UUID(run["id"]), provider=provider))
        persisted = client.get(f"/api/v1/planning-runs/{run['id']}").json()
        assert persisted["status"] == "awaiting_confirmation"
        revision = client.get(f"/api/v1/planning-runs/{run['id']}/revision").json()
        assert provider.calls == 1
        assert revision["validation_result"]["valid"] is True
        assert revision["validation_result"]["warnings"][0]["code"] == "route_schedule_adjusted"
        assert revision["difference_summary"]["schedule_adjustments"]
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json() == before
        assert client.post(f"/api/v1/plan-revisions/{revision['id']}/accept").status_code == 200


def test_initial_plan_cannot_finish_without_covering_requested_dates() -> None:
    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={
            "title": "Initial coverage check", "destination": "杭州",
            "start_date": "2026-11-01", "end_date": "2026-11-02",
            "total_budget_fen": 60000, "daily_budget_fen": 30000,
        }).json()
        run = client.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={
            "run_type": "initial_plan", "user_request": "生成完整行程",
        }).json()
        asyncio.run(execute_planning_run(uuid.UUID(run["id"]), provider=EmptyDraftProvider()))
        result = client.get(f"/api/v1/planning-runs/{run['id']}").json()
        assert result["status"] == "failed"
        issue = next(item for item in result["error_details"]["validation_errors"] if item["code"] == "missing_plan_days")
        assert issue["details"]["missing_dates"] == ["2026-11-01", "2026-11-02"]
        assert client.get(f"/api/v1/planning-runs/{run['id']}/revision").status_code == 404
