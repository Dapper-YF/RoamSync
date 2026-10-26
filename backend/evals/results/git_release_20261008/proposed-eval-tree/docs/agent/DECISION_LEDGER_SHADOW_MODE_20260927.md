# Decision Ledger Shadow Mode / 校验职责拆分（2026-09-27）

## 为什么需要职责拆分

此前专用 Demo 五次首轮 Planning 均未生成 pending Revision。最近一次 `29dbac6c-030c-4a5e-aa25-74cf643990b3` 已到 Candidate、AMap 路线和 Validator，却因 `decision_evidence_unresolved`、`decision_memory_basis_missing`、`decision_tradeoff_cost_unverified` 等 Ledger 依据错误进入 `planner_constraints_unsatisfied`。这些错误不能证明候选行程不可执行。历史 artifact 保留，不覆盖。

## Before Pipeline

真实路径为 Planner JSON → `PlannerDraftOutput`/`resolve_planner_output` 候选解析 → `enrich_candidate_routes` → `validate_candidate_plan`（时间、路线、预算、意图范围、锁定与 Activity Semantics）→ 必要时一次时间型 route repair 并重新校验 → `validate_decision_ledger` → Goal Check → `save_plan_revision` → 用户 Accept/Reject。此前 `validate_node` 把 Ledger issues 直接追加到候选 `validation_result.errors` 并置 `valid=false`，导致 Goal Check 与 Revision 不可达。

## Candidate Correctness

| 责任边界 | 典型错误 | Shadow 下是否阻塞 |
| --- | --- | --- |
| 严格 Planner 候选解析 / 允许集合 | 非法 `place_candidate_id`、日期、时间、候选结构 | 是 |
| `validate_candidate_plan` | `unknown_place`、`time_overlap`、`route_travel_time_conflict`、时间窗/预算/意图范围违规 | 是 |
| 受保护状态和正式语义 | 锁定活动变更、`must_do` 或 `can_skip=false` 被删除、低于 `minimum_duration_minutes` | 是 |
| Goal Check | 明确 hard Goal 不满足，至多一次 bounded repair 后仍失败 | 是 |
| 用户决定 / 正式写入 | 过期版本、重新校验失败、未确认 | 是；绝不自动应用 |

## Provenance Correctness

`validate_decision_ledger` 继续逐次运行。`decision_goal_basis_missing`、`decision_evidence_unresolved`、`decision_provenance_duplicate`、`decision_explanation_unsupported`、`decision_route_claim_unsupported`、`decision_route_evidence_missing`、`unsupported_addition` 等只说明理由或来源未证实。无效 Ledger 的状态为 `invalid`，`entries=[]`，保留去重的错误码。历史无 Ledger、且无解析错误的快照仍为 `unavailable`；新模型 Ledger 字段解析失败为 `invalid`，不会伪装成历史快照。

## Error Classification

`unsupported_addition` 指真实候选新增地点缺少合格 Ledger 依据；与非法地点 ID 不同。前者在 shadow 只污染 provenance，后者在候选解析/Validator 硬阻塞。合法删除 `can_skip=true` 活动但理由错误也只污染 provenance；删除 `must_do` 等正式硬约束仍由候选 Validator 拦截。模型解释不通过、但路线和候选合法时，可以产生 pending Revision；用户不会看到未经核验的具体理由。

## Shadow Behavior

`DECISION_LEDGER_VALIDATION_MODE=shadow` 为默认；`enforced` 保留 Stage 2.2 评测用的阻塞模式。两者均执行 Ledger 校验，不改写模型理由、不伪造 evidence、不修改 Planner 或路线规则。Trace 记录模式、Ledger 状态、候选结果及错误码；Revision 的 `difference_summary` 记录 `decision_summary`、`decision_ledger_status`、`decision_ledger_errors`。前端只在 `validated` 展示结构化原因与活动理由；`invalid`/`unavailable` 时显示中性文案，Goal Card、事实差异和 Accept/Reject 不受影响。

## Stage 2.2 Status

**Decision Ledger MVP REMAINS OPEN。** Shadow 不证明真实模型能写出 validated Ledger，也不等于 Stage 2.2 Exit Gate。未进入 Stage 2.3。

