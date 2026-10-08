# Agent Reliability Phase — Entity Resolution & Structured Output Stability

日期：2026-09-28。范围：实体引用绑定与结构化输出稳定性；Decision Ledger MVP REMAINS OPEN（shadow）。

## 当前真实问题

2026-09-27 的真实 shadow 记录中，三次第一轮均产生 pending Revision，真实 Reject feedback 持久化并进入下一轮 Context；第二轮为 0/3，两次地点引用错误、一次 malformed JSON。Memory retrieval 与 Planner reached 可证实，身份绑定仍不稳定。

实际仓库为 `E:\Study\RoamSync`。当前工作区 `roamsync-staged` 是旧暂存副本。开始本轮时生产 Provider 已改成 GLM / glm-5.3-flash / high / streaming / 180 秒；最新已记录 Linux/PostgreSQL 基线是 368 passed，不能用旧 DeepSeek 配置描述本轮。

## Root Cause

修改前沿 Intent → Goal → Decision Context → Research Candidates → Planner Input → Structured Output Schema → Candidate Parse → Place Resolution → Route Enrichment → Validator 检查。

1. **Existing Activity**：模型仍输出 place_candidate_id；服务端根据 allowed place 的 replaces_activity_id 反推 Activity。既有身份和新增地点共用一个身份字段，模型要重新选择已知地点。
2. **New Activity**：所有地点使用长 UUID enum；GLM 单独用通用 ref_NNNN 编码，但其他 Provider 没有，且编码未区分 Activity/Place/Revision。
3. **Allowed Set**：内部 prompt、动态 enum、resolver 使用同一 allowed dict；它们的一致性不能消除模型复制 UUID 和混用身份域的错误。
4. **Memory B**：检索已按同 trip/day/formal version 隔离，摘要并非完整 Candidate A；但正式行程、Goal、路线、语义分区与兼容别名重复。此前必填 decision_ledger 还要求多个身份、证据与理由字段，大幅扩大 JSON contract。
5. **后续链**：parse/resolution 在路线计算前；路线由 AMap 查询，Validator 与硬 Goal 检查决定 Revision，accept 再事务性校验；未放宽约束。

## Existing Activity Identity

ExistingActivityDecision 仅使用 source=existing + activity_ref=activity_N，加日期、开始时间、停留时长、交通方式与语义理由。place_candidate_id 不进入这类模型输出。服务端继承真实 activity/place/source/cost；preserve、move、shorten、extend 保持实体身份。

## New Candidate References

NewActivityDecision 使用 source=candidate + candidate_ref=candidate_N；短引用在一次规划调用及其格式修正内稳定。模型不输出 provider/database UUID。新增候选仍来自上游已核实来源；同名不能授权一个未知引用。

## Deterministic Resolver

`PlannerEntityBindings` 从服务端 allowed facts 生成引用表、模型 prompt 和动态 schema。`resolve_planner_activity_references` 精确绑定两种域，拒绝不存在的引用、跨域字段、重复地点和越界日期，返回真实 CandidatePlanSnapshot 后才进入 route enrichment。没有名字相似度修复。

用户/研究提及正式活动时，先按当前 day scope、activity UUID、normalized exact name 和已有 Activity/Place 名称别名唯一绑定；多义进入既有 clarification 策略。研究阶段发现唯一正式地点则沿用其 place/activity，避免重新保存同名地点。既有其他自然语言路由规则没有扩大。

## Planner Schema Simplification

实际 wire schema 只有 activities 与 explanation；每项互斥引用和 proposed schedule/reason，不含坐标、UUID、来源、费用、路线 ID、before/after。shadow Ledger 不再是必填大契约。既有约束纠错的 previous_plan 也使用同样的 source/activity_ref/candidate_ref，移除内部 candidate_id，并将已知路线端点确定性映射到同一短引用；未知上一候选不重新授权。内部兼容上下文、持久化 snapshot 与 provenance/debug 仍保留真实身份；它们不是模型决策契约。

