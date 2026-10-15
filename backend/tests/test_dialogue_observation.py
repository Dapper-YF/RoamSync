import asyncio
import uuid
from time import monotonic

import pytest
from fastapi.testclient import TestClient

from app import dialogue_observation as observation
from app.main import app


@pytest.fixture(autouse=True)
def clear_turns():
    observation._turns.clear()
    yield
    observation._turns.clear()


def test_live_stages_are_visible_before_completion_and_do_not_mix_requests():
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()

        @observation.observed_stage("generate")
        async def generate():
            started.set()
            await finish.wait()
            return "original result"

        @observation.observe_message
        async def send(db, session_id, message, message_id):
            return await generate()

        pending = asyncio.create_task(send(None, "session-a", "private text", "message-a"))
        await started.wait()
        first = observation.snapshot("session-a", "message-a")
        assert first["status"] == "running"
        assert first["events"][-1]["stage"] == "generate"
        assert first["events"][-1]["status"] == "running"
        assert "private text" not in str(first)
        assert observation.snapshot("session-b", "message-a")["events"] == []
        first["events"].clear()
        assert observation.snapshot("session-a", "message-a")["events"]
        finish.set()
        assert await pending == "original result"
        final = observation.snapshot("session-a", "message-a")
        assert final["status"] == "completed"
        assert [e["sequence"] for e in final["events"]] == [1, 2, 3, 4]
        assert final["events"][2]["duration_ms"] >= 0
    asyncio.run(run())


def test_failure_preserves_the_original_exception_and_hides_its_payload():
    error = ValueError("authorization=private-secret")

    @observation.observe_message
    @observation.observed_stage("generate")
    async def failing(*args, **kwargs):
        raise error

    with pytest.raises(ValueError) as raised:
        asyncio.run(failing(None, "session", "input", "message"))
    assert raised.value is error
    trace = observation.snapshot("session", "message")
    assert trace["status"] == "failed"
    assert any(e["stage"] == "generate" and e["status"] == "failed" for e in trace["events"])
    assert "private-secret" not in str(trace)


def test_observer_store_failure_cannot_fail_the_message(monkeypatch):
    monkeypatch.setattr(observation, "_prune", lambda: (_ for _ in ()).throw(ValueError("store failed")))

    @observation.observe_message
    async def operation(*args, **kwargs):
        return 42

    assert asyncio.run(operation(None, "session", "input", "message")) == 42


def test_store_is_bounded_and_expires():
    @observation.observe_message
    async def operation(*args, **kwargs):
        return None

    async def fill():
        for index in range(observation.MAX_TURNS + 2):
            await operation(None, "session", "input", str(index))
    asyncio.run(fill())
    assert len(observation._turns) == observation.MAX_TURNS
    assert observation.snapshot("session", "0")["status"] == "unavailable"
    for turn in observation._turns.values():
        turn["updated"] = monotonic() - observation.TTL_SECONDS - 1
    observation._prune()
    assert not observation._turns


def test_endpoint_is_read_only_and_handles_missing_or_invalid_identity():
    session_id, message_id = uuid.uuid4(), uuid.uuid4()
    client = TestClient(app)
    path = f"/api/v1/agent-monitor/sessions/{session_id}/messages/{message_id}"
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "unavailable", "events": [], "source": "process_local"}
    assert client.get(path.replace(str(message_id), "invalid")).status_code == 422
