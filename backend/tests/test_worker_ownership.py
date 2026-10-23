"""Real PostgreSQL stale-worker counterexamples, not lease-duration mocks."""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import app.agent_worker as worker
import app.planning_graph_runtime as runtime
import app.planning_progress as progress
from app.database import PlanningRun
from app.planning_graph import _set_run_status
from app.planning_run_repository import save_plan_revision
from app.schemas import CandidatePlanSnapshot
from test_planning_transactions import database, new_trip


async def queued_run(sessions):
    tid = await new_trip(sessions)
    async with sessions() as db:
        run = PlanningRun(trip_id=tid, run_type="replan", status="queued",
            user_request="synthetic lease probe", base_trip_version=1,
            created_at=datetime(2000, 1, 1, tzinfo=UTC))
        db.add(run)
        await db.commit()
        return run.id


async def expire(sessions, rid):
    async with sessions() as db:
        row = await db.get(PlanningRun, rid)
        row.worker_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()


def test_reclaim_uses_unique_identity_even_on_same_host(monkeypatch):
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(worker, "session_factory", sessions)
            rid = await queued_run(sessions)
            await worker.claim_next_run()
            async with sessions() as db:
                old_id = (await db.get(PlanningRun, rid)).worker_id
            await expire(sessions, rid)
            await worker.claim_next_run()
            async with sessions() as db:
                assert (await db.get(PlanningRun, rid)).worker_id != old_id
    asyncio.run(scenario())


def test_expired_worker_cannot_resurrect_its_own_lease(monkeypatch):
    from app.planning_claim import active_claim, LostPlanningClaim
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(worker, "session_factory", sessions)
            monkeypatch.setattr(progress, "session_factory", sessions)
            rid = await queued_run(sessions)
            claim = await worker.claim_next_run()
            await expire(sessions, rid)
            token = active_claim.set(claim)
            try:
                with pytest.raises(LostPlanningClaim):
                    await progress.pulse(rid)
            finally:
                active_claim.reset(token)
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                assert row.worker_lease_expires_at < datetime.now(UTC)
                row.status = "cancelled"
                await db.commit()
    asyncio.run(scenario())


@pytest.mark.parametrize("alive", [False, True])
def test_orphaned_null_lease_recovers_only_after_liveness_grace(monkeypatch, alive):
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(worker, "session_factory", sessions)
            rid = await queued_run(sessions)
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                row.status = "planning"
                row.heartbeat_at = datetime.now(UTC) if alive else datetime(2000, 1, 1, tzinfo=UTC)
                await db.commit()
            claim = await worker.claim_next_run()
            if alive:
                assert claim is None or claim.run_id != rid
            else:
                assert claim.run_id == rid
    asyncio.run(scenario())


