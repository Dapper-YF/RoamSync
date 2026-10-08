# RoamSync — Knowledge Coverage & Frozen Independent Evaluation

Date: 2026-09-30. CURRENT SLICE: **COMPLETE as a bounded engineering/evaluation slice**, with explicit remaining coverage and generation failures. This is not a claim of independent human validation or perfect knowledge reliability. No more Knowledge expansion in this slice.

## 1. Starting Baseline
Accepted Phase 2.5 remains complete. main HEAD `5572849209c943c5f5ad1579db4cef0ba2fb5b25` unchanged; extensive pre-existing dirty work preserved, no commit/reset. Prior production snapshot `9c73bb878924d5f6d59e4e6f13f35e945cfe41ac3fcca1540dee3b0351849887` stays historical production evidence. Untouched baseline for this evaluation: `84518db9100bfb16d3ce954ea47fc29fcb5b82c2d0ca8f81ade2387e66dd0ab9`. Baseline includes the new runner before application/corpus changes; manifest's application/corpus hashes exactly match baseline. No production deployment of this slice.

## 2. Frozen Evaluation Method
Protocol `knowledge-coverage-v1`; fixture freeze `2026-09-30T06:37:47.761923+00:00`. 60 new cases, zero exact duplicate texts against old tests/Phase 2.5 holdout. Known gaps informed category design: expression novelty does not imply externally independent dataset design. Baseline unsealed before development. Final is **frozen-label regression**, not a blind generalization estimate. One Codex reviewer, no independent human annotation or new website audit. Outputs frozen `2026-09-30T06:54:34.342416+00:00` before final manual assessment. No application/corpus/fixture changes afterwards. Protocol: `docs/agent/KNOWLEDGE_COVERAGE_FROZEN_PROTOCOL_20260930.md`.

## 3. Dataset Composition
60 cases: profile 8, history 10, culture 10, recommendation 8, attribution/applicability traps 10, stable/live mixed 10, general conversation 4. Includes landscape, formation/artificial versus geology, heritage timeline, culture/tea, senior continuous duration versus riding/rest time, suggestion versus assertion, missing detail, attribution and live boundaries. 24 real-provider case IDs selected before baseline; no selection by final success.

## 4. Frozen Labels
Fixture SHA256 `f19b8c0b9b823a070d3295918bca2357bb5f4529f456f482f8fcdc9c27d3c5c1`; labels changed after freeze **0**. Cases include runtime, mutation, need/topics/mode, allowed/forbidden types, assertion IDs, predeclared landscape equivalence, sufficiency and scope notes. Original metrics retained. Disputes: `history_09` foundation-day question labelled historical_figures; `recommend_06` negated itinerary language requires careful interpretation. No relabelling to raise score. Freeze/label status in `freeze_manifest.json` and `failure_taxonomy.json`.

## 5. Baseline Results
60/60 runtime and authority, errors 0. Need 11/60; type 28/60; assertion coverage 13/44. Retrieval proxy: relevant 13, related but detail unanswerable 8, irrelevant/insufficient 17, missing 18, not applicable 4. Stable/live coverage 0/10. 57 registered source claims supported against exact curated wording/type/scope. Utility proxy: substantive 18, partial 3, missed 31, honest limitation 2, advice/unverified 2, general unmeasured 4; over-refusal proxy 23. These proxies are not independent human usefulness/refusal ratings.

## 6. Failure Taxonomy
Pre-edit taxonomy has all eleven required categories and per-case observed need/available IDs: need classification, retrieval ranking, missing corpus, metadata filter, assertion granularity, applicability, attribution, mixed handling, recommendation leakage, generation, evaluation label. Classification/filter failures dominate supported-detail misses. Some requested detail never exists in corpus; an unrelated retrieved paragraph cannot fill that gap. Ranking failures are possible but not isolated experimentally; no claim that ranking has been fixed. New artifacts separate these layers from a blanket “RAG not found.”

## 7. Changes Made
Four application/corpus files changed from baseline, plus seven new behavioral tests. No new service/agent/port, persistence, Planning authority, Router, Identity, Runtime, Brief, contract or adapter redesign. Changes are limited to existing need semantics, graph stable/live handling, source advice prompt and one existing assertion topic.

## 8. InformationNeed Changes
Added subject families for landscape components, artificial intervention, heritage timeline, tea objects, senior duration and source metadata. Artificial intervention alone no longer implies geological origin. Source negation and negated recommendation handling improved; live flower language remains a live boundary. Source phrases still incomplete; broad original-decision heuristic remains problematic. Need strict result is only 34/60, so this is a partial semantic improvement rather than comprehensive language understanding.

## 9. Corpus Changes
Seven existing reviewed documents retained. **Zero new sources, zero large corpus expansion.** Added only `senior_continuous_visit_time` topic on the existing senior continuous-visit assertion. JSON serialization reformatted; this is not new source content. No embedding/vector DB update.

