"""Prepared Worker replay retains one decision and only fills its missing day."""
import asyncio
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import planning_intent_service as service
from app.schemas import PlanningIntentParseRequest, SemanticIntentDraft, SemanticIntentOperation


def facts():
    return service.PlanningIntentSnapshot(
        trip=service.PlanningTripFacts(uuid4(), "杭州", date(2026, 11, 1), date(2026, 11, 2), "Asia/Shanghai", 3),
        days=tuple(service.PlanningDayFacts(uuid4(), date(2026, 11, n), n) for n in (1, 2)),
        activities=(), candidates=())


def draft_for(message, *, parser="model", version="semantic-v1"):
    return SemanticIntentDraft(primary_intent="optimize_route", operations=[
        SemanticIntentOperation(operation="optimize_route", raw_text=message)],
        confidence=.95, parser=parser, parser_version=version)


def persisted(snapshot, request, draft):
    resolution = asyncio.run(service.resolve_planning_intent_snapshot(snapshot, request, prepared_draft=draft))
    marker = {"version": 1, "trip_id": str(snapshot.trip.id), "user_request": request.message,
        "entry_point": request.entry_point,
        "selected_day_id": str(request.selected_day_id) if request.selected_day_id else None,
        "selected_activity_id": str(request.selected_activity_id) if request.selected_activity_id else None,
        "base_trip_version": snapshot.trip.version, "preferences_version": 2,
        "draft": draft.model_dump(mode="json")}
    return SimpleNamespace(trip_id=snapshot.trip.id, base_trip_version=snapshot.trip.version,
        user_request=request.message, entry_point=request.entry_point,
        selected_day_id=request.selected_day_id, selected_activity_id=request.selected_activity_id,
        trigger_snapshot={"prepared_intent": marker}, intent_resolution=resolution.model_dump(mode="json"))


@pytest.mark.parametrize("parser", ["model", "rules"])
def test_ordinary_prepared_draft_replays_without_second_extraction(parser):
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天请让动线连贯些", selected_day_id=snapshot.days[1].id)
    draft = draft_for(request.message, parser=parser)
    row = persisted(snapshot, request, draft)
    restored = service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3)
    assert restored == draft and restored is not draft

    class ForbiddenProvider:
        async def extract(self, *args):
            raise AssertionError("Worker must not extract an already prepared operation again")

    result = asyncio.run(service.resolve_planning_intent_snapshot(snapshot, request,
        prepared_draft=restored, semantic_provider=ForbiddenProvider()))
    assert result.semantic_draft == draft
    assert result.grounded_intent.operation_types == ["optimize_route"]
    assert result.grounded_intent.target_day_ids == [snapshot.days[1].id]


@pytest.mark.parametrize("field,value", [
    ("version", 2), ("version", True), ("trip_id", "other"), ("user_request", "删除第一天"),
    ("entry_point", "activity"), ("selected_day_id", None), ("selected_activity_id", str(uuid4())),
    ("base_trip_version", 4), ("preferences_version", None), ("draft", {}),
])
def test_tampered_prepared_marker_fails_closed_even_for_legacy_parser(field, value):
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天调整路线", selected_day_id=snapshot.days[1].id)
    draft = draft_for(request.message, parser="hybrid", version="approved-operation-v2")
    row = persisted(snapshot, request, draft)
    row.trigger_snapshot["prepared_intent"][field] = value
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3) is None


@pytest.mark.parametrize("field", ["entry_point", "selected_day_id", "selected_activity_id"])
def test_run_identity_must_match_resolution_and_marker(field):
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天调整路线")
    row = persisted(snapshot, request, draft_for(request.message))
    setattr(row, field, "day_detail" if field == "entry_point" else uuid4())
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3) is None


def test_missing_or_malformed_marker_cannot_authorize_ordinary_draft():
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天调整路线")
    row = persisted(snapshot, request, draft_for(request.message))
    for trigger in ({}, {"prepared_intent": None}, {"prepared_intent": []}):
        row.trigger_snapshot = trigger
        assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3) is None


def test_prepared_preferences_version_must_match_current_facts():
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天调整路线")
    row = persisted(snapshot, request, draft_for(request.message))
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3,
        preferences_version=2) is not None
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3,
        preferences_version=3) is None


