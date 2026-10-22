# Agent intelligence audit B — 2026-10-22

Scope: read-only audit of canonical source first, then independent branch from
`f116ada6d6d46db7aeb48c29c8d5b45da379be00`. No production writes/deploy/merge.
Evidence labels: VERIFIED = inspected behavior/contract; MEASURED = stored run;
INFERRED = impact deduced from code, not measured population reliability.

## Actual flow

AssistantService → scoped server session restoration → literal condition capture
→ one semantic CapabilityDecision → provenance/authorization checks → direct
Companion OR POI Research OR web excerpts OR route OR fact resolution OR itinerary
read. Multiple read groups run concurrently, then their finished prose is joined.
Companion still projects suggestions and independently derives InformationNeed;
forecast/opening-hours resolvers own typed current facts. Research generates
paragraphs with snippet references, followed by identity/numeric/limited lexical
validation. Optional images enrich an already successful answer.

Planning branches go back through AssistantService and, except for a bounded
existing-arrangement modification, AssistantRouter. Brief/grounding, existing
Planning Graph/Worker, Validator and version-bound Accept own formal changes.
SavedIntention is a separate explicit-decision write and is also measured.
Having a validated top-level intent does not eliminate downstream interpretation.

## Ten most serious quality issues at base

1. **P1 / new root cause VERIFIED:** Research normal generation receives only
   last-eight recent_users, not server effective conditions
   (`assistant_research.py:395`). Fallback alone reads memory at :470.
   Long conversations can lose diet/budget or use old corrections in successful
   prose. Older reports described poor personalization but not this broken
   state handoff. Do not call this a newly discovered symptom.
2. **P1 / new VERIFIED:** city clear removes a memory slot at
   `assistant_memory.py:153`, but :160 updates browsing_city only for truthy city;
   cleanup at :162 also requires a nonempty replacement. Old focused place,
   Trip and route context survive withdrawal. Date "先不定" is rejected by the
   clear guard. Live pre-run preserves old departure despite a reassuring reply.
3. **P1 / new structural finding VERIFIED:** read_groups consumes POI together
   with route (`assistant_capabilities.py:336`); a second independent attraction
   read has no separate argument set. component_question uses keyword fragments;
   aggregation at :416 concatenates answers. Tool union is not complete task
   decomposition or a weather/effort/route-informed recommendation. Impact on
   arbitrary compound questions remains INFERRED until independent holdout.
4. **P1 / old, narrowed but open VERIFIED:** semantic creation returns to another
   model at `assistant_service.py:697`; only selected modification paths bypass
   it. Rewrites at :786 can still change original scope. Prior P1 solved the
   bounded current-Trip case, not all planning handoffs.
5. **P1 / old quality gap, newly isolated arithmetic cause VERIFIED:** Research
   renders provider costs but has no typed comparison with the user's budget.
   `assistant_research.py:150,315`; fallback :470 is generic. Unknown expense
   cannot be treated as cheap; total/daily/per-meal units cannot be interchanged.
6. **P1 / new scope defects VERIFIED:** MemoryUpdate supports only personal and
   destination (`assistant_memory.py:16`). city-switch expires only requirements,
   leaving destination-scoped preferences/scalars. New-trip reset wipes all
   personal conditions. Trip party/budget and stable diet have no distinct scope.
   This is session-local memory, not permission for permanent profile storage.
7. **P1 / old known limit VERIFIED:** source/snippet identity plus number checks
   (`assistant_research.py:401–455`) do not entail each nonnumeric claim. A
   paragraph can cite a real POI while inventing atmosphere or suitability.
   More keyword filters cannot supply absent review/menu/on-site-walking evidence.
8. **P2 / new binding finding VERIFIED:** `assistant_practical.py:39,54` selects
   the last historical route without requiring that the current effort question
   concerns those endpoints. Old provider reads are not fresh measurements and
   cannot prove internal walking, accessibility or today's trip conditions.
9. **P2 / old known gap VERIFIED:** web_answer selects exact excerpts rather than
   synthesizing a useful answer; page date is the first date-like substring near
   page start (`assistant_capabilities.py:301`). It is not authoritative publication
   metadata. Conservative caveats prevent certainty but can leave the task undone.
10. **P1 / old disclosed blocker VERIFIED:** `destination_research.py:102`
    requires web evidence before even grounding explicit requested places. Empty
    initial planning fails when search is unavailable. This was already OPEN in
    LATEST_HANDOFF; B does not rebrand it as a new discovery or relax validation.

## Chosen development scope

Two connected improvements: (1) effective conditions plus server-calculated,
unit-compatible reference-price comparisons reach Research and its fallback;
(2) scoped withdrawal and new-trip lifecycle, with provenance for unknown values
and complete place-context detachment. Keep unknown diet/actual bill/on-site
effort unknown. No new agent, vector store, permanent preference DB or planner.

Deferred high-value capabilities: multi-read task arguments and evidence-based
decision synthesis; subject/time-bound remembered evidence; source-specific
menu/accessibility/opening evidence; creation handoff preserving one intent.
Each addresses an observed user goal; none is a reason to add more agent roles.
No Web/backend API additions are needed for the chosen scope. Existing JSON
conversation_memory gains optional trip/topic scope and withdrawal metadata;
older version-1 records remain readable. Existing formal permission boundaries
and Validator/Accept are unchanged. A owns deployment/test infrastructure;
C owns Web. Shared handoff/architecture docs are amended only on B's worktree
and must be reconciled by A during integration.

## Evidence status

Protocol and fixture were frozen in commit 1c17429 before product edits.
Eight targeted source-audit probes run on base: seven fail, one passes; this is
development evidence, not holdout accuracy. Raw XML/log preserve failures.
Full live, matched-evidence, regression and untouched holdout results will be
reported separately with limitations and failed attempts intact.
