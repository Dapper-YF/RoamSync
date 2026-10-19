import asyncio
from uuid import uuid4

import httpx
import pytest
from datetime import date, time
from sqlalchemy import select, func

from app.main import app
from test_formal_write_protection import sample
from test_flexible_arrangement import create_item


def test_flexible_preview_adoption_keeps_unknowns_and_does_not_start_graph(sample, monkeypatch):
    from app.assistant_service import AssistantRouter, ToolDecision
    from app.database import AssistantSession, Trip
    user = "2026-11-07至2026-11-08去南京旅游。南京博物院确定去但时间未定，玄武湖有时间再去。2026-11-07 15:00-16:00留白。请形成允许留白的安排建议。"
    async def decide(self, context):
        assert context["prefer_flexible"] is True
        return ToolDecision(tool="create_trip", reply="形成供你采用的安排", destination="南京市", start_date=date(2026, 11, 7), end_date=date(2026, 11, 8), flexible=True,
            choices=[{"kind": "selected", "label": "南京博物院", "source_quote": "南京博物院确定去但时间未定"},
                {"kind": "selected", "label": "玄武湖", "source_quote": "玄武湖有时间再去"},
                {"kind": "free_window", "label": "留白", "source_quote": "2026-11-07 15:00-16:00留白", "day_date": "2026-11-07", "start": "15:00", "end": "16:00"}])
    monkeypatch.setattr(AssistantRouter, "decide", decide)
    from app.schemas import CitySuggestionResponse
    async def city(*args):
        return [CitySuggestionResponse(name="南京市", adcode="320100", citycode="025", longitude=118.8, latitude=32.05)]
    original_prepare = __import__("app.assistant_service", fromlist=["prepare_action"]).prepare_action
    async def prepare(db, decision, current, trips, city_search=None, **kwargs):
        return await original_prepare(db, decision, current, trips, city, **kwargs)
    monkeypatch.setattr("app.assistant_service.prepare_action", prepare)
    async def scenario():
        async with sample.sessions() as s, s.begin():
            row = AssistantSession(messages=[], applied_actions={})
            s.add(row)
            await s.flush()
            sid = row.id
            before = await s.scalar(select(func.count()).select_from(Trip))
        context = {"version": "assistant-context-v1", "topic_id": "flex-create", "prefer_flexible": True}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(f"/api/v1/assistant/sessions/{sid}/messages", json={"message": user, "message_id": str(uuid4()), "context": context})
            assert response.status_code == 200, response.text
            assert response.json()["trip_id"] is None
            action = response.json()["pending_action"]
            assert action and len(action["choices"]) == 3, response.text
            async with sample.sessions() as s:
                assert await s.scalar(select(func.count()).select_from(Trip)) == before
            context["preview_action_id"] = action["id"]
            mid = str(uuid4())
            adopted = await c.post(f"/api/v1/assistant/sessions/{sid}/messages", json={"message": "就按这份来", "message_id": mid, "context": context})
            assert adopted.status_code == 200, adopted.text
            tid = adopted.json()["trip_id"]
            assert tid and adopted.json()["latest_run_id"] is None
            saved = (await c.get(f"/api/v1/trips/{tid}/arrangement-items")).json()
            assert len(saved["items"]) == 3 and all(not d["activities"] for d in saved["days"])
            assert next(i["kind"] for i in saved["items"] if i["label"] == "玄武湖") == "optional"
            assert next(i["day_date"] for i in saved["items"] if i["label"] == "南京博物院") is None
            assert (await c.post(f"/api/v1/assistant/sessions/{sid}/messages", json={"message": "就按这份来", "message_id": mid, "context": context})).status_code == 200
            assert (await c.get(f"/api/v1/trips/{tid}/arrangement-items")).json() == saved
        # This synthetic pre-trip session is not shared legacy state for other
        # tests. Remove it so older tests asserting their one-turn session stay isolated.
        from sqlalchemy import delete
        async with sample.sessions() as s, s.begin():
            await s.execute(delete(AssistantSession).where(AssistantSession.id == sid))
    asyncio.run(scenario())


@pytest.mark.parametrize("origin,quote", [("ai_suggestion", ""), ("user_explicit", "周日总统府14:00-15:00已预约")])
def test_booking_cannot_be_fabricated_or_extended_beyond_user_quote(origin, quote):
    from app.assistant_service import ToolDecision
    from app.flexible_creation import prepare_choices
    decision = ToolDecision(tool="create_trip", reply="preview", destination="南京市", start_date=date(2026, 11, 7), end_date=date(2026, 11, 8), flexible=True,
        choices=[{"kind": "appointment", "label": "总统府", "origin": origin, "source_quote": quote, "day_date": "2026-11-08", "start": "14:00", "end": "16:00"}])
    async def scenario():
        with pytest.raises(ValueError):
            await prepare_choices(decision, {"name": "南京市"}, quote)
    asyncio.run(scenario())


