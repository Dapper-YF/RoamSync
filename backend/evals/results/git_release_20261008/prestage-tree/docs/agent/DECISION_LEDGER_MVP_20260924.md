# Stage 2.2 — Decision Ledger MVP（进行中）

状态：**Decision Ledger MVP REMAINS OPEN**。以下是 2026-09-24 的代码与真实运行结果；不覆盖 Stage 0、Goal-Aware Planning 或 Stage 2.1 的历史证据。

## 修改前的问题

Planner 输出 `activities + explanation`。每项活动虽有自然语言 `reason`，但不存在逐项、机器可读的 decision provenance。`difference_summary` 有预算、路线调整和 Goal Check 等派生事实，不回答某个移除、新增或缩短为何发生。Stage 2.1 有效 baseline 曾出现反馈“步行太多”但候选步行 174→174 分钟；合法性与是否回应反馈必须分开。

## Decision Ledger Model

`DecisionLedgerEntry` 位于 `backend/app/schemas.py`，随 `PlannerDraftOutput` 同一次结构化响应返回。字段包括 `decision_id`、七种 `action_type`、既有/新增目标引用、`before/after`、有限 `primary_reason`、`supporting_evidence`、`goal_refs`、`memory_refs`、`semantic_refs` 和可观察 `tradeoff_cost`。历史 `CandidatePlanSnapshot` 的 ledger 为 `null`；新 Planner 输出必须显式包含列表。没有新数据库表或迁移。

## Planner Contract

`backend/app/openai_planner.py` 在同一次 Planner 响应中要求 Candidate 与 Ledger；没有增加单独的解释模型。Schema 保持现有地点 ID/日期边界。模型必须为新增、移除、缩短和至少 30 分钟的移动写记录；路线尚未查询时不得把“减少步行”作为已实现事实。`explanation` 仍是用户可读文本，不是机器证据来源。

## Evidence / Provenance

来源类型限定为 Goal、Decision Context、Decision Memory、Activity Semantics、Route Fact、Execution State、Provider Fact。校验读取正式 itinerary、Goal、同 Trip/同目标日的拒绝 Memory、正式活动语义，以及前后真实路线；不读取 Chain-of-Thought。无根据的 `fact_key` 或与正式值不一致的 `value` 被拒绝。新地点引用的 provider fact 必须指向正式候选列表的 ID。

## Ledger Validation

`backend/app/decision_ledger.py` 在 AMap route enrichment 和现有时间修复之后检查最终 Candidate。其输出被并入现有 `PlanValidationResult`，但职责独立于原有行程合法性 Validator。缺失的 destructive 记录为 `decision_provenance_missing`，缺失的新增依据为 `unsupported_addition`。检查 action 与实际 diff、目标/记忆/语义引用、前后时间与时长、路线数值和代价；失败先进入现有一次 review，仍失败则无 PlanRevision。系统隐式保留的 locked/active/completed 活动不被误判为删除。`preserve` 表示身份保留，不表示时间不变。

当前状态仍有局限：部分 evidence key 与事实引用的 contract 对 DeepSeek 不够稳定。Ledger validator 会阻止虚假记录，但模型可能无法在有限 review 内修正，因此本阶段尚未获得完整成功的生产 Revision。

## Goal Integration

仅允许引用本次实际存在的 `end_before`、`max_walking_minutes`、`pace`、`minimize_walking`、`preserve_existing`。`satisfy_hard_goal` 必须引用实际硬目标。Goal Check 仍单独负责候选是否满足目标，Ledger 不替代它。

## Memory Integration

`memory_refs` 必须对应当前 Decision Context 检索到的 `source_revision_id`。真实 Run `5d69f075-ab19-4f64-ae96-1a49311b60a9` 和 `e13e0a61-56aa-4649-bb31-63646926562e` 均确认携带 1 条拒绝 Memory 到 Planner，但在 Planner 输出校验处失败，不能声称 Memory 已影响一个有效 Revision。

## Activity Semantics Integration

`semantic_refs` 对照正式 `importance`、`can_skip`、`minimum_duration_minutes`；删除不可跳过活动或缩至最短时长以下仍由已有 deterministic validator 拒绝。Ledger 另拒绝与正式语义不符的依据，不把 Planner 自述当作活动权限。

## Route Evidence

步行与总路线的 before/after 由正式 RouteLeg 和 enrichment 后的 CandidateRouteLeg 计算，估算路线不作为已核验 route claim。`reduce_walking` 需要真实减少以及相符的 before/after evidence；否则 `decision_route_claim_unsupported` 或 `decision_route_evidence_missing`。前端不展示未经验证的路线改善。

## Live Candidate

