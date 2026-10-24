# RoamSync stage3 implementation and acceptance

Status: MEASURED NO-GO. This isolated repair/acceptance round is closed;
the product closeout objective is NOT achieved. No official merge or deployment.

## Final answer

用户现在仍不能通过自然对话可靠完成一次旅行的咨询、选择、安排、修改和采用。
部分真实流程已打通，工程检查通过，但新封存题严格3/20、完整连续组0/5，
浏览器完整黄金链未通过。不能用开发重复采样、HTTP200或安全拒绝替代任务完成。

冻结产品：`758477fe674b14464cb2f0c9c031b27133a6b638`；app SHA256：
`3cf56be0bcd2530e3c8e6191376c43c8aa3597904f3b72c49f223c38739a4e70`。
隔离分支：`codex/product-closeout-stage3-20261024`，工作树
`E:/Study/RoamSync-product-closeout-stage2-20261024`。后续证据提交仅改文档。
正式HEAD核实仍`ea3ba833e6a77122c08c1c9327c18a346e3c48ef`，保留六项原有
tracked修改；正式源码、正式数据库、部署均未操作。旧`de72864 → 71e07c2`
位于`ea3ba83 → c2be562`祖先链；本轮复用了这些修复和测试。

## Final gates — same frozen product

|门槛|实测|判定|
|---|---|---|
|新独立题≥16/20|3/20；只通过9、10、17；20轮各提交一次，补采样0|失败|
|完整连续任务|0/5组全通；浏览器链需多次澄清/重新请求且保存后修改失败|失败|
|越权正式写入|封存样本观察0；浏览器仅明确采用后创建Trip|样本内通过|
|关键无证据保证|独立复核确认critical0；仍有预算概率及候选解释依据不足|不能视为通用安全证明|
|后端全量|主1902/专38全部通过，0跳过，运行前后源码一致|通过|
|Web|265通过、typecheck/build通过；限制2个测试worker|通过|
|真实生成对象安全|同一实际GLM/AMap生成pending Revision克隆验证重复、旧版本、并发、固定活动、回滚5类均通过|通过|
|工具证据完整性|浏览器/开发捕获有高德参数、结果与耗时；封存runner漏捕外部envelope|不足，明确保留|

Web首次默认并行的两项5秒超时和后端首次9失败保留在`batch6/full-1`及
`web-test.log`，没有删除。修复后重新冻结，使用新库执行完整检查；源码未再变化。
这不是重跑独立题：封存题直到最终冻结才执行，且只执行一次；使用后转为回归集。
独立复核按用户≥16/20门槛报告；其封存rubric更高的20/20条款未替代用户门槛。

## Frozen independent groups

|连续组|严格通过|实际阻断|
|---|---|---|
|地点比较与多轮指代|0/4|首个地点未解析，后续指代、路线/介绍子目标进入泛化澄清|
|条件更新与回读|0/4|人数/同行要求被拒，日期清除失败；后续有效态未达到用户目标|
|要求与证据推断|2/4|能回答入口/饮食推断；预算90×3=270子目标漏答并有“大概率够用”|
|生成、修改、采用、重读|0/4|生成被来源/授权校验拒绝，候选不存在，依赖步骤连续失败|
|保存态读取与Revision|1/4|读取准确；35分钟Revision实际形成，但理由无依据，差异漏答，最终采用ValueError|

独立Astra Medium复核任务由工具显式指定`gpt-6-astra`/`medium`；评审者只能从
父任务调度元数据获知此配置，不声称独立认证模型服务内部身份。实际产品模型配置
GLM `glm-5.3-flash`，Planner high/20000tokens/90s/retry0；selector/answer按现有
low及单轮预算执行。完整非秘密配置见外部`batch6/freeze.json`及runtime manifest。

## Browser continuity and remaining blockers

空白独立库、同一持久会话、真实模型/高德；没有预置候选、手工补库或拼接结果。
原始对话全文：[BROWSER_FULL_CHAIN.md](E:/Study/RoamSync-stage3-evidence-20261024/BROWSER_FULL_CHAIN.md)。

1. MEASURED：比较原句明确包含地址，但模型source_ref只指向前一段比较文字；服务端
   恢复该片段后地址不在目标来源范围，返回澄清。共同来源依赖没有完整表达。
2. MEASURED：首次生成模型输出重复day_index，被schema拒绝；降级仅确认更新日期，
   丢失“还需生成候选”的任务。自然追问后才生成真实ready候选。
3. MEASURED：首次修改额外携带仅生成允许的source_refs，严格拒绝；简化追问后
   真正展示120→75分钟差异。午餐12–13、宽窄13:16及180分钟未变。
4. MEASURED：“先不采用，再讨论推断”被模型误标discard；服务端正确未丢弃/未写入，
   但实际问题未回答。咨询、暂缓和丢弃的动作目标仍会混淆。
