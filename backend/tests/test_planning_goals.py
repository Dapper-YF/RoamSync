from datetime import UTC, datetime, time
import uuid

from app.planning_goals import (
    can_repair_hard_goals,
    check_goal_satisfaction,
    extract_planning_goals,
    formal_route_facts,
)
from app.database import PlanRevision
from app.schemas import CandidateActivity, CandidatePlanSnapshot, CandidateRouteLeg, GoalSatisfactionResult, PlanRevisionResponse


def _context() -> dict:
    return {
        "preferences": {"max_walking_minutes": None},
        "days": [{
            "id": "day-1", "date": "2026-10-20", "route_mode": "walk",
            "activities": [
                {"id": "a", "place_id": "place-a", "display_name": "博物馆", "scheduled_time": "09:00:00", "duration_minutes": 60, "status": "planned"},
                {"id": "b", "place_id": "place-b", "display_name": "西湖", "scheduled_time": "11:00:00", "duration_minutes": 60, "status": "planned"},
            ],
            "route_legs": [{"from_activity_id": "a", "to_activity_id": "b", "mode": "walk", "duration_minutes": 30, "distance_meters": 2100}],
        }],
    }


def _resolution() -> dict:
    return {"grounded_intent": {"target_day_ids": ["day-1"], "constraints": {"requested_pace": "relaxed", "max_walking_minutes": None}}}


def _snapshot(*, end: time, walking_minutes: int) -> CandidatePlanSnapshot:
    place_a, place_b = uuid.uuid4(), uuid.uuid4()
    return CandidatePlanSnapshot(
        activities=[
            CandidateActivity(candidate_id="a", day_date="2026-10-20", place_candidate_id=place_a, planned_start_time=time(9), duration_minutes=60, estimated_cost_fen=0, transport_mode_to_here="walk", source_ids=[]),
            CandidateActivity(candidate_id="b", day_date="2026-10-20", place_candidate_id=place_b, planned_start_time=end, duration_minutes=30, estimated_cost_fen=0, transport_mode_to_here="walk", source_ids=[]),
        ],
        route_legs=[CandidateRouteLeg(candidate_id="leg", day_date="2026-10-20", from_activity_ref="a", to_activity_ref="b", position=0, mode="walk", distance_meters=1000, duration_minutes=walking_minutes, provider="test", calculated_at=datetime.now(UTC))],
    )


def test_extracts_goal_aware_request_without_extra_model_call():
    goals = extract_planning_goals(
        user_request="请调整2026-10-20当天行程，轻松一点，尽量少走路，18:00前结束，现有活动尽量不要大改。",
        intent_resolution=_resolution(), context=_context(),
    )
    assert goals.target_days == ["2026-10-20"]
    assert goals.hard_goals.end_before == "18:00"
    assert goals.soft_goals.pace == "relaxed"
    assert goals.soft_goals.minimize_walking is True
    assert goals.soft_goals.preserve_existing is True


def test_walking_request_can_reuse_an_existing_numeric_preference():
    context = _context()
    context["preferences"]["max_walking_minutes"] = 35
    goals = extract_planning_goals(user_request="请少走路", intent_resolution=_resolution(), context=context)
    assert goals.hard_goals.max_walking_minutes == 35


def test_formal_route_facts_reuse_persisted_route_evidence():
    goals = extract_planning_goals(user_request="18点前结束", intent_resolution=_resolution(), context=_context())
    facts = formal_route_facts(_context(), goals)
    assert facts["days"][0]["activity_sequence"] == ["博物馆", "西湖"]
    assert facts["days"][0]["walking_duration_minutes"] == 30
    assert facts["days"][0]["route_legs"][0]["distance_meters"] == 2100


