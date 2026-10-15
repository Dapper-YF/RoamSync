# Official Collector Source Repair & Reviewed Promotion Gate — 2026-10-07

RESULT: PARTIAL. REGULAR + EXCEPTION READINESS: NOT READY. This bounded source-repair slice is closed with recorded limitations; continue to End-to-End Demo Acceptance.

## Reality and budget

VERIFIED: main/HEAD5572849 and historical dirty work preserved. Current backend exactly matched prior d982 collector manifest before edits. Docker was initially unavailable; docker desktop start restored the existing engine/containers. No reset/rebase/commit, no production data deletion. Budget: one bounded repair slice, one official front-end/detail investigation, one new triage/review/promotion module and real full-list recheck. No additional venue/API capability.

## Official source repair

MEASURED: official cn index HTTP200 references app.3c0c0d72.js. That official script defines POST /api/content/detail and contentId/categoryCode/siteId request parameters. The actual request for notice39496, Notice/site22 returned HTTP200/success with content=null. description, file, linkUrl and extension1–6 are also null. Detail does not recover the body. Its title encoding is damaged; no invented decoded text or inferred effective range was used. Probe URLs/parameters, timestamps, raw responses and hashes are in official_discovery_probe.json and zhejiang_39496_detail.json.

No official body or evidence proving exclusion from supported date/venue scope was obtained. Publication2016 is only a historical triage hint; it cannot establish expiry. Missing body remains schema_broken, never automatic out_of_scope. We freeze date-specific official-notice-only capability instead of repeatedly extending collector engineering.

## Candidate triage

VERIFIED: app/travel_facts/source_review.py labels obviously_irrelevant, likely_operational, venue_scope_ambiguous, effective_date_ambiguous, schema_broken, historical, possible_supersession, temporary_closure. Closure/revision items get high inspection priority. All items remain in artifacts; auto_accepted and auto_out_of_scope are always false. Categories overlap and are hints, not accepted truth or exception-absence proof. This reduces inspection effort by grouping and priority, not by batch approving hundreds of notices.

