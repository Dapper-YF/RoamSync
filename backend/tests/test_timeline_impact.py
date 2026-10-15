from datetime import datetime
from zoneinfo import ZoneInfo

from app.timeline_impact import TimelineStop, project_timeline_impact


TZ = ZoneInfo("Asia/Shanghai")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 21, hour, minute, tzinfo=TZ)


def test_positive_experience_shift_is_absorbed_by_downstream_slack() -> None:
    impact = project_timeline_impact(
        current_boundary_at=at(12, 20),
        remaining_stops=[TimelineStop("next", at(12, 30), 60)],
        daily_end=at(14, 45),
    )
    assert impact.stops[0].time_shift_minutes == -10
    # The formal start still governs a flexible activity; capacity is retained
    # as slack rather than silently rewriting the formal schedule.
    assert impact.stops[0].slack_minutes == 85
    assert impact.feasible


def test_late_actual_start_plus_extension_is_a_signed_total_shift() -> None:
    # Formal current end is 12:00; actual start 10:10 + planned 120 + extend 30
    # makes the authoritative boundary 12:40, i.e. +40 rather than +30.
    impact = project_timeline_impact(
        current_boundary_at=at(12, 40),
        remaining_stops=[TimelineStop("next", at(12, 20), 30)],
        daily_end=at(15),
    )
    assert impact.stops[0].time_shift_minutes == 20
    assert impact.stops[0].projected_end == at(13, 10)


def test_fixed_window_and_daily_end_are_deterministically_infeasible() -> None:
    fixed = project_timeline_impact(
        current_boundary_at=at(13, 31),
        remaining_stops=[TimelineStop("appointment", at(13, 30), 30, fixed_window=True)],
        daily_end=at(18),
    )
    assert not fixed.fixed_window_feasible
    assert fixed.stops[0].time_shift_minutes == 1
    end = project_timeline_impact(
        current_boundary_at=at(20, 30),
        remaining_stops=[TimelineStop("last", at(20), 60)],
        daily_end=at(21),
    )
    assert not end.feasible
    assert end.stops[0].slack_minutes < 0


def test_early_boundary_preserves_negative_shift_without_mutating_schedule() -> None:
    impact = project_timeline_impact(
        current_boundary_at=at(11, 30),
        remaining_stops=[TimelineStop("next", at(12), 30)],
        daily_end=at(15),
    )
    assert impact.stops[0].time_shift_minutes == -30
    assert impact.stops[0].projected_start == at(12)
    assert impact.stops[0].slack_minutes == 180