## Memory Context Compression

保留三条以内明确 Reject 摘要的 source_revision_id、target_day、reason_code/text、candidate metrics；摘要活动引用列表最多十项。去掉重复 current_formal_plan、planning_goals、formal_route_facts、user_preferences 和 Ledger refs；editable/protected 活动、Goal、真实路线与执行边界仍提供一次。数据库原反馈与 same trip/day/formal version 隔离保持。评测记录每次 Planner 输入压缩前后字符数与 Provider 实际 token usage。

## JSON Reliability

当前实际 Provider 使用 GLM streaming Chat Completions 的 json_object 模式，动态 schema 作为结构指导；真正的 enum/身份校验由服务端执行，不能把 JSON Object 模式声称为 Provider 强制严格 schema。DeepSeek-compatible 分支继续使用 Responses text.format.json_schema 或既有 Chat JSON Schema fallback；本轮真实 10+10 批次验证的是 GLM，DeepSeek 分支由契约测试验证，未宣称其真实批次通过。

使用 json.dumps 构造请求，json.loads + strict Pydantic 解析。SDK 没有现成且已验证的无语义修复能力，因此不新增 trailing comma 修复。仅保留完整 Markdown JSON fence 的既有 envelope normalization。未知 candidate_99 不替换。结构化修正最多一次，反馈限制 600 字符，附前次可见输出（最多 16000 字符），不保存 thinking。

## Error Classification

planner_schema_failure、planner_invalid_reference、planner_malformed_output、planner_semantic_constraint_failure、provider_failure、candidate_validation_failure。兼容外层 planner_invalid_output；trace/error_details 与评测记录细分 category。Provider outage 独立计数，不伪装成结构错误。

## Normal Reliability Benchmark

固定 travel-decision-agent-demo、2026-10-20、相同 request、每次 reset。使用真实 production runtime、Intent provider、Tavily、Research、Planner、AMap、Validator、Revision persistence。observer 只记录，不改策略。运行十次，逐项记录 reached/parse/resolution/validation/revision。

## Memory Replan Benchmark

十次 reset → First Planning → pending Revision → 显式 too_rushed 反馈“五项活动仍显得紧凑，希望多留休息与停留时间” → 持久化 Reject → 第二请求“请再调整一次…” → 检索 → Planner B → Revision。使用与 Web Reject API 相同的 repository service；无 accept。每个样本比较正式 activities/routes/version 未变。反馈文案以 artifact 的实际 FEEDBACK 为准。

## Success Rates

MEASURED：固定批次 10 个 Normal 样本、10 个真实 Reject/Memory 循环，共 30 个生产 PlanningRun、33 次 Planner 生成调用。门槛保持 Normal Revision >=9/10，First Revision >=9/10，Second Parse/Revision >=8/10，成功 Reject 样本中 Memory 检索率 100%；没有把成功标准提高为 100%。

| 指标 | Normal | Memory First | Memory Second |
|---|---:|---:|---:|
| Intent reached | 10/10 | 10/10 | 10/10 |
| Planner reached | 10/10 | 10/10 | 10/10 |
| Structured parse | 10/10 | 10/10 | 10/10 |
| Reference resolution | 10/10 | 10/10 | 10/10 |
| Candidate valid | 10/10 | 10/10 | 10/10 |
| Pending PlanRevision | 10/10 | 10/10 | 10/10 |

Feedback persistence 10/10；Memory retrieval + visible to Planner 10/10（eligible denominator=10）；完整两轮成功 10/10。20 个 reset 样本的正式 activities/routes/version 全部未变，没有 Accept。

终止 Provider 故障 0/30；malformed JSON 0/30；invalid reference 0/30；schema/semantic/candidate validation 终止错误均 0。所有 33 次已记录 Planner 生成调用均在第一次结构化输出中通过 parse/resolution。首轮 Memory Planning 中，既有业务约束/Goal 纠错额外调用了 Planner 3 次；相关 run 与 call count 已单独记录。表中的 Candidate valid 是每个 Run 的最终校验结果，成功率包含原有的有界业务纠错，并非宣称每个首个候选均无需调整。

