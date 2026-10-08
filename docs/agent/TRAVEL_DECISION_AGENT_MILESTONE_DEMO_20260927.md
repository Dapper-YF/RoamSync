# Travel Decision Agent MVP — Milestone Demo（未通过现场 Exit Gate）

日期：2026-09-27。状态：**依赖预检通过，完整两轮现场链未通过**。本文件区分已验证能力和仍需真实验证的能力；不能把 `DEMO READY` 的外部依赖预检误读为端到端 Demo 成功。

## 阶段成果

已完成的生产能力包括 Goal-Aware Planning、Decision Context Engine、Decision Memory、Activity Decision Semantics。此次组合了独立可重置的真实 Trip、前端语义显示和按真实检索结果展示的记忆提示。Decision Ledger 仍为 **OPEN**，本轮未修改其 schema、reason taxonomy、DeepSeek 输出契约或 Recovery ledger。

## 相比 9 月 21 日的变化

9 月 21 日主要证明活动执行、延长停留、提前离开、延误传播、slack、disruption detection、Recovery Planning 和 PlanRevision：现实变化后，系统知道什么时候需要重新规划。现在已有 Goal、Decision Context、Decision Memory、Activity Semantics、Goal Satisfaction：Agent 能把用户目标、正式路线与执行现实、明确拒绝反馈和活动重要性带入决策。**本次新 Demo 尚未证明这些能力在同一条两轮 live 链中稳定组合成功。**

## Demo Trip

- 独立 ID：`00000000-0000-4000-8000-000000000003`，标题为 `Travel Decision Agent Demo · 杭州人文一日游`，日期为 `2026-10-20`。
- 5 项杭州真实地点；杭州 adcode `330100`、citycode `0571`，地点坐标齐全。
- 真实 AMap Route 2.0 路线 4 条，非估算；正式行程无冲突。当前最终 fixture 的步行路线时长合计 174 分钟，结束时间为 18:04，存在减少步行和提前结束的真实空间；较早的锁定午餐变体结束更晚，不能混用其数据。
- 专用 Trip 的候选地点范围已收敛为 5 个正式地点；没有预造 Candidate 或路线结果。最初曾设置一项午餐 `schedule_locked`，因两次失败均指向第 3 项且午餐正好是第 3 项，在没有完整输出证据的情况下将其作为 fixture 假设移除；必去与最短停留语义不变。移除后链路推进至 Validator，但仍未产出 Revision。

## Activity Semantics

- 中国美术学院美术馆：`must_do`、`can_skip=false`、`minimum_duration_minutes=60`；浏览器真实显示“必去”“至少 60 分钟”，正式停留 90 分钟。
- 西湖·断桥：`high`、`can_skip=true`，前端显示“比较想去”。仓库枚举没有 `preferred`，未为 Demo 改 schema。
- 河坊街·南宋御街：`low`、`can_skip=true`，前端显示“可选”。
- 雷峰塔和绿茶餐厅·湖滨店：`normal`。当前专用 fixture 无锁定活动；这不是必去和最短停留的替代品。
- 尚无通过校验的 live Candidate，不能声称本轮 Planner 实际保留了必去活动或遵守最短停留。

## First User Goal

固定请求：

> 请帮我调整 2026-10-20 当天的行程。我希望轻松一点，尽量少走路，18:00 前结束，现有活动尽量不要大改。

## Goal Extraction

现有生产链仍执行 Intent、PlanningGoals 和 Decision Context 构建。失败 run 的 `decision_context_summary` 记录目标日 `2026-10-20`、5 项正式活动、正式路线状态 `available`、4 项可编辑及 1 项受保护活动。由于本次没有 PlanRevision，**前端 Goal Card 尚无本专用 Trip 的 live 显示证据**；不能把已有 Goal-Aware Demo 的成功数据移作本次成果。

## First Candidate

5 次真实同文请求尝试均未获得 pending PlanRevision：

1. `11677f8d-2cfb-4a26-81e6-c93cfae809e0`：`planner_invalid_output`，第 3 项引用未核实地点。
2. `431e6693-92aa-4c99-8566-3f42e51f2f77`：同类失败。
3. 收敛候选范围并重置后，`7bdb175e-af05-45ad-bdc6-1c55135cdd5e` 曾到达 Candidate、AMap route enrichment 和一次受限修正；修正后的 explanation 不符合既有结构化格式，`planner_invalid_output`。记录 token usage 36,002。
4. `576523d0-a70b-4f09-9644-9fbef8bd81ba`：再次引用未核实地点，`planner_invalid_output`。
5. 取消可选午餐锁定后，`29dbac6c-030c-4a5e-aa25-74cf643990b3` 到达 Candidate、路线和 Validator 阶段，最终 `planner_constraints_unsatisfied`；错误为 `decision_evidence_unresolved`、`decision_memory_basis_missing`、`decision_tradeoff_cost_unverified`，记录 token usage 56,072。没有 pending Revision。

