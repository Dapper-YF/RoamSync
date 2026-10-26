import json,pathlib,xml.etree.ElementTree as ET
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-release-20261008')
SHA='322f55334d16e8cacec60e5e6c126d61cfcca122'
def suite(n):
 s=ET.parse(A/n).getroot().find('testsuite');return dict(s.attrib)
result=suite('candidate322f553_clean_full_confirm.xml')
assert result['tests']=='863' and all(result[k]=='0' for k in ('failures','errors','skipped'))
audit=json.loads((A/'candidate322f553_final_audit.json').read_text(encoding='utf-8'))
web=json.loads((A/'candidate322f553_web_binding.json').read_text(encoding='utf-8'))
common=f'''# Current clean-release checkpoint — 2026-10-08

Status: **EXTERNAL_PROVIDER_BLOCKED / NOT READY**. Application commit `{SHA}` on `codex/roamsync-planner-reliability-20261008`. The documentation-only checkpoint is recorded externally in `blocked_final_binding.json` after this report is committed; its application bytes remain those of322f553. Original8ee7dbf/0b5010fe and all prior candidate history are intact.

MEASURED clean checkout `E:/Study/RoamSync-planner-reliability-clean-v3-20261008`, initially Git clean, locked Linux Backend/Worker/Web builds completed. Backend manifest `{audit['backend_source_sha256']}`. API/Worker each175 shipped source files exactly match, no source mounts. Web source `{web['web_source_sha256']}`, locked inputs, RootFS and built artifacts exactly match4a523b7; reuse the identical-source125 tests/typecheck/build evidence in candidate_web_checks.log, rather than claiming a new uncached test run. Container pnpm11.19.0, browser CLI11.25.0, uv0.11.15 frozen/Python3.11.

MEASURED fresh empty PostgreSQL17, migrations0→20260924_0034, unchanged source full regression: **863 passed,0 failures/errors/skips,2 deprecation warnings**,37.40s. First full attempt862passed/1failed is retained. Existing navigation test uses40ms provider delay and5ms sleep; original event ordering was not recorded. Its one bounded unchanged targeted rerun passed; separate uncommitted Event-controlled diagnostic proves stale-write rejection when supersede commits before provider response and legal completion when response precedes commit (2passed). Timing fragility is INFERRED; first failure cause remains UNLOCATED. No timing relaxation, test-source edit or production operation was used.

MEASURED current Provider protocol fixed3 model calls before execution, serial/retries0/90s timeout: API simple3.180s completed/stop; Worker strict structured1.678s completed/stop; Worker actual strict Research15.425s FAILED RemoteProtocolError→RemoteProtocolError, mapped planner_unavailable. Research received HTTP200 HTTP/1.1 event-stream headers, then failed before a terminal model result; no finish_reason/completion status is available. Result **2/3**, not a reliability pass. Deeper proxy/gateway/provider origin UNLOCATED. The protocol mandates stopping E2E after any failure; no further model probe batch was performed. Earlier6/6 including2Research successes are historical, not current health proof. Browser first greeting HTTP502 before any Trip/PlanningRun; anonymous failed session retained. Current322f553 Candidate and complete lifecycle gates **NOT PASSED / PAUSED**.

Historical malformed Research JSON and transport failure remain separate: original malformed raw response/parse position/finish reason were not retained, so truncation/provider mismatch/repair root is UNLOCATED. Current streaming transport failure cannot be declared a JSON parser defect. Exact measured Research request17133bytes, system2277chars/3561bytes, user6265chars/12651bytes; glm-5.3-flash at official BigModel Chat Completions endpoint, json_object plus strict schema, stream enabled, max_tokens20000. Schema, strict parser/repair policy and Validator unchanged; no prefix salvage, invalid-field discard, fake Candidate or provider replacement.

VERIFIED approved source repairs:26e33f7 and4a523b7 bound exact meta phrases/date-frame parsing, preserving real activity aliases/unknown-venue checks. Third approved patch322f553 retains days referenced by Execution pointers as read-only context while protecting all non-requested activities with outside_requested_scope. Context focus old1fail/8pass→9pass; actual failed-context replay succeeds with only requested third-day editable. Invariant function AST unchanged, Validator/Graph bytes unchanged. These repairs do not prove a new real Candidate while Provider is blocked.

Historical4a523b7 real core rehearsal passed initial10-activity Candidate→day2 edit3→2activities/360→300min→Accept(formal9activities/version2)→Execution/extend30→four explicitly simulation navigation inputs→real Disruption/Recovery→explicit Recovery Accept(version3/cost25000fen). Untouched dates, completed/current/navigation-target fields preserved. Older stale Candidate Reject/feedback and honest rationale_unavailable passed. **Current-version Reject was not passed**; current activity was pending/navigation target at Recovery validation, not a proved in_progress recovery protection case. These are4a evidence only, not322 acceptance. No real GPS claim.

VERIFIED final read-only audit: production seven formal tables/Trip versions exact against baseline; all four pre-existing isolated Trip/days/PlanningRun histories exact. Production API8000/Web3000/Worker and images/configuration unchanged; current isolated API8001/Web3001 use322 source. Failed histories preserved, no new322 Trip. Production differences:21 shipped paths (14app/7eval), Web bundle; productionPG17.11/head0034, candidate migration files unchanged. Public APP_ENV differs for isolation; external provider configuration was retained without printing credentials. No deploy/main merge/push/production DB migration/reset/data deletion. Source Repair remains PARTIAL/published-date-only facts; Ledger2.2 OPEN.

Next gate: after external service recovery, prescribe a new small finite health batch and require its success before a fresh normal UI/API322 Candidate→day2 modification/untouched dates→Accept→current-version Reject/feedback→Execution/extend30→explicit simulation delay→Disruption→Recovery validation/confirmation→version/cost/protected-state checks→honest missing-rationale explanation. Bind all new evidence to this same application source; any additional source fix requires appropriate scope authorization and a new candidate identity. Do not repeat feature development or substitute historical results.

Future production plan, only after full real gates and separate human online approval: capture immutable current images/configuration and approved database backup; verify provider health, runtime hashes and schema; confirm an API startup command that does not implicitly migrate production; schedule controlled API/Worker/Web cutover and smoke checks. Current schema has no candidate migration delta. Roll back by restoring preserved prior image IDs and external configuration, stop only newly deployed services, retain Trips/failed histories; no destructive reset or unapproved schema rollback. Deployment/main/production DB remain unauthorized. No further source authorization is needed for the three already approved patches; any new source scope or production operation requires its own approval.

Evidence (raw outputs excluded from Git): `backend/evals/results/planner_reliability_20261008/provider_health_current322_gate.json`, health_current322_protocol.json, call7/8/9.json, candidate322f553_first_attempt_failed, candidate322f553_clean_full.xml, candidate322f553_clean_full_confirm.xml, nav_ordering_diagnostic.xml, nav_existing_test_confirm.xml, candidate322f553_final_audit.json, candidate322f553_web_binding.json, scope_actual_context_replay.json, scope_fix_staged_audit.json, production_difference_and_rollback_inventory.json. Failed evidence and earlier successful evidence retained with original identities.
'''
for rel in ['docs/agent/REPOSITORY_REPRODUCIBILITY_20261007.md','docs/agent/ROAMSYNC_DEMO_ACCEPTANCE_20261007.md','docs/agent/ROAMSYNC_LONG_TERM_PROGRESS.md']:
 p=W/rel;old=p.read_text(encoding='utf-8-sig');marker='## Historical checkpoint preserved below'
 assert marker in old
 historical=old.split(marker,1)[1].lstrip()
 p.write_text(common+'\n'+marker+'\n\nThe following frozen report describes prior versions; its pending authorizations and test counts are historical. The current checkpoint above governs.\n\n'+historical,encoding='utf-8',newline='\n')
