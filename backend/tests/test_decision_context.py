import pytest

from app.decision_context import DecisionContextInvariantError, assert_decision_context_invariants, build_decision_context


def _context() -> tuple[dict, dict, dict]:
    completed = "activity-completed"
    current = "activity-current"
    target = "activity-target"
    locked = "activity-locked"
    editable = "activity-editable"
    day = {
        "id": "day-1", "date": "2026-10-20", "route_legs": [
            {"from_activity_id": current, "to_activity_id": target, "mode": "walk", "distance_meters": 900,
             "duration_minutes": 14, "provider": "AMap Route 2.0"},
        ],
        "activities": [
            {"id": completed, "display_name": "已完成", "scheduled_time": "09:00", "duration_minutes": 30,
             "category": "culture", "longitude": 120.1, "latitude": 30.1, "schedule_locked": False, "status": "completed"},
            {"id": current, "display_name": "当前活动", "scheduled_time": "10:00", "duration_minutes": 30,
             "category": "culture", "longitude": 120.2, "latitude": 30.2, "schedule_locked": False, "status": "active"},
            {"id": target, "display_name": "导航目标", "scheduled_time": "11:00", "duration_minutes": 30,
             "category": "food", "longitude": 120.3, "latitude": 30.3, "schedule_locked": False, "status": "planned"},
            {"id": locked, "display_name": "锁定活动", "scheduled_time": "12:00", "duration_minutes": 30,
             "category": "culture", "longitude": 120.4, "latitude": 30.4, "schedule_locked": True, "status": "planned"},
            {"id": editable, "display_name": "可调整活动", "scheduled_time": "13:00", "duration_minutes": 30,
             "category": "nature", "longitude": 120.5, "latitude": 30.5, "schedule_locked": False, "status": "planned"},
        ],
    }
    context = {
        "days": [day], "preferences": {"pace": "balanced", "max_walking_minutes": 80},
        "external_facts": {"search": {"status": "ok"}},
        "execution_recovery": {
            "frozen_activity_ids": [completed], "protected_activity_ids": [current, target],
            "execution_state": {
                "current_activity_id": current, "navigation_target_activity_id": target,
                "current_eta": "2026-10-20T11:45:00+08:00", "delay_minutes": 45,
                "minimum_downstream_slack_minutes": -34, "first_impacted_activity_id": target,
                "risk_state": "infeasible",
            },
        },
    }
    goals = {"target_days": ["2026-10-20"], "hard_goals": {"end_before": "18:00"}, "soft_goals": {"pace": "relaxed"}}
    resolution = {"grounded_intent": {"target_day_ids": ["day-1"]}, "request": {"intent": {"protected_activity_ids": []}}}
    return context, goals, resolution


def test_context_exposes_persisted_route_and_execution_facts_with_provenance():
    context, goals, resolution = _context()
    result = build_decision_context(context=context, goals=goals, resolution=resolution)

    route = result["route_context"]["days"][0]
    execution = result["execution_context"]
    assert route["route_fact_status"] == "available"
    assert route["route_legs"][0]["source"] == "AMap Route 2.0"
    assert execution["delay_minutes"] == 45
    assert execution["current_eta"] == "2026-10-20T11:45:00+08:00"
    assert execution["minimum_downstream_slack_minutes"] == -34
    assert execution["current_activity"]["name"] == "当前活动"
    assert result["provenance"]["route_context"] == "persisted_amap_route"


def test_context_carries_request_scoped_decision_memory_with_provenance():
    context, goals, resolution = _context()
    memory = [{
        "source_revision_id": "revision-a", "source_run_id": "run-a", "decision": "rejected",
        "rejection_reason_code": "too_much_walking", "rejection_reason_text": "走路太多",
        "target_day": "2026-10-20", "retrieved_at": "2026-09-24T10:00:00+08:00",
    }]
    result = build_decision_context(context=context, goals=goals, resolution=resolution, decision_memory=memory)

    assert result["decision_memory"] == memory
    assert result["provenance"]["decision_memory"] == "same_trip_same_target_day_rejected_revisions"


def test_activity_semantics_coexist_with_goals_memory_and_recovery_context():
    context, goals, resolution = _context()
    editable = context["days"][0]["activities"][-1]
    editable.update(importance="must_do", can_skip=False, minimum_duration_minutes=20,
                    importance_source="user_explicit", can_skip_source="user_explicit",
                    minimum_duration_source="user_confirmed")
    memory = [{"decision": "rejected", "rejection_reason_code": "too_rushed"}]
    result = build_decision_context(context=context, goals=goals, resolution=resolution, decision_memory=memory)

    semantic = next(item for item in result["activity_decision_semantics"] if item["activity_id"] == editable["id"])
    assert semantic["importance"] == "must_do"
    assert semantic["can_skip"] is False
    assert semantic["minimum_duration_minutes"] == 20
    assert semantic["provenance"]["minimum_duration_minutes"] == "user_confirmed"
    assert editable["id"] in result["protected_constraints"]["editable_activity_ids"]
    assert result["goal_context"] == goals
    assert result["decision_memory"] == memory
    assert result["execution_context"]["delay_minutes"] == 45


def test_completed_current_navigation_target_and_locked_are_never_editable():
    context, goals, resolution = _context()
    result = build_decision_context(context=context, goals=goals, resolution=resolution)
    contract = result["protected_constraints"]

    assert set(contract["protected_activity_ids"]) == {
        "activity-completed", "activity-current", "activity-target", "activity-locked",
    }
    assert contract["editable_activity_ids"] == ["activity-editable"]
    assert not set(contract["protected_activity_ids"]) & set(contract["editable_activity_ids"])


def test_invariant_rejects_protected_editable_overlap_and_unknown_route_endpoint():
    with pytest.raises(DecisionContextInvariantError) as exc_info:
        assert_decision_context_invariants({
            "goal_context": {"target_days": ["2026-10-20"]},
            "formal_itinerary": {"days": [{"date": "2026-10-20", "activities": [{"activity_id": "A"}]}]},
            "route_context": {"days": [{"route_legs": [{"from_activity_id": "A", "to_activity_id": "missing"}]}]},
            "execution_context": {},
            "protected_constraints": {"protected_activity_ids": ["A"], "editable_activity_ids": ["A"]},
        })
    assert set(exc_info.value.codes) == {"protected_editable_overlap", "route_leg_references_unknown_activity"}