前四条属于 reset 前的专用 Trip 运行，原 run 行被专用 reset 删除；错误类别和 ID 保存在独立结果 artifact。第 5 条仍在当前专用 Trip 数据库中。本轮没有放宽校验、伪造地点或 bypass Planner。

## Goal Satisfaction

未到达有效 Candidate 后的完整 Validator / Goal Check，因此没有本 Trip 的真实结束时间、步行达标数值或目标满足结论。历史 Goal-Aware Demo 的 17:55/72 分钟数据不用于此处。

## Reject Feedback

无 pending PlanRevision，因此未执行真实 Reject；`reason_code`、`reason_text` 的生产持久化在本次两轮 Demo 中**尚未验证**。既有后端拒绝反馈测试仍通过。

## Decision Memory

现有 retrieval 只选择同 Trip、同目标日、同正式版本的明确拒绝反馈。新增 read-model 映射与 UI 提示只显示该 run 的 `trigger_snapshot.decision_context_summary.decision_memory.feedback`，包含来源 Revision ID、reason code/text，绝不从用户第二轮消息臆造记忆。单元测试通过；本次因第一轮无 Revision，**未取得真实第二轮 memory retrieval / Planner 可见证据**。

## Second Candidate

未启动。不能把“请再调整一次”在没有上一轮真实 Reject 的情况下当作有效 Memory Demo。

## Frontend

真实浏览器打开专用 Trip，确认 5 项活动、中文语义标签、正式路线和最新失败信息可见；最新运行在前端明确显示 `decision evidence unresolved`、`decision memory basis missing`、`decision tradeoff cost unverified`，没有误报成功。未看到本专用 Trip 的 Goal Check、Before/After、Reject 或第二版方案，因为后端未产出 pending Revision。Decision Summary 仍折叠；只有 `validated` 条目才会展示，不作为 Demo 依赖。

## Reset

在仓库目录或任意目录执行 `powershell -NoProfile -ExecutionPolicy Bypass -File E:\Study\RoamSync\scripts\reset-travel-decision-demo.ps1`。该命令仅删除并重建固定 ID 的专用 Trip，由 PostgreSQL 外键级联清除其 PlanningRuns、PlanRevisions、反馈、路线和执行状态，再以真实 AMap 路线重建。它不触碰 Stage 2.2 eval Trip 或 artifact。重置命令已在真实容器执行并在隔离 PostgreSQL 测试覆盖。

## Preflight

`powershell -NoProfile -ExecutionPolicy Bypass -File E:\Study\RoamSync\scripts\demo-preflight.ps1` 检查 Backend、Frontend、PostgreSQL、worker、Tavily、AMap POI、AMap route、DeepSeek。最终全部通过，输出 `DEMO READY`；**仅代表依赖可用，不代表两轮规划通过**。发现宿主 PowerShell 的旧 `TAVILY_API_KEY` 覆盖 `.env` 后，仅在启动进程中移除覆盖并重建 api/worker，没有更换 provider 或修改 Agent。`start-travel-decision-demo.ps1` 提供清除这一继承覆盖、启动、预检、重置的入口；该整合入口尚未完整执行验收。

## Three Stability Runs

完整链 `Reset → First Planning → Goal Check → Reject → Memory → Second Planning → PlanRevision`：**0/3**。5 次第一轮尝试均被生产校验阻断，因此不能开展三次稳定性计数。失败证据：`backend/evals/results/travel_decision_demo/live_20260927.json`。

## Backend Regression

Linux/PostgreSQL 全量：**350 passed, 2 warnings**。专用 seed/reset、活动语义和清理范围有新增测试。未调整 deterministic validator 或正式应用边界。

## Web Regression

**96 passed**，TypeScript typecheck 与生产构建通过。新增当前 run 的真实 Memory 提示与 API 映射测试；浏览器只验证了专用 Trip 的活动语义和失败呈现。

## Known Limitations

- **Decision Ledger remains open**，不得宣称 Agent 已会最佳取舍、Critic/Reflection/Multi-Agent/长期 Memory 已完成。
- 当前 Milestone 专用场景的 DeepSeek 结构化输出不稳定；取消可选锁定后又确认 Decision Ledger 校验是当前生产 Revision 路径的实际闸门。虽然 Demo 视觉内容不依赖“为什么这样调整？”，但隐藏该 UI 不能绕过生产 Ledger 校验。第三方依赖预检通过不消除这些问题。
- 不存在本次有效 First PlanRevision、Reject、Memory 第二轮或 3/3 稳定性证据。现场不能按完整 Demo 成功口径汇报。
- 已有 Memory 为同 Trip/日/版本的短期显式拒绝反馈，不是长期偏好学习。

## 下一阶段

保持 Stage 2.2 和 Decision Ledger 为 OPEN。要正式开放本 Milestone Demo，必须先在当前生产契约下取得第一轮 pending Revision，再按真实 Reject、Memory retrieval、第二轮 Revision 和 3 次 reset 完整运行逐项复验；本轮不以修改 Ledger/Planner 输出契约、假候选或假路线绕过。
