import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
import pytest

from app.candidate_decisions import collect_candidate_route_facts, compare_candidates, place_exposure, review_candidate_decisions, weather_days
from app.openai_planner import OpenAIResponsesPlanner, build_planner_input
from app.schemas import CandidatePlanSnapshot
from tests.test_openai_planner import _settings, _state


NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


class FirstAllowed:
    """A deterministic wiring fixture, never evidence of live model quality."""
    async def create(self, **kwargs):
        payload = json.loads(kwargs["input"])
        choice = payload["new_place_candidates"][0]
        return SimpleNamespace(status="completed", model="fixture", usage=SimpleNamespace(total_tokens=0),
            output_text=json.dumps({"activities": [{"source": "candidate", "candidate_ref": choice["candidate_ref"],
                "day_date": payload["allowed_dates"][0], "planned_start_time": "09:00", "duration_minutes": 60,
                "transport_mode_to_here": "walk", "reason": "根据本次明确要求选择可用地点并保留固定活动。"}], "explanation": "已生成待确认候选。"}))


def candidate(id, name, tags, rating=4.8):
    return {"id": id, "name": name, "category": "culture", "rating": rating,
            "tags": tags, "source": {"provider": "AMap POI", "id": "source"}}


def context():
    return {"trip": {"destination": "杭州", "timezone": "Asia/Shanghai"},
            "days": [{"date": "2026-10-17", "activities": []}],
            "preferences": {"daily_start_time": "09:00", "daily_end_time": "18:00"},
            "weather_sensitive": True,
            "external_facts": {"weather": {"status": "available", "provider": "open_meteo", "queried_at": NOW.isoformat(),
                "payload": {"timezone": "Asia/Shanghai", "hourly": {"time": [f"2026-10-17T{hour:02d}:00" for hour in range(9, 18)],
                                        "precipitation_probability": [80] * 9}}}}}


def requirement(strength="hard", **kwargs):
    return {"id": "req-1", "key": "avoid_category", "value": "culture", "text": "不要文化类", "status": "active",
            "strength": strength, "source": {"kind": "user_explicit", "ref": "message-1"}, "scope": {"kind": "global_preference"}, **kwargs}


def test_weather_changes_actual_candidate_order_without_excluding_unknown_or_outdoor():
    ctx = context()
    candidates = [candidate("park", "公园", ["公园"], 5), candidate("museum", "博物馆", ["博物馆"], 4)]
    dry = deepcopy(ctx)
    dry["external_facts"]["weather"]["payload"]["hourly"]["precipitation_probability"] = [0] * 9
    dry_rank, _ = compare_candidates(dry, candidates, allowed_dates={"2026-10-17"}, now=NOW)
    wet_rank, evidence = compare_candidates(ctx, candidates, allowed_dates={"2026-10-17"}, now=NOW)
    assert dry_rank[0]["id"] == "park" and wet_rank[0]["id"] == "museum"
    assert len(wet_rank) == 2
    assert evidence["candidates"][1]["exposure"]["confidence"] == "low_confidence_taxonomy_inference"


def test_reviewed_westlake_source_is_exact_and_taxonomy_is_never_verified_indoor():
    lake = candidate("lake", "西湖", []) | {"longitude": 120.14, "latitude": 30.24,
        "source": {"provider": "AMap POI", "url": "https://www.amap.com/search?id=B023B13L9M"}}
    assert place_exposure(lake, context())["assertion_id"] == "west_lake.landscape_components"
    assert place_exposure(lake, {"trip": {"destination": "南京"}})["hint"] == "unknown"
    assert place_exposure(lake | {"source": {"provider": "user_note"}}, context())["hint"] == "unknown"
    assert place_exposure(lake | {"source": {"provider": "AMap POI", "url": "https://www.amap.com/search?id=WRONG"}}, context())["hint"] == "unknown"
    assert place_exposure(candidate("x", "博物馆", ["博物馆"]))["confidence"] == "low_confidence_taxonomy_inference"
    assert place_exposure(candidate("x", "室内博物馆", []) | {"description": "保证室内避雨"})["hint"] == "unknown"


