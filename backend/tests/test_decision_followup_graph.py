"""Explanation contradictions must not reach confirmation even in shadow mode."""
import asyncio
import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.planning_graph import DraftGeneration
from app.planning_graph_runtime import execute_planning_run
from app.schemas import CandidatePlanSnapshot
from tests.test_planning_graph import _setup_test_checkpoints


class UnsupportedFuturePromise:
    async def generate(self, state):
        return DraftGeneration(snapshot=CandidatePlanSnapshot(activities=[], decision_ledger=[],
            explanation="天气和营业状态将由系统进一步核验确认。"), provider="test", model="bad-claim", token_usage=0)


def test_graph_rejects_unsupported_promise_before_revision_without_formal_mutation():
    asyncio.run(_setup_test_checkpoints())
    with TestClient(app) as client:
        trip = client.post("/api/v1/trips", json={"title": "C-line isolated claim rejection test",
            "destination": "杭州", "start_date": "2026-11-01", "end_date": "2026-11-01",
            "total_budget_fen": None, "daily_budget_fen": None}).json()
        before = client.get(f"/api/v1/trips/{trip['id']}").json()
        run = client.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={"run_type": "replan",
            "user_request": "重新规划全程"}).json()
        asyncio.run(execute_planning_run(uuid.UUID(run["id"]), provider=UnsupportedFuturePromise()))
        result = client.get(f"/api/v1/planning-runs/{run['id']}").json()
        assert result["status"] == "failed"
        errors = result["error_details"]["validation_errors"]
        assert any(e["code"] == "decision_explanation_unsupported" and
                   e["details"]["code"] == "unimplemented_future_verification_claim" for e in errors)
        assert client.get(f"/api/v1/planning-runs/{run['id']}/revision").status_code == 404
        assert client.get(f"/api/v1/trips/{trip['id']}").json() == before
