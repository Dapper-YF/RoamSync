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