def test_weather_unknown_on_stale_missing_coverage_past_or_bad_values():
    for transform in (
        lambda c: c["external_facts"]["weather"].update(queried_at=(NOW - timedelta(minutes=31)).isoformat()),
        lambda c: c["external_facts"]["weather"]["payload"]["hourly"]["precipitation_probability"].pop(),
        lambda c: c["external_facts"]["weather"]["payload"]["hourly"]["precipitation_probability"].__setitem__(0, None),
        lambda c: c["external_facts"]["weather"].update(provider="unverified"),
    ):
        ctx = context()
        transform(ctx)
        assert weather_days(ctx, now=NOW)["2026-10-17"]["status"] == "unknown"
    assert weather_days(context(), now=NOW + timedelta(days=2))["2026-10-17"]["status"] == "unknown"


def test_only_explicit_supported_hard_requirements_exclude_soft_and_unknown_remain():
    ctx = context()
    places = [candidate("culture", "馆", []), candidate("nature", "园", []) | {"category": "nature"}]
    ctx["effective_requirements"] = [requirement("soft")]
    ranked, comparison = compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)
    assert len(ranked) == 2 and ranked[0]["id"] == "nature"
    ctx["effective_requirements"] = [requirement()]
    assert [p["id"] for p in compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)[0]] == ["nature"]
    ctx["effective_requirements"] = [requirement(key="accessibility", value="step_free")]
    assert len(compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)[0]) == 2


def test_day_requirement_projection_does_not_leak_revocation_or_other_day_hard_filter():
    ctx = context()
    ctx["effective_requirements"] = [requirement()]
    ctx["effective_requirements_by_date"] = {"2026-10-17": [], "2026-10-18": [requirement()]}
    ranked, comparison = compare_candidates(ctx, [candidate("x", "馆", [])], allowed_dates={"2026-10-17", "2026-10-18"}, now=NOW)
    assert len(ranked) == 1
    assert [d["eligible"] for d in comparison["candidates"][0]["day_comparisons"]] == [True, False]


def test_exact_provider_anchor_route_changes_rank_estimate_is_unknown():
    ctx = context()
    ctx["planning_goals"] = {"soft_goals": {"minimize_walking": True}}
    ctx["days"][0]["activities"] = [{"id": "fixed", "place_id": "fixed-place", "scheduled_time": "14:00",
                                     "duration_minutes": 60, "schedule_locked": True, "status": "planned"}]
    places = [candidate("far", "远馆", [], 5), candidate("near", "近馆", [], 4)]
    ctx["candidate_route_facts"] = [{"candidate_id": key, "date": "2026-10-17", "status": "available", "is_estimated": False,
                                    "duration_minutes": duration, "provider": "amap", "to_activity_id": "fixed",
                                    "direction": "candidate_to_fixed_activity", "mode": "walk",
                                    "expires_at": (NOW + timedelta(hours=1)).isoformat()}
                                   for key, duration in [("far", 40), ("near", 10)]]
    assert compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)[0][0]["id"] == "near"
    ctx["candidate_route_facts"][1]["is_estimated"] = True
    ranked, evidence = compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)
    assert ranked[0]["id"] == "far"
    assert evidence["candidates"][1]["day_comparisons"][0]["route_to_fixed_activity"]["status"] == "unknown"


def test_one_rainy_evening_does_not_overrule_a_feasible_dry_visit():
    ctx = context()
    places = [candidate("park", "公园", ["公园"], 5) | {"suggested_duration_minutes": 120},
              candidate("museum", "博物馆", ["博物馆"], 4) | {"suggested_duration_minutes": 120}]
    probabilities = ctx["external_facts"]["weather"]["payload"]["hourly"]["precipitation_probability"]
    probabilities[:] = [0] * 8 + [80]
    ranked, evidence = compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)
    assert ranked[0]["id"] == "park"
    assert evidence["weather_days"]["2026-10-17"]["rain_risk"] == "mixed"
    assert evidence["candidates"][0]["day_comparisons"][0]["candidate_rain_risk"] == "mixed_dry_slot_available"
    probabilities[:] = [80] * 9
    assert compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)[0][0]["id"] == "museum"


