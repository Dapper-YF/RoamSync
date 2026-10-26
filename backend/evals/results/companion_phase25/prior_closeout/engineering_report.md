# Travel Companion Phase 2.5 — Final Acceptance

Date: 2026-09-30, Asia/Shanghai. **Phase 2.5 COMPLETE**：本次限定的路由安全、知识可靠性修复、评审、回归与正式发布闭环已完成。此结论不表示 holdout 全题覆盖或普通模型知识均经验证。

实际仓库 `E:\Study\RoamSync`；HEAD 保持 `5572849`，未提交或重置既有工作树。最终验收采用文件清单而非 HEAD 代表当前源码：

`092c79626184262f5c8b530174fbca290e883ea39a89d7f4710303816d38713e`

主证据目录：`backend/evals/results/companion_phase25/final/`。`source_snapshot.json` 包含 backend app、tests、migrations、eval 程序、依赖及构建文件；`acceptance_binding.json` 关联同一快照、最终 JUnit、两类真实模型批次、正式运行文件和 HTTP smoke。后续报告与交接文档不属于运行源码清单。

## 1. Starting Reality

开始时审计真实 dirty tree、最新交接、Phase 2 报告、Conversation Policy、既有 eval/tests 和正式容器。工作树已有大量未提交/未跟踪文件，不能把 git diff 全部算作本轮改动，也不能用旧报告的 587 passed 替代当前证据。

已确认 Independent Companion Runtime、server-owned stable suggestion identity、多轮引用、PlanningBrief、Tourism Knowledge adapter、五类 claim、applicability/attribution、自然 renderer 均存在。普通 loading 为“正在回复…”，greeting 不读取 Planning-heavy context；明确 Planning 请求已有独立权限与确认生命周期。

本轮仅修 Router、现有 prompt/provider 输出解析、现有 renderer、InformationNeed 与一个 Brief 目的地提取 bug，并补回归和验收。未重建 Runtime、Renderer、Identity、Brief、Adapter 或 Planning Graph。`audit_binding.json` 记录关键受保护文件自初始审计未变，包括 assistant service、planning graph/context/run repository、revision、planner repository、trip execution、tourism adapter、companion runtime/contracts。Web 与 Android 本轮无源码/契约改动。

## 2. Router Root Cause

旧 `_NEW_TRIP` 把旅行愿望、目的地与时长表达作为创建旅行的授权信号，导致“国庆想出去但怕一个人无聊”“玩三四天”在尚未要求规划时获得 mutation authority。问题是授权语义边界，不是两个句子的字面特例。已存在 pending action 也不能单独证明当前用户允许新的规划动作。

## 3. Router Fix

`travel_goal_router.py` 移除目的地/日期/时长驱动的新旅行授权，保留锚定的明确复用/改期动作；补足“给我做…行程”“排一下”“加进去”“缩短为”等明确动作表达。信息问答与探索 guard 仍先保护非变更目标。

“三天”“800元左右”“10月2号出发”“就第二个”只有在先前明确授权的 planning clarification 上下文中续接 Planning。Cancelled/failed/rejected 上下文不能续接；pending action 本身不能发起 authority。按既有协议，authorized clarification 的 runtime 为 planning、`mutation_requested=false`，权限来自先前明确请求。

PostgreSQL 集成证明六轮探索新建 PlanningRun 为 0；随后明确请求可进入既有 Planning 路径并创建 1 个 Run，Trip.version 保持不变。预旅行路径仍要求日期澄清/确认，不能把进入 Planning 等同已落库新旅行。

## 4. Conversation Policy Alignment

普通 general knowledge prompt 与来源 prompt 最小对齐：先回答当前目标，探索是合法终点；明确 Planning 前不主动追问日期、预算等 planning slots，不反复附带规划 CTA，允许兴趣/节奏类探索问题。没有新增 CTA 状态机。

真实六轮链保持“独行担忧 → 时长 → 南京 → 城市文化 → 老街巷”的连续性，最后明确规划才生成南京三天 Brief。最终真实批次无不必要 slot 问题或重复 planning CTA；source holdout `rec_03` 仍有一次条件性的可选日期邀请，作为限制保留，不能据此宣称所有来源回答均零 CTA。

## 5. Grounded Response Fixes

复用现有 `_answer_text`：即使已有支持正文，也显示影响理解的缺失主题；使用自然语句说明形成确切年份等不可确认的部分，避免“资料限制：”工程标题。

