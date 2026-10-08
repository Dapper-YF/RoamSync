from datetime import datetime
from zoneinfo import ZoneInfo

from app.navigation.delay_impact import RemainingStop, propagate_delay
from app.navigation.event_detector import DetectorState, EventPolicy, detect_execution_events
from app.navigation.execution_projection import project_execution_progress


TZ = ZoneInfo("Asia/Shanghai")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 15, hour, minute, tzinfo=TZ)


def _projection(eta: datetime, *, fixed=False):
    impact = propagate_delay(current_eta=eta, remaining_stops=[RemainingStop("appointment", at(10), 60, fixed_window=fixed)], daily_end=at(12))
    return impact, project_execution_progress(from_activity_id="from", to_activity_id="appointment", itinerary_version=7,
        planned_arrival=at(10), current_eta=eta, impact=impact, warning_slack_minutes=15)


def test_delay_absorbed_by_buffer_is_only_an_observation():
    impact, projection = _projection(at(10, 5))
    events, _ = detect_execution_events(projection=projection, impact=impact, observed_at=at(9), policy=EventPolicy(consecutive_observations=1))
    assert [event.event_type for event in events] == ["eta_delayed"]


def test_negative_slack_requires_consecutive_confirmation_but_hard_window_is_immediate():
    impact, projection = _projection(at(11, 1))
    policy = EventPolicy(warning_slack_minutes=15, disruption_slack_minutes=-1, consecutive_observations=2)
    first, state = detect_execution_events(projection=projection, impact=impact, observed_at=at(9), policy=policy)
    second, _ = detect_execution_events(projection=projection, impact=impact, observed_at=at(9, 1), policy=policy, previous=state)
    assert "itinerary_infeasible" not in [event.event_type for event in first]
    assert "itinerary_infeasible" in [event.event_type for event in second]

    missed_impact, missed_projection = _projection(at(10, 1), fixed=True)
    immediate, _ = detect_execution_events(projection=missed_projection, impact=missed_impact, observed_at=at(9), policy=policy)
    assert any(event.event_type == "missed_time_window" and event.kind == "disruption" for event in immediate)


def test_recovery_before_confirmation_resets_infeasible_counter():
    bad_impact, bad = _projection(at(11, 1))
    policy = EventPolicy(consecutive_observations=2)
    _, state = detect_execution_events(projection=bad, impact=bad_impact, observed_at=at(9), policy=policy)
    good_impact, good = _projection(at(10, 1))
    events, reset = detect_execution_events(projection=good, impact=good_impact, observed_at=at(9, 1), policy=policy, previous=state)
    assert not any(event.kind == "disruption" for event in events)
    assert reset.infeasible_observation_count == 0
    assert reset.current_risk_state == "critical"
    assert reset.last_risk_transition_at == at(9, 1)