历史 2026-09-27 第二轮为 0/3（引用错误 2/3，malformed JSON 1/3）；本轮观察到错误率降低为 0/10。Provider 在本阶段之前已由 DeepSeek 改为 GLM，因此这不是相同 Provider/config 的受控因果比较，不单独把全部提升归因于本轮改动。

字符数是同一序列化方式下的 context body；token usage 是 Provider 实际返回的 input/output/total usage，包含 Provider 的计费口径。分组均值与耗时如下：

- Normal：context 27149.2 → 17867.2 字符，平均减少 34.22%；累计 135607 tokens；单次 47.73–125.29 秒。
- Memory First：context 27585.15 → 18181.08 字符，平均减少 34.12%；累计 178696 tokens；单次 69.83–185.85 秒。
- Memory Second：context 29157.6 → 18541.6 字符，平均减少 36.43%；累计 140260 tokens；单次 47.11–165.27 秒。

该批次的精确 run/revision/source-memory refs、成功 counts、失败 categories 与分母见 `backend/evals/results/agent_reliability/reliability_20260928.json`。预备调用 af8a068c-17f9-4188-a80f-2230b2df96d9 产生 pending，但评测记录器字段名错误；修正后重新开始固定批次，该预备调用未计入。

## Frontend Error UX

Planner 内部契约失败展示“这次方案生成失败，我没有应用任何更改。可以重试本次需求。”；开发 errorDetails 保留原始分类。普通 UI 不显示 UUID/candidate contract。失败 Run 的重试直接调用 PlanningRun 创建接口，沿用原 request、Trip 与 run type，确保独立 run；即使存在 Assistant Session，也不重新经过语义路由。网络提交失败仍保留原有幂等机制。不调用 Reject、Memory 写入或 formal mutation。

## Tests

引用正反例、两种域字段混用、四类既有调整身份保持、未知引用不猜、wire schema/prompt 一致和无 UUID、Memory 大小与原始事实不变、唯一正式活动优先绑定、模糊/多义拒绝、Web error masking、原请求 retry、独立 run/无重复 Memory/正式状态不变。

## Regression

VERIFIED：全部生产变更与新增 metrics 用例合并后的 Linux 容器 / 隔离 PostgreSQL 完整回归 391 passed、2 个原有 Starlette warnings。Web 100 passed；Assistant Session 下独立重试分支的 focused 19 tests、pnpm typecheck 与 pnpm build 再次 PASS。React act warning 为既有非失败 warning。无数据库 migration 变更。最终镜像构建中的 Linux Web 100 tests/typecheck/build 再次 PASS；api/web/postgres healthy，worker running，readiness 与 Web HTTP 均 200。最终 Demo 保留第二轮 pending Revision，Trip.version=1，未 Accept。

## Remaining Failure Modes

LLM/provider 随机性、格式错误、语义日程约束、AMap 路线不可用及网络中断仍可能发生。shadow Ledger unavailable/invalid 仍记录并隐藏未经核验理由。现有长 UUID CandidatePlanSnapshot 是系统持久化契约，不再要求模型维护。

## Final Status

Agent Reliability MVP COMPLETE。全部本阶段 Exit Gate 通过；Decision Ledger MVP REMAINS OPEN，Stage 2.2 OPEN，shadow 保持。此结论适用于本次固定 Demo 与当前 GLM 配置，不是所有请求或 Provider 的普遍成功率承诺。

## Next Recommendation

保留 travel-decision-agent-demo 作为最终 Demo stability fixture，保留本次独立 artifact 与报告。本阶段完成后停止；不自动进入 Stage 2.3、Critic、Reflection、Long-term Memory、Preference Learning、Multi-Agent、新 Recovery 或导航能力。
