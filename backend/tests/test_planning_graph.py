import asyncio
import uuid

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.main import app
from app.planning_graph import DraftGeneration, PlanningGraphState, build_planning_graph
from app.planning_graph_runtime import invoke_compiled_graph
from app.schemas import CandidateActivity, CandidatePlanSnapshot


class EmptyDraftProvider:
    async def generate(self, state: PlanningGraphState) -> DraftGeneration:
        return DraftGeneration(
            snapshot=CandidatePlanSnapshot(activities=[]),
            provider="test",
            model="deterministic-empty",
            token_usage=0,
        )


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
        json={"user_request": request},
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
        _, created = _create_trip_and_run(client, "天气怎么样")

        async def scenario() -> None:
            graph = build_planning_graph(InMemorySaver(), EmptyDraftProvider())
            run = await _get_run(created["id"])
            first = await invoke_compiled_graph(graph, run)
            assert first.pending_interrupt is not None
            assert first.pending_interrupt["kind"] == "clarification"

            resumed = await invoke_compiled_graph(
                graph,
                run,
                resume={"decision": "clarify", "answer": "帮我规划行程"},
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