Curator inference 使用“如果你喜欢…”，agent inference 使用“我倾向于认为”，recommendation 使用“我的建议是”；不把建议写成 UNESCO 等来源机构的结论。最终 prose 中已知内部 topic key 换为中文或移除括号形式，原 claims/evidence metadata 完整保留供审计。

真实评估同时暴露并修正 evidence_ref/assertion_id 混用、非法 suggestion_type、额外 authority 字段、尾随 prose 和 JSON 字符串原始换行等输出问题。现有 provider 增加一次有界格式修复（最多两次 generation），使用同一 schema/context，不新增工具或 authority；完整 JSON 解析后仍经过严格 Pydantic 验证，尾随文本/多对象/越权字段不能通过前缀截取被静默接受。原始字符串换行规范化不放松业务 schema；第二次错误仍失败。最终批次无格式修复，但此前失败与修复记录保留。

InformationNeed 最小修正：明确西湖映射已有杭州 corpus scope；无城市名称的明确来源问题可查现有资料；历史/摄影混合与茶文化选取相关已有类型；适用性证明按事实问题处理；今年桂花季/节时间和当前花况守住 live 边界。未扩大 corpus，未建立正式 place identity。

## 6. Eval Protocol Versioning

协议见 `docs/agent/COMPANION_PHASE25_EVAL_PROTOCOL_20260930.md`，v2 明确七类 mode：general_conversation、source_grounded_knowledge、recommendation、live_fact_required、decision_explanation、explicit_planning、exploration_non_planning。Case 记录 goal/runtime/mutation/knowledge required/planning allowed/answer mode/evidence expectation。

普通“西湖有什么历史”允许 general model answer，记录 `model_general_knowledge_unverified`；“根据可靠资料”“给我来源”“有依据吗”才要求 source path。Live/original-rationale 的更强边界优先。

原 `holdout_v1.json` 字节不变，SHA256 `07505a83aa6921639f70f82af4670a1a6624b038000cf5a849757e718ddeec22`。其 pending 字段是归档 fixture；当前 50 条完成评审存在独立版本化结果中。旧协议默认知识问答 RAG：保留旧标签和原 wording 的 controlled need/routing 诊断；仅对原 knowledge-required case 的 source replay 添加明确来源请求并记录变换。解封后结果参与修 bug，故最终是非盲回归，不能称 untouched blind holdout。

## 7. Holdout Results

最终 `holdout_review_live.json` 与 `manual_review.json`：50 reviewed，pending 0，errors 0。混合/建议回答实际调用当前 Companion provider 13 次，格式修复 0；事实/live/rationale 分支按现有实现确定性执行，不把 50 cases 宣称为 50 次模型生成。

| 指标 | 结果 | 含义 |
| --- | --- | --- |
| Runtime routing | 50/50 | 原 fixture 无独立 goal taxonomy 标签，不等于 goal accuracy |
| Planning authorization | 50/50 | 全部应非 planning，均守住权限 |
| 旧 need 标签一致 | 39/50 | 保留 factual/advisory/mixed 不一致 |
| 原 expected assertion ID 覆盖 | 34/50 | ID 不同的语义等价回答也不改标签判通过 |
| 有调用的检索相关性 | 43/44 | `profile_02` 检索老人 guidance，与地理问题无关 |
| 结构化 recommendation separation | 50/50 | 不能代替对建议内部隐含事实的评审 |

每题有 routing、authority、need、relevance、sufficiency、claims、scope、attribution、usefulness 记录。`hist_04` 将人工堤岛时期问题误当湖泊地质形成，未利用已有对应断言；`profile_02` 返回不相关资料后限制回答。另有适用性、连续游览时长、茶地点、UNESCO title-only、多目标混合的覆盖缺口；未修改 expected labels 来掩盖。

## 8. Claim-level Review Results

单一 Codex reviewer；不是独立人工双标注。复核实际提供的断言文字、target/scope 和 canonical source metadata；不是只检查 citation ID 有效，也不是对官网作新的独立事实核验或通用 entailment 验证。

| 批次 | supported source facts | partially_supported | unsupported structured source facts | not_applicable inference | recommendation_not_fact |
| --- | ---: | ---: | ---: | ---: | ---: |
| Real scenarios | 14 | 0 | 0 | 5 | 3 |
| Holdout source replay | 57 | 0 | 0 | 38 | 28 |

