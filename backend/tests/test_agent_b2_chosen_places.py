"""Synthetic map fixtures prove identity/write boundaries, not real AMap quality."""
import asyncio
from datetime import date
import os
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.destination_research as research
from app.database import Activity, PlaceCandidate, SourceRecord, Trip, TripPreferences
from app.planning_errors import PlannerProviderError, PlannerConstraintsUnsatisfiedError
from app.schemas import PlaceSearchResultResponse


@pytest.fixture
def sessions():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


def synthetic_poi(name="甲馆", identity="synthetic_a", address="测试区甲街12号"):
    return PlaceSearchResultResponse(provider_place_id=identity, name=name, category="culture",
        description=address, neighborhood="测试区", longitude=120.1, latitude=30.2,
        suggested_duration_minutes=60, estimated_cost_fen=0,
        source_url="https://www.amap.com/search?id=" + identity)


async def new_trip(sessions, approved=("甲馆", "乙馆")):
    async with sessions() as db:
        trip = Trip(title="Synthetic chosen POI boundary", destination="测试市", destination_adcode="330100",
            start_date=date(2026, 11, 29), end_date=date(2026, 11, 29))
        db.add(trip)
        await db.flush()
        db.add(TripPreferences(trip_id=trip.id))
        await db.commit()
        return trip.id, {"trip": {"version": trip.version, "destination": trip.destination,
            "destination_adcode": trip.destination_adcode}, "preferences": {"version": 1},
            "days": [{"date": "2026-11-29", "activities": []}], "approved_requested_places": list(approved)}


async def stored(sessions, trip_id):
    async with sessions() as db:
        places = list((await db.scalars(select(PlaceCandidate).where(PlaceCandidate.trip_id == trip_id))).all())
        sources = list((await db.scalars(select(SourceRecord).where(SourceRecord.trip_id == trip_id))).all())
        activities = list((await db.scalars(select(Activity).join(PlaceCandidate,
            Activity.place_candidate_id == PlaceCandidate.id).where(PlaceCandidate.trip_id == trip_id))).all())
        return places, sources, activities


async def clean_trip(sessions, trip_id):
    async with sessions() as db:
        await db.execute(delete(Trip).where(Trip.id == trip_id))
        await db.commit()


def no_discovery(monkeypatch):
    build = AsyncMock(side_effect=AssertionError("chosen identity must not invoke discovery model"))
    model = AsyncMock(side_effect=AssertionError("chosen identity must not invoke discovery model"))
    monkeypatch.setattr(research, "build_model_client", build)
    monkeypatch.setattr(research, "create_model_response", model)
    monkeypatch.setattr(research.asyncio, "sleep", AsyncMock())
    return build, model


def test_chosen_names_work_without_web_and_persist_actual_map_identity(sessions, monkeypatch):
    build, model = no_discovery(monkeypatch)
    async def run():
        trip_id, context = await new_trip(sessions)
        searches = []
        async def search(name, city):
            searches.append((name, city))
            assert not db.in_transaction(), "no business transaction across external map work"
            return [synthetic_poi(name, "synthetic_" + str(len(searches)))]
        try:
            async with sessions() as db:
                result = await research.research_destination(db, trip_id, context=context,
                    user_request="甲馆选测试区甲街12号，乙馆选测试区甲街12号。请创建一日候选，只排这两个地方。",
                    external_facts={"search": {"status": "unavailable", "reason": "search_authentication_failed"}}, search=search)
                assert not db.in_transaction()
            assert searches == [("甲馆", "330100"), ("乙馆", "330100")]
            assert result["status"] == "available" and result["provider"] == "amap"
            assert result["evidence_kind"] == "map_identity_only" and result["model"] is None and result["token_usage"] == 0
            assert len(result["places"]) == 2
            assert all(item["requested"] and item["reason"] == "用户明确选择；地图仅核实地点身份，特色、营业、票价仍待核实。"
                for item in result["places"].values())
            places, sources, activities = await stored(sessions, trip_id)
            assert {p.name for p in places} == {"甲馆", "乙馆"}
            assert {p.slug for p in places} == {"amap-synthetic_1", "amap-synthetic_2"}
            assert all(source.provider == "AMap POI" and source.url.startswith("https://www.amap.com/") for source in sources)
            assert len(sources) == 2 and not activities
            build.assert_not_called(); model.assert_not_awaited()
        finally:
            await clean_trip(sessions, trip_id)
    asyncio.run(run())


