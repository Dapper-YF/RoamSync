# RoamSync project state

Last updated: 2026-09-30

## Scope

RoamSync is a local, single-user travel-planning prototype. Its primary product
claim is not “generate a travel guide”; it keeps a formal itinerary and lets a
model propose a reviewable candidate revision. The backend validates the
candidate and the user must approve it before formal data changes.

Authentication, tenant authorization, real booking/payment, vector RAG, MCP,
and continuous automatic event monitoring are not implemented capabilities.

## Architecture

React Web and a Kotlin/Compose Android client call a FastAPI backend. Web workspace and Agent monitor share the same build on port 3000; Vite development/preview also use strict port 3000 and replace the Docker Web while developing. Pre-trip conversations can be explicitly reset through a locked session-only API that replaces the session identity and removes history/pending previews; saved trip conversations remain protected. PostgreSQL
stores formal trip state and planning artifacts. A Compose worker claims
`PlanningRun` jobs using a database lease; LangGraph persists execution
checkpoints in PostgreSQL. The production model is now `glm-5.3-flash` via
BigModel streaming Chat Completions; legacy Responses providers remain compatible.
All Planner providers use separate request-local activity_N/candidate_N semantic references.
The deterministic server resolver restores formal identity before route enrichment
and existing candidate validation. AMap supplies POIs/routes. Web search and Open-Meteo
are optional external-fact inputs for the current planning flow.

`travel_goal_router.py` precedes assistant tool selection: conversation
and exploration enter an independent bounded Companion LangGraph; explicit planning
keeps the existing workflow; execution chat points to deterministic activity
controls. Optional per-turn routing metadata uses AssistantSession JSON without
migration. Companion context uses SELECT-only readers, including on imported
trips without preferences. Clear non-planning requests and answer-only intent
routes cannot create new PlanningRuns through the direct planning API. Historical
question runs/checkpoints remain compatible. Suggestion, candidate decision and
formal mutation have separate authority. See the Phase 0 engineering report for
historical routing evidence and limitations. Phase 1 adds CompanionContext,
durable structured Suggestion identities/interactions and explanation provenance.
Explicit Planning builds a PlanningBrief from saved user/Suggestion refs and
passes it to the existing ToolRouter; it is not a Revision or a new Graph hard
constraint. Phase 2 imports only Tourism Knowledge implementation commit 5023a28's
add-file diff and registers a public-contract adapter through KnowledgeToolPort.
Seven reviewed Hangzhou documents from four official/institutional sources use
lexical BM25, in-memory curated ingest and explicit need/filter selection.
Ordinary stable travel conversation (history/culture, photography, food, local
life, recommendations and comparisons) bypasses that small corpus and uses a
bounded model general-knowledge reply, marked unverified in result metadata.
The final answer contains recommendations once; structured Suggestion identities
remain available for follow-up. Explicit source requests retain reviewed retrieval.
Web defaults to final prose with a collapsed Thinking answer-basis/source disclosure.
Source requests, live facts, and original planning rationale keep their existing
evidence boundaries.
Persisted results carry document/chunk/source provenance, citation refs and
grounding limitations. Live/decision advisory is enforced before generation;
valid citations are not claim entailment. Live facts safely degrade;
long-term preference learning and automatic summaries remain deferred. Ledger
Stage 2.2 and Demo rehearsal remain OPEN. Current evidence is in the Phase 2 report.

Core request path:

```text
AssistantSession → Travel Goal Router → independent Companion Graph / Execution UI boundary
                                   → explicit PlanningBrief → existing Planning tool selection
Planning API (non-planning guard) → PlanningRun → worker/LangGraph
→ intent resolution → optional destination research → candidate draft
→ route enrichment + deterministic validation → PlanRevision
→ explicit accept/reject → transactional formal itinerary update
```

## Core modules and state

- `backend/app/assistant_service.py`: bounded JSON tool router for reply,
  trip creation/rescheduling/reuse, query, and plan requests; early Companion
  dispatch/session persistence and explicit PlanningBrief adapter.
- `backend/app/companion_runtime.py`, `companion_graph.py`: independent
  information-need workflow, generation/interaction and no self-authorized handoff.