def test_goal_satisfaction_reports_end_before_and_walking_satisfied_or_violated():
    goals = extract_planning_goals(user_request="18:00前结束，步行不超过20分钟", intent_resolution={"grounded_intent": {"target_day_ids": ["day-1"], "constraints": {"max_walking_minutes": 20}}}, context=_context())
    passed = check_goal_satisfaction(goals=goals, before_context=_context(), snapshot=_snapshot(end=time(17, 20), walking_minutes=15))
    assert {item.status for item in passed.results} == {"satisfied"}
    failed = check_goal_satisfaction(goals=goals, before_context=_context(), snapshot=_snapshot(end=time(18), walking_minutes=25))
    assert [item.status for item in failed.results] == ["unsatisfied", "unsatisfied"]


def test_goal_check_counts_implicitly_retained_locked_activity_and_its_end_time():
    context = _context()
    context["days"][0]["activities"][1].update(schedule_locked=True, scheduled_time="19:00:00", duration_minutes=30)
    goals = extract_planning_goals(user_request="18:00前结束，轻松一点，保留现有活动", intent_resolution=_resolution(), context=context)
    candidate = CandidateActivity(
        candidate_id="a", day_date="2026-10-20", place_candidate_id=uuid.uuid4(),
        planned_start_time=time(9), duration_minutes=60, estimated_cost_fen=0,
        transport_mode_to_here="walk", source_ids=[],
    )
    result = check_goal_satisfaction(goals=goals, before_context=context, snapshot=CandidatePlanSnapshot(activities=[candidate]))
    by_goal = {item.goal: item for item in result.results}
    assert by_goal["end_before"].status == "unsatisfied"
    assert by_goal["end_before"].evidence["candidate_end"] == "19:30"
    assert by_goal["pace_relaxed"].evidence["activity_count_after"] == 2
    assert by_goal["preserve_existing"].evidence["preserved_count"] == 1


def test_hard_goal_repair_is_bounded_to_one_attempt():
    result = GoalSatisfactionResult.model_validate({"results": [{"goal": "end_before", "type": "hard", "status": "unsatisfied", "evidence": {}}]})
    assert can_repair_hard_goals(repair_count=0, result=result) is True
    assert can_repair_hard_goals(repair_count=1, result=result) is False


def test_plan_revision_serializes_goal_summary_for_the_frontend():
    goals = extract_planning_goals(user_request="18点前结束，轻松一点", intent_resolution=_resolution(), context=_context())
    result = check_goal_satisfaction(goals=goals, before_context=_context(), snapshot=_snapshot(end=time(17, 20), walking_minutes=15))
    revision = PlanRevision(
        id=uuid.uuid4(), planning_run_id=uuid.uuid4(), trip_id=uuid.uuid4(), revision_number=1,
        reason="测试候选", before_snapshot={}, proposed_snapshot=_snapshot(end=time(17, 20), walking_minutes=15).model_dump(mode="json"),
        difference_summary={"planning_goals": goals.model_dump(mode="json"), "goal_satisfaction": result.model_dump(mode="json")},
        validation_result={"valid": True, "errors": [], "warnings": []}, source_ids=[], status="pending",
        created_at=datetime.now(UTC), decided_at=None,
    )
    response = PlanRevisionResponse.model_validate(revision)

    assert response.planning_goals is not None
    assert response.planning_goals.hard_goals.end_before == "18:00"
    assert response.goal_satisfaction is not None
    assert response.goal_satisfaction.results[0].status == "satisfied"


def test_plan_revision_serializes_persisted_rejection_feedback():
    revision = PlanRevision(
        id=uuid.uuid4(), planning_run_id=uuid.uuid4(), trip_id=uuid.uuid4(), revision_number=1,
        reason="测试候选", before_snapshot={}, proposed_snapshot={"activities": []}, difference_summary={},
        validation_result={"valid": True, "errors": [], "warnings": []}, source_ids=[], status="rejected",
        rejection_reason_code="too_rushed", rejection_reason_text="两个文化场馆停留时间太短",
        created_at=datetime.now(UTC), decided_at=datetime.now(UTC),
    )
    response = PlanRevisionResponse.model_validate(revision)

    assert response.rejection_reason_code == "too_rushed"
    assert response.rejection_reason_text == "两个文化场馆停留时间太短"
