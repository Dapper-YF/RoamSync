from evals.intent_cases import INTENT_EVAL_CASES


def test_intent_eval_dataset_is_large_unique_and_balanced() -> None:
    assert len(INTENT_EVAL_CASES) == 115
    assert len({case["id"] for case in INTENT_EVAL_CASES}) == 115
    assert all(case["text"].strip() for case in INTENT_EVAL_CASES)
    assert all(case["expected_primary"] != "mixed" for case in INTENT_EVAL_CASES)
    assert all(case["expected_operations"] for case in INTENT_EVAL_CASES)
    assert sum(case["should_clarify"] for case in INTENT_EVAL_CASES) >= 15
    assert sum("grounding" in case["tags"] for case in INTENT_EVAL_CASES) >= 40
    assert sum("typo" in case["tags"] for case in INTENT_EVAL_CASES) >= 5
    assert sum("multi_intent" in case["tags"] for case in INTENT_EVAL_CASES) >= 5
    assert sum("cross_turn_reference" in case["tags"] for case in INTENT_EVAL_CASES) >= 5
    assert {case["expected_route"] for case in INTENT_EVAL_CASES} == {
        "answer",
        "clarify",
        "plan_preview",
        "reject",
    }
