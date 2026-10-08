# RoamSync Demo Acceptance — 2026-10-08

Status: PARTIAL / PRE-RELEASE ACCEPTANCE. The bounded real-system lifecycle and subsequent P0 corrections are verified in isolation. Product milestone remains unproven: Git reproducibility, clean-ref rehearsal and production binding/deployment are not achieved.

## Reality and runtime

Repository E:\Study\RoamSync; main HEAD5572849209c943c5f5ad1579db4cef0ba2fb5b25; historical dirty/untracked work preserved. Source Repair closed PARTIAL, regular+exception NOT READY. Production API/worker retain accepted source fc3a06ba3cf95aaa6317f95f3b3cc300d2dd582299ac24ac7b91dce995f3bdfb; no Demo deployment or Git writes.

Real-provider acceptance uses a separate PG17/tmpfs database, API127.0.0.1:8001, worker and Vite3001. Actual GLM, AMap, Tavily and Open-Meteo are used, with no request/model/provider mocks. Existing production and earlier isolated trips were preserved. Assistant/Planning calls and confirmations use normal UI/API contracts. Credentials remain external and raw evidence is excluded from the proposed release.

## Requirement-by-requirement audit

|Goal gate|Authoritative evidence|Result and limit|
|---|---|---|
|1 Natural exploration|conversation.json turns1–3, visible screenshots, real provider outputs|Bounded flow passed; no formal mutation; general advice is unverified model prose|
|2 Trustworthy Knowledge|knowledge-scope.json + frozen60 current rerun|Passed bounded scope: Nanjing honestly unavailable; Hangzhou sourced claims. Original Nanjing→West Lake answer was a defect, retained and corrected|
|3 Verifiable dynamic facts|knowledge-scope.json turns3–4, native ResolvedFacts and visible provenance|Fresh Oct8 fetch: Nanjing Oct9 forecast; Zhejiang Oct8 closed official schedule. No operational/admission guarantee|
|4 Explicit handoff|conversation.json turn7/creation/PlanningBrief|Create preview and explicit confirmation required; no Trip changes during exploration|
|5 Candidate/Validator|conversation/lifecycle Revision validation and actual model/route observations|Passed; initial candidate kept formal activities empty; bounded repeat evidence, not universal stability|
|6 Accept/reject|lifecycle acceptance; current-review.json fresh valid-version candidate/rejection; older review.json|Passed normal UI: rejection persisted feedback without changing formal Trip/days/version. Resumed clarification history retained separately|
|7 Correct version|lifecycle before/after; execution before/after|Formal version1→2 on user acceptance;2→3 on Recovery acceptance; rejection retains3|
|8 Execution|execution.json started/experience/accelerated_execution and visible UI|Persisted start/arrive/play/complete state verified in synthetic fixture|
|9 Experience affects time|execution.json experience_before/after|Explicit extend30 projects end+30 and records time impact; no automatic itinerary replan|
|10 Disruption detected|execution.json observations/disruption and detector state|Real ingestion/detector; labeled simulation navigation input, not physical GPS|
|11 Recovery generated|execution.json recovery and real worker/model progress|Validated pending candidate generated from actual persisted disruption|
|12 Confirmation updates state|execution.json after and protected field checks|Explicit UI approval resolves disruption, preserves completed/current activities, version+1; summary19000fen equals formal costs19000fen|
|13 Honest explanation|explanation.json|rationale_unavailable, based_on_prior_decision=false, explicit missing original reasons; Ledger2.2 remains OPEN|
|14 Real E2E|conversation→lifecycle→execution→explanation, current-review and knowledge-scope followups|Real system segments passed; latest fixes covered by full regression and targeted live segments. Initial conversation's Knowledge error invalidated its original full-pass claim|
|15 Reproducible production|REPOSITORY_REPRODUCIBILITY_20261007.md + exact release allowlist|NOT ACHIEVED. Git authorization, clean-ref build/rehearsal and production deployment/binding/smoke remain|
|16 Demo rehearsal|screenshots, actual visible candidate/confirmation/disruption/recovery/reject/explanation|Isolated staged rehearsal passed with corrections. Clean-ref complete rehearsal still pending; global Demo Ready not declared|
|17 Explicit limits|this report, frozen outputs, failed histories, Source Repair report|Documented; update again after release proof|

## Bounded changes and actual defects

- Restore only the session-associated same-trip PlanningRun when the newly created Trip mounts; previous UI hid a real pending candidate.
- Distinguish preserved dates/budget/party/preferences and completed-activity groups from actual venue names; unknown venue references still clarify.
- Bind the exact initial pending Revision/hash/version for day edits, supply separate draft context, preserve untouched dates exactly and recheck source eligibility at approval. The earlier day2-only formalized trip is retained as a failed attempt.
- Align route enrichment, validation and acceptance with canonical frozen/protected Execution IDs. In-progress/paused trips enforce invariants even for ordinary Planning, including pending current/navigation target. The acceptance integration test now proves those activities survive actual approval; route-time/daily-window checks were retained.
- Include implicitly retained activities in candidate cost totals without double charging represented replacements. Earlier real failed route recovery and21000-vs24000 summary mismatch remain failed history.
- Bind explicit Nanjing to Knowledge destination filtering; the finite Hangzhou corpus cannot answer a Nanjing reliable-source question. Exact-city correction does not expand Knowledge corpus or frozen labels. Browser assertions now inspect the requested destination and visible content.
- Exclude evals/results from backend Docker build context; raw acceptance data is not runtime package content.