- `backend/app/companion_contracts.py`, `companion_state.py`: bounded outputs,
  durable server identities, exact reference projection and explicit user Brief.
- `backend/app/companion_context.py`, `companion_provider.py`: minimal SELECT-only
  context and separate structured model boundary; no missing-preference repair.
- `backend/app/companion_information.py`: deterministic knowledge types and
  explicit metadata filters, separate stable/live/original-decision needs.
- `backend/app/tourism_knowledge_adapter.py`, `companion_knowledge.py`: bounded
  public-contract mapping and reviewed-corpus composition root.
- `backend/app/tourism_knowledge/`: independent ingestion/retrieval foundation;
  `knowledge_corpus/hangzhou_reviewed_v1.json` is a small real-source paraphrase
  corpus, not production destination coverage or an operational fact database.
- `backend/app/planning_graph.py`: fixed workflow nodes for resolve, clarify,
  answer, plan, validate, one correction, persist, approval, accept/reject.
- `backend/app/openai_planner.py`: schema-bounded semantic model draft; it chooses
  supplied activity/candidate refs and dates but cannot authorize or persist changes.
- `backend/app/planner_entity_resolution.py`: strict existing/new decision domains,
  request-local schema/prompt bindings, deterministic identity resolution and compact Memory input.
- `backend/app/plan_revision_service.py`: deterministic checks and transactional
  candidate acceptance.
- `backend/app/trip_execution_service.py`: execution records, manual
  event-to-replan queueing entry, and Phase 1A user-owned activity-experience
  facts (`user_extend_stay`, `user_leave_early`).
- `backend/app/timeline_impact.py`: source-neutral deterministic downstream
  schedule/slack/fixed-window/day-end projection. Navigation and activity
  experience each provide their own authoritative current boundary.
- `backend/app/activity_experience_impact.py`: read-only adapter from persisted
  activity execution facts to the shared timeline core.
- `backend/app/navigation/observation_ingestion.py`: transactionally accepts
  versioned navigation facts, reuses the deterministic delay/event core, and
  enqueues at most one active recovery run for a confirmed disruption.

Formal state: `Trip`, `TripPreferences`, `DayPlan`, `Activity`, `RouteLeg`,
`Expense`, `PlaceCandidate`, `SourceRecord`.

Trip budget semantics: `total_budget_fen` and `daily_budget_fen` are both
`NULL` when no budget constraint exists; when supplied, both are positive and
the planner/validator treat them as hard caps. Estimated activity cost remains
available in either state.

Planning state: `PlanningRun`, `PlanRevision`, `CandidateRouteLeg`, LangGraph
checkpoints. Conversation state: `AssistantSession` JSON messages with optional
goal_routing, companion_result and planning_brief; no Phase 1 migration. Execution state:
`TripExecution`, `ActivityExecution`, `TravelEvent`. `TravelEvent` now has an
optional client action identifier, unique per execution when present, so
historical events remain compatible while new experience commands are
idempotent. Navigation state:
`NavigationSession`, a versioned runtime projection of a formal itinerary leg,
and `TripDisruptionEvent`, a de-duplicated persisted macro-disruption fact.
Its stable identity is trip/version/from-activity/to-activity; the replaceable
`RouteLeg` UUID is only optional source evidence. `NavigationDetectionState`
persists debounce/risk state per session so workers and process restarts share
one decision history. Execution projection and event detection are
deterministic. Accepted observations can now create a de-duplicated disruption
and queued recovery `PlanningRun`. Phase B adds an Android execution-client
vertical slice: it reads the persisted execution projection, uses one atomic
backend start-navigation command to create or resume the unique live
`NavigationSession`, and can cancel that session. It does not use a live map
provider, GPS algorithm, AMap Navigation SDK, or post-recovery navigation restart.

## Current Agent milestone addendum (2026-09-27)

