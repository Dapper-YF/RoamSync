import pathlib,json,hashlib,xml.etree.ElementTree as ET,subprocess
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-followup-fix-20261008')
SHA='26e33f7ecec848403c0992953c61216ddb305fec'
source=json.loads((A/'proposed_fix_source_manifest.json').read_text(encoding='utf-8'))
for p in ('app/planning_intent_service.py','tests/test_planning_intents.py'):source['files'][p]=hashlib.sha256((W/'backend'/p).read_bytes()).hexdigest()
source['sha256']=hashlib.sha256(json.dumps(source['files'],sort_keys=True).encode()).hexdigest()
(A/'followup_source_manifest.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
red=ET.parse(A/'followup_red.xml').getroot().find('testsuite').attrib
green=ET.parse(A/'followup_green.xml').getroot().find('testsuite').attrib
assert red['failures']=='1' and red['tests']=='5'
assert green['failures']=='0' and green['tests']=='5'
checkpoint=f'''# Current reliability checkpoint — 2026-10-08

Status: NOT READY. Original application8ee7dbf/documentation0b5010fe preserved. The human-approved six-path candidate is {SHA}, branch codex/roamsync-planner-reliability-20261008; clean checkout E:/Study/RoamSync-planner-reliability-clean-20261008. Source6d0257506c8ae65cbfc640cbdbfd3376b23bac2cf9623306432513f48ddca1eb. Initial checkout was Git clean; later untracked browser evidence under backend/evals/results does not alter tracked source. API/Worker175 shipped files exactly match, no mounts; external provider configuration unchanged. Nginx3001/API8001 share isolated PG17; old failed Runs and Trips remain exactly preserved.

MEASURED: clean Git locked Backend/Worker/Web builds; empty PG17 migrations0→0034;858 passed/0fail/error/skip/2existing warnings. Web typecheck,125tests and build freshly passed. Bounded predefined real GLM6/6 completed/stop,0retries; strict Research2/2. This is a small sample, not an availability guarantee. Historical Research JSON raw completion/parse position and deeper transport origin remain UNLOCATED; separate categories, no guessed fix or provider replacement.

The new-ref normal browser exploration/facts/create preview/confirmation generated a valid nonempty8-activity Candidate: Trip58239cd8-b097-4898-870f-f49f1a98719d, Run5981caad-00b9-40ca-8d2f-671b4a92717b, Revision1e0c5bab-5d7d-45fc-bafe-6f7761112739. Validator valid=true/errors=[]; route schedule warning transparently recorded. UI visible, pending, formalactivities0/version1. Day2 edit Runbbea2a1a-e7f1-4bf6-bd6f-cc12ab8200a4 remains awaiting_clarification: generated “其他日期安排不变” is incorrectly treated as a missing activity. One normal UI supplement returns200 but retains the same ambiguity. This is a confirmed internal parser defect, independent of historical JSON/transport categories. Candidate Accept and Execution/Disruption/Recovery/Reject/Explanation have NOT passed on this candidate.

Independent follow-up proposal, NOT applied or committed: replace the exact equality with re.fullmatch(r"其他日期(?:安排)?不变", value), after real alias matching; add the observed form regression plus exact real-alias precedence and unknown venue negative checks. Five focused cases: old candidate1failed/4passed; patched5passed. Validator, Graph, route/time/budget, settings and explicit confirmation unchanged. Proposed source {source['sha256']}; further source commit needs exact human authorization. Raw evidence/patch/manifests are excluded from Git in backend/evals/results/planner_reliability_20261008.

Production remains unchanged on8000/3000; no deployment/main merge/production migration/reset/Trip deletion. No RELEASE CANDIDATE READY claim. Next: approve the measured follow-up patch, create a new source identity and repeat affected clean locked regression/build/runtime binding and full real browser chain. After complete success only, request online approval. Future deployment plan: preserve current image IDs and external configuration; after explicit authorization take and verify DB backup, confirm production schema/readiness, resolve the automatic migration entrypoint separately, deploy API/Worker/Web together and perform read-only bindings. Rollback restores prior images/configuration while retaining PG volume and newer user records; no down migration/reset/restoration over newer data without separate authorization.

## Historical checkpoint preserved below

'''
docs=['docs/agent/REPOSITORY_REPRODUCIBILITY_20261007.md','docs/agent/ROAMSYNC_DEMO_ACCEPTANCE_20261007.md','docs/agent/ROAMSYNC_LONG_TERM_PROGRESS.md']
for p in docs:
    text=(W/p).read_text(encoding='utf-8')
    assert text.startswith('> Current checkpoint')
    text=text.split('\n\n',1)[1]
    (W/p).write_text(checkpoint+text,encoding='utf-8')
handoff=f'''# Latest Handoff

## Snapshot

2026-10-08. Goal ACTIVE / NOT READY. Approved six-path candidate26e33f7 clean builds and initial Candidate passed. Day2 edit still blocked by a newly measured phrase variant. Follow-up patch tested independently; not applied/committed, exact authorization needed. Production not authorized.

## Current Freeze / Rehearsal Status

Candidate {SHA}; branch codex/roamsync-planner-reliability-20261008 from0b5010fe. Original8ee7dbf/0b5010fe intact. Clean source6d0257506c8ae65cbfc640cbdbfd3376b23bac2cf9623306432513f48ddca1eb;175 API/Worker files exact/no mounts; built Nginx3001/API8001/isolatedPG17. Only untracked raw browser evidence generated later, tracked source exact.

## Latest shadow-mode evidence

MEASURED GLM fixed6/6 completed/stop,0retry; strictResearch2/2; bounded sample only. New-ref Candidate8activities valid/pending/UIvisible; formal0/version1. Day2 Run bbea2a1a… awaiting_clarification for “其他日期安排不变”; one normal supplement does not clear it. Downstream not passed.

## Prior milestone baseline (before shadow split)

Production fc3a06ba… unchanged. Earlier dirty-tree full lifecycle and old8ee7 initial Candidate remain historical, not new-ref proof. Three old failed Runs and all preexisting isolated Trip/days/Runs preserved. Source Repair PARTIAL; published-date-only facts. Ledger2.2 OPEN.

## Prior verification

Candidate26e33f7 locked clean Linux/Python3.11/emptyPG17 migrations0→0034:858passed/0fail/error/skip/2warnings. Web125/typecheck/build passed. First9-line patch had4red→green regressions. Follow-up one-line optional-word patch:5focused cases old1fail/4pass → proposed5pass; real aliases take precedence, unknown venue still not meta. Proposed source {source['sha256']}.

## Prior blockers (historical)

Research original malformed raw/finishreason/parseposition unavailable; exact root UNLOCATED. RemoteProtocolError is transport/protocol category; deeper gateway/proxy/provider cause UNLOCATED. Current health recovered without provider/config changes. Confirmed internal meta/activity misclassification persists for measured “安排” variant. No mock/salvage/relaxed Validator.

## Interview framing

Evidence backend/evals/results/planner_reliability_20261008, candidate_clean_binding.json/candidate_clean_full.xml/candidate_rehearsal_initial/candidate_rehearsal_clarification/proposed_intent_meta_followup.patch/followup_green.xml. Exact further two-source/test patch and four existing reports prepared for review; await authorization for new source commit. Then new clean Git acceptance through Candidate/Accept/Reject/Execution/Disruption/Recovery/Explanation; no old pass substitution. Production/main/DB unchanged; final online approval after all gates pass.
'''
(W/'docs/handoff/LATEST_HANDOFF.md').write_text(handoff,encoding='utf-8')
paths=['backend/app/planning_intent_service.py','backend/tests/test_planning_intents.py',*docs,'docs/handoff/LATEST_HANDOFF.md']
proposal={'base_commit':SHA,'branch':'codex/roamsync-planner-reliability-20261008','paths':{p:hashlib.sha256((W/p).read_bytes()).hexdigest() for p in paths},'source_manifest':source['sha256'],'followup_red':red,'followup_green':green,'scope_expansion':False,'production_authorized':False,'awaiting_human_authorization_for_changed_patch':True}
(A/'followup_authorization_proposal.json').write_text(json.dumps(proposal,indent=2),encoding='utf-8')
# Existing local handoff is an uncommitted operator status record; no source or index changes.
pathlib.Path(r'E:\Study\RoamSync\docs\handoff\LATEST_HANDOFF.md').write_text(handoff,encoding='utf-8')
print(json.dumps({'proposal':'followup_authorization_proposal.json','proposed_source':source['sha256'],'red':'1 failed,4 passed','green':'5 passed','release_source_unchanged':True}))
