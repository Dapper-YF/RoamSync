"""Real PostgreSQL proof: SELECT-only read-through, guards, no second truth."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app.database import ActivityExecution, NavigationSession, engine, session_factory
from app.demo_seed import DEMO_TRIP_ID, demo_uuid
from app.main import app
from app.travel_facts.execution import ExecutionFactAdapter, SqlExecutionReader
from app.travel_facts.models import ExecutionSubject, FactRequirement
from app.travel_facts.repository import InMemoryFactRepository
from app.travel_facts.service import TravelFactService
from evals.travel_facts.fixtures import policies


def setup(client):
    assert client.post("/api/v1/demo/reset").status_code==200
    response=client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/execution/start",
        json={"day_plan_id":str(demo_uuid("day","day-1"))})
    assert response.status_code==200, response.text
    execution=response.json()
    leg=client.get(f"/api/v1/trips/{DEMO_TRIP_ID}/days").json()[0]["route_legs"][0]
    response=client.post(f"/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions",json={
        "trip_execution_id":execution["id"],"from_activity_id":leg["from_activity_id"],"to_activity_id":leg["to_activity_id"]})
    assert response.status_code==201,response.text
    return execution,response.json()


def subject(execution, navigation, **updates):
    return ExecutionSubject(**{**dict(kind="navigation_session",ref=navigation["id"],trip_ref=str(DEMO_TRIP_ID),
        trip_execution_ref=execution["id"],itinerary_version=navigation["itinerary_version"],
        route_revision=navigation["route_revision"]),**updates})


async def database_snapshot():
    async with session_factory() as db:
        names=(await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
        # Existing known table names only. Full row snapshots catch timestamp,
        # projection, log, event and planning-run mutations, not just row counts.
        return {name:(await db.execute(text(f'SELECT row_to_json(t)::text FROM "{name}" t ORDER BY row_to_json(t)::text'))).scalars().all()
                for name in names}


def test_postgresql_navigation_readthrough_select_only_and_observation_age_preserved():
    with TestClient(app) as client:
        execution,navigation=setup(client)
        async def scenario():
            now=datetime.now(UTC)
            async with session_factory() as db:
                item=await db.get(NavigationSession,uuid.UUID(navigation["id"]))
                # Synthetic accepted canonical row; fact adapter must read this
                # exact row, without invoking ingestion/detection or writes.
                item.last_location_sequence=1; item.last_observation_fingerprint="fixture-only"
                item.last_location_at=now; item.observation_source="real_gps"; item.navigation_status="navigating"
                item.current_eta=now+timedelta(minutes=20); item.remaining_distance_meters=1200
                item.last_location_longitude=120.15; item.last_location_latitude=30.25
                await db.commit()
            freshness,authority=policies(); repo=InMemoryFactRepository()
            resolver=TravelFactService(repo,freshness,authority,[ExecutionFactAdapter(freshness)])
            req=FactRequirement(fact_type="navigation.eta",subject=subject(execution,navigation))
            before=await database_snapshot(); statements=[]
            def record(conn,cursor,statement,parameters,context,executemany):
                statements.append(statement)
            event.listen(engine.sync_engine,"before_cursor_execute",record)
            try:
                first=await resolver.resolve_fact(req); second=await resolver.resolve_fact(req)
            finally:
                event.remove(engine.sync_engine,"before_cursor_execute",record)
            assert first.usable_as_current and second.value==first.value
            assert first.value.timestamp==now+timedelta(minutes=20)
            assert first.selected_fact.observed_at==second.selected_fact.observed_at==now
            assert await database_snapshot()==before
            assert statements and all(s.lstrip().upper().startswith(("SELECT","SET TRANSACTION")) for s in statements)
            assert sum("READ ONLY" in s for s in statements)==2
            assert not (await repo.get(req)).facts
            stale=TravelFactService(repo,freshness,authority,[ExecutionFactAdapter(freshness)],clock=lambda:now+timedelta(seconds=11))
            result=await stale.resolve_fact(req)
            assert result.resolution_status=="stale" and result.value is None
            assert await database_snapshot()==before
        asyncio.run(scenario())


@pytest.mark.parametrize("change", ["itinerary","route","ownership","unobserved"])
def test_postgresql_canonical_guards(change):
    with TestClient(app) as client:
        execution,navigation=setup(client)
        async def scenario():
            updates={"itinerary_version":2} if change=="itinerary" else {"route_revision":99} if change=="route" else {
                "trip_ref":"00000000-0000-0000-0000-000000000001"} if change=="ownership" else {}
            freshness,authority=policies()
            resolver=TravelFactService(InMemoryFactRepository(),freshness,authority,[ExecutionFactAdapter(freshness)])
            before=await database_snapshot()
            result=await resolver.resolve_fact(FactRequirement(fact_type="navigation.eta",subject=subject(execution,navigation,**updates)))
            assert result.value is None and not result.usable_as_current
            assert result.resolution_status==("unavailable" if change in {"itinerary","route"} else "no_evidence")
            if change in {"itinerary","route"}:
                assert result.provider_failures==("roamsync_execution:canonical_version_mismatch",)
            assert await database_snapshot()==before
        asyncio.run(scenario())


def test_postgresql_activity_readthrough_observes_canonical_update_without_cache():
    with TestClient(app) as client:
        execution,navigation=setup(client)
        async def scenario():
            async with session_factory() as db:
                item=await db.scalar(select(ActivityExecution).where(ActivityExecution.trip_execution_id==uuid.UUID(execution["id"])))
                item_id=item.id
            freshness,authority=policies(); repo=InMemoryFactRepository()
            resolver=TravelFactService(repo,freshness,authority,[ExecutionFactAdapter(freshness)])
            req=FactRequirement(fact_type="execution.activity_status",subject=subject(execution,navigation,
                kind="activity_execution",ref=str(item_id),route_revision=None))
            before=await database_snapshot(); first=await resolver.resolve_fact(req)
            assert first.value.status=="pending" and await database_snapshot()==before
            async with session_factory() as db:
                item=await db.get(ActivityExecution,item_id); item.status="completed"
                await db.commit()  # Canonical owner changes; not the fact layer.
            before=await database_snapshot(); second=await resolver.resolve_fact(req)
            assert second.value.status=="completed" and await database_snapshot()==before
            assert not (await repo.get(req)).facts
        asyncio.run(scenario())