Decision Ledger now runs in default `shadow` mode: provenance is checked and
reported as `validated`/`invalid`/`unavailable`, but only independent candidate
correctness and hard Goal checks gate the pending PlanRevision. `enforced` mode
retains the Ledger gate for Stage 2.2 evaluation. User approval and transactional
revalidation are unchanged. Stage 2.2 remains OPEN. Three live first-round runs
produced valid pending revisions; three second-round runs failed strict model
candidate parsing after real Reject and correctly retrieved Decision Memory.
Complete two-round stability remains 0/3. Current evidence and final regression
are in `docs/agent/DECISION_LEDGER_SHADOW_MODE_20260927.md`; this addendum
supersedes the historical verification counts below.

## Agent Reliability milestone (2026-09-28)

Agent Reliability MVP COMPLETE on the fixed travel-decision-agent-demo fixture.
MEASURED: Normal 10/10 pending revisions; 10 real Reject/Memory cycles each
produced both first and second pending revisions, persisted feedback and
retrieved the same source Revision. 30 PlanningRuns / 33 Planner generations;
all generation parse/reference checks passed, with three extra existing
business-constraint/Goal correction calls. Formal state remained unchanged.
VERIFIED: final Linux/PostgreSQL regression 391 passed, 2 existing warnings;
Web 100 passed plus typecheck/production build. Existing identity is server-owned,
new candidates use short refs, shadow Ledger is optional in the primary output,
and failed-run retry creates an independent run with the original request/type.
Decision Ledger MVP and Stage 2.2 remain OPEN. This measured GLM batch is not a
controlled same-provider comparison with historical DeepSeek failures, nor a
universal success-rate guarantee. See the dedicated reliability report/artifact.

## Invariants and known boundary

### Planning worker stall guard (2026-09-30)

The worker executes up to two independently leased planning runs concurrently
(`AGENT_WORKER_CONCURRENCY`, default 2). Each run has an end-to-end wall-clock
deadline (`AGENT_RUN_TIMEOUT_SECONDS`, default 360); expiry persists
`planning_run_timeout` and exits through normal worker lease cleanup. Provider
requests default to a 90-second timeout and zero SDK retries, with at most one
retry configurable. Destination research uses its own low reasoning setting,
separate from itinerary generation. This bounds queue blockage; external model
availability and candidate quality remain provider-dependent. See
`docs/agent/PLANNING_WORKER_STALL_20260930.md`.

2026-09-28 verified addendum: GLM structured-output boundary now has exact
request-local references, one repair with prior visible output, streamed content
completion checks and transport/provider error classification. Final Planner
config is glm-5.3-flash / high / 180 seconds. Isolated Linux/PostgreSQL regression
passed 368 tests with 2 existing warnings. Real run e2a4137e-cc22-4861-abf2-8143e8ec370a
created pending Revision a5e96be3-572d-4c75-b1ed-08419043c5bf; end 17:45,
walking 174→61 minutes, 5/5 activities preserved. Browser shows Goal results and
Accept/Reject. No acceptance or formal mutation. Ledger remains invalid in
shadow mode; verified model reasons are not available. Stage 2.2 remains OPEN;
one successful final-config run is not a repeated-stability Exit Gate.
See docs/agent/AI_STRUCTURED_OUTPUT_FIX_20260928.md and its independent artifact.

- Model output remains a candidate until user approval.
- Candidate validation checks trip ownership, dates, sources, time windows,
  overlaps, route evidence, budget, protected activity state, and grounded scope.
- Acceptance revalidates inside a database transaction.
- Manual Activity edits increment `Trip.version`; candidate acceptance checks
  that formal version, with regression coverage for a stale candidate after a
  manual activity edit.
- Phase 1A `user_extend_stay` and `user_leave_early` are execution facts, not
  itinerary mutations. Extension totals and projected end are derived from
  `actual_started_at`, formal planned duration, and valid persisted events; no
  replanning path consumes them yet.
- Phase 1B derives but does not persist experience time impact. A live
  NavigationSession ETA is authoritative after departure; the preceding
  activity-experience boundary is not combined with it, preventing double
  counting. No experience impact creates a disruption or planning run.
- An active/rerouting NavigationSession is unique per TripExecution at database
  level. Location writes require a greater sequence and matching itinerary
  version; route results require matching itinerary and route revisions.
  Candidate acceptance supersedes live sessions in its transaction before it
  changes formal itinerary version.