@pytest.mark.parametrize("invalid", ["expired", "reverse", "wrong_anchor", "transit", "estimated"])
def test_walking_comparison_does_not_promote_untrusted_or_other_mode_route(invalid):
    ctx = context()
    ctx["planning_goals"] = {"soft_goals": {"minimize_walking": True}}
    ctx["days"][0]["activities"] = [{"id": "fixed", "place_id": "fixed-place", "scheduled_time": "14:00",
                                     "duration_minutes": 60, "schedule_locked": True, "status": "planned"}]
    places = [candidate("preferred", "喜欢的馆", [], 5), candidate("claimed_near", "路线可疑的馆", [], 4)]
    trusted = {"candidate_id": "claimed_near", "date": "2026-10-17", "status": "available", "is_estimated": False,
               "duration_minutes": 5, "provider": "amap", "to_activity_id": "fixed",
               "direction": "candidate_to_fixed_activity", "mode": "walk", "expires_at": (NOW + timedelta(hours=1)).isoformat()}
    modifications = {"expired": {"expires_at": (NOW - timedelta(seconds=1)).isoformat()},
                     "reverse": {"direction": "fixed_activity_to_candidate"}, "wrong_anchor": {"to_activity_id": "unrelated"},
                     "transit": {"mode": "transit"}, "estimated": {"is_estimated": True}}
    ctx["candidate_route_facts"] = [trusted | modifications[invalid]]
    ranked, evidence = compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)
    assert ranked[0]["id"] == "preferred"
    if invalid != "transit":
        assert evidence["candidates"][1]["day_comparisons"][0]["route_to_fixed_activity"]["status"] == "unknown"
    ctx["candidate_route_facts"] = [trusted]
    assert compare_candidates(ctx, places, allowed_dates={"2026-10-17"}, now=NOW)[0][0]["id"] == "claimed_near"


def test_fixed_anchor_comparison_accounts_for_directed_walk_and_soft_rest():
    ctx = context()
    ctx["days"][0]["activities"] = [{"id": "fixed", "place_id": "fixed-place", "scheduled_time": "12:00",
                                     "duration_minutes": 60, "schedule_locked": True, "status": "planned"}]
    ctx["preferences"]["daily_end_time"] = "13:00"
    ctx["candidate_route_facts"] = [{"candidate_id": "visit", "date": "2026-10-17", "status": "available",
        "is_estimated": False, "duration_minutes": 55, "provider": "amap", "to_activity_id": "fixed",
        "direction": "candidate_to_fixed_activity", "mode": "walk", "expires_at": (NOW + timedelta(hours=1)).isoformat()}]
    place = candidate("visit", "展馆", []) | {"suggested_duration_minutes": 120}
    _, evidence = compare_candidates(ctx, [place], allowed_dates={"2026-10-17"}, now=NOW)
    before = evidence["candidates"][0]["day_comparisons"][0]["fixed_time_fit"]["before_fixed_anchor"]
    assert before["status"] == "fits_without_rest_buffer_only"
    assert before["known_free_minutes"] == 180 and before["soft_rest_buffer_minutes"] == 10
    ctx["days"][0]["activities"][0]["scheduled_time"] = "11:00"
    _, evidence = compare_candidates(ctx, [place], allowed_dates={"2026-10-17"}, now=NOW)
    assert evidence["candidates"][0]["day_comparisons"][0]["fixed_time_fit"]["before_fixed_anchor"]["status"] == "does_not_fit_with_known_route"


def test_route_collection_covers_two_target_days_with_bounded_calls(monkeypatch):
    import uuid
    from app import maps_service

    trip_id = uuid.uuid4()
    candidates = [uuid.uuid4(), uuid.uuid4()]
    anchors = [uuid.uuid4(), uuid.uuid4()]
    places = {place_id: SimpleNamespace(id=place_id, trip_id=trip_id) for place_id in [*candidates, *anchors]}
    class Session:
        async def get(self, _model, place_id):
            return places.get(place_id)
    calls = []
    async def route(_session, origin, destination, mode):
        calls.append((origin.id, destination.id, mode))
        return SimpleNamespace(is_estimated=False, duration_minutes=15, distance_meters=800,
                               provider="AMap Route 2.0", expires_at=NOW + timedelta(hours=1))
    monkeypatch.setattr(maps_service, "resolve_route_result", route)
    ctx = {"preferences": {"transport_modes": ["walk"]},
           "candidates": [{"id": str(place_id)} for place_id in candidates],
           "days": [{"date": f"2026-10-{day}", "activities": [{"id": f"fixed-{day}", "place_id": str(anchor),
               "scheduled_time": "14:00", "schedule_locked": True, "status": "planned"}]}
                    for day, anchor in [(17, anchors[0]), (18, anchors[1])]]}
    facts = asyncio.run(collect_candidate_route_facts(Session(), ctx, target_dates={"2026-10-17", "2026-10-18"}, limit=4))
    assert len(calls) == len(facts) == 4
    assert {(fact["candidate_id"], fact["date"]) for fact in facts} == {
        (str(candidate_id), day) for candidate_id in candidates for day in ("2026-10-17", "2026-10-18")}
    assert all(fact["status"] == "available" and fact["direction"] == "candidate_to_fixed_activity" for fact in facts)


