# RoamSync Demo Acceptance — 2026-10-08

Status: NOT READY — clean Git source builds and regression passes, but the fresh real-provider Candidate gate failed. Long-term goal remains ACTIVE. Production unchanged; deployment/main merge/production DB changes are not authorized.

## Current release identity and evidence

Branch codex/roamsync-demo-release-20261007 from main5572849. Application release 8ee7dbf0ddc27fdb8fd55bc20fad9777ec4bf209; final documentation checkpoint is recorded in release_final_binding.json. Source e7e22849869443bb73f96bce736fb86a1c4b3745f2a48f6f32da3273176622a6. Independent initial-clean checkout E:/Study/RoamSync-release-20261008 has all366 approved hashes and two deletions. Runtime API/Worker have no source mounts;175 shipped files match. Nginx production Web3001 proxies isolated API8001; separate PostgreSQL17 and actual GLM/AMap/Tavily/Open-Meteo, no mocks.

|Gate|Current clean-ref result|
|---|---|
|Exploration / routing safety|VERIFIED real UI: no Trip mutation/Run during conversation; explicit Nanjing reliable-source gap disclosed|
|Knowledge coverage|Controlled frozen60 preserves known need34/60, assertions35/44, mixed7/10; finite coverage, not universal correctness|
|Dynamic facts|Second conversation verified usable forecast and official published-date hours; first geocoding outage retained|
|Explicit Planning|Preview + user confirmation creates the isolated Trip and initial Run|
|Candidate / Validator|FAILED: research invalid JSON; two UI retries fail provider transport; no valid Candidate|
|Candidate modification / Accept / Reject / Feedback|UNVERIFIED in this fresh release chain; earlier isolated evidence is historical|
|Formal version progression|Trip version1, zero formal activities; no unauthorized mutation after failure|
|Execution / experience / Disruption / Recovery|NOT EXECUTED because Candidate prerequisite failed|
|Recovery explicit acceptance / protection / costs|NOT EXECUTED on clean release|
|Honest Explanation|Earlier isolated rationale_unavailable evidence retained; fresh clean chain not reached; Ledger2.2 OPEN|
|Repository reconstruction|VERIFIED exact clean Git source, locked builds and isolated full regression|
|Complete real E2E / Demo rehearsal|NOT PASSED; no substitution of older dirty-tree results|
|Reproducible production deployment|NOT ACHIEVED / NOT AUTHORIZED|

## Actual failures and preservation

First Chrome run stopped at Open-Meteo geocoding provider_unavailable; application honestly said location/weather could not be verified. Direct later geocoding probe returned200. Second complete conversation passed weather and opening checks and confirmed creation. Initial Run failed planner_research_invalid_output; original failure and screenshots/traces remain. Two retries used the normal UI “重试本次需求”, the same Trip and original request, after each prior Run had terminal failed status. They failed planner_unavailable; final log reports RemoteProtocolError. Direct model diagnostic without proxy also failed APIConnectionError/ConnectError. These are actual observed failures, not proven attribution to a specific upstream component.

The fixture remains version1 with zero formal activities. All three failed Runs are retained. Source bytes, labels and assertions were unchanged. No fabricated candidate, provider mock, automatic reset or production mutation. Lifecycle driver's prerequisite failure is not an independent product defect and is not counted as executed downstream acceptance.

## Regression and manifest verification

Clean locked Linux/Python3.11/empty PG17 migrated0→0034:854 passed,0failed/error/skip,2 existing warnings. Web locked install/typecheck/125tests/build passed. Controlled clean-checkout Knowledge60 and Phase2.5 holdout50 results unchanged. Backend/Worker175 source hashes exact; Web built artifacts/image IDs retained. Production seven formal tables and Trip versions exactly match the preceding baseline. Final documentation-only checkpoint leaves application source unchanged and is independently rebound before final reporting.

## Historical successful rehearsal — not current clean-ref proof

Previous dirty-tree isolated Trip verified real Candidate→day2 lighter edit→explicit acceptance→Execution/extend30→simulated delay→Disruption→Recovery→explicit acceptance, versions1→2→3. Candidate costs aligned with formal costs19000fen. Fresh current-version candidate rejection saved feedback without formal change; Knowledge scope and missing-original-rationale Explanation passed targeted live tests. Source corrections captured in application release preserve pending candidate UI, untouched days, settings intent, canonical Execution protection and implicit retained cost totals, plus explicit-city Knowledge filtering. No new functionality was developed in this release-preparation round apart from the approved packaging/reset amendment.

Keep historical wrong-city Knowledge, incomplete day2-only formal itinerary, route mismatch and cost mismatch failures distinct from later corrected results. Published opening dates are not operational guarantees. Simulated navigation and compressed normal activity actions are acceptance inputs, not physical GPS/travel-duration evidence. Nanjing curated corpus unavailable; Hangzhou corpus finite. Source Repair bounded slice remains PARTIAL, regular/exception NOT READY; no new source promotion.

## Next gate and rollback

NOT READY for online confirmation. Restore stable actual model transport, then continue unchanged clean-ref browser lifecycle through validated Candidate/modification/Accept/Reject/Execution/Disruption/Recovery/Explanation/Feedback. Preserve failures and inspect authoritative Run status before retry. Rebind final clean checkout, images and runtime manifests. Only after success report production differences and await final human online authorization. Rollback/deployment plan and retained production image IDs are in Repository Reproducibility report / production_rollback_inventory.json. Production schema changes need separate approval; existing data must never be reset.

Raw current evidence: backend/evals/results/git_release_20261008; clean_rehearsal_attempt1, attempt2, retry1, final_failed; clean_rehearsal_verdict.json; clean_backend_full.xml and clean checkout/image/runtime/production manifests. No raw chats/screenshots/private artifacts were committed.

## CHATGPT HANDOFF SUMMARY

CURRENT SLICE: Git reproducible release preparation and isolated acceptance.
RESULT: Git capture/clean builds/regression VERIFIED; complete real lifecycle NOT READY.
RELEASE: Application8ee7dbf; final documentation SHA recorded in release_final_binding.json / final response.
TESTS: Backend854; Web125/typecheck/build; unchanged frozen60/holdout50.
PRODUCTION: Existing accepted snapshot retained; formal baseline exact; no deployment/merge/DB changes.
NEXT: Provider transport gate, then unchanged full clean-ref real lifecycle; final online approval only after success.
GOAL: ACTIVE; no claim of product completion.
