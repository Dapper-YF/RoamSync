import asyncio
from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.assistant_context import ContextEnvelope, capture_effective_requirements, restore_context
from app.drafts.contracts import DraftCreate, DraftPlan, RunRequest
from app.drafts.repository import DraftRepository, metadata
from app.drafts.routes import create_router
from app.drafts.service import DraftService
from app.requirements import capture_explicit_requirements, project_requirements, promote_requirements, revoke_requirement


def fresh_assistant_session_id():
    from app.database import AssistantSession, session_factory
    async def create():
        async with session_factory() as session:
            row = AssistantSession(id=uuid4(), trip_id=None, messages=[], applied_actions={})
            session.add(row)
            await session.commit()
            return str(row.id)
    return asyncio.run(create())


def test_scoped_revocation_keeps_other_days_and_city_trip_isolation():
    records = capture_explicit_requirements([], "全程慢游", scope={"kind": "draft", "draft_id": "d", "city": "杭州"}, source_ref="first", force=True)
    root = records[0]["id"]
    records = revoke_requirement(records, root, scope={"kind": "day", "draft_id": "d", "city": "杭州", "day_index": 2})
    assert project_requirements(records, draft_id="d", city="杭州市", day_index=1)[0]["id"] == root
    assert project_requirements(records, draft_id="d", city="杭州", day_index=2) == []
    assert project_requirements(records, draft_id="d", city="杭州", day_index=3)
    promoted = promote_requirements(records, draft_id="d", trip_id="t", city="杭州", start_date=date(2026, 11, 1))
    assert project_requirements(promoted, trip_id="t", city="杭州", target_date="2026-11-02") == []
    assert project_requirements(promoted, trip_id="t", city="杭州", target_date="2026-11-03")
    assert project_requirements(promoted, trip_id="other", city="杭州", target_date="2026-11-03") == []
    assert project_requirements(promoted, trip_id="t", city="南京", target_date="2026-11-03") == []


def test_local_replacement_retains_provenance_and_hardness():
    scope = {"kind": "draft", "draft_id": "d"}
    records = capture_explicit_requirements([], "必须慢游", scope=scope, source_ref="u1", force=True)
    records = capture_explicit_requirements(records, "第二天希望紧凑", scope=scope, source_ref="u2", force=True)
    assert project_requirements(records, draft_id="d", day_index=1)[0]["strength"] == "hard"
    day2 = project_requirements(records, draft_id="d", day_index=2)
    assert len(day2) == 1 and day2[0]["value"] == "intensive"
    assert day2[0]["supersedes"] == [records[0]["id"]]
    assert day2[0]["source"] == {"kind": "user_explicit", "ref": "u2"}


def test_compound_requirements_have_independent_identity_and_local_revocation():
    records = capture_explicit_requirements([], "希望轻松，预算500元，拍照为主，步行不超过30分钟", scope={"kind": "draft", "draft_id": "d"}, source_ref="same-turn", force=True)
    by_key = {r["key"]: r for r in records}
    assert set(by_key) == {"pace", "budget_fen", "interest", "max_walking_minutes"}
    assert by_key["pace"]["value"] == "relaxed" and by_key["budget_fen"]["value"] == 50000
    assert by_key["interest"]["value"] == "photography" and by_key["max_walking_minutes"]["value"] == 30
    assert len({r["id"] for r in records}) == 4 and {r["source"]["ref"] for r in records} == {"same-turn"}
    records = revoke_requirement(records, by_key["pace"]["id"], scope={"kind": "day", "draft_id": "d", "day_index": 2})
    assert {r["key"] for r in project_requirements(records, draft_id="d", day_index=2)} == {"budget_fen", "interest", "max_walking_minutes"}
    assert len(project_requirements(records, draft_id="d", day_index=1)) == 4


def test_later_day_mention_never_scopes_earlier_trip_interest():
    records = capture_explicit_requirements([], "喜欢拍照，第2天预算200元", scope={"kind": "draft", "draft_id": "d"}, source_ref="turn")
    interest = next(r for r in records if r["key"] == "interest")
    budget = next(r for r in records if r["key"] == "budget_fen")
    assert interest["scope"]["kind"] == "draft" and interest["scope"]["day_index"] is None
    assert budget["scope"]["kind"] == "day" and budget["scope"]["day_index"] == 2


@pytest.mark.parametrize("text,expected", [("不太想购物", "soft"), ("尽量避免购物", "soft"), ("避免购物", "soft"), ("不要安排购物", "hard"), ("禁止购物", "hard")])
def test_avoidance_keeps_user_strength_without_automatic_upgrade(text, expected):
    records = capture_explicit_requirements([], text, scope={"kind": "draft", "draft_id": "d"}, source_ref="turn", force=True)
    assert len(records) == 1 and records[0]["key"] == "avoid_category"
    assert records[0]["strength"] == expected