def test_planner_payload_and_generated_selection_change_for_fixed_candidate_hard_requirement():
    state, _, _ = _state()
    state["planning_context"]["days"][0]["activities"][0]["category"] = "nature"
    first = state["planning_context"]["candidates"][0]
    first.update(category="culture", rating=5)
    import uuid
    second = deepcopy(first) | {"id": str(uuid.uuid4()), "name": "自然候选", "category": "nature", "rating": 3}
    state["planning_context"]["candidates"].append(second)
    planner = OpenAIResponsesPlanner(_settings(), client=SimpleNamespace(responses=FirstAllowed()))
    baseline = asyncio.run(planner.generate(deepcopy(state)))
    state["planning_context"]["effective_requirements"] = [requirement()]
    changed = asyncio.run(planner.generate(state))
    assert str(baseline.snapshot.activities[0].place_candidate_id) == first["id"]
    assert str(changed.snapshot.activities[0].place_candidate_id) == second["id"]
    assert review_candidate_decisions(state["planning_context"], changed.snapshot)["hard_errors"] == []
    assert review_candidate_decisions(state["planning_context"], baseline.snapshot)["hard_errors"][0]["code"] == "effective_requirement_unsatisfied"


def test_post_generation_review_soft_tradeoff_does_not_fail_or_claim_booking():
    state, _, _ = _state()
    ctx = state["planning_context"]
    ctx["effective_requirements"] = [requirement("soft", value=ctx["candidates"][0]["category"])]
    _, allowed, _ = build_planner_input(state, max_candidates=40)
    from app.schemas import CandidateActivity
    place = next(p for p in allowed.values() if p.replaces_activity_id is None)
    snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id="selected", day_date="2026-11-01", place_candidate_id=place.id,
        planned_start_time="10:00", duration_minutes=60, estimated_cost_fen=place.estimated_cost_fen, transport_mode_to_here="walk", source_ids=[place.source_id])])
    review = review_candidate_decisions(ctx, snapshot)
    assert review["hard_errors"] == []
    assert review["selected_observations"][0]["soft_requirement_tradeoffs"] == ["req-1"]
    assert review["fixed_activities"][0]["source"] == "persisted_schedule_locked_not_booking_confirmation"