- Navigation observations require a live session plus matching itinerary and
  route revisions. Sequence and payload fingerprint provide CAS and exact-retry
  idempotency; conflicting duplicates, stale timestamps, and old versions are
  rejected. Planning remains asynchronous after the queued run is committed.
- `POST /trips/{trip_id}/navigation/start` locks the Trip/TripExecution,
  validates the expected itinerary version, then creates execution and session
  together or resumes the already-live session. The current leg is resolved
  solely from persisted formal RouteLeg and ActivityExecution facts.

## Verification baseline

2026-09-30 Travel Companion Phase 2.5 COMPLETE (bounded engineering acceptance).
Final manifest `9c73bb878924d5f6d59e4e6f13f35e945cfe41ac3fcca1540dee3b0351849887`.
MEASURED: focused164; Linux/Python3.11/PostgreSQL17 migrations/full backend650
passed/0 failed/2 existing warnings; Web123/typecheck/build PASS. Real16
scenarios runtime16/16, goal15/16, premature authority0/6; holdout50 reviewed,
pending0, runtime/authority50/50, old need39/50, exact assertion coverage34/50.
Original fixture/labels preserved; final source replay nonblind. Single Codex
reviewer, bounded registered source review, not universal entailment or fresh
website verification. One advice route detail (Su/Bai causeways) is not supported
by provided assertions; general/advice implicit facts remain unverified.
VERIFIED: production API/worker rebuilt, each144 runtime files match; API/Web/
PostgreSQL healthy, worker running; HTTP smoke8/8, prepared南京3天 Brief enters
date clarification; eight production smoke cases pass, Trip/Run counts and all
versions unchanged. Prior632/six-turn closeout archived in prior_closeout.
Authorized field forms and named-subject pronoun bug fixed; current source and
production matched. Local blocked PostgreSQL host port55432 changed to54329,
existing data volume preserved; production migration20260924_0034 head. No Demo reset,
confirmation, new Phase/Agent/Travel Facts/Weather/embedding/corpus expansion
or Android contract change this round. Runtime/Identity/Brief/Adapter and
Planning approval preserved. Demo rehearsal NOT READY, Ledger Stage2.2 OPEN.
Current evidence: `docs/agent/TRAVEL_COMPANION_PHASE25_FINAL_20260930.md` and
`backend/evals/results/companion_phase25/final_verification.json`.
Earlier verification figures below are historical.

2026-09-29 Travel Companion Phase 2 (current measured working tree): fresh
pre-edit Linux/Python 3.11/PostgreSQL 17 baseline 429 passed/2 existing warnings;
final 542 passed/0 failed/2 existing warnings, 52.27s. Added 82 imported Phase A
and 31 Companion integration cases. Web 101 passed plus typecheck/build;
Android 35 passed/0 failed/skipped. Real-source lexical benchmark 8/8 and offline
tool selection 20 cases, precision/recall 1.0 (14 fake generations, real 0).
Actual GLM batch: 20 expressions, 14 completed model turns, fake 0, invalid refs 0;
two repeated targeted cases after final fixes added one completed model turn.
Real evaluation found an unsupported Hangzhou-parent-suitability assertion;
applicability metadata and a narrow server guard safely degraded the measured
repeat. Formation-year need recall, unverified generic statements, attribution
and general claim entailment remain limitations; valid refs do not prove all
claims. Next recommended stage is Companion Knowledge Reliability. Phase 1
runtime remains 21/21 and Goal corpus 60/60 with Error A/B 0. No DB in live eval;
formal mutation and explicit handoff evidence comes from PostgreSQL tests.
See `docs/agent/TRAVEL_COMPANION_PHASE2_20260929.md` and
`backend/evals/results/companion_phase2/`. No deployment or Demo reset;
rehearsal NOT READY and Ledger Stage 2.2 OPEN remain.