@pytest.mark.parametrize("text,key,expected", [
    ("预算200元左右，可以略超", "budget_fen", "soft"),
    ("预算不超过200元，可以略超", "budget_fen", "soft"),
    ("预算200元", "budget_fen", "soft"),
    ("预算不超过200元", "budget_fen", "hard"),
    ("步行30分钟左右也可以", "max_walking_minutes", "soft"),
    ("步行不超过30分钟", "max_walking_minutes", "hard"),
])
def test_approximate_budget_and_walking_are_preferences_not_silent_hard_caps(text, key, expected):
    records = capture_explicit_requirements([], text, scope={"kind": "topic", "topic_id": "x"}, source_ref="turn")
    numeric = next(r for r in records if r["key"] == key)
    assert numeric["strength"] == expected
    assert numeric["text"] == text


@pytest.mark.parametrize("text,key,strength", [("每日预算不超过200元", "daily_budget_fen", "hard"),
    ("每天预算200元左右", "daily_budget_fen", "soft"), ("总预算不超过600元", "budget_fen", "hard")])
def test_daily_budget_keeps_its_own_dimension_without_becoming_total_budget(text, key, strength):
    records = capture_explicit_requirements([], text, scope={"kind": "topic", "topic_id": "x"}, source_ref="same-source")
    record = next(r for r in records if r["key"] == key)
    assert record["strength"] == strength and record["source"]["ref"] == "same-source"


@pytest.mark.parametrize("text", ["收藏这家", "锁定第二天", "推荐轻松玩法？", "这家怎么样", "AI建议去公园"])
def test_suggestion_favorite_and_lock_are_not_requirements(text):
    assert capture_explicit_requirements([], text, scope={"kind": "topic", "topic_id": "topic"}, source_ref="u") == []


def test_corrupt_legacy_records_are_ignored_without_guessing():
    assert project_requirements([{}, {"id": "old", "text": "AI推测"}, None], trip_id="t") == []


def test_topic_switch_preserves_only_explicit_global_preference_and_ignores_forged_records():
    local = capture_effective_requirements(ContextEnvelope(topic_id="x", browsing_city="杭州"), "希望慢游", message_id="local")
    global_context = capture_effective_requirements(local, "长期偏好：希望轻松", message_id="global")
    incoming = ContextEnvelope(topic_id="x", browsing_city="南京", requirement_records=local.requirement_records)
    restored, history = restore_context(incoming, [{"context": global_context.model_dump(mode="json")}])
    assert not history
    assert len(restored.requirement_records) == 1 and restored.requirement_records[0]["scope"]["kind"] == "global_preference"
    clean, _ = restore_context(incoming, [])
    assert clean.requirement_records == []


class Generator:
    source = "fixture"
    seen = None
    async def generate(self, draft, requirements):
        self.seen = draft.requirement_records
        return DraftPlan(days=[{"day_index": n, "title": f"day{n}", "items": [{"name": f"place{n}"}]} for n in range(1, 4)])


def test_http_multiturn_draft_revoke_and_reload_without_affecting_other_dates():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    repo, generator = DraftRepository(engine), Generator()
    service = DraftService(repo, generator)
    app = FastAPI(); app.include_router(create_router(service, lambda: "owner"))
    with TestClient(app) as client:
        draft = client.post("/api/v1/drafts", json={"city": "杭州", "day_count": 3, "requirements": "全程慢游"}).json()
        path = f"/api/v1/drafts/{draft['id']}"
        generated = client.post(path + "/runs", json={"request_id": str(uuid4()), "expected_version": draft["version"], "requirements": "希望保留休息时间"})
        assert generated.status_code == 200, generated.text
        draft = generated.json()
        before = draft["plan"]
        records = client.get(path + "/requirements").json()
        root = next(r for r in records["records"] if r["key"] == "pace")
        revoked = client.post(path + "/requirements/revoke", json={"expected_version": draft["version"], "requirement_id": root["id"], "day_index": 2})
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["plan"] == before
        records = client.get(path + "/requirements").json()
        assert any(r["id"] == root["id"] for r in records["effective_by_day"]["1"])
        assert not any(r["id"] == root["id"] for r in records["effective_by_day"]["2"])
        assert any(r["id"] == root["id"] for r in records["effective_by_day"]["3"])
        stale = client.post(path + "/requirements/revoke", json={"expected_version": draft["version"], "requirement_id": root["id"]})
        assert stale.status_code == 409
        draft = client.get(path).json()
        changed = client.post(path + "/runs", json={"request_id": str(uuid4()), "expected_version": draft["version"], "requirements": "第二天希望紧凑", "target_day_indices": [2]})
        assert changed.status_code == 200, changed.text
        assert changed.json()["plan"]["days"][0] == before["days"][0]
        assert generator.seen and any(r["status"] == "revoked" for r in generator.seen)
    engine.dispose()


