"""Known quality regressions: competing objectives and unsupported promises."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from app.candidate_decisions import compare_candidates, review_candidate_decisions, unsupported_decision_claims
from app.planning_explanation import describe_plan_changes
from app.schemas import CandidateActivity, CandidatePlanSnapshot
from tests.test_openai_planner import _state


def walking_case():
    state, _, _ = _state()
    ctx = state["planning_context"]
    first = ctx["candidates"][0]
    second = deepcopy(first)
    second.update(id="9a4bb3a6-150d-477e-a86b-4edffb748fc8", name="另一候选", category="culture")
    first.update(category="nature", name="景观候选")
    ctx["candidates"] = [first, second]
    ctx["preferences"]["interest_categories"] = ["nature"]
    ctx["planning_goals"] = {"soft_goals": {"minimize_walking": True}}
    anchor = ctx["days"][0]["activities"][0]
    anchor.update(status="planned", scheduled_time="14:00")
    ctx["candidate_route_facts"] = [{"candidate_id": p["id"], "date": "2026-11-01", "to_activity_id": anchor["id"],
        "direction": "candidate_to_fixed_activity", "mode": "walk", "status": "available", "is_estimated": False,
        "provider": "amap", "duration_minutes": m,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
        for p, m in [(first, 54), (second, 28)]]
    return ctx


def test_longer_walk_has_explicit_interest_tradeoff_not_false_optimality():
    ctx = walking_case()
    _, comparison = compare_candidates(ctx, ctx["candidates"], allowed_dates={"2026-11-01"})
    pair = comparison["walking_tradeoffs"][0]
    assert pair["extra_directed_walk_minutes"] == 26
    assert pair["status"] == "competing_objectives"
    assert "matches_saved_interest_category" in pair["longer_option_supported_advantages"]
    ctx["candidate_comparison"] = comparison
    p = ctx["candidates"][0]
    snapshot = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id="chosen", day_date="2026-11-01",
        place_candidate_id=p["id"], planned_start_time="09:00", duration_minutes=60,
        estimated_cost_fen=0, transport_mode_to_here="walk")])
    review = review_candidate_decisions(ctx, snapshot)
    assert review["hard_errors"] == []  # A soft objective never becomes a hard ban.
    summary = describe_plan_changes(ctx, snapshot, "少走路且喜欢景观", decision_review=review)
    assert "多26分钟" in summary and "符合已保存的兴趣类别" in summary
    assert "是否值得由你决定" in summary
    ctx["preferences"]["interest_categories"] = []
    _, comparison = compare_candidates(ctx, ctx["candidates"], allowed_dates={"2026-11-01"})
    assert "matches_saved_interest_category" not in comparison["walking_tradeoffs"][0]["longer_option_supported_advantages"]


def test_different_anchors_or_expired_routes_cannot_support_pairwise_claim():
    ctx = walking_case()
    ctx["candidate_route_facts"][1]["to_activity_id"] = "different-fixed-activity"
    _, c = compare_candidates(ctx, ctx["candidates"], allowed_dates={"2026-11-01"})
    assert c["walking_tradeoffs"] == []


def test_unknown_exposure_or_duration_never_becomes_evidenced_advantage():
    ctx = walking_case()
    ctx["preferences"]["interest_categories"] = []
    ctx["weather_sensitive"] = True
    ctx["candidates"][0].update(tags=[], suggested_duration_minutes=None)
    ctx["candidates"][1].update(tags=["公园"], suggested_duration_minutes=480)
    ctx["external_facts"] = {"weather": {"status": "available", "provider": "open_meteo",
        "queried_at": datetime.now(UTC).isoformat(), "payload": {"timezone": "Asia/Shanghai", "hourly": {
            "time": [f"2026-11-01T{h:02d}:00" for h in range(9, 21)], "precipitation_probability": [90] * 12}}}}
    _, c = compare_candidates(ctx, ctx["candidates"], allowed_dates={"2026-11-01"})
    advantages = c["walking_tradeoffs"][0]["longer_option_supported_advantages"]
    assert not any("weather" in item or "duration" in item for item in advantages)
    ctx = walking_case()
    ctx["candidate_route_facts"][1]["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    _, c = compare_candidates(ctx, ctx["candidates"], allowed_dates={"2026-11-01"})
    assert c["walking_tradeoffs"] == []


def budget_case():
    ctx = walking_case()
    ctx["days"][0]["activities"] = []
    ctx["actual_budget"] = {"local_date": "2026-11-01", "today_spent_fen": None}
    ctx["effective_requirements"] = [{"id": "budget", "key": "daily_budget_fen", "value": 5000,
        "scope": {"kind": "day", "date": "2026-11-01"}, "strength": "hard", "status": "active",
        "source": {"kind": "user_explicit", "ref": "test"}}]
    ctx["effective_requirements_by_date"] = {"2026-11-01": ctx["effective_requirements"], "2026-11-02": []}
    return ctx, CandidatePlanSnapshot(activities=[])


def test_unknown_spending_cannot_claim_compliance_even_after_disclaimer():
    ctx, snapshot = budget_case()
    snapshot.explanation = "实际消费未知，兼顾预算合规与体验。"
    assert unsupported_decision_claims(ctx, snapshot)[0]["code"] == "budget_claim_not_evaluable"
    snapshot.explanation = "实际消费未知，不能认定预算合规。"
    assert unsupported_decision_claims(ctx, snapshot) == []
    for text in ("实际消费未知但预算合规。", "总费用不会超过预算。"):
        snapshot.explanation = text
        assert unsupported_decision_claims(ctx, snapshot)[0]["code"] == "budget_claim_not_evaluable"
    for text in ("无法保证总费用不会超过预算。", "实际消费未知，不能认定预算合规。", "未声称任何实际消费或总花费已满足预算。", "预算合规与否尚待核验。", "预算合规尚待确认。"):
        snapshot.explanation = text
        assert unsupported_decision_claims(ctx, snapshot) == []
    snapshot.explanation = "当前预算合规。"
    ctx["actual_budget"]["today_spent_fen"] = 0
    assert unsupported_decision_claims(ctx, snapshot) == []


def test_no_future_verification_promise_and_server_unknown_summary():
    ctx, snapshot = budget_case()
    for claim in ("天气、开放与预约情况已交由后端与系统进一步确认。", "营业情况以后端核验为准。"):
        snapshot.explanation = claim
        assert unsupported_decision_claims(ctx, snapshot)[0]["code"] == "unimplemented_future_verification_claim"
    snapshot.explanation = "营业状态未知，请你出行前向场馆确认。"
    assert unsupported_decision_claims(ctx, snapshot) == []
    snapshot.explanation = "系统不会自动核验营业状态，请自行确认。"
    assert unsupported_decision_claims(ctx, snapshot) == []
    summary = describe_plan_changes(ctx, snapshot, "符合预算", decision_review=review_candidate_decisions(ctx, snapshot))
    assert "预算尚无法完整核验" in summary
    assert "不承诺后续自动核验" in summary
