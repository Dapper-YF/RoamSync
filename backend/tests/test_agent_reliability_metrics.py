from evals.agent_reliability.run import summarize, memory_rates


def test_provider_outage_separate_from_agent_reference_and_json_failure():
    summary = summarize([
        {"failure_category":"provider_failure", "planner_reached":True},
        {"failure_category":None, "planner_reached":True,"parse_success":True,"reference_resolution_success":True,"revision_produced":True,"attempt_failure_categories":["planner_malformed_output"]},
        {"failure_category":"planner_invalid_reference","planner_reached":True,"parse_success":True,"attempt_failure_categories":["planner_invalid_reference"]},
    ])
    assert summary["rates"]["provider_failure_rate"]["numerator"]==1
    assert summary["rates"]["malformed_json_rate"]["numerator"]==1
    assert summary["rates"]["invalid_reference_rate"]["numerator"]==1
    assert summary["rates"]["plan_revision_rate"]["denominator"]==3


def test_memory_rates_keep_full_cycle_and_eligible_denominators_distinct():
    rows=[{"first":{"revision_produced":True},"feedback_persisted":True,"memory_retrieved":True,"second":{"parse_success":True,"revision_produced":True}},
          {"first":{"revision_produced":True},"feedback_persisted":True,"memory_retrieved":True,"second":{"parse_success":False,"revision_produced":False}},
          {"first":{"revision_produced":False},"feedback_persisted":False}]
    rates=memory_rates(rows)
    assert rates["memory_retrieval_rate"]=={"numerator":2,"denominator":2,"rate":1}
    assert rates["second_parse_rate"]=={"numerator":1,"denominator":3,"rate":1/3}
    assert rates["second_revision_rate"]["denominator"]==3
    assert memory_rates([])["second_revision_rate"]["rate"] is None
