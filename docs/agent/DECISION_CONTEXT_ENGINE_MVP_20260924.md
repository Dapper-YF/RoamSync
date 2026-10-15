# Decision Context Engine MVP — Stage 1.1

日期：2026-09-24  
范围：在既有 Goal-Aware Planning 主链中建立 Planner 前的确定性 Decision Context。

## 修改前的问题

正式路线、导航 ETA、延误、slack 与运行时保护状态分别存在于不同 read model。Planner 输入曾依赖多处局部拼装，导致活动可能同时出现在 runtime protected 与 editable 集合中；恢复规划也无法证明当前 ETA 和正式 route legs 已真正进入 Planner。

## Decision Context Model

新增内部 read model `decision_context`，仅选择当前 target day 的事实：

```text
goal_context
formal_itinerary
route_context
execution_context
protected_constraints
user_preferences
active_disruption
provider_facts
provenance
```

它复用 `PlanningContext`、持久化 RouteLeg、执行/导航投影与既有 Goal Model；不新增数据库表、不重复调用 AMap、不保存 prompt 或 Chain-of-Thought。

## Goal Context

直接复用 `PlanningGoals`，包含 hard/soft goals 及 `user_goal_and_grounded_intent` provenance。没有第二套 Goal schema。

## Route Context

每条正式路线向 Planner 前输入提供起止 activity ID、交通方式、距离、时长、步行距离/时长和 provider source。没有正式 leg 时明确为 `route_fact_status=unavailable`，不会伪造路线。

## Execution Context

Recovery Context 提供已完成活动、当前活动、导航目标、`current_eta`、`delay_minutes`、`minimum_downstream_slack_minutes`、first impacted activity、risk state 与 active disruption；来源为 execution/navigation/disruption projection。

## Protected / Editable Contract

`protected_constraints` 是唯一修改权限来源：completed/skipped、当前运行活动、navigation target、`schedule_locked` 和已有请求保护均进入 protected。editable 由 target-day activity IDs 减去 protected 得出。

Planner 前会确定性检查：

```text
protected ∩ editable = ∅
所有 activity / route endpoint / execution reference 都存在
goal target day 属于 formal itinerary
```

失败返回 `decision_context_invalid`，不会把矛盾 Context 交给模型。

## Context Provenance

每个真实 PlanningRun 的既有 `trigger_snapshot` 记录脱敏 `decision_context_summary`：目标日、activity 数、route availability、protected/editable IDs、执行字段是否存在和各类事实来源。它不记录完整 prompt、授权信息或模型推理。

## Normal Planning Live Run

Goal-Aware Demo reset 后运行：`cd7c6df1-cc26-4dd1-9379-0d99a806ee21`。

- 真实 Tavily、AMap、DeepSeek、Validator、Goal Check、PlanRevision 均到达；
- revision `5252074b-36f6-4807-bbec-69ebc76b03db` 仍为 `pending`；
- Validator 通过；17:40 ≤ 18:00，步行 61 ≤ 80 分钟；
- Demo fixture 未修改，未自动应用 revision。

## Recovery Live Run

旧 Stage 0 trip 保留不动，从其 duplicate service 创建独立副本 `e12a0e34-1001-47fc-b266-6dc5eef3ea5e`。

- 真实 navigation observation 注入 +45 分钟；`current_eta=11:30`、minimum slack `-34`；
- recovery run：`3ed17781-4175-49c4-8310-79645e51c1a7`；
- Context Summary：5 项 formal activities、route facts available、4 protected、1 editable，所有 ETA/delay/slack/current/target 字段存在；
- DeepSeek 与 Validator 均 reached；最终为 `planner_constraints_unsatisfied / candidate_route_set_mismatch`。

这不是 Context 缺失：Planner 已得到正确事实但仍生成路线证据不完整的候选，记录为后续 Trade-off / Candidate Quality weakness。本阶段不修 Planner 策略。

原始机器可读 artifact：`backend/evals/results/decision_context_stage11/decision_context_engine_mvp_20260924.json`。

## Planner 现在实际看到了什么

输入按 `USER GOALS`、`CURRENT FORMAL PLAN`、`ROUTE FACTS`、`EXECUTION STATE`、`PROTECTED ACTIVITIES`、`EDITABLE ACTIVITIES`、`USER PREFERENCES`、`EXTERNAL FACTS` 分区传递。`allowed_places` 只包含 editable 既有活动和已核实候选，无法引用 protected activity。

## Tests

- Context route/execution/provenance；
- completed/current/navigation target/locked 不可编辑；
- protected/editable overlap、未知 route endpoint invariant；
- Planner input partition 与 runtime protected exclusion；
- Goal-Aware 既有测试持续通过。

## Regression

Linux/PostgreSQL：`325 passed, 2 warnings in 40.44s`。

## Frontend Impact

无默认用户界面改动，避免增加明天 Demo 风险。Goal Card、PlanRevision 与 Accept/Reject 保持原样。

## Remaining Weaknesses

- Context correctness 不保证模型能产生完整候选路线；本次 recovery 被 `candidate_route_set_mismatch` 拒绝。
- Stage 1.1 不新增 Activity importance、Decision Memory、Critic 或 RAG。

## 下一阶段建议

等待下一条指令后再考虑 Stage 1.5 Decision Memory；不要在本阶段继续扩展。
