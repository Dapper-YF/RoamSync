import uuid
from datetime import date, datetime, time, timezone

from app.decision_ledger import reconcile_route_repair_ledger, validate_decision_ledger
from app.schemas import CandidateActivity, CandidatePlanSnapshot, CandidateRouteLeg, DecisionLedgerEntry, PlanRevisionResponse


ACTIVITY = uuid.uuid4()
PLACE = uuid.uuid4()
NEW_PLACE = uuid.uuid4()
MEMORY = uuid.uuid4()


def context():
    return {
        "days": [{"date": "2026-10-20", "activities": [{"id": str(ACTIVITY), "place_id": str(PLACE), "display_name": "原活动", "scheduled_time": "15:00:00", "duration_minutes": 90, "status": "planned"}],
                  "route_legs": [{"mode": "walk", "duration_minutes": 60}]}],
        "candidates": [{"id": str(NEW_PLACE), "name": "新活动"}],
        "decision_context": {
            "goal_context": {"target_days": ["2026-10-20"], "hard_goals": {"end_before": "18:00"}, "soft_goals": {"minimize_walking": True}},
            "protected_constraints": {"editable_activity_ids": [str(ACTIVITY)], "protected_activity_ids": []},
            "activity_decision_semantics": [{"activity_id": str(ACTIVITY), "importance": "low", "can_skip": True, "minimum_duration_minutes": 45}],
            "decision_memory": [{"source_revision_id": str(MEMORY), "rejection_reason_code": "too_much_walking"}],
        },
    }


def activity(*, duration=90, start=time(15), replacement=ACTIVITY, place=PLACE):
    return CandidateActivity(candidate_id=str(uuid.uuid4()), day_date=date(2026, 10, 20), place_candidate_id=place,
                             planned_start_time=start, duration_minutes=duration, estimated_cost_fen=0,
                             transport_mode_to_here="walk", replaces_activity_id=replacement)


def snapshot(activities, ledger, walking=30, explanation="按你的要求调整行程。"):
    return CandidatePlanSnapshot(activities=activities, explanation=explanation, decision_ledger=ledger,
        route_legs=[CandidateRouteLeg(day_date=date(2026, 10, 20), from_activity_ref="a", to_activity_ref="b", position=0,
                                     mode="walk", distance_meters=2000, duration_minutes=walking, provider="amap",
                                     calculated_at=datetime.now(timezone.utc))])


def record(action, *, target=ACTIVITY, **overrides):
    value = {"decision_id": str(uuid.uuid4()), "action_type": action,
             "target_activity_id": str(target) if action != "add" else None,
             "target_place_candidate_id": str(target) if action == "add" else None,
             "primary_reason": "satisfy_hard_goal", "goal_refs": ["end_before"],
             "supporting_evidence": [{"source_type": "goal", "fact_key": "end_before", "value": "18:00"}]}
    value.update(overrides)
    return DecisionLedgerEntry.model_validate(value)


def codes(candidate, before=None):
    issues, summary = validate_decision_ledger(context=before or context(), snapshot=candidate)
    return {issue.code for issue in issues}, summary


def test_schema_parses_structured_ledger_and_valid_remove():
    ledger = [record("remove", semantic_refs=[{"activity_id": str(ACTIVITY), "importance": "low", "can_skip": True}])]
    parsed = CandidatePlanSnapshot.model_validate_json(snapshot([], ledger).model_dump_json())
    assert parsed.decision_ledger[0].action_type == "remove"
    assert codes(parsed)[1]["status"] == "validated"


def test_missing_destructive_and_addition_are_rejected():
    assert "decision_provenance_missing" in codes(snapshot([], []))[0]
    assert "unsupported_addition" in codes(snapshot([activity(replacement=None, place=NEW_PLACE)], []))[0]


def test_action_must_match_actual_diff_for_remove_shorten_and_move():
    assert "decision_action_mismatch" in codes(snapshot([activity()], [record("remove")]))[0]
    assert "decision_action_mismatch" in codes(snapshot([activity()], [record("shorten")]))[0]
    assert "decision_action_mismatch" in codes(snapshot([activity()], [record("move")]))[0]
    assert not codes(snapshot([activity(duration=60)], [record("shorten")]))[0]
    assert not codes(snapshot([activity(start=time(14))], [record("move")]))[0]


def test_invalid_goal_memory_and_semantic_references():
    candidate = snapshot([activity(duration=60)], [record("shorten", goal_refs=["not_a_goal"],
        memory_refs=[str(uuid.uuid4())], semantic_refs=[{"activity_id": str(ACTIVITY), "importance": "must_do"}])])
    assert {"decision_goal_ref_invalid", "decision_memory_ref_invalid", "decision_semantic_ref_invalid"} <= codes(candidate)[0]


def test_goal_memory_and_semantic_evidence_can_coexist_when_grounded():
    candidate = snapshot([activity(duration=60)], [record("shorten", primary_reason="respect_user_feedback",
        goal_refs=["end_before"], memory_refs=[str(MEMORY)],
        semantic_refs=[{"activity_id": str(ACTIVITY), "importance": "low", "can_skip": True, "minimum_duration_minutes": 45}],
        supporting_evidence=[{"source_type": "goal", "fact_key": "end_before", "value": "18:00"},
                             {"source_type": "activity_semantics", "fact_key": "minimum_duration_minutes", "value": 45}])])
    assert not codes(candidate)[0]