## Tests

新增生产图四象限测试：候选有效/无效 × Ledger 有效/无效；有效候选产生 pending Revision 且状态对应，候选无效均不产生 Revision。另测 `enforced` 继续阻塞无效 Ledger、异常 Ledger 输出隔离、历史 `unavailable` 与新解析失败 `invalid` 区分。原有 walking 不变却声称减少步行的 Ledger 测试继续通过；Web 测试确认该类文案不展示，Accept/Reject 保持现有边界。

## Regression

Linux/PostgreSQL 最终全量后端：**354 passed, 2 warnings**（此前 350 passed）。Web 全量：**97 passed**（此前 96 passed），TypeScript typecheck 与生产构建通过。已知 React 测试中的 `act(...)` 提示未影响结果。

## Demo First Run

专用 Trip：`00000000-0000-4000-8000-000000000003`，目标日期 `2026-10-20`。本轮重建后 Tavily、AMap POI、AMap Route、DeepSeek、数据库、worker、前后端预检均 PASS，Trip 已 reset。首轮 Run `b6ee159c-6d8e-4f92-94a0-5852fcbe9a2a` 真实到达 pending Revision `53806875-e482-4be2-8caa-fb0a24940e54`，消耗 16,662 tokens。Intent/Goals/Context/DeepSeek/Candidate/AMap 路线/Validator/Goal Check/Revision 均 reached。候选 `valid=true`、5 项原活动保留、4 条候选路线；结束 `17:56 ≤ 18:00`、步行 `61 ≤ 80` 分钟。正式行程原步行 174 分钟。Ledger `invalid`，错误 `decision_route_evidence_missing`，未被升格为 validated，也未妨碍合法 Revision。真实浏览器显示 Goal Card、候选、Reject/Accept，并显示“调整原因暂未通过核验”“AI生成的候选调整”，没有展示模型未经核验的具体理由。

通过真实前端 Reject，反馈 `too_rushed` 与补充文字写入第一版 Revision；正式 5 项行程仍未改变。第二轮 Run `f6bbf104-29d4-43a6-91ce-02542ddbd57a` 的 `decision_context_summary.decision_memory` 已确认 count=1、source_revision_id 指向第一版、`context_propagated=true`、`visible_to_planner=true`。第二轮真实结果为 `planner_invalid_output`：模型两次在第 1 项引用本次未核实地点 ID，严格候选解析拦截，未到达候选/路线/Validator/Goal/Revision；消耗 38,010 tokens。该失败属于候选身份正确性，不是 Ledger。首轮成功不能等同完整两轮 Demo 通过。

## Remaining Blocker

按 `Reset → 首轮 Planning → pending Revision → Reject → Memory → 第二轮 Planning → pending Revision` 连续测量 3 次，**完整通过 0/3**。三次首轮均成功、均保留正式行程至用户确认、均记录 `decision_ledger_status=invalid`，且真实拒绝反馈均进入第二轮 Planner Context。第二轮分别为：

1. `f6bbf104-29d4-43a6-91ce-02542ddbd57a`：两次模型输出引用未核实地点 ID，`planner_invalid_output`，38,010 tokens。
2. `7e7c039a-439a-4dfb-a9d2-7cae3da5fbe2`：同类未核实地点 ID，`planner_invalid_output`，provider 未提供可记录的 token usage（值为 0，不解释为零次调用）。
3. `86f6e19f-9fc4-4d7e-bfe0-d07a950fcd8b`：JSON 缺少分隔符，`planner_invalid_output`，17,259 tokens。

这是候选结构化输出正确性阻塞，非 Ledger-only failure，不能用 shadow 放行。未继续无限重试，也未修改 Planner prompt、allowed places、目标或硬校验。三次运行的有限证据在 `backend/evals/results/travel_decision_demo/shadow_live_20260927.json`；前两次记录经专用 reset 后仅在 artifact 中保留，第三次仍在当前专用 Trip 数据库。**Travel Decision Agent Milestone Demo NOT READY；Decision Ledger MVP REMAINS OPEN。**