@pytest.mark.parametrize("condition", ["rain", "walking", "fixed_time"])
def test_generated_final_selection_changes_under_fixed_weather_route_or_schedule_condition(condition):
    import uuid
    state, _, _ = _state()
    ctx = state["planning_context"]
    first = ctx["candidates"][0]
    first.update(rating=5, tags=["公园"], source={**first["source"], "provider": "AMap POI"})
    second = deepcopy(first) | {"id": str(uuid.uuid4()), "name": "备选展馆", "rating": 4, "tags": ["博物馆"], "suggested_duration_minutes": 60}
    ctx["candidates"].append(second)
    for day in ctx["days"]:
        day["id"] = str(uuid.uuid4())
    state["intent_resolution"]["grounded_intent"] = {"target_day_ids": [ctx["days"][0]["id"]]}
    planner = OpenAIResponsesPlanner(_settings(), client=SimpleNamespace(responses=FirstAllowed()))
    baseline = asyncio.run(planner.generate(deepcopy(state)))
    if condition == "rain":
        ctx["weather_sensitive"] = True
        ctx["external_facts"] = {"weather": {"status": "available", "provider": "open_meteo", "queried_at": datetime.now(UTC).isoformat(),
            "payload": {"timezone": "Asia/Shanghai", "hourly": {"time": [f"2026-11-01T{h:02d}:00" for h in range(9, 21)], "precipitation_probability": [80] * 12}}}}
    elif condition == "walking":
        ctx["planning_goals"] = {"target_days": ["2026-11-01"], "hard_goals": {}, "soft_goals": {"minimize_walking": True}}
        ctx["candidate_route_facts"] = [{"candidate_id": cid, "date": "2026-11-01", "status": "available", "is_estimated": False,
            "duration_minutes": duration, "provider": "amap", "to_activity_id": ctx["days"][0]["activities"][0]["id"],
            "direction": "candidate_to_fixed_activity", "mode": "walk",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
            for cid, duration in [(first["id"], 40), (second["id"], 10)]]
    else:
        ctx["preferences"]["daily_end_time"] = "12:00"
        ctx["days"][0]["activities"][0].update(status="planned", scheduled_time="10:00", duration_minutes=120)
    changed = asyncio.run(planner.generate(state))
    assert str(baseline.snapshot.activities[0].place_candidate_id) == first["id"]
    assert str(changed.snapshot.activities[0].place_candidate_id) == second["id"]
    assert review_candidate_decisions(ctx, changed.snapshot)["status"] == "checked"


def test_review_reports_implicit_protected_hard_conflict_without_deleting_it():
    state, _, _ = _state()
    ctx = state["planning_context"]
    ctx["effective_requirements"] = [requirement()]
    review = review_candidate_decisions(ctx, CandidatePlanSnapshot(activities=[]))
    assert review["hard_errors"][0]["code"] == "effective_requirement_protected_conflict"
    assert ctx["days"][0]["activities"][0]["schedule_locked"] is True


def test_numeric_effective_goals_use_target_date_and_no_duplicate_completed_estimate():
    from app.planning_goals import _effective_requirement_results
    from app.schemas import CandidateActivity
    import uuid
    state, _, _ = _state()
    ctx = state["planning_context"]
    old = ctx["days"][0]["activities"][0]
    old["estimated_cost_fen"] = 10000
    ctx["actual_budget"] = {"total_spent_fen": 7000, "today_spent_fen": 7000, "local_date": "2026-11-01"}
    snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id="new", day_date="2026-11-02", place_candidate_id=uuid.uuid4(),
        planned_start_time="17:00", duration_minutes=90, estimated_cost_fen=3000, transport_mode_to_here="walk")])
    budget = requirement(key="budget_fen", value=10000)
    day_end = requirement(id="end", key="end_before", value="18:00", scope={"kind": "day", "date": "2026-11-02"})
    ctx["effective_requirements_by_date"] = {"2026-11-01": [budget], "2026-11-02": [budget, day_end]}
    results = _effective_requirement_results(ctx, snapshot)
    assert results[0]["status"] == "satisfied"
    assert results[0]["evidence"]["candidate_budget_exposure_fen"] == 10000
    assert results[1]["status"] == "unsatisfied"
    assert review_candidate_decisions(ctx, snapshot)["hard_errors"][0]["details"]["requirement_id"] == "end"
    ctx["effective_requirements_by_date"] = {"2026-11-02": [requirement(key="budget_fen", value=5000, scope={"kind": "day", "date": "2026-11-02"})]}
    result = _effective_requirement_results(ctx, snapshot)[0]
    assert result["status"] == "not_evaluable"
    assert result["evidence"]["actual_spent_fen"] is None
    assert result["evidence"]["candidate_remaining_estimated_cost_fen"] == 3000


def test_raw_current_context_projects_local_revocation_before_accept_review():
    from app.requirements import add_requirement, revoke_requirement
    from app.schemas import CandidateActivity
    state, _, _ = _state()
    ctx = state["planning_context"]
    ctx["trip"]["id"] = state["trip_id"]
    ctx["days"][0]["activities"][0]["category"] = "nature"
    records = add_requirement([], text="不要文化", scope={"kind": "trip", "trip_id": state["trip_id"]}, source_ref="test",
                              key="avoid_category", value="culture", strength="hard")
    records = revoke_requirement(records, records[0]["id"], scope={"kind": "day", "trip_id": state["trip_id"], "day_index": 2})
    ctx["effective_requirements"] = records
    ctx["preferences"]["requirement_records"] = records
    p = ctx["candidates"][0]
    snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id="new", day_date="2026-11-02", place_candidate_id=p["id"],
        planned_start_time="10:00", duration_minutes=60, estimated_cost_fen=0, transport_mode_to_here="walk")])
    assert review_candidate_decisions(ctx, snapshot)["hard_errors"] == []
    snapshot.activities[0].day_date = snapshot.activities[0].day_date.replace(day=1)
    assert review_candidate_decisions(ctx, snapshot)["hard_errors"][0]["code"] == "effective_requirement_unsatisfied"