@pytest.mark.parametrize("items,message,expected_id", [
    ([synthetic_poi(), synthetic_poi(identity="synthetic_other", address="测试区乙路8号")],
        "甲馆选测试区乙路8号。请创建候选，只排这一个地方。", "synthetic_other"),
    ([synthetic_poi()], "我选甲馆。请创建候选，只排这一个地方。", "synthetic_a"),
    ([synthetic_poi()], "只安排甲馆这一个地方，创建候选。", "synthetic_a"),
    ([synthetic_poi()], "甲馆选测试区甲街12号的那个。请创建候选，只排这一个地方。", "synthetic_a"),
    ([synthetic_poi()], "甲馆选测试区甲街12号的景区。请创建候选，只排这一个地方。", "synthetic_a"),
])
def test_unique_full_name_or_literal_address_selects_identity(sessions, monkeypatch, items, message, expected_id):
    no_discovery(monkeypatch)
    async def run():
        trip_id, context = await new_trip(sessions, ("甲馆",))
        try:
            async with sessions() as db:
                result = await research.research_destination(db, trip_id, context=context, user_request=message,
                    external_facts={}, search=AsyncMock(return_value=items))
            places, sources, activities = await stored(sessions, trip_id)
            assert len(result["places"]) == len(places) == len(sources) == 1 and not activities
            assert places[0].slug == "amap-" + expected_id
        finally:
            await clean_trip(sessions, trip_id)
    asyncio.run(run())


def test_live_wording_with_synthetic_map_results_preserves_both_choices(sessions, monkeypatch):
    no_discovery(monkeypatch)
    message = ("人民公园选小南街8号的那个，宽窄巷子选少城街道金河路口的景区。两个都想去。"
        "请创建成都2026年11月9日的一日候选，10点后出发，18点前结束，只排这两个地方，"
        "中午留一小时吃饭。先给我看，等我采用后再保存。")
    async def run():
        trip_id, context = await new_trip(sessions, ("人民公园", "宽窄巷子"))
        search = AsyncMock(side_effect=[[synthetic_poi("人民公园", "synthetic_park", "小南街8号")],
            [synthetic_poi("宽窄巷子", "synthetic_lanes", "少城街道金河路口")]])
        try:
            async with sessions() as db:
                result = await research.research_destination(db, trip_id, context=context,
                    user_request=message, external_facts={}, search=search)
            assert {item["name"] for item in result["places"].values()} == {"人民公园", "宽窄巷子"}
            assert len((await stored(sessions, trip_id))[0]) == 2
        finally:
            await clean_trip(sessions, trip_id)
    asyncio.run(run())


@pytest.mark.parametrize("items,message", [
    ([synthetic_poi(), synthetic_poi(identity="synthetic_other", address="测试区乙路8号")], "我选甲馆"),
    ([synthetic_poi(), synthetic_poi(identity="synthetic_other")], "甲馆选测试区甲街12号"),
    ([synthetic_poi()], "甲馆选测试区不存在路999号"),
    ([synthetic_poi()], "我选甲馆（地址：测试区不存在路999号）"),
    ([synthetic_poi()], "我选甲馆地址为测试区不存在路999号"),
    ([synthetic_poi()], "我选测试区不存在路999号的甲馆"),
    ([], "我选甲馆"),
    ([synthetic_poi("测试市甲馆")], "我选甲馆"),
    ([synthetic_poi("甲馆停车场")], "我选甲馆"),
])
def test_unknown_ambiguous_alias_or_address_mismatch_has_zero_partial_writes(sessions, monkeypatch, items, message):
    no_discovery(monkeypatch)
    async def run():
        trip_id, context = await new_trip(sessions, ("乙馆", "甲馆"))
        search = AsyncMock(side_effect=[[synthetic_poi("乙馆", "synthetic_b")], items])
        try:
            async with sessions() as db:
                with pytest.raises(PlannerProviderError) as caught:
                    await research.research_destination(db, trip_id, context=context,
                        user_request="我选乙馆，" + message + "。请创建候选，只排这两个地方。",
                        external_facts={}, search=search)
                assert caught.value.code == "planner_requested_place_unresolved"
                assert not db.in_transaction()
            assert await stored(sessions, trip_id) == ([], [], [])
        finally:
            await clean_trip(sessions, trip_id)
    asyncio.run(run())


