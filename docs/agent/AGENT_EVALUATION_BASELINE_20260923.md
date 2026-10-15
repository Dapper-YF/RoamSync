# Stage 0 baseline: Travel Agent Benchmark v1

Run date: 2026-09-23. Command executed from `backend`:

```text
uv run --no-sync python -m evals.run_travel_benchmark --output evals/results/baseline-offline
```

This is the reproducible **offline architecture baseline**, not a claim about a live paid-model score. It runs nine structured scenarios against observed current-system capability boundaries and writes one trace/result JSON per case. A live-provider adapter is intentionally not run in CI: the repository's current provider may be paid and nondeterministic. The result schema is shared so a live PlanningRun can be added later without changing metrics or fixtures.

## Results

| Scenario | Current observable result | Baseline signal |
|---|---|---|
| initial-hangzhou-cultural | requires live provider run | no live quality score in offline CI |
| ambiguous-relaxed | plans_without_value_clarification | clarification quality is not yet measured as a successful intelligence capability |
| must-do-show-conflict | requires live provider run | requires fixture/provider-backed run |
| recovery-delay-45 | requires live provider run | recovery scope/must-preserve baseline pending adapter |
| reject-repeat-density | rejection_not_in_planner_context | Repeat Error = true |
| culture-not-shopping | requires live provider run | preference result pending adapter |
| budget-pressure | requires live provider run | validator result pending adapter |
| provider-failure | fails_closed | Constraint Violation Rate = 1.0; no invented external tool recorded |
| bad-but-valid-rush | no_semantic_critic | Bad-but-valid Detection = false |

The deliberately poor results are baseline evidence, not defects hidden by test doubles: plan-mode input contains no structured rejection reason, and current graph has no semantic critic. The fixture baseline must not be used to compare model quality; its purpose is repeatability and an honest record of currently unimplemented evaluation dimensions.

## Live production observations

`initial_plan_with_budget_expression` is a preserved real production failure: the exact request "杭州一日游，预算800元，喜欢文化和自然体验，不要购物。" created PlanningRun `ca98…0401`, resolved `adjust_budget` despite `initial_plan`, required `target_day`, and stopped at clarification. Planner, route enrichment, validator and PlanRevision were not reached; token usage was zero. This is **Request Interpretation / Intent Routing Failure**, not Planner failure; downstream semantic metrics are N/A.

The unmodified downstream control wording resolved to `create_plan`, then failed at Tavily authentication before Planner invocation (PlanningRun `5fbb…9b54`). This proves the distinct downstream external-provider boundary and is not evidence of DeepSeek Planner behavior. Both artifacts are committed under `backend/evals/results/stage0_live_baseline/`.

## Trace contract

`travel-agent-trace-v1` records scenario/run ID, graph step, compact input fact references, tool call/result metadata, planner candidate count/provider/token usage, validation codes, user decision and timing. It excludes prompts, full database rows and secrets. `PlanningGraph.build_planning_graph(..., trace_observer=...)` now emits optional observation events; the default is `None`, so ordinary PlanningRuns retain their original execution path.

## Evaluation layers

- Deterministic: constraint violation, explicit must-preserve goal satisfaction, avoid-category preference preservation, recovery unnecessary-change rate, tool precision/recall, explanation claim/evidence consistency, repeat-error and critic-detection flags.
- Semantic/human compatible: a stable `travel-agent-semantic-rubric-v1` packet scores relaxed pace, trade-off grounding and uncertainty honesty on 0–2 per rubric item, with mandatory evidence and pass/fail/unknown. No LLM judge is called automatically.

## Environment evidence

Framework tests passed: `3 passed in 0.06s` (`tests/test_travel_benchmark.py`). A local PostgreSQL integration attempt was blocked before application assertions because Psycopg async rejects Windows' ProactorEventLoop. The repository's Docker Linux test command was also attempted but Docker Desktop's Linux engine pipe was unavailable. No regression conclusion is claimed until `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test` runs successfully in a Linux/Docker environment.
