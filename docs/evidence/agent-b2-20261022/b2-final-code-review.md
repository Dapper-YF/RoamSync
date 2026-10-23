# B2 final scoped code review

Review date: 2026-10-23. Reviewer: independent operation_review sub-agent.
Baseline: 6a65ece3acc3ea9a32087c11a2cbbe05173862dc.
Final inspected HEAD: 8c6f7ed8cdeab5dced58565fbd4c288af97f987e;
latest B product boundary change identified by coordinator: 96ac7d5.

## Decision

Approve the committed B-owned boundary candidate for finite measurement. No new
actionable P0/P1 was established in this scoped review after the previously
reported authority defects were repaired. This is not release approval or a
claim of general language correctness. Overall delivery remains NO-GO.

The current uncommitted planning_graph.py compatibility change and uncommitted
AGENT_ARCHITECTURE.md change are excluded. The Graph compatibility change needs
its own review after commit. Transaction, repository, claim, checkpoint ownership
and concurrency acceptance remain A's independent responsibility.

## Inspected behavior and evidence

Read AGENTS.md, the B2 design, handoff context, and baseline-to-candidate changes
in assistant operation/capabilities/turn/service, flexible creation, condition
memory and requirement projections, planning intent snapshot/semantic handoff,
committed Graph integration, Companion information-need override and the narrow
chosen-place research path. Read relevant public development tests; no C sealed
holdout was opened or executed.

Earlier independent executable counterexamples found three P1 classes: negative
or hypothetical flexible items becoming selected, complete negative operations
receiving authority, and negated/per-person amounts becoming trip totals. A
subsequent review found positive verbs authorizing a different negated target.
Those findings were reported before repair, and their repaired cases were
independently re-executed during this review sequence.

Final offline execution against the inspected working tree used
E:/Study/RoamSync/backend/.venv/Scripts/python.exe and actual production helpers:

| Input / proposed target | Observed result |
| --- | --- |
| 去甲馆但乙馆别加入 / selected 乙馆 | rejected |
| 甲馆选A入口但乙馆先别选 / selected 乙馆 | rejected |
| 加入甲馆，不要加入乙馆 / add_activity 乙馆 | rejected |
| 加入甲馆但别加入乙馆 / add_activity 乙馆 | rejected |
| 去乙馆 | selected, date unknown |
| 乙馆备选 | optional, date unknown |
| 南京博物院确定去但时间未定 | selected, date unknown |
| 玄武湖有时间再去 | optional, date unknown |
| 第二天加入乙馆 | approved add_activity |
| 宽窄巷子晚半小时 | approved reorder_activities |
| 玄武湖有时间再加入 / formal add_activity | rejected |

The optional bridge is opt-in only from flexible choice preparation; the formal
operation helper retains allow_optional=False. It therefore restores the legacy
loose-choice wording without promoting that tested tentative wording into a
formal add operation. Earlier execution also verified negative creation clauses
become direct decisions, negative/per-person totals stay unset, and affirmative
whole-trip totals remain accepted.

Static inspection confirms the intended handoff: semantic metadata supplies the
tool decision without a second router; prepared drafts preserve the original
request; restoration checks persisted request/trip/version binding and invalid
prepared markers fail closed; supplied drafts suppress another semantic provider
selection. Clarification answers fill a missing day without replacing original
operation evidence in the committed B2 path. Read components retain separate
arguments/results and aggregate web sources with component-specific identifiers.
Conditions preserve original evidence and reject unverifiable scalar equivalence;
continuous/internal walking requirements remain distinct from route walking caps.

## Limits and known blockers

- Source and branch inspection plus deterministic helper execution are narrower
  than real-provider behavioral measurement. This reviewer made no network or DB
  calls and did not rerun the full test suites or browser lifecycle.
- The coordinator reports green overlapping helper, chosen-place and real-PG
  claim-to-new-Graph checks. Those are coordinator evidence, not independently
  rerun here, and their counts must not be summed or treated as quality metrics.
- The known public workflow still fails to produce a revision when strict chosen
  map identity cannot reconcile source shorthand names/addresses. This is a
  conservative bridge with a real usability cost; this review does not recommend
  loosening identity evidence to make that same question pass.
- The coordinator also identifies a known unsupported 15-minute assurance in
  live public behavior. That remains a release/quality blocker; finite code
  review approval does not clear it.
- Literal authority and entity/action binding intentionally clarify unrecognized
  coordinated wording. The tested repairs do not certify all negation, quotation,
  correction, scope, or natural-language formulations.
