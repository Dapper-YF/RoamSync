"""Post-freeze reporting only; never modifies application, labels or raw outputs."""
import json, hashlib, statistics
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'backend/evals/results/knowledge_coverage'
def read(name): return json.loads((OUT/name).read_text(encoding='utf-8'))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name, obj): (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
b, f, r = [read(x+'_results.json') for x in ('baseline','final','real')]
freeze, manifest, fixture = [read(x+'.json') for x in ('output_freeze','freeze_manifest','frozen_v1')]
assert all(digest(OUT/name)==sha for name,sha in freeze['outputs'].items())
assert digest(OUT/'frozen_v1.json')==freeze['fixture_sha256']
assert all(digest(ROOT/'backend'/name)==sha for name,sha in f['snapshot']['files'].items())
assert all(b['snapshot']['files'][name]==sha for name,sha in manifest['pre_development_hashes'].items())
changed = [name for name,sha in f['snapshot']['files'].items() if b['snapshot']['files'].get(name)!=sha]
assert set(changed)=={'app/companion_information.py','app/companion_graph.py','app/companion_provider.py','app/knowledge_corpus/hangzhou_reviewed_v1.json','tests/test_knowledge_coverage.py'}
manual = {
 'profile_01': ('useful','Landscape components answered within registered scope.'),
 'history_01': ('useful','Artificial intervention facts answered.'),
 'history_02': ('missed','Natural geology/artificial split still misses supported component.'),
 'history_04': ('missed','Epoch/source need and recall incomplete.'),
 'history_05': ('useful','Registered history facts answered.'),
 'history_06': ('honest_limitation','Missing requested detail is disclosed.'),
 'history_09': ('unsupported_fallback','Source wording missed. Tang/Song pavilion generalization and Bai Juyi/Qing literature suggestions lack supplied evidence; label historical_figures is also disputed, unchanged.'),
 'culture_01': ('missed','Negated recommendation plus explanation falsely takes original decision rationale path.'),
 'culture_03': ('useful','Stable culture facts within evidence.'),
 'culture_05': ('useful','Stable culture facts within evidence.'),
 'culture_07': ('useful','Stable tea facts within evidence.'),
 'recommend_01': ('partial','Source facts present but requested observation suggestion absent.'),
 'recommend_02': ('useful','Senior advice qualified; source applicability retained.'),
 'recommend_03': ('useful','Senior advice qualified; source applicability retained.'),
 'recommend_04': ('unsupported_fallback','Missed source trigger. Ride 1.5–2h, walk 1–1.5h, rest 10–20min, and national-standard/provenance characterization lack supplied support.'),
 'recommend_05': ('partial','Named tea locations supported; convenience/quiet judgments are unverified inference.'),
 'recommend_07': ('partial','No source-supported exact Sudi/Baidi segment; limitation explicit, generic advice allowed.'),
 'trap_01': ('useful','Does not certify West Lake accessible/safe for every senior.'),
 'trap_02': ('partial','No fabricated official photography endorsement; missing detail disclosed.'),
 'trap_04': ('useful','Does not extrapolate West Lake evidence into all-Hangzhou ranking.'),
 'trap_07': ('partial','Correct canonical page title; requested URL not explicitly presented in answer despite metadata.'),
 'mixed_01': ('missed','Literary influence topic missed; whole answer limits live part, stable part lost.'),
 'mixed_03': ('partial','Stable tea facts answered and current-live part explicitly unavailable.'),
 'general_01': ('unverified_general','Natural general comparison; factual correctness not audited.'),
}
review = {'reviewed_at':datetime.now(timezone.utc).isoformat(), 'reviewer':'Single Codex reviewer; no independent human or fresh external website audit', 'output_freeze':freeze, 'labels_changed':0,
 'method':'Raw machine metrics retained. All final per-case evidence/registered claim checks recorded below. Real subset prose reviewed manually; no all-output factuality percentage. Coverage proxy is not semantic relevance or model usefulness.',
 'real_manual': [{'case_id':k,'outcome':v[0],'note':v[1]} for k,v in manual.items()],
 'real_manual_counts':dict(Counter(v[0] for v in manual.values())),
 'unsupported_sample_units':{'recommend_04':4,'history_09':2},
 'unsupported_sample_note':'At least six reviewed prose units lack supplied evidence. This is not exhaustive claim segmentation or proof they are false in the world. They are excluded from structured source-fact denominator; do not report zero unsupported all-output facts.',
 'final_cases':[]}
for old,new in zip(b['cases'],f['cases']):
 assert old['case_id']==new['case_id'] and old['expected']==new['expected']
 review['final_cases'].append({'case_id':new['case_id'], 'baseline_review':old['review'], 'final_review':new['review'], 'registered_claim_checks':new['claims_review'],
 'detail_coverage_boundary':'No required assertion IDs: related evidence cannot prove detail answerability.' if not new['expected']['expected_assertion_ids'] else 'Coverage of frozen IDs/equivalence only; recommendation fulfillment assessed separately.'})
write('manual_review.json',review)
lat=[x['latency'] for x in r['cases']]
usage={k:sum(o.get('usage',{}).get(k,0) or 0 for o in r['provider_observations']) for k in ('prompt_tokens','completion_tokens','total_tokens')}
stats={'cases':24,'actual_generations':len(r['provider_observations']),'format_repairs':sum(max(0,o['format_attempt']-1) for o in r['provider_observations']), 'usage':usage,'latency_seconds':{'total':round(sum(lat),3),'median':statistics.median(lat),'max':max(lat)},'manual_outcomes':review['real_manual_counts']}
write('comparison.json',{'baseline':b['summary'],'final':f['summary'],'real':r['summary'],'real_statistics':stats,'scoring_limitations':review['method']})
tests={}
for name in ('focused','backend_final'):
 suites=ET.parse(OUT/(name+'.xml')).getroot().findall('testsuite')
 tests[name]={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}
 assert tests[name]['errors']==tests[name]['failures']==0
verification={'verified_at':datetime.now(timezone.utc).isoformat(),'fixture_sha256':freeze['fixture_sha256'],'labels_changed_after_freeze':0,'baseline_pre_development_hashes_match':True,'final_source_sha256':f['snapshot']['sha256'],'final_source_files_match':True,'frozen_output_hashes_match':True,'changed_backend_files_since_baseline':changed,'protected_files_unchanged':True,'tests':tests,'deployment':'Not performed; production remains accepted Phase 2.5 snapshot. Current working tree has new coverage changes.','head':manifest['head'],'review_artifacts':{x:digest(OUT/x) for x in ('manual_review.json','comparison.json')}}
write('verification.json',verification)
report=f'''# RoamSync — Knowledge Coverage & Frozen Independent Evaluation

Date: 2026-09-30. CURRENT SLICE: **COMPLETE as a bounded engineering/evaluation slice**, with explicit remaining coverage and generation failures. This is not a claim of independent human validation or perfect knowledge reliability. No more Knowledge expansion in this slice.

## 1. Starting Baseline
Accepted Phase 2.5 remains complete. main HEAD `{manifest['head']}` unchanged; extensive pre-existing dirty work preserved, no commit/reset. Prior production snapshot `9c73bb878924d5f6d59e4e6f13f35e945cfe41ac3fcca1540dee3b0351849887` stays historical production evidence. Untouched baseline for this evaluation: `{b['snapshot']['sha256']}`. Baseline includes the new runner before application/corpus changes; manifest's application/corpus hashes exactly match baseline. No production deployment of this slice.

## 2. Frozen Evaluation Method
Protocol `knowledge-coverage-v1`; fixture freeze `{manifest['frozen_at']}`. 60 new cases, zero exact duplicate texts against old tests/Phase 2.5 holdout. Known gaps informed category design: expression novelty does not imply externally independent dataset design. Baseline unsealed before development. Final is **frozen-label regression**, not a blind generalization estimate. One Codex reviewer, no independent human annotation or new website audit. Outputs frozen `{freeze['frozen_at']}` before final manual assessment. No application/corpus/fixture changes afterwards. Protocol: `docs/agent/KNOWLEDGE_COVERAGE_FROZEN_PROTOCOL_20260930.md`.

## 3. Dataset Composition
60 cases: profile 8, history 10, culture 10, recommendation 8, attribution/applicability traps 10, stable/live mixed 10, general conversation 4. Includes landscape, formation/artificial versus geology, heritage timeline, culture/tea, senior continuous duration versus riding/rest time, suggestion versus assertion, missing detail, attribution and live boundaries. 24 real-provider case IDs selected before baseline; no selection by final success.

## 4. Frozen Labels
Fixture SHA256 `{freeze['fixture_sha256']}`; labels changed after freeze **0**. Cases include runtime, mutation, need/topics/mode, allowed/forbidden types, assertion IDs, predeclared landscape equivalence, sufficiency and scope notes. Original metrics retained. Disputes: `history_09` foundation-day question labelled historical_figures; `recommend_06` negated itinerary language requires careful interpretation. No relabelling to raise score. Freeze/label status in `freeze_manifest.json` and `failure_taxonomy.json`.

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
Final source SHA256 `{f['snapshot']['sha256']}`. 60 cases, errors 0; runtime/authority 60/60; need 34/60, types 48/60; assertions 35/44; mixed 7/10; natural prose checks 60/60. Registered source claims 85/85 supported against registry. This **does not mean zero unsupported facts in all generated prose**. Machine utility: substantive 30, partial 14, missed 9, honest limitation 2, advice/unverified 1, general unmeasured 4; over-refusal proxy 8. Raw outputs unchanged after freeze.

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
Preselected 24 cases, glm / glm-5.3-flash; **{stats['actual_generations']} actual model generations**, 0 runtime errors, {stats['format_repairs']} format repairs. Other paths are deterministic server rendering/limits, not hidden model calls. Tokens: prompt {usage['prompt_tokens']}, completion {usage['completion_tokens']}, total {usage['total_tokens']}. End-to-end per-case latency median {stats['latency_seconds']['median']}s, max {stats['latency_seconds']['max']}s, sequential total {stats['latency_seconds']['total']}s; includes deterministic cases, not a provider benchmark.

Runtime/authority 24/24, strict need 14/24, type 19/24, assertion coverage 13/18, mixed 1/2, prose checks 24/24. All 35 structured source facts match registry/scope. Single-reviewer prose outcomes: {json.dumps(stats['manual_outcomes'],ensure_ascii=False)}. Counts are mutually exclusive primary outcomes, not exhaustive statement grading.

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

FROZEN EVAL: cases 60; protocol knowledge-coverage-v1; hash `{freeze['fixture_sha256']}`; labels changed after freeze 0.

BASELINE: need 11/60; retrieval relevant proxy 13/60; assertions 13/44; usefulness supported detail coverage 13/44 (neutral provider).

FINAL: need 34/60; retrieval relevant proxy 35/60; assertions 35/44; usefulness supported detail coverage 35/44; mixed 7/10.

CORPUS CHANGES: 0 sources / 0 assertions; one existing senior-duration topic.

INFORMATION NEED CHANGES: subject families, artificial/geology separation, source/negation wording, stable/live handling.

REAL MODEL: 24 preselected cases / 9 actual generations / 0 errors / 0 repairs; 35 registered source facts supported; at least 6 unsupported supplied-evidence prose units remain.

BACKEND: focused 139; full 657 passed / 2 existing warnings; no deployment.

KNOWN LIMITATIONS: strict need only 34/60; source fallback, historical detail, negation and mixed literary gaps; label disputes unchanged; single reviewer; proxy metrics not universal factuality/usefulness.

DO NOT REDO: Phase 2.5, Router/Runtime/Identity/Brief/Adapter/Planning approval architecture; preserve dirty work and old evidence.

NEXT RECOMMENDED SLICE: Travel Facts Integration v1 / verified forecast. Not implemented.
'''
(ROOT/'docs/agent/COMPANION_KNOWLEDGE_COVERAGE_20260930.md').write_text(report,encoding='utf-8')
print(json.dumps({'tests':tests,'real':stats,'source':f['snapshot']['sha256']},ensure_ascii=False))