## 10. Assertion Changes
Zero new assertions; existing text/type/scope/source retained. Continuous visit duration guidance is not proof of riding/walking/rest intervals or a mandatory rule for every senior. Frozen-ID coverage improves 13/44 to 35/44; equivalence groups were declared before development. Coverage counts cases, not every fact in an answer.

## 11. Retrieval Changes
No ranking or adapter-boundary changes. Mixed stable/live queries project the recognised stable topic into the existing tool, preserving live refusal at the adapter. Current evidence: relevant proxy 35/60; related but detail unanswerable 9, irrelevant/insufficient 7, missing 5, not applicable 4. “Relevant” is an assertion-coverage proxy, not an independently annotated semantic relevance score. A recall miss and absent assertion remain separate failure causes.

## 12. Recommendation Safety
Source prompt permits generic creative suggestions but prohibits unsupported named routes/date/time as verified source advice. Real `recommend_07` states no supported exact Sudi/Baidi segment and uses generic堤道 advice. Senior/all-Hangzhou traps retain scope. Remaining `recommend_04` missed source intent and returned unsupported quantities; prompt protection cannot help if source mode was never selected. `recommend_05` location names supported, convenience/quiet judgments unverified. Do not treat all recommendation sentences as source facts.

## 13. Mixed-question Handling
Stable knowledge retrieval and live gap can coexist. Model is not called to invent mixed live data; server renders registered stable facts and natural live limitation. Coverage 0/10 to 7/10. Pure live stays limited. Literary-influence wording in `mixed_01` remains missed. No verified forecast/Travel Facts consumed.

## 14. Final Frozen Results
Final source SHA256 `897a784a97d31cdf0ecd5fd97ee9e11f97ff72244ba424e96e347e5208e52f77`. 60 cases, errors 0; runtime/authority 60/60; need 34/60, types 48/60; assertions 35/44; mixed 7/10; natural prose checks 60/60. Registered source claims 85/85 supported against registry. This **does not mean zero unsupported facts in all generated prose**. Machine utility: substantive 30, partial 14, missed 9, honest limitation 2, advice/unverified 1, general unmeasured 4; over-refusal proxy 8. Raw outputs unchanged after freeze.

## 15. Baseline vs Final
| Measure | Baseline | Final |
|---|---:|---:|
| Runtime / authority | 60/60 | 60/60 |
| Need strict | 11/60 | 34/60 |
| Allowed / forbidden type check | 28/60 | 48/60 |
| Supported detail case coverage | 13/44 | 35/44 |
| Retrieval relevant proxy | 13 | 35 |
| Stable/live coverage | 0/10 | 7/10 |
| Over-refusal proxy | 23 | 8 |

For usefulness, use supported-detail coverage **13/44 → 35/44** as the controlled source-answer outcome. Neutral provider does not measure model creativity. Machine “substantive” can count unrelated facts on insufficient-evidence cases; raw utility buckets are retained for reproducibility, not promoted as manual usefulness. Missing assertions and no facts drive refusal proxy, which is not pure behavioral refusal. Protocol intent and this raw scorer limitation are explicitly distinguished.

## 16. Real Model Evaluation
Preselected 24 cases, glm / glm-5.3-flash; **9 actual model generations**, 0 runtime errors, 0 format repairs. Other paths are deterministic server rendering/limits, not hidden model calls. Tokens: prompt 14926, completion 3332, total 18258. End-to-end per-case latency median 0.069s, max 14.366s, sequential total 87.977s; includes deterministic cases, not a provider benchmark.

Runtime/authority 24/24, strict need 14/24, type 19/24, assertion coverage 13/18, mixed 1/2, prose checks 24/24. All 35 structured source facts match registry/scope. Single-reviewer prose outcomes: {"useful": 10, "missed": 4, "honest_limitation": 1, "unsupported_fallback": 2, "partial": 6, "unverified_general": 1}. Counts are mutually exclusive primary outcomes, not exhaustive statement grading.

At least **six reviewed prose units lack supplied evidence**: four in `recommend_04` (ride 1.5–2h; walk 1–1.5h; rest 10–20min; standard/provenance characterization), two historical detail/sourcing suggestions in `history_09`. These are unverified/unsupported relative to supplied evidence, not independently proven false. General comparison is intentionally unverified and not fact-graded. `recommend_01` misses requested advice; `trap_07` gives canonical title but omits requested URL in visible prose. Exact source support is not a general entailment/factuality verifier. Detailed outputs/calls/evidence/claims/observations are in `real_results.json`, review in `manual_review.json`.