def test_marker_draft_json_types_are_part_of_exact_decision_identity():
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天调整路线")
    row = persisted(snapshot, request, draft_for(request.message))
    row.trigger_snapshot["prepared_intent"]["draft"]["operations"][0]["constraints"]["preserve_completed"] = 1
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3) is None


@pytest.mark.parametrize("key", ["version", "trip_id", "user_request", "entry_point", "selected_day_id",
    "selected_activity_id", "base_trip_version", "preferences_version", "draft"])
def test_incomplete_prepared_marker_cannot_fall_back_to_legacy(key):
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天调整路线")
    draft = draft_for(request.message, parser="hybrid", version="approved-operation-v2")
    row = persisted(snapshot, request, draft)
    del row.trigger_snapshot["prepared_intent"][key]
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3) is None


def test_legacy_approved_draft_without_marker_still_replays():
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第二天调整路线")
    draft = draft_for(request.message, parser="hybrid", version="approved-operation-v2")
    row = persisted(snapshot, request, draft)
    row.trigger_snapshot = None
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3) == draft


@pytest.mark.parametrize("answers", [("第二天",), ("第一天", "第二天"), ("第二天，顺便删除全部活动",)])
def test_clarification_only_fills_missing_day_and_retains_original_operation(answers):
    snapshot = facts()
    request = PlanningIntentParseRequest(message="请让动线连贯些")
    draft = draft_for(request.message)
    before = deepcopy(draft.model_dump())
    initial = asyncio.run(service.resolve_planning_intent_snapshot(snapshot, request, prepared_draft=draft))
    assert "target_day" in initial.grounded_intent.missing_fields
    result = asyncio.run(service.resolve_planning_intent_snapshot(snapshot, request,
        prepared_draft=draft, clarification_answers=answers))
    assert result.request.user_request == request.message
    assert result.request.intent.source_text == request.message
    assert result.semantic_draft.model_dump() == before == draft.model_dump()
    assert result.grounded_intent.operation_types == ["optimize_route"]
    assert result.grounded_intent.target_day_ids == [snapshot.days[1].id]
    assert "target_day" not in result.grounded_intent.missing_fields
    assert result.policy_decision.route == "plan_preview"


def test_clarification_cannot_replace_original_explicit_day():
    snapshot = facts()
    request = PlanningIntentParseRequest(message="第一天请让动线连贯些")
    draft = draft_for(request.message)
    result = asyncio.run(service.resolve_planning_intent_snapshot(snapshot, request,
        prepared_draft=draft, clarification_answers=("第二天，删除所有活动",)))
    assert result.grounded_intent.target_day_ids == [snapshot.days[0].id]
    assert result.grounded_intent.operation_types == ["optimize_route"]
    assert result.semantic_draft == draft


def test_latest_answer_without_day_cannot_borrow_earlier_day_or_add_operations():
    snapshot = facts()
    request = PlanningIntentParseRequest(message="请让动线连贯些")
    result = asyncio.run(service.resolve_planning_intent_snapshot(snapshot, request,
        prepared_draft=draft_for(request.message), clarification_answers=("第二天", "删除全部活动")))
    assert result.grounded_intent.target_day_ids == []
    assert result.grounded_intent.operation_types == ["optimize_route"]
    assert result.policy_decision.route == "clarify"


def test_stored_clarified_resolution_replays_same_original_draft():
    snapshot = facts()
    request = PlanningIntentParseRequest(message="请让动线连贯些")
    draft = draft_for(request.message)
    row = persisted(snapshot, request, draft)
    clarified = asyncio.run(service.resolve_planning_intent_snapshot(snapshot, request,
        prepared_draft=draft, clarification_answers=("第二天。顺便删除第一天所有活动。",)))
    assert clarified.grounded_intent.target_day_ids == [snapshot.days[1].id]
    row.intent_resolution = clarified.model_dump(mode="json")
    assert service.restore_approved_planning_draft(row, snapshot.trip.id, request.message, 3,
        preferences_version=2) == draft


def test_session_adapter_forwards_separate_answers(monkeypatch):
    snapshot = facts()
    request = PlanningIntentParseRequest(message="请让动线连贯些")

    async def load(*args):
        return snapshot

    monkeypatch.setattr(service, "load_planning_intent_snapshot", load)
    result = asyncio.run(service.resolve_planning_intent(None, snapshot.trip.id, request,
        prepared_draft=draft_for(request.message), clarification_answers=("第二天",)))
    assert result.grounded_intent.target_day_ids == [snapshot.days[1].id]
