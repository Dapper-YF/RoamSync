import asyncio
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.database import PlanRevision, PlanningRun, session_factory
from app.decision_memory import retrieve_decision_memory
from app.main import app


async def _insert_revision(*, trip_id: uuid.UUID, target_day: str, version: int, status: str, reason: str | None = None, text: str | None = None) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as session:
        formal_activity_id = str(uuid.uuid4())
        run = PlanningRun(
            trip_id=trip_id, run_type="replan", status="awaiting_confirmation" if status == "pending" else "rejected", user_request="请再调整一次",
            entry_point="trip_planner", base_trip_version=version,
        )
        session.add(run)
        await session.flush()
        revision = PlanRevision(
            planning_run_id=run.id, trip_id=trip_id, revision_number=1, reason="候选方案",
            before_snapshot={"days": [{"date": target_day, "activities": [{"id": formal_activity_id}]}]},
            proposed_snapshot={"activities": [{
                "candidate_id": "candidate-a", "day_date": target_day, "place_candidate_id": str(uuid.uuid4()),
                "planned_start_time": "10:00:00", "duration_minutes": 60, "estimated_cost_fen": 0,
                "transport_mode_to_here": "walk", "source_ids": [], "replaces_activity_id": formal_activity_id, "locked": False,
            }]},
            difference_summary={"goal_satisfaction": {"results": []}}, validation_result={"valid": True}, source_ids=[],
            status=status, rejection_reason_code=reason, rejection_reason_text=text,
            created_at=datetime.now(UTC), decided_at=datetime.now(UTC) if status == "rejected" else None,
        )
        session.add(revision)
        await session.commit()
        return run.id, revision.id


def test_reject_feedback_persists_and_memory_is_scoped_to_trip_day_and_version():
    from app.demo_seed import DEMO_TRIP_ID

    with TestClient(app) as client:
        assert client.post("/api/v1/demo/reset").status_code == 200
        trip = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        target_day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]["date"]
        other_day = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[1]["date"]

        _, revision_id = asyncio.run(_insert_revision(
            trip_id=uuid.UUID(str(DEMO_TRIP_ID)), target_day=target_day, version=trip["version"], status="pending",
        ))
        other_trip = client.post("/api/v1/trips", json={
            "title": "memory isolation", "destination": "杭州", "start_date": target_day,
            "end_date": target_day, "total_budget_fen": 100000, "daily_budget_fen": 100000,
        }).json()
        asyncio.run(_insert_revision(
            trip_id=uuid.UUID(other_trip["id"]), target_day=target_day, version=other_trip["version"],
            status="rejected", reason="too_much_walking", text="另一趟旅行的反馈",
        ))
        response = client.post(f"/api/v1/plan-revisions/{revision_id}/reject", json={
            "reason_code": "too_rushed", "reason_text": "两个文化场馆停留时间太短",
        })
        assert response.status_code == 200
        assert response.json()["rejection_reason_code"] == "too_rushed"
        assert response.json()["rejection_reason_text"] == "两个文化场馆停留时间太短"

        async def retrieve(day: str, version: int, trip_id: uuid.UUID = uuid.UUID(str(DEMO_TRIP_ID))):
            async with session_factory() as session:
                return await retrieve_decision_memory(session, trip_id=trip_id, target_days=[day], base_trip_version=version)

        matching = asyncio.run(retrieve(target_day, trip["version"]))
        assert len(matching) == 1
        assert matching[0]["source_revision_id"] == str(revision_id)
        assert matching[0]["rejection_reason_text"] == "两个文化场馆停留时间太短"
        assert matching[0]["previous_candidate_summary"]["end_time"] == "11:00"
        assert asyncio.run(retrieve(other_day, trip["version"])) == []
        assert asyncio.run(retrieve(target_day, trip["version"] + 1)) == []
        # Same date is not sufficient: another trip's feedback must never leak in.
        assert all(item["trip_id"] == str(DEMO_TRIP_ID) for item in matching)


def test_retry_creates_independent_run_without_duplicate_memory_or_formal_mutation():
    from app.demo_seed import DEMO_TRIP_ID
    with TestClient(app) as client:
        client.post("/api/v1/demo/reset")
        days = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()
        trip = client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()
        _, revision_id = asyncio.run(_insert_revision(trip_id=DEMO_TRIP_ID, target_day=days[0]["date"], version=trip["version"], status="rejected", reason="too_rushed", text="多留休息时间"))
        payload = {"run_type":"replan", "user_request":"第一天轻松一点", "selected_day_id":days[0]["id"]}
        first = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",json=payload)
        second = client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/planning-runs",json=payload)
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] != second.json()["id"]
        assert first.json()["user_request"] == second.json()["user_request"] == payload["user_request"]
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json() == days
        assert client.get(f"/api/v1/trips/{DEMO_TRIP_ID}").json()["version"] == trip["version"]
        async def memories():
            async with session_factory() as session:
                return await retrieve_decision_memory(session,trip_id=DEMO_TRIP_ID,target_days=[days[0]["date"]],base_trip_version=trip["version"])
        memory = asyncio.run(memories())
        assert len(memory)==1 and memory[0]["source_revision_id"]==str(revision_id)
