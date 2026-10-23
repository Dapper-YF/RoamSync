"""Real database probes at Graph/research external I/O boundaries."""
import asyncio

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import text

import app.planning_graph as graph_module
from app.database import PlanningRun, Trip, TripPreferences
from app.initial_places_service import prepare_initial_candidates
from test_planning_transactions import database, new_trip, force_semantic_fallback


class ProbeReached(Exception):
    pass


async def assert_no_idle_transactions(sessions):
    async with sessions() as probe:
        assert await probe.scalar(text("SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid() "
            "AND state = 'idle in transaction'")) == 0


@pytest.mark.parametrize("stage", ["facts", "semantic", "destination"])
def test_graph_external_work_has_no_retained_transaction(monkeypatch, stage):
    if stage == "semantic":
        force_semantic_fallback(monkeypatch)
    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            message = "请帮我规划南京完整行程"
            async with sessions() as setup:
                run = PlanningRun(trip_id=tid, run_type="initial_plan", status="queued",
                    user_request=message, base_trip_version=1)
                setup.add(run)
                await setup.commit()
                rid = run.id
            monkeypatch.setattr(graph_module, "session_factory", sessions)
            async def network_probe(*_args, **_kwargs):
                await assert_no_idle_transactions(sessions)
                raise ProbeReached
            async def facts(*_args, **_kwargs):
                return {"search": {"status": "available"}}
            monkeypatch.setattr(graph_module, "_collect_external_facts", network_probe if stage == "facts" else facts)
            class Provider:
                extract = staticmethod(network_probe)
            graph = graph_module.build_planning_graph(InMemorySaver(),
                semantic_provider=Provider() if stage == "semantic" else None,
                destination_researcher=network_probe if stage == "destination" else None)
            with pytest.raises(ProbeReached):
                await graph.ainvoke({"run_id": str(rid), "trip_id": str(tid), "user_request": message,
                    "run_type": "initial_plan"}, config={"configurable": {"thread_id": str(rid)}})
    asyncio.run(scenario())


def test_initial_place_search_closes_read_transaction():
    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            async with sessions() as caller:
                async def search(*_args):
                    assert not caller.in_transaction()
                    await assert_no_idle_transactions(sessions)
                    raise ProbeReached
                with pytest.raises(ProbeReached):
                    await prepare_initial_candidates(caller, tid, search=search)
    asyncio.run(scenario())


@pytest.mark.parametrize("changed", ["itinerary", "preferences"])
def test_graph_does_not_rebase_after_external_facts_change(monkeypatch, changed):
    from app.planning_errors import PlannerConstraintsUnsatisfiedError
    async def scenario():
        async with database() as sessions:
            tid = await new_trip(sessions)
            message = "请帮我规划南京完整行程"
            async with sessions() as setup:
                run = PlanningRun(trip_id=tid, run_type="initial_plan", status="queued",
                    user_request=message, base_trip_version=1)
                setup.add(run)
                await setup.commit()
                rid = run.id
            monkeypatch.setattr(graph_module, "session_factory", sessions)
            async def facts(*_args, **_kwargs):
                async with sessions() as editor:
                    if changed == "itinerary":
                        (await editor.get(Trip, tid)).version += 1
                    else:
                        (await editor.get(TripPreferences, tid)).version += 1
                    await editor.commit()
                return {"status": "synthetic evidence"}
            monkeypatch.setattr(graph_module, "_collect_external_facts", facts)
            graph = graph_module.build_planning_graph(InMemorySaver())
            with pytest.raises(PlannerConstraintsUnsatisfiedError, match="planning_facts_changed"):
                await graph.ainvoke({"run_id": str(rid), "trip_id": str(tid), "user_request": message,
                    "run_type": "initial_plan"}, config={"configurable": {"thread_id": str(rid)}})
    asyncio.run(scenario())