No DB/public schema/migration/new Agent/Fact type/Memory redesign. All current fixes are working-tree/isolated runtime changes; production is unchanged.

## Verification

MEASURED: latest Linux/Python3.11/PG17 full 854 passed,0failed/error/skipped (backend_scope_final.xml),2 existing Starlette warnings. It uses the existing isolated test DB at migration0034; the earlier empty-PG full is separate history. Authority focused47 and followup21; Knowledge scope Linux48. Windows Knowledge run had one existing Proactor DB integration failure; Linux48 closes that environment-dependent check. Web125/typecheck/build previously passed and current Web runtime source remained unchanged; new Playwright drivers ran against real API/model/providers.

Frozen Knowledge60 rerun retains need34/60, assertions35/44, mixed7/10 and exact summary; original labels/results not overwritten. Foundation28 remains Source Repair evidence. Current-review fresh run passes without clarification; its earlier clarification/resume is separately retained. Knowledge scope live4 turns passes. Production seven formal tables/counts/full-row hashes and Trip versions exactly match baseline (formal_current_final.json).

Final verification.json, final_source.json, slice_source_overlay.zip and refreshed release_allowlist.json bind exact reviewed files and test artifact hashes. Git index remains empty. Historical/backend checkpoints are explicitly distinguished from the latest source.

## Limitations and rollback

Navigation input source=simulation; activity progression was compressed through normal actions and the future-dated synthetic Trip was deliberately started early. These are labeled acceptance inputs, not evidence of physical travel/device GPS or actual duration learning. A positive-slack20min delay correctly did not produce disruption; later infeasible inputs did. Provider availability/model output vary; one scripted pass cannot prove universal quality. Nanjing curated Knowledge coverage is unavailable; Hangzhou coverage is finite with known frozen gaps. Opening Hours remains official published-date-only for two venues; no regular/exception completeness/current status. Original accepted Recovery rationale is unavailable; honest fallback is tested, not Ledger2.2 completion.

Baseline Source Repair manifest ec632e11594c179402b09eecdb10cce8adeed0228cdd58f608d343aab522383c. Source-specific backups/overlay identify this slice; rollback restores only identified paths after preserving later user edits. Never reset/clean the dirty worktree. Isolated containers can be stopped independently; production images/config/database were untouched. Production release must retain existing images/config for rollback and must not reset user trips.

## Next slice candidates

|Candidate|Product impact|Risk/dependency|Demo impact|Cost|
|---|---|---|---|---|
|Git reproducible release + clean-ref rehearsal|High; closes gate15 and source identity|Explicit user history approval, then locked dependencies/current providers|Highest remaining blocker|Bounded build/rehearsal/deployment|
|Decision provenance2.2|Moderate; richer original reasons|Honest fallback works; original recording remains unavailable|Below reproducibility|Medium|
|Additional source promotion/coverage|Low immediate lifecycle value|Official completeness still NOT READY|Low|Potentially unbounded; deferred|

Select reproducible release. Proposed branch codex/roamsync-demo-release-20261007, exact allowlisted backend/Web/operator/docs files plus two explicit existing deletions. Exclude Android changes, credentials, raw acceptance/private data and unrelated artifacts. No history operations executed. After explicit approval: grouped commits, clean Git checkout, locked builds/PG regression/live complete rehearsal, then production deploy/binding/smoke and formal-state safety. Do not claim product complete before these gates.

# CHATGPT HANDOFF SUMMARY

CURRENT GOAL: Stable trustworthy lifecycle Travel Agent System.
CURRENT SLICE: End-to-End Demo Acceptance.
RESULT: PARTIAL — isolated real chain and P0 followups verified; release gate pending.
WHAT CHANGED: Candidate UI restore/edit preservation; intent metadata; protected execution route/approval/cost alignment; Knowledge city scope; real review/fact/explanation tests.
PRODUCT IMPACT: Formal changes remain explicit-confirmation gated; ordinary Planning cannot silently remove current/navigation-target activities; wrong-city sourced answers fail closed.
TESTS: Latest Linux full854; Web125/typecheck/build; Knowledge frozen60 unchanged; actual UI lifecycle/recovery/reject/scope/Explanation.
PRODUCTION: Prior accepted source retained; formal seven-table snapshot unchanged; no Demo deployment.
KNOWN LIMITATIONS: Simulation/compressed synthetic execution; finite Knowledge/date-specific facts; Ledger2.2 OPEN; dirty Git cannot reproduce release.
NEXT SLICE: Git-reproducible release and clean-ref rehearsal.
WHY NEXT: Highest remaining product milestone blocker; reviewed implementation is ready for exact release audit.
USER DECISION REQUIRED: YES before proposed Git branch/stage/grouped commits, per user goal section22. Goal remains ACTIVE.
