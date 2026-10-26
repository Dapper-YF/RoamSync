# RoamSync Intent Control Evaluation Baseline

Date: 2026-09-04

Dataset: `roamsync-intent-v1`, 115 Chinese requests.

Coverage includes full-trip planning, day-scoped changes, known and unknown
places, replacement, removal, reordering, read-only questions, unsupported
operations, ambiguity, misspellings, compound operations, and cross-turn UI
references.

## Deterministic baseline

Command: `python -m evals.run_intent_eval`

| Metric | Result |
| --- | ---: |
| Primary intent accuracy | 95.65% |
| Operation exact match | 95.65% |
| Entity grounding accuracy | 100% |
| Target-day accuracy | 100% |
| Clarification recall | 88.24% |
| Clarification false-block rate | 0% |
| Workflow route accuracy | 95.65% |
| Unauthorized writes | 0 |

All five deterministic failures are intentionally retained misspelling cases.
They define the current responsibility of the semantic-model fallback rather
than expanding regex rules to approximate fuzzy natural-language understanding.

## Model-enabled baseline

Command: `python -m evals.run_intent_eval --use-model`

| Metric | Result |
| --- | ---: |
| Primary intent accuracy | 100% |
| Operation exact match | 100% |
| Entity grounding accuracy | 100% |
| Target-day accuracy | 100% |
| Clarification recall | 100% |
| Clarification false-block rate | 0% |
| Workflow route accuracy | 100% |
| Unauthorized writes | 0 |

The rule layer handled 110 cases and the DeepSeek structured fallback handled
five deliberately fuzzy or misspelled cases. All five model calls succeeded,
with zero fallbacks, 12,821 total tokens, 7,314.7 ms model P50 latency, and
9,580.03 ms model P95 latency.

## Live providers

Command: `python -m evals.run_provider_smoke`

- AMap passed: one city and twelve POIs were returned with provider IDs.
- DeepSeek passed using `deepseek-v4-flash`: the structured intent probe used
  1,729 tokens and completed in 5,958 ms.

## Planner + AMap end-to-end acceptance

Command: `python -m evals.run_planner_e2e_smoke`

The live graph generated a candidate plan with DeepSeek, validated it, and
calculated three route legs with `AMap Route 2.0`. It then stopped at the
first-class approval interrupt. The smoke test rejected the proposal and
verified that the formal itinerary was unchanged.

| Check | Result |
| --- | ---: |
| Candidate revision created | Passed |
| Candidate validation | Passed |
| Real AMap route legs | 3 |
| Approval interrupt | Passed |
| Formal state unchanged before approval | Passed |
| Planner token usage | 7,960 |

The intent-control and real Planner acceptance gates are **passed**. Repeatable
verification commands are:

```text
python -m evals.run_intent_eval --use-model
python -m evals.run_provider_smoke
python -m evals.run_planner_e2e_smoke
```