def test_trip_requirements_persist_in_api_planning_run_and_recovery_snapshot():
    from app.main import app as main_app
    from app.requirement_routes import create_router as trip_router
    app = FastAPI(); app.include_router(trip_router(lambda: "owner"))
    with TestClient(main_app) as original, TestClient(app) as client:
        trip = original.post("/api/v1/trips", json={"title": "requirements test", "destination": "杭州", "start_date": "2026-11-01", "end_date": "2026-11-03"}).json()
        path = f"/api/v1/trips/{trip['id']}/requirements"
        state = client.get(path).json()
        added = client.post(path, json={"expected_version": state["version"], "text": "全程慢游", "key": "pace", "value": "relaxed"})
        assert added.status_code == 200, added.text
        state = added.json(); root = state["records"][0]
        revoked = client.post(path + "/revoke", json={"expected_version": state["version"], "requirement_id": root["id"], "day_date": "2026-11-02"})
        assert revoked.status_code == 200, revoked.text
        assert not revoked.json()["effective_by_date"]["2026-11-02"]
        assert revoked.json()["effective_by_date"]["2026-11-01"]
        run = original.post(f"/api/v1/trips/{trip['id']}/planning-runs", json={"run_type": "initial_plan", "user_request": "帮我规划行程"})
        assert run.status_code == 201, run.text
        assert run.json()["trigger_snapshot"]["effective_requirements"] == revoked.json()["records"]
        context = original.get(f"/api/v1/trips/{trip['id']}/planning-context")
        assert context.status_code == 200
        assert context.json()["effective_requirements"] == revoked.json()["records"]
        # Automatic Recovery uses the exact same repository, including its facts.
        from app.database import session_factory
        from app.planning_run_repository import create_planning_run
        from app.schemas import PlanningRunCreate
        from uuid import UUID
        async def automatic():
            async with session_factory() as session:
                return await create_planning_run(session, UUID(trip["id"]), PlanningRunCreate(run_type="replan", user_request="体验变化后恢复安排"),
                    trigger_type="experience_impact", trigger_key=f"test:{uuid4()}", trigger_snapshot={"impact": {"additional_stay_minutes": 30}})
        recovery = asyncio.run(automatic())
        assert recovery.trigger_snapshot["effective_requirements"] == revoked.json()["records"]
        assert recovery.trigger_snapshot["impact"]["additional_stay_minutes"] == 30


