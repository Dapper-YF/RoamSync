"""Eval correctness and refusal boundaries, not synthetic intelligence scores."""
import copy
import pytest

from evals.planning_quality.run import cases, facts_for, isolation_target, load_fixture, state_for, compare_generations


def test_fixture_pairs_have_single_declared_independent_variables():
    assert len(cases()) == 8
    for pair in load_fixture()["pairs"]:
        a, b = pair["variants"]
        changed = {k for k in a.keys() | b.keys() if k != "id" and a.get(k) != b.get(k)}
        assert changed == {"interest": {"interests"}, "weather": {"rain", "weather_code"},
            "festival_date": {"date"}, "news_validity": {"published_date", "effective_from", "effective_until"}}[pair["id"]]


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://roamsync:123123@127.0.0.1:54329/roamsync",
    "postgresql+psycopg://roamsync_phase0_eval:x@postgres:5432/roamsync_phase0_eval",
    "postgresql+psycopg://roamsync_phase0_eval:x@127.0.0.1:54329/roamsync_phase0_eval",
    "postgresql+psycopg://roamsync_phase0_eval:x@127.0.0.1:55500/roamsync",
])
def test_production_or_wrong_database_is_refused(monkeypatch, url):
    monkeypatch.setenv("ROAMSYNC_PHASE0_ISOLATED", "1")
    with pytest.raises(ValueError):
        isolation_target(url)


def test_isolation_requires_explicit_marker_and_loopback_port(monkeypatch):
    url = "postgresql+psycopg://roamsync_phase0_eval:x@127.0.0.1:55500/roamsync_phase0_eval"
    monkeypatch.delenv("ROAMSYNC_PHASE0_ISOLATED", raising=False)
    with pytest.raises(ValueError):
        isolation_target(url)
    monkeypatch.setenv("ROAMSYNC_PHASE0_ISOLATED", "1")
    assert isolation_target(url) == 55500


def test_no_mock_output_can_be_scored_as_real_quality():
    rows = [{"pair": "interest", "variant": "culture", "selected_keys": ["museum"], "mechanical_pass": True},
            {"pair": "interest", "variant": "shopping", "selected_keys": ["mall"], "mechanical_pass": True}]
    assert compare_generations(rows, "mock")[0]["quality_verdict"] == "not_applicable_mock"


def test_real_comparison_cannot_claim_completion_from_failed_or_missing_variant():
    rows = [{"pair": "interest", "variant": "culture", "selected_keys": ["museum"], "mechanical_pass": False}]
    pair = compare_generations(rows, "real")[0]
    assert pair["candidate_selection_changed"] is None
    assert pair["all_requested_repetitions_succeeded"] is False


def test_real_comparison_requires_the_entire_registered_repeat_count():
    rows = [{"pair": "interest", "variant": v, "selected_keys": ["museum"], "mechanical_pass": True}
            for v in ("culture", "shopping")]
    assert compare_generations(rows, "real", repetitions=3)[0]["all_requested_repetitions_succeeded"] is False


def test_expired_metadata_is_preserved_in_collector_input_not_relabelled_fresh():
    valid, expired = [c for c in cases() if c["pair"] == "news_validity"]
    a, b = facts_for(valid), facts_for(expired)
    assert a["search"]["payload"]["results"][0]["content"] == b["search"]["payload"]["results"][0]["content"]
    assert b["search"]["payload"]["results"][0]["effective_until"] == "2024-11-02"


def test_preferences_and_weather_cannot_silently_change_controlled_pool():
    baseline = state_for(cases()[0])["planning_context"]["candidates"]
    for case in cases():
        assert state_for(case)["planning_context"]["candidates"] == baseline


def test_brief_and_history_are_observed_as_dropped_without_adding_a_business_adapter():
    from app.openai_planner import build_planner_input
    state = state_for(cases()[0])
    expected, _, _ = build_planner_input(state, max_candidates=40)
    other = copy.deepcopy(state)
    other["conversation"] = [{"user": "different preference"}]
    other["planning_context"]["planning_brief"] = {"confirmed_preferences": ["different preference"]}
    actual, _, _ = build_planner_input(other, max_candidates=40)
    assert actual == expected


def test_negative_control_uses_original_parser_and_keeps_mock_provider_identity():
    import asyncio
    from app.config import Settings
    from evals.planning_quality.run import ObservedPlanner
    settings = Settings(_env_file=None, planner_provider="openai", planner_api_key="fixture", planner_model="phase0-fixed-response")
    provider = ObservedPlanner(settings, "mock")
    state = state_for(cases()[0])
    result = asyncio.run(provider.generate(state))
    mapping = {p["id"]: p["name"] for p in state["planning_context"]["candidates"]}
    assert result.provider == "mock"
    assert result.token_usage == 0
    assert [mapping[str(a.place_candidate_id)] for a in result.snapshot.activities] == ["评测露天公园", "评测节庆广场"]
    assert provider.inner.last_reliability["reference_resolution_success"] is True
