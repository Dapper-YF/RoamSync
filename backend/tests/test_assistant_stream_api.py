import uuid
import json

from fastapi.testclient import TestClient

from app.assistant_stream import emit
from app.companion_contracts import CompanionDraft
from app.companion_provider import ModelCompanionProvider
from app.main import app
from app.database import AssistantSession, session_factory


def test_stream_endpoint_commits_complete_turn_and_replay_is_idempotent(monkeypatch):
    calls = []
    async def generate(self, context, need):
        calls.append(context)
        emit("analysis_delta", delta="按当前问题整理体验。")
        emit("answer_delta", delta="可以先了解城市文化。")
        return CompanionDraft(analysis_summary="按当前问题整理体验。", response_text="可以先了解城市文化。")
    monkeypatch.setattr(ModelCompanionProvider, "generate", generate)
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        # Empty-input session creation intentionally resumes the last unbound
        # conversation. This test needs its own identity, even on a reused DB.
        async def seed_session():
            async with session_factory() as db:
                row = AssistantSession(messages=[], applied_actions={})
                db.add(row)
                await db.commit()
                return str(row.id)
        session_id = client.portal.call(seed_session)
        session = client.post("/api/v1/assistant/sessions", json={"session_id": session_id}).json()
        url = f"/api/v1/assistant/sessions/{session['id']}/messages/stream"
        payload = {"message": "南京有什么文化体验？", "message_id": str(uuid.uuid4())}
        response = client.post(url, json=payload)
        assert response.headers["x-accel-buffering"] == "no"
        assert "text/event-stream" in response.headers["content-type"]
        events = [json.loads(frame[6:]) for frame in response.text.strip().split("\n\n") if frame.startswith("data: ")]
        assert [e["type"] for e in events] == ["status", "analysis_delta", "answer_delta", "done"]
        saved = events[-1]["session"]
        assert len(saved["messages"]) == 1
        assert saved["messages"][0]["companion_result"]["analysis_summary"]
        assert saved["latest_run_id"] is None
        replay = client.post(url, json=payload)
        repeated = [json.loads(frame[6:]) for frame in replay.text.strip().split("\n\n") if frame.startswith("data: ")]
        assert [e["type"] for e in repeated] == ["status", "done"]
        assert len(repeated[-1]["session"]["messages"]) == 1
        assert len(calls) == 1
        async def remove_session():
            async with session_factory() as db:
                await db.delete(await db.get(AssistantSession, uuid.UUID(session_id)))
                await db.commit()
        client.portal.call(remove_session)
