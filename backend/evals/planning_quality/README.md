# Planning decision quality — Phase 0

This evaluation reuses `OpenAIResponsesPlanner`, its semantic-reference parser,
`build_planning_graph`, `invoke_compiled_graph`, route enrichment, the unmodified
candidate Validator, Goal checks, shadow Ledger and Revision approval interrupt.
`BenchmarkTrace` is the existing trace format. No business module is changed.

All locations, POI identities, event notices, weather and routes are **synthetic**.
The fixture is for variable sensitivity and missing-constraint detection, not a
claim about actual Hangzhou attractions or provider freshness.

## Run from `E:\Study\RoamSync\backend`

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
& .venv/Scripts/python.exe -B -m evals.planning_quality.version_audit --output evals/results/planning_quality_phase0_20261011/version.json
& .venv/Scripts/python.exe -B -m evals.planning_quality.run --mode deterministic --output evals/results/planning_quality_phase0_20261011/deterministic.json
& .venv/Scripts/python.exe -B -m evals.planning_quality.isolate --mode mock --output evals/results/planning_quality_phase0_20261011/mock.json
& .venv/Scripts/python.exe -B -m evals.planning_quality.isolate --mode real --repetitions 3 --output evals/results/planning_quality_phase0_20261011/real.json
```

Use a new output filename to retain previous runs. No installer or `uv sync` is
performed. Docker must already contain `postgres:17-alpine` (`--pull=never`).

## Evidence levels

- **Deterministic**: original prompt projection, candidate order, original search
  query construction and research source projection. No generation, DB or network.
  Records every broad/focused query, not just the final one.
- **Mock Provider integration**: fixed semantic JSON passes through the original
  Planner parser and Graph to a pending Revision. The mock deliberately chooses
  the last two candidates (outdoor park/festival), ignores all A/B changes and
  gives an explicit negative-control reason. Acceptance by Validator identifies
  a missing dynamic constraint; it is never a real-model quality score.
- **Real Provider / Real Model**: actual configured Planner with frozen inputs,
  synthetic route provider and controlled candidate pool. It does not test live
  Tavily/AMap/Weather or model-based Destination Research discovery. Original
  deterministic intent routing is retained. The first Provider failure stops the
  registered batch; skipped cases and partial evidence remain visible.
- **UI E2E**: not executed here. A successful pending Revision proves neither UI
  creation nor user confirmation nor formal accepted-itinerary behavior.

Graph modes require the dedicated DB/user `roamsync_phase0_eval`, a non-production
loopback port, explicit isolation flag, matching checkpoint URL and an ownership
marker. Verification happens **before importing app.database**. The wrapper
creates one named, labelled PostgreSQL container with tmpfs storage, no production
volume and no production Compose network. It migrates only that empty DB, creates
the marker and starts no API/Worker/Web. It verifies name, ID and ownership label
before deleting only its own container. `.resource.json` preserves cleanup proof.
Interrupted/killed wrappers may leave the named resource; inspect that inventory
and label before removing it. Never run broad Docker/Git cleanup commands.

The test Trip and PlanningRun/Revision writes occur only in that disposable DB.
In-memory LangGraph checkpoints are used. Every case stops at `approval`; no
Accept/Reject resumes occur. Formal Trip version/day/activity/route fingerprints
must remain unchanged. Existing Validator, route/Goal correction and confirmation
rules are not weakened; the synthetic route adapter is explicitly identified.

## Controls and observations

Eight variants form four pairs: interest; hourly weather; trip date; notice
temporal envelope. City, budget, candidate descriptions/identities/order, request,
route facts and model parameters are otherwise fixed. UUIDs differ only to own
isolated DB rows; comparisons use stable fixture identities. Weather code and rain
probability change together as one forecast condition. Publication/effective
dates change together as one notice-validity condition; this is not an estimate
of the independent effect of each timestamp.

Real comparisons require >=3 repetitions. Variant order is counterbalanced on
alternate repetitions. Existing GLM sampling remains temperature=1.0/top_p=0.95;
reasoning/model/token budget are recorded; transport retries=0, one original
format repair and bounded Graph correction remain. No seed control is exposed.
The report lists within-variant variation and cross-variant selections. A change
alone is not a quality pass and incomplete repeats cannot pass.

Artifacts contain synthetic user goals/preferences, actual Planner-visible input,
raw supplied facts, projected research sources, pool/source/identity mapping,
selected and excluded candidates, visible reasons, Validator and Ledger results,
candidate diff, Graph trace and fingerprints. Per-alternative exclusion reasons
are marked missing because the current Planner does not emit them. Brief/history
loss is observed through projection tests; this eval does not add a Brief adapter.
No hidden model reasoning is collected. A reason mentioning a preference is not
proof of causal use or factual entailment. Event venue selection must be reviewed
separately from a claim that the event occurs on the travel date.

Exit Phase 0 after binding source/runtime versions and recording results/gaps.
Do not expand corpus, add Agents, replace Planner/Validator or deploy from this eval.