以上是经过 server grounding 的结构化 claims。额外人工检查发现 holdout `rec_04` 的建议内有“三面云山一面湖”修辞短句，现有断言未支持：另记 **1 个 unsupported embedded phrase**，不能当官方引文或遗漏后报告绝对 unsupported=0。普通模型回答和建议隐含的一般判断仍为 unverified，不纳入支持事实分母。`partially_supported=0` 不代表每题证据完整；题目级缺失另计 sufficiency/coverage。

## 9. Real Model Evaluation

最终 `real_model.json`：16 scenarios 完成，errors 0，真实 provider generations 8，format repairs 0，无 fake fallback。六轮探索链、明确规划转换、exact fact、summary、unsupported detail、attribution/applicability traps、source recommendation、general knowledge、live hours、缺少 original rationale 均覆盖。

人工 goal 15/16（93.75%）；一个 source 文化摄影 recommendation 被 Router 分为 explanation。Runtime 16/16，authority 正确；goal 小分类不一致没有造成权限错误。普通南京问题未强制 RAG、7 条回答保留 general unverified metadata，不伪称 verified source。

Conversation continuity 人工看过上下文输出，六轮中未因时长或目的地触发 Planning；最终明确请求的 Brief 是南京、3 天。独立 eval 不连接 mutation port/DB，实际 Run 与版本保证来自 SQL integration，不用该批次冒充 DB 证据。

早期 interrupted/attempt/before-fix artifacts 保留，发现过字段越界、错误 enum、非完整 JSON、raw newline、evidence ref 混用与 topic key 泄漏。它们不属于最终快照分数；最终评估是在这些小范围修复和最后一处测试协议纠正后重新执行的，外部模型未来可用性不保证。

## 10. Planning Authorization Metrics

Real exploration premature authority **0/6 (0%)**，runtime **16/16**；holdout authority **50/50**。Focused SQL 六轮 exploration 的 PlanningRun 增量 0，explicit request 后增量 1；Trip.version 未变。非授权 pending/cancelled context 与 authorized date/duration/budget/reference followups 均有回归。

正式 smoke 前五轮 mutation=false，最后 mutation=true 且 PlanningBrief prepared。预旅行 session 缺具体日期，正常进入 Planning 澄清，没有创建旅行或 Run；不能把这次 smoke 描述成真实正式规划执行完成。

## 11. Tool Selection Metrics

Real cases TP=6、FP=0、FN=0，knowledge precision/recall=1.0，仅对已声明协议的 16 cases；general mode 不调用 RAG。Source holdout replay 44 次 required calls，TP=44、FP=0、FN=0，precision/recall=1.0；其 43/44 relevance 与 34/50 assertion coverage 说明“调用对工具”远不等于“回答完整”。Unnecessary tool calls=0（这两个限定协议集合）。

旧 wording 的 controlled holdout 仅作 need/routing 诊断，不参与最终 answer quality。没有新增网络工具、embedding、Travel Facts 或 Weather 接入。

## 12. Grounding Metrics

实际 source facts 14+57 条在所提供 registry wording/scope/attribution 范围均支持；bounded review 未发现这些结构化断言扩大 applicability 或错误归给来源机构（14/14、57/57）。建议与 inference 不计为 publisher fact；一个 unsupported embedded 修辞短句另计，故不能声明全输出 factual accuracy=100%。

Exact formation year、来源不能证明的老人目的地适用性/推荐引文、live hours 与 original rationale 均诚实降级。Source title 与 curator title 分开；通用老人原则不是“杭州必适合老人”的证明。Source registry 只证明当前资料内的支持，不证明来源网页此刻更新状态或 corpus 全面性。

## 13. Answer Coverage

Real：16/16 获得响应或 Brief，**10/16 substantive (62.5%)**、5/16 partial/honest limitation、1/16 planning transition；不能将 completion 当作完整知识回答率。无不必要 slot question（0/16），重复 planning CTA cases=0；探索子集为0/6。

Holdout：28/50 useful substantive（56%），14/50 partial/honest limited，6/50 useful safe live limitation，2/50 missed/irrelevant。排除两个 missed case 时，48/50 至少有部分帮助或恰当限制；这不是 96% 完整回答覆盖。Safe limitation 避免编造当前花况/营业时间，但 mixed live case 可能连稳定子问题一起保守拒答，质量上仍有成本。

