# Decision Memory MVP（2026-09-24）

## 修改前的问题

旧系统可以把 PlanRevision 和 PlanningRun 标为 `rejected`，但没有保存用户拒绝原因。下一次 PlanningRun 只读取正式行程和当前请求，Planner 不知道上一版为何被拒绝。

## Reject Feedback Contract

`POST /api/v1/plan-revisions/{revision_id}/reject` 现在接受可选的 `reason_code` 与 `reason_text`。reason code 仅包括 `too_rushed`、`too_much_walking`、`activity_mix_not_preferred`、`schedule_too_late`、`too_expensive`、`other`。Web 的“暂不采用”先展示轻量反馈 UI，必须选择一个原因，补充文字可选；Accept 路径没有改变。

## Decision Memory Model

`DecisionMemoryItem` 是读取模型而不是新长期偏好表。每项包含 rejected revision/run、trip、target day、reason、压缩 candidate summary、goal summary、base trip version 与 retrieved time。candidate summary 只保存活动数、结束时间、步行/路线负担和 added/removed/changed references，不保存完整 candidate JSON 或隐藏 prompt。

## Persistence

迁移 `20260924_0033_plan_revision_rejection_feedback.py` 给 `plan_revisions` 添加 `rejection_reason_code` 与 `rejection_reason_text`。拒绝后可从 API 与数据库重新读取；关联 run 的既有 `trigger_snapshot` 记录非敏感的 `decision_memory_feedback` provenance。

## Retrieval

检索严格限制为：同一 trip、同一 target day、同一 `base_trip_version`、近期（最多三条）、且有显式 reject feedback 的 rejected revisions。不同 trip、不同日期和 formal version 已隔离。它不是 embedding、跨旅行记忆或长期偏好学习。

## Decision Context Integration

Memory 只经 `decision_context.decision_memory` 进入下游，不创建第二套 Planner context。`trigger_snapshot.decision_context_summary` 记录 source revision/run IDs、数量、`context_propagated` 和 `visible_to_planner`。运行 trace 记录 `memory_retrieved`、`memory_context_propagated`、`memory_visible_to_planner`，不保存完整 prompt 或 Chain-of-Thought。

## Planner Visibility

Planner 输入新增 `previous_user_feedback` 分区，与 `user_goals` 并存。系统指令将 reason code 解释为仅本次重规划的取舍指引：例如 `too_rushed` 优先降低密度、保留或增加既有主要游览停留时间；不会把一次 Reject 写成永久用户偏好，也不会强制指定某个活动。

## Live Plan A

独立 eval trip：`79778c6-d213-42f6-8c75-ff9c348e9532`，日期 `2026-10-20`。

- 有效 Plan A run：`8719ff6f-40f7-4616-a3f8-a32c61e22659`
- Revision A：`b2f560e5-f5ae-4789-adf9-883886e4a45e`
- 真实链路：Tavily、AMap、DeepSeek、Route Enrichment、Validator、Goal Check、PlanRevision 全部 reached。
- A：4 项活动、步行 61 分钟、路线 143 分钟、17:56 结束；Validator valid。硬目标 `18:00 前结束` 与 `80 分钟步行上限` satisfied。

此前同 trip 的一次 A 尝试 `9be66a55-c9c4-4d51-a3b1-f085bd4a3d47` 被 `planner_invalid_output` 拦截，原因是模型引用未核实地点；它没有 revision，故不作为 Memory A。

## Reject Feedback

通过真实 production API 拒绝 A：

- `reason_code=too_rushed`
- `reason_text=两个文化场馆停留时间太短，希望每个至少有更充足的游览时间。`

结果：Revision A 和 Run A 均为 `rejected`，reason 可从 API 重新读取。

## Live Plan B

最终有效 B run：`55ef1c54-e149-4565-a412-6d31a8f76915`；B 的用户请求仅为“请再调整 2026-10-20 当天的行程。”，没有重复 Reject 原因。它使用真实 PostgreSQL、Tavily、AMap、DeepSeek 和 PlanRevision，产生 pending Revision `429213b2-3dbd-4c47-91a3-713b0a723249`。

B run 的 production snapshot 显示 `decision_memory.count=1`，source revision 为 A、source run 为 A；同一代码路径将它传入 Planner 的 `previous_user_feedback`。中间 B 尝试 `d3a9eb27-e7d0-4ffd-9955-28a494ba6fef` 已看到同一 memory，但被 route travel-time validator 拦截，未作为比较对象。

## A vs B

| 指标 | A | B |
| --- | ---: | ---: |
| 活动数 | 4 | 4 |
| 对应文化游览停留 | 75 分钟 | 90 分钟 |
| 步行分钟 | 61 | 176 |
| 路线分钟 | 143 | 176 |
| 状态 | rejected | pending confirmation |

## Repeat Error

对 `too_rushed`，B 没有增加活动数，并把对应文化游览从 75 分钟增加到 90 分钟：`repeat_error=false`（针对“停留太短”这一反馈）。但 B 的步行变高，这不是本次 reason 的通过证据，不能称为全面方案改善。

## Memory Causality

`memory_available=true`、`memory_retrieved=true`、`memory_visible=true`、`behavior_changed=true`。由于 B 未重复拒绝文本、同 trip/day/version 的唯一新增输入是 A 的 rejection feedback，且文化停留增加，`memory_causality_supported=true`（仅支持该具体“too_rushed”维度）。

## Frontend

Reject 反馈 UI 已覆盖：打开反馈、选择 reason、输入补充文本、提交、取消；已有 Accept 不受影响。反馈不会在前端 local state 中充当唯一事实。

## Tests

- Reject reason persistence/API response
- same trip + same day + recent rejected retrieval
- different day / different trip / stale version isolation
- Decision Context memory integration
- Planner input 中 Goal 与 Memory 并存
- PlanRevision feedback serialization
- 前端 Reject feedback UI 与 Accept 回归

## Regression

Linux/PostgreSQL：`329 passed, 2 warnings in 41.95s`。

## Known Limitations

Memory 是确定性最近拒绝反馈，不是长期偏好。`too_rushed` 的方向性适配已观察到，但 DeepSeek 候选仍可能使非本次反馈维度（如步行）变差；Validator 只保证可执行，不保证所有软目标最优。Recovery 不属于本阶段 Exit Gate。

## Next Stage Recommendation

保持本阶段完成后停止。若后续启动新阶段，可评估 Activity Decision Semantics 或更细粒度的 trade-off evaluation；不要在本阶段把 reject feedback 扩展为长期偏好学习。
