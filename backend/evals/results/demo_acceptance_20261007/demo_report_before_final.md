# RoamSync Demo Acceptance — current audit (2026-10-07)

Status: IN PROGRESS / NOT READY. Long-term product milestone unproven. This artifact is not a declaration of complete rehearsal.

## Runtime and reproducibility

Actual source baseline and production evidence inspected; Docker engine restored. Source Repair closed PARTIAL with NOT READY regular+exception. Safe Git release proposal exists in REPOSITORY_REPRODUCIBILITY_20261007.md; no commit/stage/reset/rebase authorization. Dirty release reproducibility remains a final milestone blocker.

The real-provider runtime is isolated: roamsync-acceptance-pg (PG17/tmpfs), roamsync-acceptance-api:8001, roamsync-acceptance-worker; actual production image/environment credentials inherited without printing/persisting keys. Current app mounted read-only. Separate Vite3001 proxies only to isolated8001; production8000 and user data preserved. No seed/reset of existing trips. Test fixture begins with an empty isolated DB and creates its own synthetic itinerary through normal user-facing controls.

## Fresh frontend gates

MEASURED: Web20 files/123 tests passed, TypeScript typecheck passed, production build passed (stdout observed); existing act warnings recorded as warnings, not failures. These gates alone do not prove real conversation or lifecycle. Browser acceptance uses real API/providers/model and no request mocks; screenshots/response metadata checkpoint after each turn, durable Run polling, failures retained. A wait timeout must not restart a still-live Run.

## Explicit requirement audit

|Requirement|Current evidence/gate|Status|
|---|---|---|
|1 Exploration natural|Actual UI hello/solo exploration then Nanjing; inspect user-visible answer and routing|IN PROGRESS|
|2 Knowledge trustworthy|Explicit reliable-source question; inspect evidence/limitations/claims, no guessed supplied facts|PENDING|
|3 Dynamic facts verifiable|Actual next-day forecast and supported Oct7 official opening; inspect ResolvedFact/evidence|PENDING|
|4 Explicit Planning handoff|Create-preview UI, actual PlanningBrief/prefs, no Trip before confirmation|PENDING|
|5 Candidate/Validator stable|Real model/POI/route research, pending Revision valid; formal activities unchanged|PENDING|
|6 accept/reject stable|Explicit synthetic-fixture UI decisions; verify persisted status and no mutation on rejection|PENDING|
|7 itinerary version correct|Compare formal rows before/after accepted revision and stale/idempotent behavior|PENDING|
|8 Execution correct|Real execution-start/activity controls and persisted read model|PENDING|
|9 Experience affects time|Extend stay30, inspect events/projection/downstream impact|PENDING|
|10 Disruption detected|Schema-valid replayed observation input through actual ingestion/detector; not real device GPS|PENDING|
|11 Recovery generated|Real persisted disruption/experience→worker/model→validated pending Recovery|PENDING|
|12 Recovery accept correct|Explicit fixture approval; version/activities/protected execution consistent|PENDING|
|13 Explanation honest|Distinguish original recorded rationale/current explanation/unverified inference; Ledger remains OPEN unless actual proof|PENDING|
|14 Real user E2E|Complete API+browser chain, model/provider trace, source-bound snapshots|PENDING|
|15 Deployment reproducible|Approved Git ref clean-checkout build/binding required; proposal exists only|UNPROVEN / APPROVAL LATER|
|16 Rehearsal passes|Actual user-visible flow and repeated stable final-code rehearsal, not just HTTP200|PENDING|
|17 Limits explicit|Date-specific opening only, finite Knowledge, source restrictions, model failures, fake-GPS distinction|DOCUMENTED / update with results|

## Safety constraints

No automatic formal user-trip mutation. Only isolated synthetic fixture decisions are scripted as explicit user actions. Candidate approvals still pass existing Validator/transaction/version controls. Navigation observations are labeled acceptance inputs, not evidence of actual travel/device GPS. No relaxing constraints or fabricating mock candidates to pass gates. No new Agent, Memory or Fact type.

## Evidence

backend/evals/results/demo_acceptance_20261007 contains production formal baseline, safe runtime configuration, browser conversation.json and screenshots as they become available. Candidate-only success will not be presented as full Demo acceptance. Current live browser/test handle is tracked through actual process status; inspect its Run before any resend.


## Real lifecycle defects and bounded corrections

MEASURED: initial real Planner produced a validated9-activity/3-day candidate
without formal activities. Two real UI defects were exposed: mounting the newly
created Trip hid its existing session Run; and a day2 adjustment interpreted
retained dates/budget/party/preferences as protected Activity names. Run restore
now reads only the session-associated same-trip Run. Intent metadata correction
passed117 focused tests; Web component25 passed.

A resumed real Run then produced and explicitly applied a lighter day2 candidate
(3 activities/300minutes ->2/270, version1->2). Deeper inspection CONTRADICTED
full itinerary acceptance: days1/3 disappeared because only empty formal days
were supplied. attempt4_incomplete_trip preserves this failed product result;
the initial narrow browser assertion is not a complete success claim.

Bounded initial-candidate edit support now binds the session's exact pending
Revision/hash/version as draft-only context, preserves outside-target dates
exactly, excludes their places from target choices, validates preserved records
and reloads source eligibility at approval. No public schema/DB migration or
formal-history authority expansion. Candidate edit/planner/graph/run/assistant
focused75 passed,0failed/error/skipped, candidate_edit_focused_final.xml.
New browser assertions require unchanged outside-date snapshots and nonempty
formal days. Full milestone regression and live acceptance remain pending.

The next real conversation preserved earlier isolated fixtures. The router
honestly asked whether to create another identical Trip; this is a confirmed
clarification, not a provider failure or an automatically restarted Run. The
fixture now answers through the normal UI to create a new independent Trip;
earlier production/isolated records are not reset. API startup was also observed
before readiness once; JSON-read failures are harness timing history.


## Recovery reality / latest checkpoint

MEASURED: corrected initial-candidate UI chain passed: day2 4activities/360min
->2/270; other dates exactly preserved; all3 formal days nonempty; version1->2.
Actual experience UI started/arrived/played and extended30; projected end moved
exactly30. Execution deliberately started the future-dated synthetic fixture
early; actual clock was not forged. Time impact was persisted; this is not proof
of a real physical trip or30min making the schedule infeasible.

One simulated20min arrival-delay observation followed by3 severe observations
produced a real itinerary_infeasible event (delay253min/slack-104) and real
Recovery. First Recovery failed route_set_mismatch: enrichment omitted the
implicitly retained planned navigation target while Validator protected it.
Fixed shared execution protection in route enrichment/graph/save paths; focused39
passed. Real explicit retry then generated valid Recovery and UI acceptance
advanced2->3, resolved disruption, retained protected business fields. Browser
assertion found only bookkeeping updated_at changed on the completed Activity;
compare status/version/place/schedule/duration/cost/source exactly while allowing
that timestamp to change. This partial chain is retained in pre_final_rehearsal.

STRONGER AUDIT FAILED cost summary: stored planned_total21000 versus formal
activity costs24000fen; navigation target3000fen was implicitly retained but
omitted from summary arithmetic. Summary now includes execution/user protected
retention, tested through actual isolated navigation context. Recovery focused40
passed; Web125/typecheck/build passed earlier current frontend runtime. A new
complete final-code conversation/candidate/lifecycle rehearsal is live; final
Execution cost equality is a required assertion. No production deployment yet.