MEASURED: current Nanjing341 candidates:251 obvious irrelevant,90 likely operational,15 temporary closure,19 possible supersession,319 historical;89 prior review_required. Zhejiang561 normalizable:394 obvious irrelevant,167 likely operational,62 temporary closure,16 possible supersession,502 historical, plus1 schema_broken record;167 prior review_required/error refs. Full category counts/rows are in live/*_triage.json. Venue/date ambiguity overlaps other categories; historic irrelevant rows are not hundreds of urgent human approvals.

## Reviewed registry governance

VERIFIED: registry has policy/version/previous_registry_hash. Reviews validate official profile/canonical venue/schema, exact content/HTML hash, explicit reviewer/time/reason, accepted branch and ordered ISO date ranges. Duplicate (source,notice) entries are rejected instead of last-write-wins. revise_registry explicitly replaces one identity in a new version with optimistic expected-hash check; previous object remains unchanged. evals/source_repair.py writes registry/evidence exclusively and refuses overwrite.

```sh
python -m evals.source_repair --output evals/results/source_repair_20261007/live-v2 --target-date 2026-10-07
python -m evals.source_repair --registry-in review-v1.json --review-in explicit-review.json --registry-out review-v2.json --expected-hash CURRENT_REGISTRY_HASH
```

Inherited v1 reviews remain only the two prior exact accepted snapshots. No new notice approved. Reviewer identities are recorded, not authenticated or signed; production approval workflow remains deferred.

## Promotion gate

VERIFIED: discovered→triaged→reviewed→accepted→promotable eligibility is separate from actual production promotion. Gate checks official domain/API, collection identity, schema/pagination/status/errors, 30-minute offline collection-age policy including future timestamps, exact canonical branch, reviewed effective date, frozen raw-content/HTML hash, existing parser understanding, overlapping-source conflicts, superseded state, exception completeness. A complete review registry must account for every nonduplicate record; keyword-rejected notices cannot certify absence of exceptions. New parser-incompatible accepted notices are blocked. Eligibility output is hash-bound to registry/content/collection and does not deploy/write DB.

30 minutes is an engineering gate for this offline evaluation, not a provider SLA. Source freshness does not imply date applicability. Promotion remains offline; no runtime provider registration, regular schedule overlay or authority redesign.

## Real gates and readiness

MEASURED: Nanjing4 pages342 physical entries and full second-pass stability; existing381205 content hash still matches, accepted1, promotion=false due exception_review_incomplete. Zhejiang6 pages562 physical entries and second-pass stability;46554 hash matches but accepted0;39496 still null. Promotion=false due schema_invalid/collection_incomplete/not_accepted_snapshot/exception_review_incomplete. Both exception_scan_complete=false. live/live_acceptance.json binds final source.

REGULAR + EXCEPTION: NOT READY. Verified regular source, complete reviewed exceptions, target-date overlay and temporary-closure precedence are not established. The gate is not a regular-schedule implementation. Keep v1 published-date-only truth; no fallback or expansion.

## Verification and rollback

MEASURED: Windows focused77 and Linux/Python3.11 focused77 passed,0 failed/error/skipped; new gate failures cover incomplete review, pagination/schema, stale/future collection, hash/scope/domain/range/status/parser, duplicate registry, invalid review and optimistic revision. Foundation28/28. No DB changes, runtime path changes or deployment, so no unnecessary full backend run; prior824 full is historical, not this slice's current measurement.

VERIFIED: baseline d98284b9f4c6590c2c6acc16ddf30eef0d9104551fb03305b54a1bc38b1f67d1; final ec632e11594c179402b09eecdb10cce8adeed0228cdd58f608d343aab522383c. All prior manifest files unchanged; added only app/travel_facts/source_review.py, evals/source_repair.py, tests/test_source_review.py. verification.json and slice_source_overlay.zip provide exact source attribution/overlay. Rollback is removal of these identified additions from integration; no blanket reset/clean. Existing production API167 runtime files still match fc3; source tools were not deployed. Source probes/triage have no DB port. Formal baseline captured for the following Demo slice; do not claim a new accepted-production-trip rehearsal from source tooling.

## Next slice candidates

|Candidate|Product impact|Reliability risk/dependency|Demo impact|Cost|
|---|---|---|---|---|
|End-to-End Demo Acceptance|High: prove complete user chain|Existing runtime/providers; isolated fixture required|Highest blocker|Bounded but live/model dependent|
|Review authentication and runtime promotion|Moderate: fact maintenance|Source completeness still blocked|Low while core rehearsal unknown|Medium|
|Decision Ledger 2.2 closure|Potentially high explanation reliability|Need current demo failure evidence first|Unknown until real run|Medium/high|

Select End-to-End Demo Acceptance. No new user decision needed for read-only audits, isolated test fixtures, evaluation and bounded fixes. Git history operations require separate explicit user approval; propose a concrete reproducibility plan before rehearsal.

# CHATGPT HANDOFF SUMMARY

CURRENT GOAL: Stable, trustworthy, demonstrable lifecycle Travel Agent System.
CURRENT SLICE: Official Collector Source Repair & Reviewed Promotion Gate.
RESULT: PARTIAL (bounded engineering delivered; external source completeness not proved).
WHAT CHANGED: Deterministic triage, versioned explicit registry replacement, hash-bound promotion eligibility, live gate artifacts and reversible slice overlay.
PRODUCT IMPACT: Accepted notices cannot silently become production truth; missing scope/schema/parser/conflict/completeness blocks eligibility.
TESTS: Linux focused77; Windows focused77; Foundation28/28; both real full-list rechecks, official detail probe.
PRODUCTION: No deployment. Existing v1/date-specific-only production retained.
KNOWN LIMITATIONS: Null official detail, pending venue/date reviews, finite triage; no regular+exception, authenticated approval or runtime promotion.
NEXT SLICE: End-to-End Demo Acceptance.
WHY NEXT: Complete user flow and UI/state consistency outrank more provider engineering; one-slice source budget exhausted.
USER DECISION REQUIRED: NO for next evaluation; YES only before future Git history operations or genuine architectural/product fork.
