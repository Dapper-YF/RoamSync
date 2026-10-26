from app.navigation.recovery import RecoveryActivity, enumerate_recovery_options, recovery_metrics


def test_compression_option_recovers_only_the_needed_deficit_and_metrics_are_recomputed():
    options = enumerate_recovery_options(
        deficit_minutes=20,
        activities=[RecoveryActivity("future-optional", 60, minimum_duration_minutes=30)],
    )
    compress = next(item for item in options if item.type == "compress_activity")
    assert compress.recovered_minutes == 20
    assert compress.remaining_deficit_minutes == 0
    assert recovery_metrics(before_deficit_minutes=20, option=compress) == {
        "recovered_delay_minutes": 20,
        "resulting_minimum_slack_minutes": 0,
        "activities_removed": [],
        "activities_compressed": [{"activity_id": "future-optional", "by_minutes": 20, "resulting_duration_minutes": 40}],
        "travel_mode_changes": [], "changed_future_activity_count": 1,
        "remaining_hard_violations": [], "estimated_cost_delta_fen": None,
    }


def test_no_fact_backed_recovery_keeps_an_explicit_risk_option():
    options = enumerate_recovery_options(deficit_minutes=20, activities=[RecoveryActivity("fixed", 60)])
    assert [item.type for item in options] == ["keep_current_plan"]
    assert options[0].remaining_deficit_minutes == 20