@pytest.mark.parametrize("adopt", [False, True])
def test_real_sql_draft_promotion_transfers_day_override_for_create_only_and_adopt(adopt):
    import os
    from datetime import UTC, datetime, timedelta
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.database import TripPreferences, PlanningRun
    from app.draft_promotion.contracts import PreviewRequest, ConfirmRequest
    from app.draft_promotion.repository import metadata as promotion_metadata
    from app.draft_promotion.service import DraftPromotionService
    from app.place_content.contracts import Place
    url = os.environ["DATABASE_URL"]
    database_name = url.rsplit("/", 1)[-1]
    assert database_name.startswith("roamsync_") and ("test" in database_name or database_name.endswith("_intelligence"))
    engine = create_engine(url, poolclass=NullPool)
    metadata.create_all(engine); promotion_metadata.create_all(engine)
    async_engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    repo, owner = DraftRepository(engine), str(uuid4())
    draft = repo.create(owner, DraftCreate(city="杭州", day_count=3, requirements="希望慢游，拍照为主"))
    now = datetime.now(UTC)
    places = [Place.model_validate({"ref": {"place_id": str(uuid4()), "external_ref": {"provider_place_id": str(n)}},
        "name": f"test{n}", "category": "attraction", "city": "杭州", "location": {"longitude": 120 + n / 1000, "latitude": 30},
        "source": {"source_url": "https://fixture.invalid/place", "fetched_at": now,
            "expires_at": now + timedelta(hours=1)}}) for n in range(3)]
    def fill(current):
        current.plan = DraftPlan(days=[{"day_index": n + 1, "title": f"day{n+1}", "items": [{"name": p.name,
            "place_id": p.ref.place_id, "identity_status": "provider_confirmed"}]} for n, p in enumerate(places)])
    draft = repo.mutate(owner, draft.id, draft.version, fill)
    service = DraftService(repo, Generator())
    root = next(r for r in draft.requirement_records if r["key"] == "pace")
    draft = service.revoke_requirement(owner, draft.id, draft.version, root["id"], 2)
    class Places:
        async def get_place(self, ref, **_):
            return next(p for p in places if p.ref.place_id == ref)
    promotion = DraftPromotionService(repo, sessions, Places())
    async def scenario():
        plan = await promotion.preview(owner, draft.id, PreviewRequest(expected_version=draft.version, start_date="2026-11-01"))
        assert not plan.coverage.blockers
        request = ConfirmRequest(request_id=uuid4(), prepared_id=plan.id, prepared_hash=plan.prepared_hash,
            action="create_and_adopt" if adopt else "create_only", confirmation="创建并采用当前方案" if adopt else "创建旅行")
        operation = await promotion.confirm(owner, request)
        operation = await promotion.resume(owner, operation.id)
        assert operation.status == ("applied" if adopt else "created"), operation.model_dump_json()
        async with sessions() as session:
            pref = await session.get(TripPreferences, operation.target_trip_id)
            day1 = project_requirements(pref.requirement_records, trip_id=str(operation.target_trip_id), city="杭州", target_date="2026-11-01")
            day2 = project_requirements(pref.requirement_records, trip_id=str(operation.target_trip_id), city="杭州", target_date="2026-11-02")
            assert {r["key"] for r in day1} == {"pace", "interest"}
            assert {r["key"] for r in day2} == {"interest"}
            if adopt:
                run = await session.get(PlanningRun, operation.target_run_id)
                assert run.trigger_snapshot["effective_requirements"] == pref.requirement_records
        await async_engine.dispose()
    asyncio.run(scenario())
    engine.dispose()


def test_companion_topic_to_draft_explicit_bridge_uses_owner_cas_and_never_plan_write():
    from app.database import session_factory
    from app.assistant_service import send_message
    from app.assistant_places import ContentServicePlaces
    from app.main import app
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    repo = DraftRepository(engine)
    draft = repo.create("owner", DraftCreate(city="杭州", day_count=3))
    class Port(ContentServicePlaces):
        async def search(self, **_): return []
        async def get_place(self, _): return None
    port = Port(None, repo, "owner")
    async def answer(*_): return "已结合当前信息回答。"
    with TestClient(app) as client:
        session_id = fresh_assistant_session_id()
    from uuid import UUID
    async def send(text, context):
        async with session_factory() as session:
            return await send_message(session, UUID(session_id), text, uuid4(),
                context=context, companion_responder=answer, place_port=port)
    first = asyncio.run(send("希望轻松，拍照为主，步行不超过30分钟", {"topic_id": "bridge", "browsing_city": "杭州"}))
    source_refs = {r["source"]["ref"] for r in first.messages[-1]["context"]["requirement_records"]}
    imported = asyncio.run(send("把刚才的要求加入当前草稿", {"topic_id": "bridge", "browsing_city": "杭州",
        "read_draft_id": str(draft.id), "read_draft_version": draft.version}))
    saved = repo.get("owner", draft.id)
    assert imported.messages[-1]["requirement_sync"]["status"] == "saved"
    assert {r["key"] for r in saved.requirement_records} == {"pace", "interest", "max_walking_minutes"}
    assert {r["source"]["ref"] for r in saved.requirement_records} == source_refs
    assert saved.plan is None and saved.version == draft.version + 1
    before = saved.model_dump(mode="json")
    stale = asyncio.run(send("第二天希望紧凑", {"topic_id": "bridge", "browsing_city": "杭州",
        "read_draft_id": str(draft.id), "read_draft_version": draft.version}))
    assert stale.messages[-1]["requirement_sync"]["status"] == "version_conflict"
    assert repo.get("owner", draft.id).model_dump(mode="json") == before
    engine.dispose()