## 14. Files Changed

本轮改动清单，不能以整份 dirty git status 归因：

- `backend/app/travel_goal_router.py`：明确授权边界与 followup。
- `backend/app/companion_provider.py`：策略对齐、refs/enum 说明、一次格式修复与严格完整 JSON 解析。
- `backend/app/companion_graph.py`：材料缺口、建议语气、topic prose 清理。
- `backend/app/companion_information.py`：已有 scope/类型匹配和 live guard。
- `backend/app/companion_state.py`：“规划/安排南京三天”的目的地提取。
- `backend/tests/test_phase25_final.py`：新增本轮 focused/unit/PostgreSQL 回归。
- `backend/tests/test_assistant_tools.py`、`test_conversation_regressions.py`：旧隐式创建输入改为明确规划，保留原原子性、预算、确认、历史等断言。
- `backend/evals/phase25_final.py`：snapshot/live/holdout/source replay 版本化执行和证据输出。
- `scripts/phase25_diagnostic.py`、`phase25_review.py`、`phase25_release_smoke.py`、`phase25_release_binding.py`：诊断、逐题评审、正式 smoke 与只读最终绑定。
- 评估 artifacts、v2 protocol、本报告、LATEST_HANDOFF、PROJECT_STATE。

本轮没有更改 Web/Android；受保护核心文件是否本就 dirty 与是否本轮修改不同，见 audit binding。

## 15. Focused Tests

最终 `backend/evals/results/companion_phase25/final_focused.xml`：**155 passed / 0 failed / 0 error / 0 skipped，13.969s JUnit**。覆盖 Router 正反例、授权 followup、renderer、schema repair/失败边界、source mode、live traps、Brief、SQL mutation 与既有 Companion/assistant/conversation 兼容性。

中间修复优先 focused，复用现有隔离 PostgreSQL 与已存在 test image/挂载代码；没有每改几行就新建 compose project 或数据库。Focused 完成后才执行最终完整套件。

## 16. Full Regression

Linux / Python 3.11 / PostgreSQL 17，`alembic upgrade head` 成功，完整 backend 最终 **632 passed / 0 failed / 0 skipped / 2 existing Starlette warnings，33.79s**。证据 `final/backend_final.xml`、`backend_final.log`，不是引用旧 587 数字。

本轮最终验收阶段 test image 构建一次，使用既有隔离 test PostgreSQL。首次完整套件 631 passed / 1 failed：`test_explicit_daily_budget_is_preserved` 仍用废弃的隐式创建输入；修为明确“帮我规划…”后保留预算断言。失败证据 `backend_before_protocol_fixture_fix.xml/log` 留存；该测试文本变化进入新 manifest，focused、real、holdout 重新绑定并重复执行，再跑 full 632。没有对已通过代码无意义地持续扩大测试。

最终命令：

```text
docker compose -f compose.test.yaml build api-test
docker compose -f compose.test.yaml run --rm --no-deps -v E:/Study/RoamSync/backend/tests:/app/tests -v E:/Study/RoamSync/backend/evals/results/companion_phase25/final:/artifacts api-test sh -c 'uv run --no-sync alembic upgrade head && uv run --no-sync pytest --junitxml=/artifacts/backend_final.xml'
```

Web 虽无本轮源码改动，现有兼容性检查仍执行：**123 tests / 20 files passed、typecheck PASS、production build PASS**（`web_test.log`、`web_typecheck.log`、`web_build.log`）。Android contract 未变，没有新开发或本轮重跑 Android；历史结果不能作为新最终快照的 Android 验收。Demo rehearsal NOT READY、Ledger Stage 2.2 OPEN 不因此变更。

## 17. Release / Container Update

通过上述 gate 后，从验收工作树独立执行 `docker compose build api agent-worker`、`docker compose up -d --no-deps --wait api agent-worker`；没有将 test 容器晋升正式容器。日志 `production_build.log`、`production_startup.log`。

| 正式容器 | Image ID | 状态 |
| --- | --- | --- |
| roamsync-api | sha256:75cc7fbd6a49e0fe2a3683903f4c98d5400498c9be7a961299ef366c5cf22b36 | running / healthy |
| roamsync-agent-worker-1 | sha256:514bd7295fbbeefa6c51ba94182f4f53522c075b73a0951a76ae414b46c3bd87 | running，python app.agent_worker 进程存在；未配置 Docker healthcheck |
| roamsync-web | sha256:9794c7029f6ca25800174e7072d701065df2b6bbff6110dd168f4c6b614f99b8 | 既有镜像，running / healthy |
| roamsync-postgres | sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73 | running / healthy |