@pytest.mark.parametrize("message,approved", [
    ("不要去甲馆。请创建候选，只排这一个地方。", ["甲馆"]),
    ("假设我选甲馆，请创建候选，只排这一个地方。", ["甲馆"]),
    ("假定我选甲馆，请创建候选，只排这一个地方。", ["甲馆"]),
    ("如果有空，我选甲馆。请创建候选，只排这一个地方。", ["甲馆"]),
    ("朋友说我选甲馆。请创建候选，只排这一个地方。", ["甲馆"]),
    ("他说‘我选甲馆，只排这一个地方’。请创建候选。", ["甲馆"]),
    ("'我选甲馆，只排这一个地方'，只是例子。请创建候选。", ["甲馆"]),
    ("并非选甲馆。请创建候选，只排这一个地方。", ["甲馆"]),
    ("我没有选甲馆。请创建候选，只排这一个地方。", ["甲馆"]),
    ("甲馆没被选中。请创建候选，只排这一个地方。", ["甲馆"]),
    ("我选甲馆。请创建候选，只排这一个地方。先别安排了。", ["甲馆"]),
    ("甲馆可能合适。请创建候选，只排这一个地方。", ["甲馆"]),
    ("我选甲馆。请创建候选。", ["甲馆"]),
    ("我选甲馆。请创建候选，只排这两个地方。", ["甲馆", "模型发明的馆"]),
    ("我选甲馆。请创建候选，只排这一个地方。", []),
    ("我选甲馆。请创建候选，只排这两个地方。", ["甲馆"]),
    ("我选甲馆。请创建候选，只排这一个地方以外的地方。", ["甲馆"]),
    ("我选甲馆。同事说只排这一个地方。请创建候选。", ["甲馆"]),
    ("我选甲馆。请创建候选，只排这一个地方，另外推荐几个新景点。", ["甲馆"]),
])
def test_unapproved_nonliteral_negative_hypothetical_or_unbounded_choice_still_needs_web(sessions, monkeypatch, message, approved):
    build, model = no_discovery(monkeypatch)
    async def run():
        trip_id, context = await new_trip(sessions, approved)
        search = AsyncMock()
        try:
            async with sessions() as db:
                with pytest.raises(PlannerProviderError) as caught:
                    await research.research_destination(db, trip_id, context=context, user_request=message,
                        external_facts={}, search=search)
                assert caught.value.code == "planner_research_unavailable"
            search.assert_not_awaited(); build.assert_not_called(); model.assert_not_awaited()
            assert await stored(sessions, trip_id) == ([], [], [])
        finally:
            await clean_trip(sessions, trip_id)
    asyncio.run(run())


def test_map_only_identity_still_checks_versions_before_persisting(sessions, monkeypatch):
    no_discovery(monkeypatch)
    async def run():
        trip_id, context = await new_trip(sessions, ("甲馆",))
        async def search(*args):
            async with sessions() as changed:
                trip = await changed.get(Trip, trip_id)
                trip.version += 1
                await changed.commit()
            return [synthetic_poi()]
        try:
            async with sessions() as db:
                with pytest.raises(PlannerConstraintsUnsatisfiedError, match="planning_facts_changed"):
                    await research.research_destination(db, trip_id, context=context,
                        user_request="我选甲馆。请创建候选，只排这一个地方。", external_facts={}, search=search)
                await db.rollback()
            assert await stored(sessions, trip_id) == ([], [], [])
        finally:
            await clean_trip(sessions, trip_id)
    asyncio.run(run())


def test_chosen_identity_respects_lost_worker_claim_before_any_snapshot_write(sessions, monkeypatch):
    from app.planning_claim import active_claim, PlanningClaim, LostPlanningClaim
    no_discovery(monkeypatch)
    async def run():
        trip_id, context = await new_trip(sessions, ("甲馆",))
        claim = active_claim.set(PlanningClaim(run_id=uuid4(), trip_id=trip_id, token="synthetic_expired_claim"))
        try:
            async with sessions() as db:
                with pytest.raises(LostPlanningClaim):
                    await research.research_destination(db, trip_id, context=context,
                        user_request="我选甲馆。请创建候选，只排这一个地方。", external_facts={},
                        search=AsyncMock(return_value=[synthetic_poi()]))
                await db.rollback()
            assert await stored(sessions, trip_id) == ([], [], [])
        finally:
            active_claim.reset(claim)
            await clean_trip(sessions, trip_id)
    asyncio.run(run())


def test_two_chosen_names_cannot_collapse_onto_one_provider_identity(sessions, monkeypatch):
    no_discovery(monkeypatch)
    async def run():
        trip_id, context = await new_trip(sessions)
        try:
            async with sessions() as db:
                with pytest.raises(PlannerProviderError) as caught:
                    await research.research_destination(db, trip_id, context=context,
                        user_request="我选甲馆，我选乙馆。请创建候选，只排这两个地方。", external_facts={},
                        search=AsyncMock(side_effect=[[synthetic_poi()], [synthetic_poi("乙馆")]]))
                assert caught.value.code == "planner_requested_place_unresolved"
            assert await stored(sessions, trip_id) == ([], [], [])
        finally:
            await clean_trip(sessions, trip_id)
    asyncio.run(run())
