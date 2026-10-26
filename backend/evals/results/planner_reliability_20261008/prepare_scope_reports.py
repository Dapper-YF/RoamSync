import pathlib,json,hashlib,xml.etree.ElementTree as ET
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-decision-context-scope-fix-20261008')
source=json.loads((A/'followup_source_manifest.json').read_text(encoding='utf-8'))
for p in ('app/decision_context.py','tests/test_decision_context.py'):source['files'][p]=hashlib.sha256((W/'backend'/p).read_bytes()).hexdigest()
source['sha256']=hashlib.sha256(json.dumps(source['files'],sort_keys=True).encode()).hexdigest()
(A/'scope_fix_source_manifest.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
red=ET.parse(A/'scope_red.xml').getroot().find('testsuite').attrib
green=ET.parse(A/'scope_green.xml').getroot().find('testsuite').attrib
assert red['tests']=='9' and red['failures']=='1' and green['tests']=='9' and green['failures']=='0'
current='''# Current clean-release checkpoint — 2026-10-08

Status: NOT READY. Application candidate4a523b7bd91df6c7c77c06cff87b2ff6a36a80de on codex/roamsync-planner-reliability-20261008; original8ee7dbf/0b5010fe remain intact. Clean checkout E:/Study/RoamSync-planner-reliability-clean-v2-20261008; backend source3ae41a2daf9229933d1429fd9b2c58ff34a3564fb802f26a337b8c9d9faee52c. API/Worker175 shipped files exactly match; no source mounts. Locked clean Linux/Python3.11/emptyPG17 migrations0→0034:859passed/0fail/error/skip/2warnings. Web125/typecheck/build passed; Web source12b8ee8dc087770ebb1bfdb7563dd0b9052867a1546b162624af0330813a16a2 and built RootFS/artifacts unchanged. Only untracked rehearsal outputs generated after initial clean build.

MEASURED real browser/Backend/Worker/GLM/AMap/Tavily/Open-Meteo/PG17: initial10-activity valid Candidate pending/UIvisible/formal0/version1; day2 edit3→2activities,360→300minutes, untouched dates exact; explicit Accept formalversion1→2 with9activities. Browser rejection of the older first candidate persists too_rushed feedback without changing accepted formal version2; this stale-only check is not a current-version rejection proof. Execution/extend30 changes projected end by30minutes, formal schedule/version unchanged. Four navigation observations explicitly source=simulation (not device GPS; no compressed visit actions used) cause real Disruption/Worker Recovery. Recovery valid and explicit UI acceptance gives version2→3, planned/formal cost25000fen, Disruption resolved; completed/current/navigation-target formal fields exactly preserved except updated_at. Honest Explanation rationale_unavailable/based_on_prior_decision=false passes, no formal/Run mutation; original-rationale Ledger2.2 remains OPEN. City scope and real facts checks pass.

Full current-version rejection gate FAILED: ordinary request adjusts2026-10-11 while current activity美龄宫 is on2026-10-09. Run11230b54-ea1a-46f6-93df-9b8fe0616c7a fails decision_context_invalid/execution_references_unknown_activity. The activity exists in the full persisted itinerary. Builder filters formal_itinerary to requested day yet carries global current_activity_id; unchanged invariant then compares it against only the scoped subset. Formal version3/days unchanged, failure history preserved. This confirmed scope assembly defect is separate from meta/activity parsing and the historical Research JSON/transport faults.

Independent proposed correction (not committed/applied to Release): include days referenced by current/navigation-target/first-impacted Execution IDs as read-only context alongside requested days; protect every non-requested activity with outside_requested_scope. Requested target and editable IDs stay confined to third day. Four new regressions, all existing context tests: original1fail/8pass, proposed9pass. Three genuinely unknown pointer negatives remain rejected; strict Invariant function AST is identical, Candidate Validator and Planning Graph byte-identical. Replay of the actual read-only context fails on4a523b7 and passes on proposed source with the same real current pointer protected and only third-day editable IDs; zero provider calls or DB writes for replay. Additional existing source/test paths need exact human scope approval. Proposed manifest: '''+source['sha256']+'''. Evidence: backend/evals/results/planner_reliability_20261008/proposed_decision_context_scope_fix.patch, scope_red.xml, scope_green.xml, scope_actual_context_replay.json, decision_context_scope_blocker.json.

Provider fixed bounded6/6 completed/stop,0retry/serial, strictResearch2/2 (17.313/23.214s), connect-reuse success; actual deadline error correctly maps ConnectTimeout→planner_timeout. This small sample and successful core chain do not establish production availability. Original malformed Research raw/finishreason/parseposition missing; exact root UNLOCATED. Historical RemoteProtocolError belongs to transport/protocol category; deeper network/gateway/provider cause UNLOCATED. Recovery observed without replacing provider/config/model. No mock, prefix salvage, weakened Validator or invented Candidate.

Production unchanged, seven formal tables/Trip versions exact and images/config retained. Read-only productionPG17.11/schema0034; candidate migrations byte-identical, no production migration executed. Candidate differs in20 shipped source paths (13app/7eval) and Web bundle; APP_ENV development→release_acceptance in isolation, same model endpoint/key (values unprinted). Existing user Trips and failures retained. No main merge/push/deploy/DB reset/volume/data deletion. Only after exact scope approval, new clean candidate full regression and complete real chain including current Reject can establish READY. Future deployment needs separate final approval: verify authorized backup/readiness/schema, preserve prior image IDs/external config, start API without automatic production migration until DB boundary resolved, deploy API/Worker/Web consistently. Rollback restores prior images/config, retains PG volume/newer user data; no down migration/reset/overwriting data without separate authorization.

## Historical checkpoint preserved below

'''
docs=['docs/agent/REPOSITORY_REPRODUCIBILITY_20261007.md','docs/agent/ROAMSYNC_DEMO_ACCEPTANCE_20261007.md','docs/agent/ROAMSYNC_LONG_TERM_PROGRESS.md']
for p in docs:
 text=(W/p).read_text(encoding='utf-8');text=text.split('## Historical checkpoint preserved below\n\n',1)[1];(W/p).write_text(current+text,encoding='utf-8',newline='\n')
handoff='''# Latest Handoff

## Snapshot

2026-10-08. Current gate NOT READY. Clean4a523b7 core Candidate→Accept→Execution→Disruption→Recovery and honest Explanation PASSED. Subsequent current-version planning/reject blocked by confirmed cross-day context scope defect. Minimal independent proposal tested; additional two existing paths need authorization. Production not authorized.

## Current Freeze / Rehearsal Status

Application4a523b7bd91df6c7c77c06cff87b2ff6a36a80de on codex/roamsync-planner-reliability-20261008; original8ee7dbf/0b5010fe intact. Clean source3ae41a2daf9229933d1429fd9b2c58ff34a3564fb802f26a337b8c9d9faee52c;175 API/Worker files exact/no mounts. Built Nginx3001/API8001/isolatedPG17. Initial Git clean; only later raw rehearsal outputs untracked.

## Latest shadow-mode evidence

Real initial Candidate10 valid/pending/formal0/version1. Day2 3→2activities/360→300minutes, untouched dates exact; Accept gives9activities/version2. Older stale Candidate Reject persists feedback/formal exact. Execution extends30; four explicit simulation navigation inputs trigger real Recovery; no compressed actions or realGPS claim. Explicit Recovery Accept version3/cost25000fen, completed/current protected/formal exact. Honest rationale_unavailable and city/facts scope passed.

## Prior milestone baseline (before shadow split)

Productionfc3a06ba…/API8000/Web3000 unchanged; seven formal tables/Trip versions exact. Old failed Runs/Trips retained; older dirty-tree successes remain historical. Source Repair PARTIAL/published-date-only facts; Ledger2.2 OPEN.

## Prior verification

Clean locked Linux/Python3.11/emptyPG17 migrations0→0034:859passed/0fail/error/skip/2warnings. Web125/typecheck/build/source/artifact binding passed. Meta parser two approved patches: red→green, true aliases/unknown venues protected. Provider fixed6/6 completed/stop,0retry; strictResearch2/2, bounded sample only. Original JSON/transport deeper roots UNLOCATED and separate.

## Prior blockers (historical)

New current Run11230b54… fails decision_context_invalid. Current美龄宫 exists Oct9 but user targetsOct11; selected-day formal context excludes it while retaining global Execution pointer, so unchanged invariant rejects. This is scope assembly, not deleted activity/provider fault. Formalversion3 exact. Independent proposal retains referenced Execution days as read-only and protects all outside requested scope; Invariant AST/Validator/Graph unchanged. Focus9 cases old1fail/8pass→new9pass; actual-context replay succeeds with onlyOct11 editable, no DB/provider calls.

## Interview framing

Evidence backend/evals/results/planner_reliability_20261008, candidate4a523b7_clean_full.xml/clean_binding/execution_invariants, decision_context_scope_blocker.json, proposed_decision_context_scope_fix.patch, scope_actual_context_replay.json. Need explicit extension to backend/app/decision_context.py + backend/tests/test_decision_context.py and original4reports, then new clean source identity/full real chain/current Reject/runtime binding. No RELEASE READY until all gates pass; production/main/DB untouched. Future online approval, backup/schema/entrypoint resolution and preserved-image rollback required separately.
'''
(W/'docs/handoff/LATEST_HANDOFF.md').write_text(handoff,encoding='utf-8',newline='\n')
paths=['backend/app/decision_context.py','backend/tests/test_decision_context.py',*docs,'docs/handoff/LATEST_HANDOFF.md']
proposal={'base_commit':'4a523b7bd91df6c7c77c06cff87b2ff6a36a80de','branch':'codex/roamsync-planner-reliability-20261008','paths':{p:hashlib.sha256((W/p).read_bytes()).hexdigest() for p in paths},'new_existing_source_paths_to_authorize':paths[:2],'source_manifest':source['sha256'],'focused_red':red,'focused_green':green,'strict_invariant_unchanged':True,'validator_graph_unchanged':True,'source_changes_not_applied_to_release':True,'production_authorized':False}
(A/'scope_fix_authorization_proposal.json').write_text(json.dumps(proposal,indent=2),encoding='utf-8')
pathlib.Path(r'E:\Study\RoamSync\docs\handoff\LATEST_HANDOFF.md').write_text(handoff,encoding='utf-8',newline='\n')
print(json.dumps({'proposal':'scope_fix_authorization_proposal.json','proposed_source':source['sha256'],'new_existing_paths':paths[:2]}))
