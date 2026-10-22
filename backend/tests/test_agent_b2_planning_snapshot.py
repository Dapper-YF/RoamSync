"""Detached planning facts and an already-decided operation cannot drift."""
import asyncio
from dataclasses import FrozenInstanceError, is_dataclass
from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.planning_intent_service as service
from app.database import DayPlan, PlaceCandidate
from app.schemas import PlanningIntentParseRequest, SemanticIntentDraft, SemanticIntentOperation


class Rows:
    def __init__(self, rows): self.rows = rows
    def __iter__(self): return iter(self.rows)
    def all(self): return self.rows
    def tuples(self): return self


class ReadSession:
    def __init__(self):
        self.trip = SimpleNamespace(id=uuid4(), destination="汕头", start_date=date(2026, 11, 18),
            end_date=date(2026, 11, 19), timezone="Asia/Shanghai", version=3)
        self.days = [SimpleNamespace(id=uuid4(), date=date(2026, 11, 18 + i), position=i) for i in range(2)]
        self.place = SimpleNamespace(id=uuid4(), name="甲馆", category="attraction")
        self.activity = SimpleNamespace(id=uuid4(), custom_name=None, scheduled_time=time(10), schedule_locked=False)
    async def get(self, model, identity): return self.trip if identity == self.trip.id else None
    async def scalars(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        return Rows(self.days if entity is DayPlan else [self.place])
    async def execute(self, stmt): return Rows([(self.activity, self.days[1], self.place)])
    async def scalar(self, stmt): return None


def loader():
    fn = getattr(service, "load_planning_intent_snapshot", None)
    assert callable(fn), "planning needs an explicit detached snapshot loader"
    return fn


def resolver():
    fn = getattr(service, "resolve_planning_intent_snapshot", None)
    assert callable(fn), "network semantic work needs a resolver with no Session"
    return fn


def test_snapshot_is_frozen_and_does_not_keep_mutable_orm_rows():
    session = ReadSession()
    request = PlanningIntentParseRequest(message="看看当前安排")
    snapshot = asyncio.run(loader()(session, session.trip.id, request))
    assert is_dataclass(snapshot) and snapshot.trip.version == 3
    assert isinstance(snapshot.days, tuple) and snapshot.days[1].date == date(2026, 11, 19)
    session.trip.destination = "旧对象被改"
    session.place.name = "旧对象被改"
    session.days[1].position = 99
    assert snapshot.trip.destination == "汕头"
    assert snapshot.candidates[0].name == "甲馆"
    assert snapshot.days[1].position == 1
    with pytest.raises(FrozenInstanceError):
        snapshot.trip.version = 4


def test_prepared_draft_keeps_query_without_calling_model_or_changing_task():
    async def run():
        session = ReadSession()
        request = PlanningIntentParseRequest(message="分析第二天甲馆的安排，只解释，不调整")
        snapshot = await loader()(session, session.trip.id, request)
        class ExplodingProvider:
            async def extract(self, *args): raise AssertionError("second interpretation")
        draft = SemanticIntentDraft(primary_intent="query_trip", operations=[
            SemanticIntentOperation(operation="query_trip", raw_text=request.message)],
            confidence=.99, parser="hybrid", parser_version="approved-operation-v2")
        resolution = await resolver()(snapshot, request, prepared_draft=draft, semantic_provider=ExplodingProvider())
        assert resolution.semantic_draft == draft
        assert resolution.policy_decision.route == "answer"
        assert resolution.grounded_intent.operation_types == ["query_trip"]
    asyncio.run(run())


def test_prepared_remove_regrounds_actual_day_activity_and_keeps_other_days():
    async def run():
        session = ReadSession()
        request = PlanningIntentParseRequest(message="第二天把甲馆撤掉，其他日期不动")
        snapshot = await loader()(session, session.trip.id, request)
        draft = SemanticIntentDraft(primary_intent="remove_activity", operations=[
            SemanticIntentOperation(operation="remove_activity", raw_text=request.message,
                activity_mentions=["甲馆"], date_expression="第二天")],
            confidence=.99, parser="hybrid", parser_version="approved-operation-v2")
        result = await resolver()(snapshot, request, prepared_draft=draft)
        assert result.semantic_draft == draft
        assert result.request.intent.intent_type == "modify_day"
        assert result.grounded_intent.target_day_ids == [session.days[1].id]
        assert result.grounded_intent.target_activity_ids == [session.activity.id]
        assert result.policy_decision.route == "plan_preview"
    asyncio.run(run())


def test_prepared_draft_never_bypasses_foreign_ui_target_or_missing_place():
    async def run():
        session = ReadSession()
        request = PlanningIntentParseRequest(message="第二天加入乙馆")
        snapshot = await loader()(session, session.trip.id, request)
        foreign = request.model_copy(update={"selected_day_id": uuid4()})
        with pytest.raises(service.IntentContextError):
            await resolver()(snapshot, foreign)
        draft = SemanticIntentDraft(primary_intent="add_activity", operations=[
            SemanticIntentOperation(operation="add_activity", raw_text=request.message,
                date_expression="第二天", place_mentions=["乙馆"])],
            confidence=.99, parser="hybrid", parser_version="approved-operation-v2")
        result = await resolver()(snapshot, request, prepared_draft=draft)
        assert result.grounded_intent.unresolved_place_mentions == ["乙馆"]
        assert result.policy_decision.route == "clarify"
    asyncio.run(run())


@pytest.mark.parametrize("prefix,clause,period", [
    ("先解释第一天甲馆的安排；", "第二天加入乙馆", None),
    ("第一天上午先回答问题；", "第二天下午加入乙馆", "afternoon"),
])
def test_prepared_operation_owns_date_and_period_in_compound_request(prefix, clause, period):
    async def run():
        session = ReadSession()
        session.place.name = "乙馆"
        request = PlanningIntentParseRequest(message=prefix + clause)
        snapshot = await loader()(session, session.trip.id, request)
        draft = SemanticIntentDraft(primary_intent="add_activity", operations=[
            SemanticIntentOperation(operation="add_activity", raw_text=clause, date_expression="第二天",
                period=period, place_mentions=["乙馆"])], confidence=.99, parser_version="approved-operation-v2")
        result = await resolver()(snapshot, request, prepared_draft=draft)
        assert result.request.intent.time_scope.day_date == session.days[1].date
        assert result.request.intent.time_scope.period == period
        assert result.grounded_intent.target_day_ids == [session.days[1].id]
        assert result.policy_decision.route == "plan_preview"
    asyncio.run(run())


def test_incompatible_prepared_operation_days_do_not_silently_mutate_first_day():
    async def run():
        session = ReadSession()
        request = PlanningIntentParseRequest(message="第一天加入甲馆；第二天也加入甲馆")
        snapshot = await loader()(session, session.trip.id, request)
        draft = SemanticIntentDraft(primary_intent="add_activity", operations=[
            SemanticIntentOperation(operation="add_activity", raw_text=clause, place_mentions=["甲馆"])
            for clause in request.message.split("；")], confidence=.99, parser_version="approved-operation-v2")
        result = await resolver()(snapshot, request, prepared_draft=draft)
        assert result.policy_decision.route == "clarify"
        assert result.requires_clarification
    asyncio.run(run())


@pytest.mark.parametrize("selected_index,expected_route", [(0, "clarify"), (1, "plan_preview"), (None, "clarify")])
def test_period_only_operation_reconciles_its_own_ui_day(selected_index, expected_route):
    async def run():
        session = ReadSession()
        session.place.name = "乙馆"
        request = PlanningIntentParseRequest(message="下午优化路线；第二天加入乙馆",
            selected_day_id=session.days[selected_index].id if selected_index is not None else None)
        snapshot = await loader()(session, session.trip.id, request)
        draft = SemanticIntentDraft(primary_intent="optimize_route", operations=[
            SemanticIntentOperation(operation="optimize_route", raw_text="下午优化路线", period="afternoon"),
            SemanticIntentOperation(operation="add_activity", raw_text="第二天加入乙馆",
                date_expression="第二天", place_mentions=["乙馆"])], confidence=.99,
            parser_version="approved-operation-v2")
        result = await resolver()(snapshot, request, prepared_draft=draft)
        assert result.policy_decision.route == expected_route
        if expected_route == "plan_preview":
            assert result.grounded_intent.target_day_ids == [session.days[1].id]
            assert result.request.intent.time_scope.period == "afternoon"
    asyncio.run(run())
