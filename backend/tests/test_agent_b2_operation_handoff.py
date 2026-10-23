import asyncio
from datetime import date
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
import pytest
import os

from app.assistant_capabilities import CapabilityDecision
from app.assistant_service import AssistantRouter, send_message
from app.database import AssistantSession
from app.schemas import CitySuggestionResponse


@pytest.fixture
def sessions():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


def test_single_approved_creation_prepares_preview_without_second_router(sessions, monkeypatch):
    message = "请创建绍兴2026年11月29日至30日的安排，第一天下午去鲁迅故里，第二天留空，先看候选等我采用。"
    async def selector(*args):
        return CapabilityDecision.model_validate({"intent":"create", "reason_code":"explicit_write",
            "authorization_quote":"请创建绍兴2026年11月29日至30日的安排", "names":["鲁迅故里"],
            "creation":{"destination":"绍兴", "start_date":"2026-11-29", "end_date":"2026-11-30",
                "flexible":True, "choices":[{"kind":"selected", "label":"鲁迅故里", "day_date":"2026-11-29",
                    "source_quote":"第一天下午去鲁迅故里"}]}})
    async def forbidden(*args):
        raise AssertionError("a second router changed the approved creation")
    monkeypatch.setattr(AssistantRouter, "decide", forbidden)
    async def cities(*args):
        return [CitySuggestionResponse(name="绍兴市", adcode="330600", citycode="0575", longitude=120.58, latitude=30.0)]
    async def run():
        async with sessions() as db:
            row = AssistantSession(messages=[], applied_actions={})
            db.add(row); await db.commit()
            row = await send_message(db, row.id, message, uuid4(), capability_selector=selector,
                city_search=cities, context={"topic_id":"b2-create", "prefer_flexible":True})
            assert row.trip_id is None and row.latest_run_id is None
            assert row.pending_action["choices"][0]["label"] == "鲁迅故里"
            assert row.pending_action["user_request"] == message
            assert "第二天留空" in row.pending_action["preferences"]
            assert "第一天下午去鲁迅故里" in row.messages[-1]["assistant"]
            assert row.pending_action["total_budget_fen"] is None
    asyncio.run(run())


def test_creation_cannot_invent_dates_or_expand_literal_place_label():
    from app.assistant_operation import approved_tool_decision
    from app.assistant_context import ContextEnvelope
    decision = CapabilityDecision.model_validate({"intent":"create", "reason_code":"explicit_write",
        "authorization_quote":"请创建成都一日候选", "creation":{"destination":"成都",
        "start_date":"2026-11-09", "end_date":"2026-11-09", "flexible":True}})
    result = approved_tool_decision(decision, "请创建成都一日候选", ContextEnvelope(), today=date(2026,10,22))
    assert result.tool == "reply" and "出发" in result.reply


def test_draft_operations_require_original_source_and_literal_place_mentions():
    from app.assistant_operation import approved_draft
    message = "请把第二天加入乙馆，其他不动"
    for raw, name in [("请删除第一天甲馆", "甲馆"), (message, "乙馆景区")]:
        draft = {"primary_intent":"add_activity", "operations":[{"operation":"add_activity", "raw_text":raw,
                 "place_mentions":[name]}], "confidence":.9, "parser_version":"model-output"}
        decision = CapabilityDecision.model_validate({"intent":"modify", "reason_code":"explicit_write",
            "authorization_quote":message, "planning_draft":draft})
        with pytest.raises(ValueError):
            approved_draft(decision, message)


def test_literal_whole_day_blank_has_no_invented_user_clock_range():
    decision = CapabilityDecision.model_validate({"intent":"create", "reason_code":"explicit_write",
        "authorization_quote":"请创建绍兴11月29日到30日的安排", "creation":{"destination":"绍兴",
        "start_date":"2026-11-29", "end_date":"2026-11-30", "flexible":True,
        "choices":[{"kind":"free_window","label":"第二天留白","source_quote":"第二天留白",
            "day_date":"2026-11-30","start":None,"end":None}]}})
    choice = decision.creation.choices[0]
    assert choice.kind == "blank_day" and choice.start is None and choice.end is None


def test_partial_day_blank_is_not_promoted_to_whole_day():
    with pytest.raises(ValueError):
        CapabilityDecision.model_validate({"intent":"create", "reason_code":"explicit_write",
            "authorization_quote":"请创建绍兴安排", "creation":{"destination":"绍兴",
            "start_date":"2026-11-29", "end_date":"2026-11-30", "flexible":True,
            "choices":[{"kind":"free_window","label":"第二天下午留白","source_quote":"第二天下午留白",
                "day_date":"2026-11-30"}]}})