def test_bare_adoption_cannot_choose_arbitrary_model_text(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            session = (await c.post("/api/v1/assistant/sessions", json={"trip_id": str(sample.trip_id)})).json()
            response = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={"message": "就按这份来", "message_id": str(uuid4()),
                "context": {"version": "assistant-context-v1", "topic_id": "no-arbitrary-adopt", "prefer_flexible": True}})
            assert response.status_code == 200, response.text
            assert "请先打开" in response.json()["messages"][-1]["assistant"]
            assert (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()["version"] == 1
    asyncio.run(scenario())


def test_preference_statement_remains_discussion_not_live_booking_lookup(sample):
    from app.database import AssistantSession
    async def scenario():
        async with sample.sessions() as s, s.begin():
            row = AssistantSession(messages=[], applied_actions={})
            s.add(row)
            await s.flush()
            sid = row.id
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(f"/api/v1/assistant/sessions/{sid}/messages", json={"message": "南京博物院确定想去但时间未定，玄武湖有时间再去。现在先讨论。",
                "message_id": str(uuid4()), "context": {"version": "assistant-context-v1", "topic_id": "preference-only", "prefer_flexible": True}})
            assert response.status_code == 200
            assert "尚未核实场次" not in response.json()["messages"][-1]["assistant"]
            assert "没有创建旅行" in response.json()["messages"][-1]["assistant"]
            assert response.json()["trip_id"] is None and response.json()["latest_run_id"] is None
        from sqlalchemy import delete
        async with sample.sessions() as s, s.begin():
            await s.execute(delete(AssistantSession).where(AssistantSession.id == sid))
    asyncio.run(scenario())


def test_simple_chat_edit_does_not_resurrect_unrelated_optional_choice(sample):
    from app.arrangement_service import bind_arrangement_references
    from app.schemas import CandidatePlanSnapshot, CandidateActivity
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            choice = await create_item(c, sample, 1, kind="optional", label="测试地点2", place_id=str(sample.places[2].id))
            iid = choice.json()["id"]
            context = {"candidates": [{"id": str(sample.places[2].id), "name": "测试地点2"}], "arrangement_items": [choice.json()]}
            snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id="model-choice-1", day_date=sample.days[1].date,
                place_candidate_id=sample.places[2].id, planned_start_time=time(14), duration_minutes=60,
                estimated_cost_fen=0, transport_mode_to_here="walk", source_ids=[sample.places[2].source_record_id])])
            mapped = bind_arrangement_references(snapshot, context)
            assert mapped.activities[0].candidate_id == f"arrangement:{iid}"
            saved = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()
            assert saved["items"][0]["kind"] == "optional" and saved["items"][0]["activity_id"] is None
    asyncio.run(scenario())


def test_planner_context_preserves_selected_optional_and_free_semantics(sample):
    from app.planning_context import build_planning_context
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await create_item(c, sample, 1, kind="selected", label="南京博物院")).status_code == 201
            assert (await create_item(c, sample, 2, kind="optional", label="玄武湖")).status_code == 201
            assert (await create_item(c, sample, 3, kind="free_window", label="留白", day_date="2026-11-07", start="15:00", end="16:00")).status_code == 201
        async with sample.sessions() as s:
            context = (await build_planning_context(s, sample.trip_id)).model_dump(mode="json")
            assert {i["kind"] for i in context["arrangement_items"]} == {"selected", "optional", "free_window"}
            assert next(i for i in context["arrangement_items"] if i["kind"] == "selected")["start"] is None
    asyncio.run(scenario())


def test_chat_and_page_edits_preserve_each_other_without_planning_run(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            first = await create_item(c, sample, 1, kind="selected", label="南京博物院")
            second = await create_item(c, sample, 2, kind="selected", label="玄武湖")
            iid = first.json()["id"]
            page = await c.put(f"/api/v1/trips/{sample.trip_id}/arrangement-items/{iid}", json={"expected_version": 3,
                "kind": "optional", "label": "南京博物院", "source_ref": "page-explicit"})
            assert page.status_code == 200
            session = (await c.post("/api/v1/assistant/sessions", json={"trip_id": str(sample.trip_id)})).json()
            mid = str(uuid4())
            context = {"version": "assistant-context-v1", "topic_id": "arrangement-test", "surface": "trip", "read_trip_id": str(sample.trip_id),
                "action_target": {"trip_id": str(sample.trip_id), "expected_version": 4, "operation": "edit_arrangement", "authorization_message_id": mid}}
            response = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={"message": "把玄武湖改成备选", "message_id": mid, "context": context})
            assert response.status_code == 200, response.text
            assert response.json()["latest_run_id"] is None
            state = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()
            assert state["version"] == 5
            assert {i["label"]: i["kind"] for i in state["items"]} == {"南京博物院": "optional", "玄武湖": "optional"}
            assert next(i for i in state["items"] if i["id"] == iid)["decision_ref"] == "page-explicit"
            again = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={"message": "把玄武湖改成备选", "message_id": mid, "context": context})
            assert again.status_code == 200
            assert (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json() == state
    asyncio.run(scenario())


def test_old_chat_action_target_cannot_overwrite_a_new_page_decision(sample):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await create_item(c, sample, 1, kind="selected", label="玄武湖")).status_code == 201
            session = (await c.post("/api/v1/assistant/sessions", json={"trip_id": str(sample.trip_id)})).json()
            mid = str(uuid4())
            response = await c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={"message": "把玄武湖改成备选", "message_id": mid,
                "context": {"version": "assistant-context-v1", "topic_id": "stale-test", "surface": "trip", "read_trip_id": str(sample.trip_id),
                    "action_target": {"trip_id": str(sample.trip_id), "expected_version": 1, "operation": "edit_arrangement", "authorization_message_id": mid}}})
            assert response.status_code in {409, 422}
            state = (await c.get(f"/api/v1/trips/{sample.trip_id}/arrangement-items")).json()
            assert state["version"] == 2 and state["items"][0]["kind"] == "selected"
    asyncio.run(scenario())