5. MEASURED：明确采用后首次创建1Trip/1Day/2Activity，正式75/180分钟；按保存态
   正确读取天数、首项、午餐、最后一天。刷新恢复同一会话和正式安排。
6. MEASURED：保存后60分钟修改被模型解释为replace_activity，完整运行失败，未建新Run。
   对保留模型输出离线解析，在`assistant_operation.py:133`复现ValueError：该操作缺少
   替换动词。现场日志只有ValueError；离线复现不是现场堆栈或补测成绩。正式八表完整不变。
7. MEASURED：正式宽窄说明仍残留模型“14:00到达”文字，实际时间13:16；自由说明与
   最终结构化排程尚未统一，不能把此说明当已验证安排事实。

另有已知范围缺口：普通聊天将已选项改为备选等仍没有可执行的Revision预览，现阶段
安全返回正式未变；显式页面表单保留。要求支持receipt是有界适配器，不是通用证据证明器。
下一轮应修复请求内来源依赖、动作/对象/否定范围和子目标完成契约，避免继续叠加特句正则。
新修复须另行冻结；本次20题只能用于回归，不能重命名为新独立成绩。

## Review package

- [独立逐题评分及全文](E:/Study/RoamSync-stage3-evidence-20261024/batch6/sealed-independent-grade.md)
- [封存单次原始状态/模型记录](E:/Study/RoamSync-stage3-evidence-20261024/batch6/sealed-once.json)
- [独立浏览器审阅](E:/Study/RoamSync-stage3-evidence-20261024/batch6/browser-independent-review.md)
- [开发真实模型全文](E:/Study/RoamSync-stage3-evidence-20261024/DEVELOPMENT_FULL_OUTPUTS.md)
- [每批提交与修改文件](E:/Study/RoamSync-stage3-evidence-20261024/batch-commits.json)
- [测试报告索引，含失败](E:/Study/RoamSync-stage3-evidence-20261024/test-results-index.json)
- [实际生成Revision安全实验与全部状态差异](E:/Study/RoamSync-stage3-evidence-20261024/batch6/real-object-safety-final.json)

以下保留开发过程中的修改前复现、根因、实现与测试，不应把其中中途成功覆盖为冻结成绩。

## Pre-unseal engineering corrections

Freeze candidate ab2c527: full backend 1892 pass/9 fail, dedicated38 pass;
Web263 pass/2 five-second timeouts under maximal parallel load, type/build pass.
The first browser comparison returns one verified place and a task-source gap;
the incomplete chain is retained, not combined with another run as success.
Sealed cases remained unopened. Full raw logs: batch6/full-1 and runtime/browser-ui.

Actual dispatch defects fixed: legacy clarify+known read must execute its known
capability; a fully blocked batch must clarify without reopening facts; bare
planning verb 排 shares preview cancellation scope; truly unbound singular
pronouns still clarify. Historical whole-batch assertions were updated to test
blocked child safety plus successful independent sibling. The old optional-item
chat test now checks unchanged formal version instead of expecting direct write.
Read task literal span IDs reuse the same source catalog as candidate generation,
with current-message provenance and no new authority. The next full freeze is
distinct; all original failures remain part of the evidence package.

## Batch5 — scoped evidence support and partial task completion

MEASURED before: external batch5-before-guard.json shows four unsupported
access/menu/bill/proximity claims pass the old local advice gate. The same six
public real questions are captured against c2be562 in batch5/real-before.json.
This is a regression/development set, not an unseen score.

Added a read-only requirement_support receipt on existing read_tools: requested,
related_information, supported, insufficient_or_stale, preserving source refs,
scope, exact place bindings, expiry and missing links. Only exact ordered route
endpoints plus explicitly requested mode and fresh bound route metadata support
a route estimate. This does not certify comfort, internal walking, meal fit or
final spending. No table, writer, permission or public write endpoint was added.
Existing bounded answer repair/local claim controls now check access, full meal,
final bill and proximity claims, and retain directly negated inferences and
concrete verification questions. This remains a bounded guard, not a general
truth prover. Astra reproduced direction/mode and caveat laundering defects;
both are now covered by negative tests.

ReadTask ambiguity is server-private metadata, not model-authorable authority.
Independent valid children execute even when a peer needs clarification, including
two-pass validation and cap-empty explanation tasks. Named identity lookup with
omitted redundant capabilities cannot degrade into unverified general prose.

MEASURED batch5/after6.xml: 68 targeted tests pass on migrated isolated PG.
Real-after3 uses GLM+AMap, resolves both places, retrieves 1.1km/16min walk and
directly rejects four invalid inferences; formal tables and source stay unchanged.
After3 also exposed a soup ingredient assumption and over-filtered verification
questions. The bounded guard was corrected with targeted regressions; the final
real-after4 capture and frozen acceptance remain separate evidence.

## Batch4 — preview, saved modification and acceptance