- Creation still requires confirmation and planning still requires the existing
  Validator/Accept boundaries. This review does not authorize production writes,
  deployment, owner rollout, or sealed-holdout access before the agreed freeze.

Only this review document was written by this reviewer. No product sources,
existing tests, Obsidian files, or production data were modified.

## Scoped Graph upgrade addendum — 523bbd7

Reviewed commit 523bbd7c9ed30577043c9319d2d795cc6ad3c916 exclusively for the
previously excluded legacy clarification compatibility change. Approve this
scoped change for the finite candidate: no actionable P0/P1 established.

Inspected planning_graph.py's migration helper and call site, the new public
legacy-checkpoint tests, the existing resolver/restoration contracts it calls,
and legacy-clarification-green.xml. The XML records 20 passing checks, including
18 legacy cases and two existing Graph clarification cases. This reviewer read
that evidence; these DB tests were not independently rerun during this addendum.

Authorization remains the persisted original request. Expanded checkpoint text
must match the exact old server append format, bounded count and nonempty trimmed
supplements. Old expanded operations are not carried forward. A present prepared
marker is reconstructed solely for validation and checked against current trip
and preference versions; invalid markers cannot fall back to the rule parser.
Without a marker, only the original request enters deterministic resolution,
with no semantic provider. Legacy supplements and the current answer reach the
existing missing-day clarification channel, not operation/entity extraction.
The committed Graph suppresses a later semantic-provider reinterpretation after
migration as well.

The migration runs after the current claim check and locked run refresh. Its
snapshot loading, preference lookup and provider-free resolver are SQL/pure work;
there is no external network call added inside that transaction. Resolution and
answer history are committed together. Existing stored answers must match the
legacy history, the fully merged history, or a current-answer-only receipt bound
to the original request and current checkpoint thread. Replaying after SQL commit
but before checkpoint persistence recognizes the merged list instead of appending
again. The test source explicitly exercises that crash boundary and confirms the
original draft/request and receipt remain unchanged.

Malformed or unbound legacy state raises LegacyClarificationRestartRequired.
A's recoverable HTTP 409 handling is outside this B commit and is not approved
by this addendum. This inspection does not independently certify A's claim or
checkpoint runtime. It clears the earlier Graph-code review exclusion only for
523bbd7; other dirty changes remain outside scope. Known public behavior blockers
and the overall NO-GO above remain unchanged. No network, DB, product-source or
test mutation was performed by this reviewer.

## Scoped recoverable runtime addendum — fc2aa5d

Reviewed the exact five-file change fc2aa5d17e141a83140bcb51d5c87c3d820c8705
(A source 85d0bd5915a7d7168bf606b7f520fbae0ad6f237), plus the existing claim,
release and progress helpers necessary to assess its concurrency behavior.
Approve this exact recovery fix for the finite candidate. No actionable P0/P1
established in the scoped inspection; this does not approve the entire A branch.

The typed legacy exception is caught before generic Graph failure handling, so
that path restores the pending clarification instead of calling _mark_failed.
Recovery refuses to run without an active claim. With one, assert_planning_claim
locks Trip then Run and checks token, expiry and status before any restoration.
The fresh session reads the same locked run and verifies the last receipt's
original request and checkpoint thread. Only status, reconstructed pending
questions and the restart-required flag change; answers, receipts, original
request and checkpoint identity are preserved. Restoration commits before the
typed exception reaches main.py's structured HTTP 409 mapping.

The restart-required flag is checked inside the locked clarification claim path
before answer/receipt append or ownership transition. Thus ordinary repeated API
submissions return the restart conflict without appending again. Existing outer
cleanup releases only a matching run/token; after successful restoration it clears
that owner's lease, and after a takeover it cannot clear the replacement owner's
lease. The heartbeat treats the restored awaiting_clarification state as a normal
interrupt and cannot move it back to researching. No added network call occurs
within the restoration transaction.

Evidence limits: inspected the new API test asserting repeated 409, restored
interrupt, retained original/answer and cleared owner lease. It replaces Graph
invocation with the typed exception and is not by itself a legacy-checkpoint
integration test. The earlier Graph addendum covers the migration side; current
fixed-source integration execution remains coordinator evidence, not independently
rerun here. No DB/network calls or source/test edits were made by this reviewer.
Missing/mismatched receipt or expired/lost claim deliberately aborts restoration
with LostPlanningClaim instead of overwriting state; no promise is made to restore
an obsolete owner's interrupt. Database outages, process termination during
recovery, and full worker concurrency behavior remain outside this exact-change
approval. Overall release NO-GO and known public behavior blockers remain.