2026-09-29 Travel Companion Phase 1 (historical measured working tree): fresh
pre-edit isolated Linux/PostgreSQL 405 passed/2 existing warnings, 46.33s; final
429 passed/0 failed/2 existing warnings, 49.69s (24 newly collected tests).
Web 101 passed plus typecheck/build; Android 35 passed/0 failed/skipped. Offline
runtime eval 21/21 with 3 fake and 0 real provider calls; mutation guarantees come
from actual PostgreSQL integration tests. Routing corpus 60/60 runtime/goal,
A=0/35 and B=0/20, zero provider calls. These development fixtures do not establish
real Companion/RAG quality. See `docs/agent/TRAVEL_COMPANION_PHASE1_20260929.md`
and `backend/evals/results/companion_phase1/`. No deployment or Demo reset;
rehearsal NOT READY and Ledger Stage 2.2 OPEN remain.

2026-09-29 Travel Goal Phase 0 (historical measured working tree): before edits,
isolated Linux/PostgreSQL 395 passed/2 warnings; final 405 passed/2 existing
warnings, 45.83s. Web 101 passed plus typecheck/build; Android unit suite 35
passed. Offline routing corpus 60/60 runtime and goal, Error A=0/35 and B=0/20,
zero provider calls. These are development-corpus/contract results, not live
Companion quality or universal routing accuracy. The Phase 0 report and
`backend/evals/results/travel_goal_routing/` are its evidence; historical
numbers below remain historical. Existing Demo rehearsal NOT READY is unchanged.

On 2026-09-21, the isolated backend Compose suite passed 286 tests after
Activity Experience Phase 1B. Android unit tests and the debug APK build last
verified for Navigation Phase B also pass. Web passed
55 tests plus TypeScript checking and ESLint. The deterministic intent dataset
contains 115 Chinese cases; a fresh rule-only run produced 93.04% primary intent
accuracy and 95.65% route accuracy. These results are dataset-specific and do
not prove end-to-end planning quality or Multi-Agent value.


## 中文 Agent 运行监控（2026-09-29）

`/dev/agent-monitor` 默认将旅行总管与中文执行时间线左右并排。
Planning 的历史投影读取 `PlanningRun.progress.events`、Revision 和必要的持久化检查点；
`dialogue_observation.py` 提供单 API 进程内、有界的同步对话阶段与真实 tool 观测，
按 session/message 隔离。它只记录时刻、耗时、节点名和状态，不修改 Agent 执行语义。
同源请求通知与只读轮询将当前对话严格关联到实际 run_id。
普通对话逐阶段时间不持久化，服务重启后只保留既有会话 runtime_trace；
规划历史仍可重启后回放。当前可验证的 Web 入口为5173开发服务，完整Web容器
构建仍被既有测试失败阻断。详情和演示输入见 `docs/AGENT_MONITOR_DEMO.md`。


## Knowledge Coverage & Frozen Evaluation (2026-09-30)

MEASURED: A bounded existing-Knowledge slice is complete in the working tree, not deployed. Sixty new cases and 24 real-provider selections were frozen before application/corpus edits; labels unchanged. Same-set baseline/final strict need 11/60→34/60, registered assertion case coverage 13/44→35/44, stable/live coverage 0/10→7/10; runtime/authority 60/60 throughout. Final source SHA 897a784a97d31cdf0ecd5fd97ee9e11f97ff72244ba424e96e347e5208e52f77; focused 139 and Linux/PostgreSQL full 657 passed (2 existing warnings).

VERIFIED: Existing need semantic families and graph mixed handling were refined, source advice prompt constrained, and one existing senior-duration assertion gained a topic. No new sources/assertions, ranking/Adapter/Router/Runtime/Identity/Brief/Planning authority redesign or Travel Facts implementation. Production remains accepted Phase 2.5 snapshot; its earlier measurements are historical, not current-tree deployment proof.

LIMITATION: This is same-reviewer frozen-label regression after baseline unsealing, not independent human/blind validation. Real 24 cases triggered 9 model generations (0 errors/repairs); 35 structured source facts matched registered scope, but at least 6 reviewed prose units lacked supplied evidence. Source intent/negation/history/mixed literary coverage gaps remain. Utility/retrieval/refusal proxies do not prove universal factuality or usefulness. Stop further Knowledge expansion; recommend Travel Facts Integration v1 / verified forecast next, not implemented. Report and hash-bound evidence: docs/agent/COMPANION_KNOWLEDGE_COVERAGE_20260930.md and backend/evals/results/knowledge_coverage/verification.json.