独立复制 Trip `46dbb354-78a8-4d93-bb4c-2dcae0903118` 保留了 5 项活动和 4 条正式路线，未覆盖原有 artifact。Run `15b99a1b-21fd-4901-b629-6a1c87b92b73` 走到真实 Tavily、AMap、DeepSeek、Candidate、路线与校验，产生 6 条 Ledger；步行 **174→174 分钟**，却声称 `reduce_walking`，因此被拦截，无 Revision。该 Run 早于后续契约校正，同时也是虚假路线声明的有效失败证据。

同一副本 Run `bbebee74-f8d0-4223-b9c2-67cea51c0858` 生成 5 条 preserve 记录，但缺 Goal/Semantic 引用，且重复记录同一 preserve；Ledger 校验失败，无 Revision。Run `44dd419b-c610-46ec-ba02-a586f225ac94` 因“不新增或删除活动”触发既有 Intent 澄清，Planner 未到达；未改 Intent。

为验证 Memory 共存，在已有 Stage 2.1 Trip 上独立启动两条新 Run（不覆盖之前的结果）：`5d69f075-ab19-4f64-ae96-1a49311b60a9` 的候选引用了未授权地点 ID；同 wording 的有界重试 `e13e0a61-56aa-4649-bb31-63646926562e` 漏掉必需 `decision_ledger` 字段。两者皆为 `planner_invalid_output`，无 Revision。详见独立 [live artifact](../../backend/evals/results/decision_ledger_stage22/live_20260924.json)。

## Decision Ledger

真实候选已证明 Planner 有时能输出结构化 Ledger；目前尚未证明一个完整、经验证并持久化的正常 Live Ledger。不得将失败 Ledger 展示为用户可置信的解释。

## Unsupported Changes

测试确认缺失删除/缩短/重要移动记录会失败，新增无目标或真实 Provider 依据会报 `unsupported_addition`。`supported_change_count` 与 `unsupported_change_count` 根据实际变更计算；不生成综合 Agent 分数。真实 Run 的未改善步行声明也被阻止进入 Revision。

## Explanation Faithfulness

当实际路线未减少步行，Candidate explanation 中的减少步行声明触发 `decision_explanation_unsupported`。前端新增的“为什么这样调整？”只读 `decision_summary.status=validated` 且 `evidence_status=validated` 的条目；模型原始 explanation 不用于生成该区域。历史 Revision 显示“暂无结构化调整依据”。

## Frontend

`web/src/components/DecisionSummary.tsx` 是默认折叠区域，展示活动、动作、核实后的时间/时长及原因，保留现有 Accept/Reject 流程。API 通过既有 `difference_summary` JSON 传递 validated summary；无需前端新 endpoint。UI 测试覆盖删除、保留、缩短、折叠、无效条目过滤及历史兼容；既有 Accept/Reject 测试继续通过。

## Recovery Smoke

`test_recovery_addition_without_basis_cannot_become_revision` 使用带 execution recovery context 的候选确认无依据新增触发 `unsupported_addition`。这是确定性测试，**尚非真实 production recovery run**，因此 Recovery Exit Gate 仍未通过。

## Tests

新增 `backend/tests/test_decision_ledger.py`，覆盖 schema、action/diff、Goal/Memory/Semantics、路线 evidence、虚假步行说明、无依据新增、历史快照及 Revision read model。新增 Web DecisionSummary 测试。最终全量结果见下节。

## Regression

最终 Linux/PostgreSQL 全量回归 **347 passed, 2 warnings**（退出码 0）；Web **94 passed**，TypeScript typecheck 与生产构建通过。生产依赖预检返回 `DEMO READY`。回归通过不替代尚未达成的 Live Revision 与 recovery Exit Gate。

## Known Limitations

1. 尚无同时覆盖 Goal + Context + Memory + Semantics、经 Ledger 验证后生成 PlanRevision 的真实生产链。
2. 尚无真实 production recovery smoke；仅有确定性防护测试。
3. Planner 在 live 中出现缺 Ledger、未授权地点 ID、重复/错误 evidence；当前安全边界会拒绝，不应描述为完成的 Agent 决策能力。
4. 路线修复可能改变 Planner 提出的时刻，因此原始 Ledger 会变旧；目前要求模型在有界 review 中修正，未实现系统生成的修复决策记录。
5. 不评价方案是否做了最佳取舍，也不进入 Stage 2.3。

## Stage 2.3 Recommendation

Stage 2.2 的剩余 Exit Gate 通过前不要启动 Stage 2.3。先稳定结构化输出与经过修复后的 Ledger 对齐，再用独立正常规划和真实 recovery 各获得一条完整证据链；之后才讨论多种合法方案之间怎样取舍。
