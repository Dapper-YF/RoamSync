# Companion Phase 2.5 evaluation protocol v2

Date: 2026-09-30. Product policy: ordinary stable conversation may use model general knowledge, explicitly unverified. Source requirements are opt-in. Destination/duration alone never grants mutation authority.

| Case mode | Expected runtime | Mutation | Knowledge required | Planning allowed | Answer mode | Evidence behavior |
| --- | --- | --- | --- | --- | --- | --- |
| general_conversation | companion | false | false | false | general knowledge | no invented source/verification claim; metadata unverified |
| source_grounded_knowledge | companion | false | true, except live/original-rationale override | false | factual or mixed | registered reviewed assertions, exact scope/attribution; show material gaps |
| recommendation | companion | false | only explicit source requirement | false | advisory or mixed | advice stays separate from source facts; citations do not prove a recommendation |
| live_fact_required | companion | false | false | false | limitation | no Travel Facts; no hours/weather/prices/current flower condition from memory |
| decision_explanation | companion | false | false | false | saved rationale or limitation | only persisted original rationale, never current RAG/model reconstruction |
| explicit_planning | planning | true | false | true | PlanningBrief/Planning | explicit user request; suggestions are not formal activities |
| exploration_non_planning | companion | false | false | false | general knowledge | concerns/preferences/possible destinations/durations remain exploration |

Authorized clarification is separately tested: runtime planning, mutation_requested false, planning allowed through a previous explicit planning turn; a field value cannot originate authority. Cancelled/failed/rejected contexts cannot continue it. The routing field knowledge_required is a coarse goal hint; actual tool need is InformationNeed. Evaluate actual calls against case protocol, not that hint.

Current closeout supplements include unit forms without currency units (800左右), time-of-day (下午吧), holiday departure dates (国庆第二天出发), unprefixed ordinal selection (第二个), explicit 放进 mutations and the exact long-form natural exploration sequence requested in the follow-up. Per-case protocol_version is phase25-v2. These do not change the authorized clarification lifecycle or original holdout labels. The earlier completed closeout is archived in prior_closeout; its metrics must not be attributed to the new source manifest. Final production smoke now has eight turns, separately testing general knowledge, source knowledge and live limitation.

Every case stores its goal, runtime, mutation flag, knowledge requirement, planning permission, answer mode and evidence expectation in the machine artifacts. The final live batch has reviewer-assigned expectations in final/manual_review.json (single Codex reviewer, not independent human annotation). The original holdout has no independent goal taxonomy labels; its reported routing score is runtime only, never an independently labelled goal score.

## Original holdout and protocol migration

Keep backend/evals/results/companion_phase25/holdout_v1.json byte-identical. It contains 50 pre-existing cases and pending fields. Those fields remain an immutable fixture, not the current review status. All 50 reviews are completed in the separate versioned holdout_review_live.json/manual_review.json artifacts.

v1 assumed stable knowledge questions require RAG. v2 retains original labels and records original controlled execution as a routing/need diagnostic. Source-mode replay appends an explicit source request only for originally knowledge-required cases. This transformation is recorded per case; it is not the original wording and is not a new blind holdout. After unsealing, results informed scoped bug fixes; all subsequent results are regression evidence, not untouched blind performance. No expected assertion IDs or expected answers were changed.

Exact assertion-ID coverage is reported as a fixture metric. Equivalent paraphrases with different IDs can be semantically useful but do not retroactively pass this metric. Need matching includes the old expected factual/advisory/mixed label; disagreements remain visible. Tool precision/recall use the case-specific requirement, and are not population estimates.

## Review rules

Review claims against the actual provided assertion text, scope and canonical source metadata, rather than merely accepting a valid citation. Source assertion matching is a bounded registry check, not a general semantic entailment engine or a fresh independent audit of the source websites.

Labels: supported, partially_supported, unsupported, not_applicable, recommendation_not_fact. Recommendations may contain implicit unverified factual assumptions; manually inspect these and record limitations. General model answers are unverified and outside verified-source claim accuracy; never include them as supported source claims.

Review routing, authorization, need, retrieval relevance, sufficiency, factual support, applicability, attribution, unsupported statements, recommendation separation and usefulness. Report substantive coverage separately from honest refusals/limitations. No-results and safe refusals do not earn complete answer coverage. Every final artifact binds the same SHA256 file manifest. Pre-final/interrupted/failed batches remain historical evidence and are excluded from final-snapshot scores while their failures remain disclosed.

## Reproduction

Use the existing isolated PostgreSQL, a mounted current backend, and the existing test image for focused tests. Do not create a new database per fix. Final commands:

- python -m evals.phase25_final snapshot
- python -m evals.phase25_final live (current configured real provider; no fake fallback)
- python -m evals.phase25_final holdout-live (actual provider for mixed/advisory source replies; factual/live/rationale branches remain deterministic)
- alembic upgrade head; pytest --junitxml=evals/results/companion_phase25/final/backend_final.xml (Linux/PostgreSQL)
- Rebuild production API and affected worker from accepted source; verify runtime-file hashes against source_snapshot.json; run scripts/phase25_release_smoke.py inside production API.

The real standalone model evaluation has no mutation port or database. PostgreSQL focused/full integration proves actual PlanningRun counts, persistence and unchanged formal state. Production smoke uses an isolated synthetic session, never Demo reset, and never confirms a candidate or trip creation.