handoff=f'''# Latest Handoff

## Snapshot

2026-10-08。EXTERNAL_PROVIDER_BLOCKED / NOT READY。三项获批补丁已提交；当前应用{SHA}。没有新增功能开发或生产操作。当前源码尚未完成真实Candidate和全生命周期，不输出RELEASE READY。

## Current Freeze / Rehearsal Status

分支codex/roamsync-planner-reliability-20261008；原8ee7dbf/0b5010fe保留。干净检出E:/Study/RoamSync-planner-reliability-clean-v3-20261008；Backend manifest {audit['backend_source_sha256']}。API/Worker各175文件完全匹配、无挂载；Web源码/锁定依赖/RootFS/产物与已验125项版本完全相同。文档checkpoint及最终干净检出绑定记录于blocked_final_binding.json。

## Latest shadow-mode evidence

当前固定3次真实Provider调用，串行、0retry：API简单3.180s成功；Worker结构化1.678s成功；严格Research15.425s收到HTTP200流后RemoteProtocolError，映射planner_unavailable，无模型完成状态。2/3，按预定策略暂停E2E，不追加探测。更深代理/网关/Provider根因UNLOCATED。浏览器首句502，未创建Trip/Run，失败会话保留。历史JSON非法原始输出缺失，根因仍UNLOCATED，独立于当前传输失败。

## Prior milestone baseline (before shadow split)

4a523b7核心真实链成功：Candidate10活动→第二天3变2、360变300分钟→Accept正式9活动/version2→Execution延长30分钟→四个明确simulation导航输入→Disruption/真实Recovery→确认version3/cost25000fen。未改日期及已完成/current/nav目标字段保持。仅旧候选Reject通过，当前版本Reject未通过；Recovery时current为pending，未证明in_progress恢复保护。诚实缺理由解释与城市/facts边界通过。上述不算322通过。无真实GPS声明。

## Prior verification

322锁定Linux/Python3.11/新空PG17迁移0→0034，最新863通过/0失败错误跳过/2警告。首次862通过1导航竞态失败保留；原测试有界单项重跑通过、事件控制两顺序诊断2通过。原失败时序未记录，原因未证实，不能宣布消除波动。Web125/typecheck/build复用完全同源码证据。获批context修复9项及实际上下文回放通过；只第三天可编辑，非请求日期只读，Invariant/Validator/Graph未变。

## Prior blockers (historical)

meta“其他日期(安排)不变”和日期框架误识别已获批修复。跨日Execution指针的上下文范围缺陷在322获批修复。旧失败Run和所有隔离Trip/days/Runs最终精确保持。原6/6Provider成功只属历史，不替代当前2/3失败门禁。Source Repair PARTIAL；Ledger2.2 OPEN。

## Interview framing

生产API8000/Web3000/Worker未变；七张正式表/Trip版本精确一致。当前与生产21个shipped源码差异(14app/7eval)+Web产物，PG17.11/schema0034，migration无差异。报告位于docs/agent两份验收报告及进度文件；原始证据backend/evals/results/planner_reliability_20261008。Provider恢复后新有界健康门禁→当前Commit新的Candidate/修改/Accept/当前Reject→Execution/Disruption/Recovery全链并重新绑定manifest。不要无限重试，不用Mock。最终真实全链通过才请求上线授权。发布先备份并保存旧镜像/config、禁止启动脚本自动迁移生产；回滚恢复旧镜像/config并保留数据。生产部署/main合并/生产DB仍未授权。
'''
assert len(handoff)<3000
(W/'docs/handoff/LATEST_HANDOFF.md').write_text(handoff,encoding='utf-8',newline='\n')
(pathlib.Path(r'E:\Study\RoamSync')/'docs/handoff/LATEST_HANDOFF.md').write_text(handoff,encoding='utf-8',newline='\n')
(A/'PLANNER_RELIABILITY_GATE_20261008.md').write_text(common,encoding='utf-8',newline='\n')
(A/'current_regression_summary.json').write_text(json.dumps({'first':suite('candidate322f553_clean_full.xml'),'latest':result,'diagnostic':suite('nav_ordering_diagnostic.xml'),'targeted_confirm':suite('nav_existing_test_confirm.xml'),'first_failure_root':'UNLOCATED; original ordering not recorded'},indent=2),encoding='utf-8')
print('Four authorized reports updated; production/source unchanged; handoff characters',len(handoff))