def test_whole_day_preview_adoption_survives_reload_and_is_idempotent(sessions, monkeypatch):
    from sqlalchemy import select
    from app.assistant_service import confirm_action
    from app.arrangement_service import free_days
    from app.database import DayPlan, Activity
    message = "请创建绍兴2026年11月29日至30日的安排，第二天留白，先给我候选。"
    async def selector(*args):
        return CapabilityDecision.model_validate({"intent":"create","reason_code":"explicit_write",
            "authorization_quote":"请创建绍兴2026年11月29日至30日的安排",
            "creation":{"destination":"绍兴","start_date":"2026-11-29","end_date":"2026-11-30","flexible":True,
                "choices":[{"kind":"blank_day","label":"第二天留白","source_quote":"第二天留白","day_date":"2026-11-30"}]}})
    async def cities(*args):
        return [CitySuggestionResponse(name="绍兴市", adcode="330600", citycode="0575", longitude=120.58, latitude=30.0)]
    async def run():
        async with sessions() as db:
            row=AssistantSession(messages=[],applied_actions={});db.add(row);await db.commit()
            sid=row.id
            row=await send_message(db,sid,message,uuid4(),capability_selector=selector,city_search=cities,
                context={"topic_id":"b2-blank","prefer_flexible":True})
            assert row.trip_id is None
            action=row.pending_action["id"]
        async with sessions() as db:
            row=await confirm_action(db,sid,action,True)
            tid=row.trip_id
            assert await free_days(db,tid)=={date(2026,11,30)}
            assert not list((await db.scalars(select(Activity).join(DayPlan).where(DayPlan.trip_id==tid))).all())
        async with sessions() as db:
            row=await confirm_action(db,sid,action,True)
            assert row.trip_id==tid and row.pending_action is None
            assert await free_days(db,tid)=={date(2026,11,30)}
    asyncio.run(run())


def test_meal_budget_does_not_become_trip_total_budget():
    from app.assistant_context import ContextEnvelope
    from app.assistant_operation import approved_tool_decision
    message="请创建绍兴2026年11月29日至30日的安排，每顿饭预算70元。"
    decision=CapabilityDecision.model_validate({"intent":"create","reason_code":"explicit_write",
        "authorization_quote":message,"creation":{"destination":"绍兴","start_date":"2026-11-29",
            "end_date":"2026-11-30","total_budget_fen":7000,"flexible":True}})
    result=approved_tool_decision(decision,message,ContextEnvelope(),today=date(2026,10,22))
    assert result.tool=="create_trip" and result.total_budget_fen is None
    assert "每顿饭预算70元" in result.preferences


def test_selected_place_date_cannot_conflict_with_its_own_source_quote():
    from app.flexible_creation import prepare_choices
    from app.assistant_service import ToolDecision
    proposal=ToolDecision(tool="create_trip",reply="预览",destination="绍兴",start_date=date(2026,11,29),
        end_date=date(2026,11,30),flexible=True,choices=[{"kind":"selected","label":"鲁迅故里",
        "source_quote":"第一天去鲁迅故里","day_date":"2026-11-30"}])
    with pytest.raises(ValueError):
        asyncio.run(prepare_choices(proposal,{"name":"绍兴市"},"第一天去鲁迅故里"))


def test_one_affirmative_action_does_not_authorize_negated_peer_operation():
    from app.assistant_operation import approved_draft
    message="请调整第二天路线；不要加入乙馆。"
    decision=CapabilityDecision.model_validate({"intent":"modify","reason_code":"explicit_write",
        "authorization_quote":"请调整第二天路线","planning_draft":{"primary_intent":"add_activity",
            "operations":[{"operation":"add_activity","raw_text":"不要加入乙馆","place_mentions":["乙馆"]}],
            "confidence":.99,"parser_version":"model-output"}})
    with pytest.raises(ValueError):
        approved_draft(decision,message)


@pytest.mark.parametrize("label",["伙食预算", "单餐预算", "一顿饭预算"])
def test_only_explicit_total_budget_scope_may_write_trip_total(label):
    from app.assistant_context import ContextEnvelope
    from app.assistant_operation import approved_tool_decision
    message=f"请创建绍兴2026年11月29日至30日的安排，{label}70元。"
    decision=CapabilityDecision.model_validate({"intent":"create","reason_code":"explicit_write",
        "authorization_quote":message,"creation":{"destination":"绍兴","start_date":"2026-11-29",
        "end_date":"2026-11-30","total_budget_fen":7000,"flexible":True}})
    assert approved_tool_decision(decision,message,ContextEnvelope(),today=date(2026,10,22)).total_budget_fen is None


def test_cropped_write_source_cannot_remove_parent_clause_polarity():
    from app.assistant_operation import approved_draft
    message="请调整第二天路线；别加入乙馆。"
    decision=CapabilityDecision.model_validate({"intent":"modify","reason_code":"explicit_write",
        "authorization_quote":"请调整第二天路线","planning_draft":{"primary_intent":"add_activity",
        "operations":[{"operation":"add_activity","raw_text":"加入乙馆","place_mentions":["乙馆"]}],
        "confidence":.99,"parser_version":"model-output"}})
    with pytest.raises(ValueError):
        approved_draft(decision,message)


def test_selected_date_cannot_borrow_another_places_clause_date():
    from app.flexible_creation import prepare_choices
    from app.assistant_service import ToolDecision
    quote="11月29日去鲁迅故里，11月30日去沈园"
    proposal=ToolDecision(tool="create_trip",reply="预览",destination="绍兴",start_date=date(2026,11,29),
        end_date=date(2026,11,30),flexible=True,choices=[{"kind":"selected","label":"鲁迅故里",
        "source_quote":quote,"day_date":"2026-11-30"}])
    with pytest.raises(ValueError):
        asyncio.run(prepare_choices(proposal,{"name":"绍兴市"},quote))
