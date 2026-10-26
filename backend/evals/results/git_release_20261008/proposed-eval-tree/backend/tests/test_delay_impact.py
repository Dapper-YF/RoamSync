from datetime import datetime
from zoneinfo import ZoneInfo

from app.navigation.delay_impact import (
    ImpactPolicy,
    RemainingStop,
    detect_impact_events,
    propagate_delay,
)


TZ = ZoneInfo("Asia/Shanghai")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 15, hour, minute, tzinfo=TZ)


def test_delay_uses_schedule_slack_before_creating_a_macro_replan_signal():
    impact = propagate_delay(
        current_eta=at(10, 10),
        remaining_stops=[
            RemainingStop("museum", at(10), 60, travel_to_next_minutes=20),
            RemainingStop("lunch", at(12), 60),
        ],
        daily_end=at(18),
    )

    # Slack is the capacity remaining until the day-end constraint, including
    # flexible downstream activities, not merely the gap before lunch.
    assert [item.slack_minutes for item in impact.stops] == [330, 330]
    events = detect_impact_events(impact, observed_at=at(9, 45))
    assert [(event.event_type, event.affects_itinerary) for event in events] == [("ETA_DELAYED", False)]


def test_delay_propagates_to_a_later_fixed_appointment():
    impact = propagate_delay(
        current_eta=at(10, 30),
        remaining_stops=[
            RemainingStop("museum", at(10), 60, travel_to_next_minutes=30),
            RemainingStop("train", at(12), 30, fixed_window=True),
        ],
        daily_end=at(20),
    )

    assert impact.stops[0].slack_minutes == 0
    assert impact.stops[1].projected_arrival == at(12)
    assert not any(event.affects_itinerary for event in detect_impact_events(impact, observed_at=at(10, 1)))

    late = propagate_delay(
        current_eta=at(10, 31),
        remaining_stops=[
            RemainingStop("museum", at(10), 60, travel_to_next_minutes=30),
            RemainingStop("train", at(12), 30, fixed_window=True),
        ],
        daily_end=at(20),
    )
    assert late.stops[0].slack_minutes == -1
    assert late.stops[1].delay_minutes == 1
    assert any(event.event_type == "MISSED_TIME_WINDOW" and event.affects_itinerary
               for event in detect_impact_events(late, observed_at=at(10, 2)))


def test_daily_end_can_become_a_macro_arrival_risk_without_an_appointment():
    impact = propagate_delay(
        current_eta=at(16, 20),
        remaining_stops=[RemainingStop("gallery", at(16), 120)],
        daily_end=at(18),
    )

    assert impact.stops[0].slack_minutes == -20
    events = detect_impact_events(impact, observed_at=at(16, 1), policy=ImpactPolicy(eta_delay_minutes=5))
    assert any(event.event_type == "ARRIVAL_RISK" and event.affects_itinerary for event in events)


def test_impact_requires_timezone_aware_inputs():
    try:
        propagate_delay(
            current_eta=datetime(2026, 9, 15, 10),
            remaining_stops=[RemainingStop("museum", at(10), 30)],
            daily_end=at(18),
        )
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:
        raise AssertionError("naive time should be rejected")
