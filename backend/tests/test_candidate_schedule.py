import uuid
from datetime import UTC, datetime, time

from app.candidate_schedule import repair_route_schedule
from app.schemas import CandidateActivity, CandidatePlanSnapshot, CandidateRouteLeg


def _snapshot(*, locked=False):
    return CandidatePlanSnapshot(
        activities=[CandidateActivity(
            candidate_id=ref, day_date="2026-09-09", place_candidate_id=uuid.uuid4(),
            planned_start_time=start, duration_minutes=60, estimated_cost_fen=0,
            transport_mode_to_here="walk", locked=locked and ref == "second",
        ) for ref, start in [("first", "10:00"), ("second", "11:00"), ("third", "12:00")]],
        route_legs=[CandidateRouteLeg(
            day_date="2026-09-09", from_activity_ref=origin, to_activity_ref=destination,
            position=position, mode="walk", distance_meters=1000, duration_minutes=30,
            provider="test-route", calculated_at=datetime.now(UTC),
        ) for position, (origin, destination) in enumerate([("first", "second"), ("second", "third")])],
    )


def _context(end="20:00"):
    return {"days": [], "preferences": {"daily_end_time": end}}


def test_repair_propagates_travel_time_through_the_day_without_changing_stops():
    original = _snapshot()
    repaired, changes = repair_route_schedule(original, _context())
    assert [item.planned_start_time.isoformat(timespec="minutes") for item in repaired.activities] == ["10:00", "11:30", "13:00"]
    assert len(changes) == 2
    assert repaired.route_legs == original.route_legs
    assert [(a.place_candidate_id, a.duration_minutes, a.estimated_cost_fen) for a in repaired.activities] == [(a.place_candidate_id, a.duration_minutes, a.estimated_cost_fen) for a in original.activities]
    assert original.activities[1].planned_start_time.isoformat(timespec="minutes") == "11:00"


def test_repair_keeps_original_when_daily_end_or_locked_stop_blocks_it():
    for snapshot, context in [(_snapshot(), _context("13:30")), (_snapshot(locked=True), _context())]:
        repaired, changes = repair_route_schedule(snapshot, context)
        assert repaired == snapshot
        assert changes == []


def test_repair_does_not_move_completed_formal_activity():
    snapshot = _snapshot()
    activity_id = uuid.uuid4()
    snapshot.activities[1].replaces_activity_id = activity_id
    context = _context()
    context["days"] = [{"activities": [{"id": str(activity_id), "status": "completed", "schedule_locked": False}]}]
    repaired, changes = repair_route_schedule(snapshot, context)
    assert repaired == snapshot
    assert changes == []


def test_valid_schedule_is_not_changed_again():
    repaired, _ = repair_route_schedule(_snapshot(), _context())
    assert repair_route_schedule(repaired, _context()) == (repaired, [])


def test_evening_route_overflow_uses_earlier_slack_without_removing_experiences():
    snapshot = _snapshot()
    snapshot.activities = snapshot.activities[:2]
    snapshot.route_legs = snapshot.route_legs[:1]
    snapshot.activities[0].planned_start_time = time(17, 30)
    snapshot.activities[0].duration_minutes = 75
    snapshot.activities[1].planned_start_time = time(19, 30)
    snapshot.activities[1].duration_minutes = 90
    snapshot.route_legs[0].duration_minutes = 52
    context = {"days": [], "preferences": {"daily_start_time": "09:00", "daily_end_time": "21:00"}}
    repaired, changes = repair_route_schedule(snapshot, context, allow_earlier=True)
    assert [a.planned_start_time for a in repaired.activities] == [time(17, 23), time(19, 30)]
    assert len(changes) == 1
    assert [a.place_candidate_id for a in repaired.activities] == [a.place_candidate_id for a in snapshot.activities]
    assert [a.duration_minutes for a in repaired.activities] == [75, 90]
    assert repaired.route_legs == snapshot.route_legs
    assert repair_route_schedule(snapshot, context) == (snapshot, [])
    snapshot.activities[0].locked = True
    assert repair_route_schedule(snapshot, context, allow_earlier=True) == (snapshot, [])


def test_earlier_repair_rejects_large_time_changes_or_insufficient_day_window():
    snapshot = _snapshot()
    context = {"days": [], "preferences": {"daily_start_time": "10:00", "daily_end_time": "13:30"}}
    assert repair_route_schedule(snapshot, context, allow_earlier=True) == (snapshot, [])
    context["preferences"] = {"daily_start_time": "09:00", "daily_end_time": "11:00"}
    assert repair_route_schedule(snapshot, context, allow_earlier=True) == (snapshot, [])