MEASURED before: batch4/before.xml and real-before/real-after through after8
retain source/schema/identity failures, an unsafe prose-only edit confirmation,
and a candidate edit that moved lunch/peer clocks. No failure is erased.
The saved duration edit now reuses the existing rule intent, Run/Worker/Revision
and Accept chain. Chat item-status changes no longer call the direct form writer.
Page forms remain explicit writes. Saved trip selector contracts exclude the
unsaved-candidate command; a substantive conflicting representation fails closed.
Only an empty redundant wrapper may request one explicit exact-value repair.
Bound server presentations anchor local preview clocks and effective windows;
overlaps block adoption rather than moving peers without approval. Accept updates
Activity versions only for actual differences and leaves unchanged rows intact.

MEASURED: batch4/compose-6 main and dedicated checks pass, including real PG
concurrent edit/accept, rollback, duplicate and unchanged-peer tests. after9 uses
real GLM/AMap: generate120 -> preview75 -> save -> read -> real Worker Revision60
-> explicit adopt. Formal diff changes only the target Activity. after10 again
adopts60 but exposes a saved-read dispatch regression; fixed by retaining the
saved_values purpose in merged read projections. Its failing output is retained.
Final-source real saved-read and final full engineering acceptance are still due.
These development repeats are not independent evaluation results.

## Batch3 — structured preview generation and local candidate edits

MEASURED before: batch3/before.xml reproduces five preview/adoption scope failures;
real-before.json retains the baseline real user failures. Root causes include
save-denial scope cancelling preview/edit, creation metadata duplicated in source
clauses, source paraphrases and canonical names, and workflow controls captured
as new travel requirements invalidating the candidate hash. Implemented scoped
action checks, server literal-span references, literal name/address query evidence,
strict empty-only format recovery and full downstream metadata/route validation.
Named pure lookups render actual provider fields without inventing sibling gaps.

MEASURED real-after6.json: real GLM/AMap ready candidate with 120min People Park,
1h lunch and actual 16min walk, followed by park90min and unchanged peer/window;
formal tables unchanged, source stable. Following Astra source/authorization
review, same-action synonym/pronoun revocation and source/quantity/kind checks
were strengthened; real-after7.json again generates and modifies a ready candidate
(90->90 in this sample, so this capture alone does not prove a non-noop change).
Earlier development captures/failures retained, including root plan output errors,
invalid source bindings, invented walking limit and condition-hash rejection.
batch3/final3.xml passes151 relevant tests; earlier final.xml had two restaurant
branch-name regressions, fixed by preserving exact full branch identities before
interpreting parenthesized address decorations. No unknown constraint was erased.

## Batch2 — effective conditions and receipts

MEASURED before: batch2/before.xml has three intended failures, and real-before
claims solo travel while stored party_size is absent and the sister's requirement
remains. Shared scalar normalization did not recognize self-only quantity, removal
lost subject boundaries and Companion could acknowledge rejected proposals.

Implemented source-bound self-only quantity, exact subject identity for removing
conditions, and versioned merged per-field application receipts. Standalone update
acknowledgements render authoritative effective state, including rejected fields.
Mixed answers receive receipts as context; this prompt boundary still needs final
live/adversarial acceptance. No formal writer change. MEASURED batch2/regression.xml
69 passed on isolated migrated PG; real-after.json confirms 1 person, sister-only
condition removed, personal no-alcohol retained and accurately recalled. Source
unchanged and formal-table fingerprints unchanged. Development failures retained.
Isolated branch codex/product-closeout-stage3-20261024 starts at c2be562;
official E:/Study/RoamSync remains ea3ba83 with its original local edits preserved.
Raw evidence: E:/Study/RoamSync-stage3-evidence-20261024. No production DB writes,
deployment or Obsidian operations. The new holdout is sealed; implementation
must not read it before the final product freeze.

## Batch1 — shared read identity and task execution

MEASURED before: batch1/before.xml has two intended failures; real-before.json
returns absent-suggestion clarification for a named comparison, then loses both
ordinal and compound reads. Root causes: competing Suggestion/place resolvers,
direct root dropping valid read_tasks, missing same-turn ellipsis and parent-city
provenance, and split direct answers losing parent subjects. Reverse route result
order also renumbered comparison members.

Implemented one frozen parent read projection, exact literal same-turn search
subjects (ID-less until provider resolution), preserved comparison order, shared
Companion projection and parent-question context. Read tasks retain independent
execution/status/results. No new writer or permission.

MEASURED after: batch1/after-r7.xml passes 49 related tests on an isolated migrated
PostgreSQL DB. real-after5.json uses real GLM and AMap: named comparisons and two
ordinal addresses work; compound route is 2.1km/29min, and missing current hours
are disclosed without losing the route. Source unchanged during capture; formal
state unchanged. General comparison prose is model knowledge, not reviewed venue
evidence. Prior after/after2/after3/after4 failures retained; after2 source drift
must not be treated as frozen evidence. Earlier local harness configuration
failures are retained separately from product failures. Astra reviewed identity
freeze, incomplete resolution and reverse-route ordering risks; regressions added.
