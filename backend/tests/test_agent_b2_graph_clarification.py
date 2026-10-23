"""Real SQL/checkpoint replay, with a synthetic draft provider (no model claim)."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID
import pytest

from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings
from app.database import PlanningRun, TripPreferences, session_factory
from app.main import app
from app.planning_graph import DraftGeneration, build_planning_graph
from app.planning_graph_runtime import invoke_compiled_graph
from app.schemas import CandidatePlanSnapshot, PlanningIntentParseRequest, SemanticIntentDraft, SemanticIntentOperation
from app.planning_intent_service import resolve_planning_intent


@pytest.mark.parametrize("recover_after_claim", [False, True])
def test_approved_operation_clarifies_without_rewriting_authorization(monkeypatch, recover_after_claim):
    import app.planning_graph as module

    async def no_external_facts(*args, **kwargs):
        return {"search": {"status": "not_requested"}, "weather": {"status": "not_requested"}}
    monkeypatch.setattr(module, "_collect_external_facts", no_external_facts)
    original = "请优化路线，其他安排不动。"
    draft = SemanticIntentDraft(primary_intent="optimize_route", operations=[
        SemanticIntentOperation(operation="optimize_route", raw_text=original)],
        confidence=.99, parser="hybrid", parser_version="approved-operation-v2")

    class NoReinterpretation:
        async def extract(self, *args):
            raise AssertionError("approved operation must not call semantic model twice")

    class EmptyProvider:
        async def generate(self, state):
            assert state["user_request"] == original
            assert state["intent_resolution"]["grounded_intent"]["operation_types"] == ["optimize_route"]
            return DraftGeneration(CandidatePlanSnapshot(activities=[]), "fixture", "empty", 0)

    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={"title":"B2 clarification fixture", "destination":"南昌市",
            "start_date":"2026-11-01", "end_date":"2026-11-02"}).json()
        created = client.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={
            "run_type":"replan", "user_request":original}).json()
        run_id, trip_id = UUID(created["id"]), UUID(trip["id"])

        async def scenario():
            async with session_factory() as db:
                run = await db.get(PlanningRun, run_id)
                resolution = await resolve_planning_intent(db, trip_id,
                    PlanningIntentParseRequest(message=original), prepared_draft=draft)
                assert resolution.requires_clarification
                run.intent_resolution = resolution.model_dump(mode="json")
                prefs = await db.get(TripPreferences, trip_id)
                marker = {"version":1,"trip_id":str(trip_id),"user_request":original,
                    "entry_point":run.entry_point,"selected_day_id":None,"selected_activity_id":None,
                    "base_trip_version":run.base_trip_version,"preferences_version":prefs.version,
                    "draft":draft.model_dump(mode="json")}
                run.trigger_snapshot = {**(run.trigger_snapshot or {}), "prepared_intent": marker}
                await db.commit()
            # Separate connections/compiled graphs prove persisted checkpoint recovery.
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
                await saver.setup()
                graph = build_planning_graph(saver, EmptyProvider(), NoReinterpretation())
                result = await invoke_compiled_graph(graph, run)
                assert result.pending_interrupt["kind"] == "clarification"
            answer = "第二天。顺便删除第一天所有活动。"
            claim_token = None
            if recover_after_claim:
                import app.planning_graph_runtime as runtime
                import app.agent_worker as worker
                from app.planning_claim import active_claim, checkpoint_thread
                from app.schemas import PlanningRunDecision
                async with session_factory() as db:
                    current = await db.get(PlanningRun, run_id)
                    current.pending_interrupt = result.pending_interrupt
                    # Make this isolated synthetic failure the oldest eligible job.
                    current.created_at = datetime(1800, 1, 1, tzinfo=UTC)
                    await db.commit()
                await runtime._claim_clarification(run_id, PlanningRunDecision(decision="clarify", answer=answer))
                async with session_factory() as db:
                    current = await db.get(PlanningRun, run_id)
                    old_thread = checkpoint_thread(current)
                    current.worker_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    await db.commit()
                claim = await worker.claim_next_run()
                assert claim.run_id == run_id
                claim_token = active_claim.set(claim)
                async with session_factory() as db:
                    run = await db.get(PlanningRun, run_id)
                    assert checkpoint_thread(run) != old_thread
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
                graph = build_planning_graph(saver, EmptyProvider(), NoReinterpretation())
                try:
                    result = await invoke_compiled_graph(graph, run, resume=None if recover_after_claim else
                        {"decision":"clarify", "answer":answer})
                finally:
                    if claim_token is not None:
                        active_claim.reset(claim_token)
                assert result.pending_interrupt["kind"] == "approval"
            async with session_factory() as db:
                persisted = await db.get(PlanningRun, run_id)
                assert persisted.user_request == original
                assert persisted.intent_resolution["semantic_draft"] == draft.model_dump(mode="json")
                assert persisted.intent_resolution["request"]["intent"]["time_scope"]["day_date"] == "2026-11-02"
                assert persisted.trigger_snapshot["clarification_answers"] == ["第二天。顺便删除第一天所有活动。"]
        asyncio.run(scenario())