API/worker 启动约 2026-09-30 11:37:23 上海时间；每个正式容器 144 个运行文件逐项匹配最终 manifest。`health/live`、`health/ready`、Web `/trips` 均 HTTP 200。Worker 启动验证不冒充实际完成远程规划任务。

`production_smoke.json` 六轮真实 HTTP：你好 → 独行担忧 → 玩三四天 → 南京怎么样 → 西湖可靠来源历史/确切形成年份 → 明确南京三天规划，全部状态正确、HTTP 200。来源正文含支持背景并自然显示确切年份缺口；最后 prepared Brief destination 南京、duration 3，Planning 提问具体日期。普通回答无持续 date/budget 追问。

Smoke 用独立 synthetic AssistantSession，未 reset Demo、未确认候选/旅行创建。前后 **178 Trips、105 PlanningRuns、全部 Trip.version 一致**。第一次 smoke 启动缺 PYTHONPATH，import 即失败且无 DB 写入，正确设置 PYTHONPATH 后完成六轮；不混为业务失败或隐去。正式数据保留额外 synthetic 会话用于证据，不删除已有资料。

## 18. Remaining Limitations

- Holdout 是解封后的 source replay，非盲；旧 need 39/50、exact assertion coverage34/50。未覆盖的信息与两个错题可复查逐题记录。
- Reviewer 只有 Codex；bounded exact assertion/scope 检查不能证明一般语义蕴含、来源全球真实性、general model facts 或跨领域泛化。
- Source `rec_03` 一次可选日期邀请、`rec_04` 一条 unsupported 修辞引文；普通 general advice 仍可能含未验证的安全性、受欢迎程度或“最佳”等判断。
- Real goal 分类15/16，runtime 正确并不代表所有自然语言目标均精确分类。Router 仍为有限规则，没有通用语言理解保证。
- JSON 有界修复提高已观察错误的可靠性；外部模型超时、不可用和两次无效输出仍可能失败，最终零错误不是长期 SLA。
- 未接 Travel Facts，实时信息安全降级；mixed live/stable 问题可能保守漏答稳定部分。预旅行明确请求后的正式 trip/run 创建仍需要既有日期/确认流程。

## 19. Deferred Issues

记录而未扩展开发：地理/茶地点/连续时长/UNESCO title-only 的 topic recall；人工堤岛时期与地质形成区别；mixed need 子问题覆盖；建议隐含事实/引文语义核验；单次可选 CTA；更多独立标注与冻结新 holdout。

未 cherry-pick `5f9f5e5`，未新增 Agent、FactResolver、Travel Facts/Weather、embedding、语料、Experience Knowledge、long-term memory、Stage 2.2、UI redesign 或 Planning Graph 重构。无 Obsidian 写入。

## 20. Recommended Next Slice

建议下一次经用户选择后，仅做**现有来源回答覆盖与独立评审**：先冻结新协议和未解封 fixture，由独立 reviewer 验证已有资料检索遗漏、mixed 子问题与建议内隐含事实。复用 Runtime/Renderer/Identity/Brief/Adapter 和权限生命周期；不自动启动新 Phase 或接入 Travel Facts。本轮到此关闭，Demo/Ledger 后续范围保持原状态。

## Evidence index

- `final/source_snapshot.json`、`audit_binding.json`、`acceptance_binding.json`：源码与 gates 绑定。
- `final/real_model.json`、`holdout_review_live.json`：最终执行原始输出/claims/tool/provider observations。
- `final/manual_review.json`、`metrics.json`：逐条评审与汇总，unsupported embedded caution 另计。
- `final_focused.xml`、`final/backend_final.xml/log`：当前最终测试数字。
- `final/web_test.log`、`web_typecheck.log`、`web_build.log`：Web 检查。
- `final/production_build.log`、`production_startup.log`、`container_status.json`、`production_smoke.json`：正式发布与 smoke。
- `holdout_v1.json` 与历史 before/attempt/interrupted artifacts：不可改写的旧 fixture 与早期诊断记录。