## Travel Facts Integration v1 — COMPLETE and deployed (2026-09-30)

VERIFIED: Foundation5f9f5e5 exact24 added paths integrated into main without
branch/snapshot merge/reset/stash/commit. Existing transport/dependencies/DB owners
retained. Companion adds thin native FactRequirement→ResolvedFact read-only tool;
server-owned future hourly forecasts, internal two-city WGS84/timezone resolution,
local deterministic hour windows, explicit forecast15min/place24h freshness,
provider_prediction semantics and failure/stale/conflict limits. Stable Knowledge
is independent; no current/past observations or other Fact capabilities exposed.

MEASURED: current-main Foundation87, focused245, clean Linux/PostgreSQL full768
passed (2 old warnings); benchmark28/28. Knowledge frozen regression remains
need34/60/assertions35/44/mixed7/10 and old outputs unchanged. Offline20 scenarios
weather precision13/13/recall13/14 (location dependency failure counted). Final
real14 scenarios/12 weather boundaries: precision/recall8/8,66 fresh hours, no
unnecessary/stale/unsupported dynamic checks or Planning authorization errors;
model generations0 on server-rendered paths. Early TLS failures remain history;
final real-provider and mixed replies pass on final source.

VERIFIED: production API+worker built/recreated with BOTH Knowledge Coverage and
Travel Facts. Final source7e01c9cee0537824e94e931e009fdfb552184d8110d5870819c7ce67dd948d3d;
165 runtime files each match. API live/ready/Web200;worker process running;
PostgreSQL healthy/migrations0034 head. Production smoke7/7, first six Companion/no
run, explicit Planning prepares Brief/date clarification (run delta0). Trip178,
PlanningRun105,PlanRevision35 and all Trip versions unchanged before deploy/after
smoke; formal Trip/day/activity/revision row hashes unchanged. No reset/approval.

LIMITATION: two-city representative forecasts, transient external failure, no
microclimate/current observation/alerts, model issue time unavailable, lexical
intent/date parsing and no independent meteorological accuracy audit. Prior
Knowledge gaps, Ledger2.2 OPEN and Demo rehearsal NOT READY retained. Recommend
separate Verified Opening Hours v1 only after source/effective-time policy design;
not implemented. Report/evidence: docs/agent/TRAVEL_FACTS_INTEGRATION_V1_20260930.md
and backend/evals/results/travel_facts_integration/verification.json.


## Verified Opening Hours v1 — 2026-10-01

VERIFIED: bounded official published-date opening schedules added to existing Companion Fact Tool. Two exact museums only: 南京博物院 main (2026 Sep25–27, Oct1–7), 浙江省博物馆之江 (Sep25–Oct8). Official CMS reviewed parser; native multi-interval/closed/unknown/local-date/last-admission contract; no cross-turn hours cache or model guessing. Target-date schedule is not current operation, admission guarantee or absence of other closures. Unknown date/venue/new notice fail closed; opaque intervening turns prevent prior venue identity reuse.

MEASURED: focused218, final clean Linux/Python3.11/PostgreSQL full795/2 existing warnings; Foundation28/28; sources2/2, real Companion20/20, production10/10. Knowledge frozen60 metrics unchanged, old output hashes intact. Earlier794 full required fresh acceptance after late identity correction; intermediate evidence preserved.

VERIFIED: API+worker each167 runtime files match source fc3a06ba3cf95aaa6317f95f3b3cc300d2dd582299ac24ac7b91dce995f3bdfb; Knowledge+forecast+hours deployed together, Web unchanged. Seven formal-state table full-row hashes/counts and Trip versions unchanged across deployment/smoke; only synthetic Assistant sessions/messages. Planning control prepares Brief/date clarification with no Run delta. Ledger2.2 OPEN/Demo NOT READY and prior Knowledge limits unchanged. Report: docs/agent/VERIFIED_OPENING_HOURS_V1_20261001.md; evidence: backend/evals/results/opening_hours_v1/verification.json. Next: official collector discovery/pagination/schema-review lifecycle, no Foundation or Router rewrite.