def test_bridge_preserves_day_budget_and_local_tombstone_and_reimport_cannot_revive():
    from app.assistant_places import ContentServicePlaces
    from app.draft_requirement_bridge import sync_draft_requirements
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    repo = DraftRepository(engine)
    draft = repo.create("owner", DraftCreate(city="杭州", day_count=3))
    source = capture_explicit_requirements([], "希望轻松，喜欢拍照，第2天预算200元", scope={"kind": "topic", "topic_id": "bridge", "city": "杭州"}, source_ref="source")
    root = next(r for r in source if r["key"] == "pace")
    source = revoke_requirement(source, root["id"], scope={"kind": "day", "topic_id": "bridge", "city": "杭州", "day_index": 2})
    history = [{"context": ContextEnvelope(topic_id="bridge", browsing_city="杭州", requirement_records=source).model_dump(mode="json")}]
    port = ContentServicePlaces(None, repo, "owner")
    envelope = ContextEnvelope(topic_id="bridge", browsing_city="杭州", read_draft_id=draft.id, read_draft_version=draft.version)
    _, state = asyncio.run(sync_draft_requirements(envelope, "把刚才的要求加入当前草稿", "import", history, port))
    assert state["status"] == "saved"
    saved = repo.get("owner", draft.id)
    day1 = project_requirements(saved.requirement_records, draft_id=str(draft.id), city="杭州", day_index=1)
    day2 = project_requirements(saved.requirement_records, draft_id=str(draft.id), city="杭州", day_index=2)
    assert {r["key"] for r in day1} == {"pace", "interest"}
    assert {r["key"] for r in day2} == {"budget_fen", "interest"}
    assert next(r for r in day2 if r["key"] == "budget_fen")["scope"]["day_index"] == 2
    photo = next(r for r in saved.requirement_records if r["key"] == "interest")
    saved = DraftService(repo, Generator()).revoke_requirement("owner", draft.id, saved.version, photo["id"])
    _, state = asyncio.run(sync_draft_requirements(envelope.model_copy(update={"read_draft_version": saved.version}),
        "把刚才的要求加入当前草稿", "repeat", history, port))
    assert state["status"] == "unchanged"
    assert next(r for r in repo.get("owner", draft.id).requirement_records if r["id"] == photo["id"])["status"] == "revoked"
    engine.dispose()


def test_bridge_out_of_range_day_rejects_entire_import_without_partial_write():
    from app.assistant_places import ContentServicePlaces
    from app.draft_requirement_bridge import sync_draft_requirements
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    repo = DraftRepository(engine)
    draft = repo.create("owner", DraftCreate(city="杭州", day_count=3))
    source = capture_explicit_requirements([], "喜欢拍照，第4天预算200元", scope={"kind": "topic", "topic_id": "bridge", "city": "杭州"}, source_ref="source")
    history = [{"context": ContextEnvelope(topic_id="bridge", browsing_city="杭州", requirement_records=source).model_dump(mode="json")}]
    envelope = ContextEnvelope(topic_id="bridge", browsing_city="杭州", read_draft_id=draft.id, read_draft_version=draft.version)
    _, state = asyncio.run(sync_draft_requirements(envelope, "把刚才的要求加入当前草稿", "import", history, ContentServicePlaces(None, repo, "owner")))
    assert state["status"] == "scope_out_of_range" and state["message"]
    assert repo.get("owner", draft.id).model_dump(mode="json") == draft.model_dump(mode="json")
    engine.dispose()


def test_trip_chat_captures_from_canonical_api_state_not_stale_topic_union():
    from app.database import session_factory
    from app.assistant_service import send_message
    from app.assistant_places import ContentServicePlaces
    from app.main import app
    from app.requirement_routes import create_router as trip_router
    from uuid import UUID
    class Port(ContentServicePlaces):
        async def search(self, **_): return []
        async def get_place(self, _): return None
    async def answer(*_): return "已结合当前要求回答。"
    api = FastAPI(); api.include_router(trip_router(lambda: "owner"))
    with TestClient(app) as original, TestClient(api) as client:
        trip = original.post("/api/v1/trips", json={"title": "canonical requirements", "destination": "杭州", "start_date": "2026-11-01", "end_date": "2026-11-03"}).json()
        session_id = fresh_assistant_session_id()
        async def send(text):
            async with session_factory() as session:
                return await send_message(session, UUID(session_id), text, uuid4(), companion_responder=answer, place_port=Port(None),
                    context={"topic_id": "canonical", "browsing_city": "杭州", "read_trip_id": trip["id"]})
        asyncio.run(send("希望轻松"))
        path = f"/api/v1/trips/{trip['id']}/requirements"
        state = client.get(path).json()
        intensive = client.post(path, json={"expected_version": state["version"], "text": "全程紧凑", "key": "pace", "value": "intensive"})
        assert intensive.status_code == 200
        asyncio.run(send("希望轻松"))
        current = client.get(path).json()
        active = [r for r in current["records"] if r["key"] == "pace" and r["status"] == "active"]
        assert len(active) == 1 and active[0]["value"] == "relaxed"
        prior = next(r for r in intensive.json()["records"] if r["status"] == "active")
        assert prior["id"] in active[0]["supersedes"]
