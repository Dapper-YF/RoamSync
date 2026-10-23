import asyncio
import uuid

import pytest

from app.config import get_settings
import app.agent_worker as worker


def test_worker_executes_two_claimed_runs_without_serializing(monkeypatch) -> None:
    run_ids = [uuid.uuid4(), uuid.uuid4()]
    settings = get_settings().model_copy(update={"agent_worker_concurrency": 2, "agent_poll_seconds": 0})
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    claimed = 0
    active = 0
    peak_active = 0
    completed = 0

    class StopWorker(Exception):
        pass

    async def claim():
        nonlocal claimed
        if claimed < len(run_ids):
            run_id = run_ids[claimed]
            claimed += 1
            return run_id
        if completed == len(run_ids):
            raise StopWorker
        return None

    async def execute(_run_id):
        nonlocal active, peak_active, completed
        active += 1
        peak_active = max(peak_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        completed += 1

    monkeypatch.setattr(worker, "claim_next_run", claim)
    monkeypatch.setattr(worker, "execute_claimed_run", execute)
    with pytest.raises(StopWorker):
        asyncio.run(worker.main())

    assert peak_active == 2


def test_worker_recovers_after_a_transient_claim_database_failure(monkeypatch):
    from sqlalchemy.exc import OperationalError
    calls, delays = [], []
    class StopWorker(Exception):
        pass
    async def claim():
        calls.append(True)
        if len(calls) == 1:
            raise OperationalError("synthetic claim", {}, OSError("synthetic interruption"))
        raise StopWorker
    async def sleep(delay):
        delays.append(delay)
    monkeypatch.setattr(worker, "claim_next_run", claim)
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    with pytest.raises(StopWorker):
        asyncio.run(worker.main())
    assert len(calls) == 2 and len(delays) == 1 and 0 < delays[0] <= 30


def test_worker_shutdown_cancels_and_awaits_inflight_execution(monkeypatch):
    entered, cancelled = None, []
    class StopWorker(Exception):
        pass
    async def scenario():
        nonlocal entered
        entered = asyncio.Event()
        calls = 0
        async def claim():
            nonlocal calls
            calls += 1
            if calls == 1:
                return uuid.uuid4()
            await entered.wait()
            raise StopWorker
        async def execute(_claim):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        settings = get_settings().model_copy(update={"agent_worker_concurrency": 2})
        monkeypatch.setattr(worker, "get_settings", lambda: settings)
        monkeypatch.setattr(worker, "claim_next_run", claim)
        monkeypatch.setattr(worker, "execute_claimed_run", execute)
        with pytest.raises(StopWorker):
            await worker.main()
    asyncio.run(scenario())
    assert cancelled == [True]