## Official Opening Schedule Collector Lifecycle — 2026-10-01

VERIFIED: new offline official_collector.py and eval/review CLI implement deterministic domain/section discovery, complete physical pagination plus second-pass stability, canonical venue/branch scope hints, required-schema/HTML fingerprints, content hash re-review, candidate/accepted separation and explicit reviewed supersession. No runtime composition/Fact contract/Agent/DB changes; no deployment. Existing v1 source files unchanged; production API/worker each167 files still match fc3a06ba3cf95aaa6317f95f3b3cc300d2dd582299ac24ac7b91dce995f3bdfb.

MEASURED: actual Nanjing4 pages342 entries/341 candidates, existing381205 rediscovered and accepted1. Zhejiang6 pages562 entries/561 normalizable candidates, existing46554 rediscovered with exact review hash, but historical39496 content=null makes source schema_changed/accepted-for-use0. Both pagination traversals and rechecks complete; exception_scan_complete false (pending review plus source schema problem). CURRENT SLICE PARTIAL; regular+exception NOT READY; production truth stays bounded v1.

MEASURED: focused165; final clean Linux/Python3.11.16/PG17/alembic0034 full824 passed/2 old warnings; Foundation28/28; real sources2/2 and Companion20/20 including forecast/Knowledge/mixed/Planning boundaries. Frozen60 summary unchanged and60 previous evidence files hashes preserved. Production seven formal-table full-row hashes/counts and Trip versions unchanged, Run delta0. Offline final source d98284b9f4c6590c2c6acc16ddf30eef0d9104551fb03305b54a1bc38b1f67d1. Report: docs/agent/OFFICIAL_OPENING_SCHEDULE_COLLECTOR_20261001.md; evidence: backend/evals/results/opening_collector/acceptance_summary.json.

LIMITATION/NEXT: only configured listings, finite lexical filtering/scope hints, no atomic CMS snapshot, historical null-body source fails closed, review authentication/version arbitration/promotion and runtime integration deferred. Resolve official source completeness and explicit candidate effective-date reviews before considering regular schedules or deploying collector-backed truth. Existing Ledger2.2/Demo/Knowledge limitations retained.

## Long-Term Product Advancement / Source Repair — 2026-10-07

VERIFIED: long-term product goal active; Source Repair bounded slice delivered deterministic triage, versioned/hash-guarded review registry and accepted-versus-promotable offline gates. Exactly3 source additions, prior source unchanged, final ec632e11594c179402b09eecdb10cce8adeed0228cdd58f608d343aab522383c. No runtime registration/deployment/DB/schema change.

MEASURED: official39496 detail body/alternatives null; both real list scans stable but exception completeness false; promotion rejected, regular+exception NOT READY. Linux/Windows focused77, Foundation28/28. Freeze bounded published-date facts; stop unbounded collector repair. Select End-to-End Demo Acceptance by product impact/dependency/demo cost comparison, proceed without new decision. Progress board and reproducibility proposal added; release/Git approval deferred until concrete allowlist/gates. Product milestone remains unproven; dirty repository, Ledger2.2 and actual lifecycle rehearsal remain risks.


## Demo acceptance runtime corrections — 2026-10-08

VERIFIED: Initial pending candidate day edits bind exact backend-owned Revision/hash/version and preserve untouched dates without formal mutation before approval. Session-associated candidate restores on Trip mount. Active/paused Execution automatically protects frozen/current/navigation-target activities in enrichment, validation and actual acceptance, including ordinary Planning; cost projections include implicit retention. Explicit Nanjing Knowledge scope cannot reuse Hangzhou corpus; no corpus/schema/Agent expansion.

MEASURED: Latest Linux/Python3.11/PG17 full854, Web125/typecheck/build, real isolated UI lifecycle/Recovery/reject/honest explanation/scoped facts; frozen60 summary unchanged. Simulation navigation and compressed synthetic execution are labeled. Production source fc3 and seven-table formal baseline unchanged. Current code not deployed; clean Git-ref release/rehearsal remains approval-gated. Report: docs/agent/ROAMSYNC_DEMO_ACCEPTANCE_20261007.md.