def test_cancelling_live_execution_makes_its_claim_recoverable(monkeypatch):
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(worker, "session_factory", sessions)
            rid = await queued_run(sessions)
            entered = asyncio.Event()
            async def stalled(_run_id):
                entered.set()
                await asyncio.Event().wait()
            monkeypatch.setattr(worker, "execute_planning_run", stalled)
            first = await worker.claim_next_run()
            task = asyncio.create_task(worker.execute_claimed_run(first))
            await asyncio.wait_for(entered.wait(), 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            replacement = await worker.claim_next_run()
            assert replacement.run_id == rid and replacement.token != first.token
    asyncio.run(scenario())


def test_heartbeat_stops_normally_at_current_owner_interrupt(monkeypatch):
    from app.planning_claim import active_claim
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(worker, "session_factory", sessions)
            monkeypatch.setattr(progress, "session_factory", sessions)
            rid = await queued_run(sessions)
            claim = await worker.claim_next_run()
            async with sessions() as db:
                (await db.get(PlanningRun, rid)).status = "awaiting_confirmation"
                await db.commit()
            token = active_claim.set(claim)
            try:
                assert await progress.pulse(rid) is False
            finally:
                active_claim.reset(token)
            async with sessions() as db:
                assert (await db.get(PlanningRun, rid)).worker_id == claim.token
    asyncio.run(scenario())


def test_heartbeat_ownership_loss_cancels_external_work(monkeypatch):
    from app.planning_claim import LostPlanningClaim
    async def lost(_run_id):
        raise LostPlanningClaim("synthetic reclaim")
    monkeypatch.setattr(progress, "pulse", lost)
    async def scenario():
        async with progress.track_progress("synthetic"):
            await asyncio.Event().wait()
    with pytest.raises(LostPlanningClaim):
        asyncio.run(scenario())


def test_api_clarification_claim_is_fenced_after_worker_reclaim(monkeypatch):
    from app.planning_claim import active_claim, CHECKPOINT_THREAD, LostPlanningClaim
    from app.schemas import PlanningRunDecision
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(worker, "session_factory", sessions)
            monkeypatch.setattr(runtime, "session_factory", sessions)
            monkeypatch.setattr(progress, "session_factory", sessions)
            rid = await queued_run(sessions)
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                row.status = "awaiting_clarification"
                row.pending_interrupt = {"kind": "clarification", "questions": ["哪一天？"], "run_id": str(rid)}
                row.trigger_snapshot = {CHECKPOINT_THREAD: "existing-interrupted-thread"}
                await db.commit()
            entered, release = asyncio.Event(), asyncio.Event()
            observed = []
            async def stalled(run_id, **_kwargs):
                entered.set()
                claim = active_claim.get()
                observed.append(claim)
                assert claim is not None, "API clarification has no execution claim"
                async with sessions() as db:
                    current = await db.get(PlanningRun, rid)
                    assert current.worker_id == claim.token
                    assert current.trigger_snapshot[CHECKPOINT_THREAD] == "existing-interrupted-thread"
                    current.status = "planning"
                    await db.commit()
                await release.wait()
                await runtime._mark_failed(run_id, "stale_api", "obsolete clarification")
            monkeypatch.setattr(runtime, "_execute_planning_run", stalled)
            task = asyncio.create_task(runtime.execute_planning_run(rid,
                decision=PlanningRunDecision(decision="clarify", answer="第一天")))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                # Let the resumed execution reach its paused provider stage.
                for _ in range(20):
                    async with sessions() as db:
                        if (await db.get(PlanningRun, rid)).status == "planning":
                            break
                    await asyncio.sleep(.01)
                assert observed and observed[0] is not None
                await expire(sessions, rid)
                replacement = await worker.claim_next_run()
                assert replacement.run_id == rid
                release.set()
                with pytest.raises(LostPlanningClaim):
                    await task
                async with sessions() as db:
                    current = await db.get(PlanningRun, rid)
                    assert current.worker_id == replacement.token and current.status == "researching"
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("ready", [False, True])
def test_clarification_claim_requires_checkpoint_and_excludes_duplicate(monkeypatch, ready):
    from app.schemas import PlanningRunDecision
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(runtime, "session_factory", sessions)
            rid = await queued_run(sessions)
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                row.status = "awaiting_clarification"
                row.pending_interrupt = {"kind": "clarification"} if ready else None
                await db.commit()
            decision = PlanningRunDecision(decision="clarify", answer="第一天")
            if ready:
                claim = await runtime._claim_clarification(rid, decision)
                with pytest.raises(ValueError, match="not waiting"):
                    await runtime._claim_clarification(rid, decision)
            else:
                with pytest.raises(ValueError, match="not ready"):
                    await runtime._claim_clarification(rid, decision)
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                assert row.status == ("researching" if ready else "awaiting_clarification")
                assert row.worker_id == (claim.token if ready else None)
    asyncio.run(scenario())


@pytest.mark.parametrize("window", ["claimed", "planning"])
def test_reclaim_keeps_accepted_clarification_after_api_exit(monkeypatch, window):
    from app.schemas import PlanningRunDecision
    from app.planning_claim import checkpoint_thread
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(runtime, "session_factory", sessions)
            monkeypatch.setattr(worker, "session_factory", sessions)
            rid = await queued_run(sessions)
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                row.status = "awaiting_clarification"
                row.pending_interrupt = {"kind": "clarification", "questions": ["哪一天？"], "run_id": str(rid)}
                await db.commit()
                original = row.user_request
            await runtime._claim_clarification(rid, PlanningRunDecision(decision="clarify", answer="第一天"))
            if window == "planning":
                async with sessions() as db:
                    (await db.get(PlanningRun, rid)).status = "planning"
                    await db.commit()
            await expire(sessions, rid)
            replacement = await worker.claim_next_run()
            assert replacement.run_id == rid
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                assert row.user_request == original
                assert row.trigger_snapshot["clarification_answers"] == ["第一天"]
                receipt = row.trigger_snapshot["clarification_receipts"][0]
                assert receipt["questions"] == ["哪一天？"] and receipt["answer"] == "第一天"
                assert receipt["original_request"] == original
                observed = {}
                class Probe:
                    async def ainvoke(self, value, config):
                        observed.update(value)
                        assert config["configurable"]["thread_id"] == checkpoint_thread(row)
                        return {}
                await runtime.invoke_compiled_graph(Probe(), row)
                assert observed["clarification_count"] == 1
    asyncio.run(scenario())


def test_unmigratable_legacy_clarification_returns_recoverable_409(monkeypatch):
    import httpx
    from app.main import app
    from app.planning_graph import LegacyClarificationRestartRequired
    async def scenario():
        async with database() as sessions:
            monkeypatch.setattr(runtime, "session_factory", sessions)
            monkeypatch.setattr(progress, "session_factory", sessions)
            rid = await queued_run(sessions)
            pending = {"kind":"clarification", "questions":["哪一天？"], "run_id":str(rid)}
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                row.status = "awaiting_clarification"
                row.pending_interrupt = pending
                await db.commit()
                original = row.user_request
            async def unbound_checkpoint(*_args, **_kwargs):
                raise LegacyClarificationRestartRequired()
            monkeypatch.setattr(runtime, "invoke_compiled_graph", unbound_checkpoint)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(f"/api/v1/planning-runs/{rid}/decision",
                    json={"decision":"clarify", "answer":"第二天"})
                repeated = await client.post(f"/api/v1/planning-runs/{rid}/decision",
                    json={"decision":"clarify", "answer":"第三天"})
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "legacy_clarification_restart_required"
            assert repeated.status_code == 409 and repeated.json() == response.json()
            async with sessions() as db:
                row = await db.get(PlanningRun, rid)
                assert row.status == "awaiting_clarification" and row.pending_interrupt == pending
                assert row.user_request == original and row.error_code is None
                assert row.worker_id is None and row.worker_lease_expires_at is None
                assert row.trigger_snapshot["clarification_answers"] == ["第二天"]
                assert row.trigger_snapshot["clarification_receipts"][0]["answer"] == "第二天"
    asyncio.run(scenario())


def test_reclaimed_attempt_has_separate_real_checkpoints_and_remains_acceptable(monkeypatch):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from app.config import get_settings
    from app.planning_graph import DraftGeneration
    from app.planning_claim import checkpoint_thread
    from app.schemas import PlanningRunDecision
    import app.planning_graph as graph_module
    async def scenario():
        async with database() as sessions:
            for module in (worker, runtime, progress, graph_module):
                monkeypatch.setattr(module, "session_factory", sessions)
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as cp:
                await cp.setup()
            rid = await queued_run(sessions)
            async with sessions() as db:
                (await db.get(PlanningRun, rid)).user_request = "请重新规划完整行程"
                await db.commit()
            entered, release = asyncio.Event(), asyncio.Event()
            class Provider:
                calls = 0
                async def generate(self, _state):
                    self.calls += 1
                    if self.calls == 1:
                        entered.set()
                        await release.wait()
                    return DraftGeneration(CandidatePlanSnapshot(activities=[]), "synthetic", "ownership-probe", 0)
            provider = Provider()
            async def execute(run_id):
                return await runtime.execute_planning_run(run_id, provider=provider)
            monkeypatch.setattr(worker, "execute_planning_run", execute)
            first = await worker.claim_next_run()
            async with sessions() as db:
                old_thread = checkpoint_thread(await db.get(PlanningRun, rid))
            old_task = asyncio.create_task(worker.execute_claimed_run(first))
            try:
                await asyncio.wait_for(entered.wait(), 10)
                await expire(sessions, rid)
                replacement = await worker.claim_next_run()
                await worker.execute_claimed_run(replacement)
                async with sessions() as db:
                    current = await db.get(PlanningRun, rid)
                    new_thread = checkpoint_thread(current)
                    assert new_thread != old_thread
                    assert current.status == "awaiting_confirmation" and current.pending_interrupt["kind"] == "approval"
                release.set()
                await old_task
                async with sessions() as db:
                    current = await db.get(PlanningRun, rid)
                    assert checkpoint_thread(current) == new_thread and current.status == "awaiting_confirmation"
                async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as cp:
                    assert await cp.aget_tuple({"configurable": {"thread_id": old_thread}}) is not None
                    assert await cp.aget_tuple({"configurable": {"thread_id": new_thread}}) is not None
                result = await runtime.execute_planning_run(rid, decision=PlanningRunDecision(decision="accept"), provider=provider)
                assert result.pending_interrupt is None and provider.calls == 2
                async with sessions() as db:
                    assert (await db.get(PlanningRun, rid)).status == "accepted"
            finally:
                release.set()
                await asyncio.gather(old_task, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("late_write", ["cleanup", "pulse", "progress", "status", "failure", "revision"])
def test_old_worker_cannot_mutate_reclaimed_job(monkeypatch, late_write):
    async def scenario():
        async with database() as sessions:
            for module in (worker, runtime, progress):
                monkeypatch.setattr(module, "session_factory", sessions)
            rid = await queued_run(sessions)
            first = await worker.claim_next_run()
            entered, release = asyncio.Event(), asyncio.Event()
            errors = []
            async def late_execution(*_args, **_kwargs):
                entered.set()
                await release.wait()
                try:
                    if late_write == "pulse":
                        await progress.pulse(rid)
                    elif late_write == "progress":
                        token = progress.active_run.set(rid)
                        try:
                            await progress.report_progress("old", "stale owner progress")
                        finally:
                            progress.active_run.reset(token)
                    elif late_write == "status":
                        async with sessions() as db:
                            await _set_run_status(db, rid, "validating")
                    elif late_write == "failure":
                        await runtime._mark_failed(rid, "old_failure", "stale owner failure")
                    elif late_write == "revision":
                        async with sessions() as db:
                            await save_plan_revision(db, rid, before_snapshot={},
                                proposed_snapshot=CandidatePlanSnapshot(activities=[]), reason="stale owner",
                                difference_summary={}, validation_result={}, source_ids=[], enrich_routes=False)
                except Exception as exc:
                    errors.append(type(exc).__name__)
            monkeypatch.setattr(worker, "execute_planning_run", late_execution)
            task = asyncio.create_task(worker.execute_claimed_run(first))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                await expire(sessions, rid)
                await worker.claim_next_run()
                async with sessions() as db:
                    current = await db.get(PlanningRun, rid)
                    expected = (current.worker_id, current.worker_lease_expires_at, current.status, current.progress)
                release.set()
                await task
                async with sessions() as db:
                    current = await db.get(PlanningRun, rid)
                    assert (current.worker_id, current.worker_lease_expires_at, current.status, current.progress) == expected
                    if late_write != "cleanup":
                        assert errors == ["LostPlanningClaim"]
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())