def test_walking_hard_goal_missing_route_is_unknown_then_known_excess_is_conflict():
    from app.schemas import CandidateActivity, CandidateRouteLeg
    from app.planning_goals import _effective_requirement_results
    state, _, _ = _state()
    ctx = state["planning_context"]
    ctx["effective_requirements"] = [requirement(key="max_walking_minutes", value=20)]
    p = ctx["candidates"][0]
    snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id="new", day_date="2026-11-01", place_candidate_id=p["id"],
        planned_start_time="12:00", duration_minutes=60, estimated_cost_fen=0, transport_mode_to_here="walk")])
    assert _effective_requirement_results(ctx, snapshot)[0]["status"] == "not_evaluable"
    snapshot.route_legs = [CandidateRouteLeg(day_date="2026-11-01", from_activity_ref="activity:" + ctx["days"][0]["activities"][0]["id"],
        to_activity_ref="new", position=0, mode="walk", distance_meters=3000, duration_minutes=50, provider="amap", calculated_at=NOW)]
    assert review_candidate_decisions(ctx, snapshot)["hard_errors"][0]["details"]["candidate_walking_minutes"] == 50


def _three_day_candidate():
    from app.schemas import CandidateActivity, CandidateRouteLeg
    import uuid
    state, _, _ = _state()
    ctx = state["planning_context"]
    ctx["days"] = [{"id": f"day-{index}", "date": f"2026-11-0{index}", "activities": []} for index in range(1, 4)]
    activities, legs = [], []
    for day in ctx["days"]:
        for index in range(2):
            activities.append(CandidateActivity(candidate_id=f"{day['id']}-{index}", day_date=day["date"], place_candidate_id=uuid.uuid4(),
                planned_start_time=f"{9 + index * 2:02d}:00", duration_minutes=60, estimated_cost_fen=1500, transport_mode_to_here="walk"))
        legs.append(CandidateRouteLeg(day_date=day["date"], from_activity_ref=f"{day['id']}-0", to_activity_ref=f"{day['id']}-1",
            position=0, mode="walk", distance_meters=2000, duration_minutes=30, provider="amap", calculated_at=NOW))
    return ctx, CandidatePlanSnapshot(activities=activities, route_legs=legs)


def test_broad_walking_limit_applies_daily_to_both_saved_requirement_and_current_goal():
    from app.planning_goals import _effective_requirement_results, check_goal_satisfaction
    from app.schemas import PlanningGoals
    ctx, snapshot = _three_day_candidate()
    ctx["effective_requirements"] = [requirement(key="max_walking_minutes", value=40)]
    results = _effective_requirement_results(ctx, snapshot)
    assert len(results) == 3
    assert [result["status"] for result in results] == ["satisfied"] * 3
    assert [result["evidence"]["candidate_walking_minutes"] for result in results] == [30] * 3
    assert all(result["evidence"]["limit_scope"] == "daily" for result in results)
    goals = PlanningGoals(target_days=[day["date"] for day in ctx["days"]], hard_goals={"max_walking_minutes": 40})
    assert all(result.status == "satisfied" for result in check_goal_satisfaction(goals=goals, before_context=ctx, snapshot=snapshot).results)
    snapshot.route_legs[1].duration_minutes = 45
    results = _effective_requirement_results(ctx, snapshot)
    assert [result["status"] for result in results] == ["satisfied", "unsatisfied", "satisfied"]
    errors = review_candidate_decisions(ctx, snapshot)["hard_errors"]
    assert len(errors) == 1 and errors[0]["details"]["date"] == "2026-11-02"


def test_broad_daily_budget_never_becomes_trip_total_or_uses_other_days_actual_spend():
    from app.planning_goals import _effective_requirement_results
    ctx, snapshot = _three_day_candidate()
    ctx["effective_requirements"] = [requirement(key="daily_budget_fen", value=4000)]
    ctx["actual_budget"] = {"total_spent_fen": 1000, "today_spent_fen": 1000, "local_date": "2026-11-01"}
    results = _effective_requirement_results(ctx, snapshot)
    assert len(results) == 3
    assert [result["evidence"]["candidate_budget_exposure_fen"] for result in results] == [4000, 3000, 3000]
    assert [result["evidence"]["actual_spent_fen"] for result in results] == [1000, None, None]
    assert all(result["evidence"]["limit_scope"] == "daily" for result in results)
    assert review_candidate_decisions(ctx, snapshot)["hard_errors"] == []
    snapshot.activities[-1].estimated_cost_fen = 2600
    errors = review_candidate_decisions(ctx, snapshot)["hard_errors"]
    assert len(errors) == 1 and errors[0]["details"]["date"] == "2026-11-03"
    ctx["effective_requirements"] = [requirement(key="budget_fen", value=4000)]
    result = _effective_requirement_results(ctx, snapshot)
    assert len(result) == 1 and result[0]["evidence"]["limit_scope"] == "trip" and result[0]["status"] == "unsatisfied"