## 17. Files Changed
Since baseline: `backend/app/companion_information.py`, `companion_graph.py`, `companion_provider.py`, `knowledge_corpus/hangzhou_reviewed_v1.json`, `backend/tests/test_knowledge_coverage.py`. New workflow: `backend/evals/knowledge_coverage.py`, `scripts/freeze_knowledge_eval.py`, `scripts/close_knowledge_coverage.py`, frozen protocol/report and `backend/evals/results/knowledge_coverage/*`; handoff/state documents updated. Git status includes extensive prior dirty work and is not a list of this slice's edits. Snapshot comparison verifies protected backend unchanged. Web/Android not edited/tested in this slice. Previous Phase 2.5 evidence remains separate.

## 18. Focused Tests
**139 passed**, 0 errors/failures/skips. Current app/tests/evals mounted into existing Linux api-test image, PostgreSQL test service reused. Modules: knowledge coverage, Companion knowledge/runtime, Phase 2.5 final, travel-goal routing. Seven new tests use non-fixture wordings, assert mixed stable knowledge plus natural live limitation without model generation, pure-live boundary and existing duration assertion. `focused.xml` / `focused.log` preserve evidence.

## 19. Full Regression
**657 passed**, 0 failures, 2 pre-existing FastAPI/Starlette 422 deprecation warnings, 65.42s. Linux/Python 3.11/PostgreSQL 17; `alembic upgrade head` then full pytest, current app/tests/evals mounted, migrations/dependency runtime unchanged. One full final run. `backend_final.xml` / `backend_final.log`; `verification.json` binds tests, fixture, frozen output and source hashes. No production rebuild/smoke for this slice: production remains Phase 2.5 code and is not falsely described as current working tree.

## 20. Remaining Gaps
Natural geology/artificial split and epoch recall; negated advice misrouted to original decision rationale; senior source phrase missing; unsupported fallback quantities/history; literary mixed topic; assertion granularity/source URL presentation; strict need 26/60 still incorrect. Related evidence on unsupported detail questions must not count as an answered detail. No fixes after output freeze. These are recorded known failures, not blockers concealed by aggregate score.

## 21. Generalization Risks
Lexical semantic families still risk narrow vocabulary fit, false positives from negation and polysemy, and new-city gaps. Dataset crafted by same agent, informed by known gaps; baseline-driven modifications reduce blindness. Category breadth and pre-freeze labels limit label chasing but do not establish unseen-user performance. Real 24/9 generations is small and model-dependent. Registered support check does not reread original sites or verify every inference. Equivalence and weak utility/relevance proxies require disclosed interpretation.

## 22. Deferred Issues
No corpus expansion, ranking redesign, broad heuristic rewrite, new evaluation relabelling, architectural rework, Decision Ledger closure, Demo rehearsal or production deployment. General knowledge stays unverified. No Travel Facts/Weather implementation, forecast API, new identity/Brief/ToolPort or approval lifecycle changes. Preserve completed Phase 2.5 and existing production evidence.

## 23. Recommended Next Slice
**Travel Facts Integration v1 / verified forecast**: allow Companion to consume verified live facts through existing boundaries, with provenance/freshness/failure fallback and stable/live separation. This is a recommendation only; no implementation here. Stop further Knowledge expansion now.

# CHATGPT HANDOFF SUMMARY

CURRENT SLICE: Knowledge Coverage & Frozen Independent Eval COMPLETE (bounded work; single-reviewer frozen regression, not independent human validation).

FROZEN EVAL: cases 60; protocol knowledge-coverage-v1; hash `f19b8c0b9b823a070d3295918bca2357bb5f4529f456f482f8fcdc9c27d3c5c1`; labels changed after freeze 0.

BASELINE: need 11/60; retrieval relevant proxy 13/60; assertions 13/44; usefulness supported detail coverage 13/44 (neutral provider).

FINAL: need 34/60; retrieval relevant proxy 35/60; assertions 35/44; usefulness supported detail coverage 35/44; mixed 7/10.

CORPUS CHANGES: 0 sources / 0 assertions; one existing senior-duration topic.

INFORMATION NEED CHANGES: subject families, artificial/geology separation, source/negation wording, stable/live handling.

REAL MODEL: 24 preselected cases / 9 actual generations / 0 errors / 0 repairs; 35 registered source facts supported; at least 6 unsupported supplied-evidence prose units remain.

BACKEND: focused 139; full 657 passed / 2 existing warnings; no deployment.

KNOWN LIMITATIONS: strict need only 34/60; source fallback, historical detail, negation and mixed literary gaps; label disputes unchanged; single reviewer; proxy metrics not universal factuality/usefulness.

DO NOT REDO: Phase 2.5, Router/Runtime/Identity/Brief/Adapter/Planning approval architecture; preserve dirty work and old evidence.

NEXT RECOMMENDED SLICE: Travel Facts Integration v1 / verified forecast. Not implemented.