def test_recovery_addition_without_basis_has_invalid_provenance():
    before = context()
    before["execution_recovery"] = {"execution_state": {"current_activity_id": str(ACTIVITY)}}
    added = activity(replacement=None, place=NEW_PLACE)
    issues, summary = codes(snapshot([activity(), added], []), before)
    assert "unsupported_addition" in issues
    assert summary["status"] == "invalid"


def test_route_claim_must_be_true_and_match_actual_facts():
    ledger = [record("shorten", primary_reason="reduce_walking", goal_refs=["minimize_walking"],
                     supporting_evidence=[{"source_type": "route_fact", "fact_key": "walking_before_minutes", "value": 60},
                                          {"source_type": "route_fact", "fact_key": "walking_after_minutes", "value": 30}])]
    assert not codes(snapshot([activity(duration=60)], ledger))[0]
    assert "decision_route_claim_unsupported" in codes(snapshot([activity(duration=60)], ledger, walking=60))[0]
    wrong = ledger[0].model_copy(update={"supporting_evidence": [ledger[0].supporting_evidence[0], ledger[0].supporting_evidence[1].model_copy(update={"value": 20})]})
    assert "decision_route_evidence_mismatch" in codes(snapshot([activity(duration=60)], [wrong]))[0]


def test_addition_needs_real_basis_and_explanation_cannot_fake_walking_reduction():
    added = activity(replacement=None, place=NEW_PLACE)
    unsupported = record("add", target=NEW_PLACE, primary_reason="other", goal_refs=[], supporting_evidence=[{"source_type": "decision_context", "fact_key": "formal_itinerary"}])
    assert "unsupported_addition" in codes(snapshot([activity(), added], [unsupported]))[0]
    supported = record("add", target=NEW_PLACE, primary_reason="other", goal_refs=[], supporting_evidence=[{"source_type": "provider_fact", "fact_key": "place_candidate_id", "value": str(NEW_PLACE)}])
    assert not codes(snapshot([activity(), added], [supported]))[0]
    assert "decision_explanation_unsupported" in codes(snapshot([activity(), added], [supported], walking=60,
        explanation="这次安排减少步行，方便轻松游览。"))[0]


def test_historical_snapshot_stays_readable():
    assert codes(CandidatePlanSnapshot(activities=[activity()]))[1]["status"] == "unavailable"


def test_unparseable_ledger_is_invalid_not_historical_unavailable():
    candidate = CandidatePlanSnapshot(activities=[activity()], provenance_parse_errors=["decision_ledger_output_invalid"])
    issues, summary = validate_decision_ledger(context=context(), snapshot=candidate)
    assert summary["status"] == "invalid"
    assert summary["entries"] == []
    assert [issue.code for issue in issues] == ["decision_ledger_output_invalid"]


def test_route_repair_reconciles_planner_move_with_system_provenance():
    original = snapshot([activity(start=time(14))], [record("move", after={"start_time": "14:00"})])
    repaired = original.model_copy(update={"activities": [original.activities[0].model_copy(update={"planned_start_time": time(15, 45)})]})
    adjustment = {"candidate_id": original.activities[0].candidate_id, "day_date": "2026-10-20", "from_time": "14:00", "to_time": "15:45"}
    reconciled = reconcile_route_repair_ledger(original=original, repaired=repaired, context=context(), adjustments=[adjustment])
    assert reconciled.decision_ledger[0].source == "deterministic_route_repair"
    errors, summary = validate_decision_ledger(context=context(), snapshot=reconciled, schedule_adjustments=[adjustment])
    assert not errors
    assert summary["entries"][0]["source"] == "deterministic_route_repair"


def test_route_repair_drops_a_move_that_it_fully_reverted():
    original = snapshot([activity(start=time(14))], [record("move")])
    repaired = original.model_copy(update={"activities": [original.activities[0].model_copy(update={"planned_start_time": time(15)})]})
    adjustment = {"candidate_id": original.activities[0].candidate_id, "day_date": "2026-10-20", "from_time": "14:00", "to_time": "15:00"}
    reconciled = reconcile_route_repair_ledger(original=original, repaired=repaired, context=context(), adjustments=[adjustment])
    assert reconciled.decision_ledger == []
    assert not validate_decision_ledger(context=context(), snapshot=reconciled, schedule_adjustments=[adjustment])[0]


def test_revision_read_model_serializes_validated_summary():
    _, summary = codes(snapshot([], [record("remove", semantic_refs=[{"activity_id": str(ACTIVITY), "can_skip": True}])]))
    response = PlanRevisionResponse.model_validate({
        "id": str(uuid.uuid4()), "planning_run_id": str(uuid.uuid4()), "trip_id": str(uuid.uuid4()),
        "revision_number": 1, "reason": "调整行程", "before_snapshot": context(),
        "proposed_snapshot": snapshot([], [record("remove", semantic_refs=[{"activity_id": str(ACTIVITY), "can_skip": True}])]).model_dump(mode="json"),
        "difference_summary": {"decision_summary": summary}, "validation_result": {"valid": True, "errors": []},
        "source_ids": [], "status": "pending", "created_at": datetime.now(timezone.utc), "decided_at": None,
    })
    assert response.model_dump(mode="json")["difference_summary"]["decision_summary"]["entries"][0]["evidence_status"] == "validated"
