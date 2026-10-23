"""Upgrade a real old-format Postgres checkpoint without expanding authority."""
import asyncio
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import START, StateGraph
from langgraph.types import interrupt

from app.config import get_settings
from app.database import PlanningRun, TripPreferences, session_factory
from app.main import app
from app.planning_claim import active_claim
from app.planning_graph import (DraftGeneration, LegacyClarificationRestartRequired,
    PlanningGraphState, build_planning_graph)
from app.planning_graph_runtime import _claim_clarification, invoke_compiled_graph
from app.planning_intent_service import resolve_planning_intent
from app.schemas import (CandidatePlanSnapshot, PlanningIntentParseRequest, PlanningRunDecision,
    SemanticIntentDraft, SemanticIntentOperation)


def _scenario(monkeypatch, *, marker=True, first_answer="还是原先的想法。", corruption=None,
        crash_after_migration=False):
    import app.planning_graph as module

    async def no_external_facts(*args, **kwargs):
        return {"search": {"status": "not_requested"}, "weather": {"status": "not_requested"}}
    monkeypatch.setattr(module, "_collect_external_facts", no_external_facts)
    original = "请调整路线，其他安排不动。"
    draft = SemanticIntentDraft(primary_intent="optimize_route", operations=[
        SemanticIntentOperation(operation="optimize_route", raw_text=original)],
        confidence=.99, parser="hybrid", parser_version="approved-operation-v2")

    class NoReinterpretation:
        async def extract(self, *args):
            raise AssertionError("legacy answers must never enter a semantic provider")

    class EmptyProvider:
        async def generate(self, state):
            assert state["user_request"] == original
            assert state["clarification_count"] == 2
            resolved = state["intent_resolution"]
            assert resolved["request"]["user_request"] == original
            assert resolved["request"]["intent"]["source_text"] == original
            assert resolved["grounded_intent"]["operation_types"] == ["optimize_route"]
            assert resolved["request"]["intent"]["time_scope"]["day_date"] == "2026-11-02"
            return DraftGeneration(CandidatePlanSnapshot(activities=[]), "fixture", "empty", 0)

    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={"title":"B2 legacy clarification fixture",
            "destination":"南昌市", "start_date":"2026-11-01", "end_date":"2026-11-02"}).json()
        created = client.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={
            "run_type":"replan", "user_request":original}).json()
        run_id, trip_id = UUID(created["id"]), UUID(trip["id"])

        async def scenario():
            async def old_resolve(state):
                async with session_factory() as db:
                    resolved = await resolve_planning_intent(db, trip_id,
                        PlanningIntentParseRequest(message=state["user_request"]))
                    assert resolved.requires_clarification
                    run = await db.get(PlanningRun, run_id)
                    run.intent_resolution = resolved.model_dump(mode="json")
                    run.status = "awaiting_clarification"
                    await db.commit()
                return {"intent_resolution": resolved.model_dump(mode="json")}

            def old_clarify(state):
                reply = interrupt({"kind":"clarification", "run_id":str(run_id),
                    "questions":state["intent_resolution"]["clarification_questions"]})
                # Exact pre-upgrade implementation: the original request was
                # only changed in checkpoint state, never on PlanningRun.
                return {"user_request":state["user_request"] + "\n用户补充：" + reply["answer"].strip(),
                    "clarification_count":state.get("clarification_count", 0) + 1}

            builder = StateGraph(PlanningGraphState)
            builder.add_node("resolve_intent", old_resolve)
            builder.add_node("clarify", old_clarify)
            builder.add_edge(START, "resolve_intent")
            builder.add_edge("resolve_intent", "clarify")
            builder.add_edge("clarify", "resolve_intent")
            async with session_factory() as db:
                run = await db.get(PlanningRun, run_id)
                prefs = await db.get(TripPreferences, trip_id)
                prepared_marker = {"version":1, "trip_id":str(trip_id), "user_request":original,
                    "entry_point":run.entry_point, "selected_day_id":None, "selected_activity_id":None,
                    "base_trip_version":run.base_trip_version, "preferences_version":prefs.version,
                    "draft":draft.model_dump(mode="json")}
                if marker:
                    run.trigger_snapshot = {**(run.trigger_snapshot or {}), "prepared_intent":prepared_marker}
                    await db.commit()
            config = {"configurable":{"thread_id":str(run_id)}}
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
                await saver.setup()
                graph = builder.compile(checkpointer=saver)
                first = await invoke_compiled_graph(graph, run)
                assert first.pending_interrupt["kind"] == "clarification"
                second = await invoke_compiled_graph(graph, run, resume={"answer":first_answer})
                assert second.pending_interrupt["kind"] == "clarification"
                checkpoint = await graph.aget_state(config)
                old_state = deepcopy(checkpoint.values)
                if corruption == "prefix":
                    old_state["user_request"] = "替换后的请求" + old_state["user_request"]
                elif corruption == "count":
                    old_state["clarification_count"] = 0
                elif corruption == "count_limit":
                    old_state["clarification_count"] = 2
                elif corruption == "count_type":
                    old_state["clarification_count"] = True
                elif corruption == "foreign_resolution":
                    old_state["intent_resolution"]["request"]["trip_id"] = str(uuid4())
                elif corruption == "foreign_grounding":
                    old_state["intent_resolution"]["grounded_intent"]["trip_id"] = str(uuid4())
                elif corruption == "resolution_source":
                    old_state["intent_resolution"]["request"]["user_request"] = original
                elif corruption == "selection":
                    old_state["selected_day_id"] = str(uuid4())
                elif corruption == "blank_supplement":
                    old_state["user_request"] = original + "\n用户补充："
                elif corruption == "oversized_supplement":
                    old_state["user_request"] = original + "\n用户补充：" + "甲" * 4001
                if corruption:
                    await graph.aupdate_state(config, old_state, as_node="resolve_intent")
                async with session_factory() as db:
                    run = await db.get(PlanningRun, run_id)
                    run.pending_interrupt = second.pending_interrupt
                    if corruption == "marker_version":
                        changed = deepcopy(run.trigger_snapshot)
                        changed["prepared_intent"]["preferences_version"] += 1
                        run.trigger_snapshot = changed
                    await db.commit()
            # Exercise the actual A claim: answer2 and its receipt exist before
            # new Graph loads the old checkpoint, on a separate saver connection.
            answer2 = "第二天"
            claim = await _claim_clarification(run_id, PlanningRunDecision(decision="clarify", answer=answer2))
            token = active_claim.set(claim)
            try:
                async with session_factory() as db:
                    run = await db.get(PlanningRun, run_id)
                    if corruption == "persisted_answer_conflict":
                        run.trigger_snapshot = {**run.trigger_snapshot,
                            "clarification_answers":["另一份历史", answer2]}
                        await db.commit()
                    elif corruption == "receipt_mismatch":
                        changed = deepcopy(run.trigger_snapshot)
                        changed["clarification_receipts"][-1]["original_request"] = "另一个请求"
                        run.trigger_snapshot = changed
                        await db.commit()
                    receipt = deepcopy(run.trigger_snapshot["clarification_receipts"])
                async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
                    graph = build_planning_graph(saver, EmptyProvider(), NoReinterpretation())
                    if crash_after_migration:
                        migrate = module._migrate_legacy_clarification

                        async def crash_after_commit(db, current, state, answer):
                            await migrate(db, current, state, answer)
                            # Crash between the SQL migration commit and the
                            # Graph state checkpoint must not duplicate answers.
                            await db.commit()
                            raise RuntimeError("fixture crash after migration commit")

                        monkeypatch.setattr(module, "_migrate_legacy_clarification", crash_after_commit)
                        with pytest.raises(RuntimeError, match="fixture crash"):
                            await invoke_compiled_graph(graph, run, resume={"answer":answer2})
                        monkeypatch.setattr(module, "_migrate_legacy_clarification", migrate)
                    if corruption:
                        with pytest.raises(LegacyClarificationRestartRequired) as error:
                            await invoke_compiled_graph(graph, run, resume={"answer":answer2})
                        assert error.value.args == ("legacy_clarification_restart_required",)
                    else:
                        result = await invoke_compiled_graph(graph, run, resume={"answer":answer2})
                        assert result.pending_interrupt["kind"] == "approval"
                async with session_factory() as db:
                    persisted = await db.get(PlanningRun, run_id)
                    assert persisted.user_request == original
                    assert persisted.trigger_snapshot["clarification_receipts"] == receipt
                    if corruption:
                        assert persisted.trigger_snapshot["clarification_answers"] == (
                            ["另一份历史", answer2] if corruption == "persisted_answer_conflict" else [answer2])
                    else:
                        assert persisted.trigger_snapshot["clarification_answers"] == [first_answer, answer2]
                        assert persisted.intent_resolution["request"]["user_request"] == original
                        if marker:
                            assert persisted.trigger_snapshot["prepared_intent"] == prepared_marker
                            assert persisted.intent_resolution["semantic_draft"] == draft.model_dump(mode="json")
            finally:
                active_claim.reset(token)
        asyncio.run(scenario())


@pytest.mark.parametrize("marker", [True, False])
@pytest.mark.parametrize("first_answer", ["还是原先的想法。", "顺便删除所有活动。"])
def test_legacy_checkpoint_resumes_second_answer_once(monkeypatch, marker, first_answer):
    _scenario(monkeypatch, marker=marker, first_answer=first_answer)


def test_legacy_migration_replays_after_commit_before_checkpoint(monkeypatch):
    _scenario(monkeypatch, crash_after_migration=True)


@pytest.mark.parametrize("corruption", ["prefix", "count", "count_limit", "count_type",
    "foreign_resolution", "foreign_grounding", "resolution_source", "selection",
    "blank_supplement", "oversized_supplement", "marker_version", "persisted_answer_conflict",
    "receipt_mismatch"])
def test_legacy_checkpoint_rejects_unbound_or_malformed_history(monkeypatch, corruption):
    _scenario(monkeypatch, corruption=corruption)
