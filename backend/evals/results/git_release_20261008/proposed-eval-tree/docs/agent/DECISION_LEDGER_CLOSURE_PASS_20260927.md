# Stage 2.2 Decision Ledger Closure Pass — 2026-09-27

**Final Stage 2.2 Status：Decision Ledger MVP REMAINS OPEN。** 本轮严格停止在 Stage 2.2；没有进入 Stage 2.3 或 Milestone Demo，也没有覆盖 2026-09-24 的失败 artifact。

## Root Cause

| 已知失败 | 分类 | 本轮判断 |
| --- | --- | --- |
| 174→174 分钟却声称 `reduce_walking` | Planner contract ambiguity | 模型在候选路线尚未计算时声称结果；确定性拦截正确，不能放松。 |
| 重复 `preserve` | Planner contract ambiguity | 旧指令未明确只记录重要保留，模型为普通未变活动重复建记录。 |
| Goal/Semantic evidence 无法解析 | Validation contract overly ambiguous | 自由 `fact_key` 与独立 refs 重复表达相同事实，容易漏引用或编造键。 |
| 地点 ID 不在 allowed set | Schema generation / provider output instability | 输出 schema 已有地点 enum，DeepSeek 仍会返回未授权 ID；解析器正确拒绝。不能把它映射为别的地点。 |
| 漏掉必需 `decision_ledger` | Schema/output instability | 顶层必需字段在真实响应里仍可能缺失；继续按现有最多一次结构化重试拒绝。 |
| 路线修复后 Ledger 时间过期 | Post-route mutation invalidation / production correctness | 原先先生成 Ledger 后确定性移动候选时刻，导致原记录与最终候选不一致。 |

本轮两次正常 Live Run 又分别暴露未授权地点 ID、以及模型把软目标标成 `satisfy_hard_goal` 并同时产生范围/时间冲突。**Decision Ledger contract remains too brittle。**

## Contract Simplification

不增加 reason taxonomy、不新增模型调用。`decision_ledger` 仍为同一 Planner structured response 的必需数组，但明确允许无重要决策时输出 `[]`。必须逐项记录 add/remove/shorten/extend/重要 move/交通方式变更；`preserve` 仅用于必去、锁定或本次 Goal/Memory 明确影响的保留，不要求所有原活动逐项记录。`before`、`after` 和代价可由系统核实后补齐，不强迫模型猜测路线修复后的时刻。

`DecisionEvidence.fact_key` 已从自由字符串收为有限枚举。模型不能自造 `less_tiring_route` 等无法核验的键。对 Goal 和活动语义，若模型在结构化 evidence 中给出可核验的键和值、但遗漏重复的 `goal_refs`/`semantic_refs`，校验器可确定性归一化为正式引用；不从 explanation 猜测依据。错误值、非法 ID 或虚假路线改善仍拒绝。

## Allowed References

Planner input 现显式给出 `allowed_ledger_references`：当前有效 Goal refs、拒绝 Memory 的 Revision IDs、正式 Activity IDs、可新增 Place Candidate IDs 与正式 Semantic refs。动态 JSON Schema 同时约束 Ledger 的 target ID、Goal/Memory ref 和 Semantic Activity ID。没有可新增地点时，新增地点 ID 集合为空。已有候选活动的 `place_candidate_id` enum 和服务端解析终审继续保留。

结构化输出第一次失败时仍只重试一次；对漏 `decision_ledger` 或非法地点 ID，`output_error` 额外列出具体缺失字段或当前允许的地点 IDs，不提供答案，不无限重试。

## Route Repair Reconciliation

仅在现有 `repair_route_schedule` 确实只改时刻、且完整行程 Validator 对修复后候选判定有效时运行。系统先核对前后候选的活动身份、时长、路线均未变，再用实际 `schedule_adjustments` 对齐 Ledger 的时间观察。若 Planner 的 move 被修复完全抵消，移除这条已不在最终 diff 中的 move；若最终形成重要时间移动，记录 `source=deterministic_route_repair`、`primary_reason=resolve_schedule_conflict`，并在 Ledger 校验时核对 candidate ID 与最终时刻。不会把系统修复伪装成 Planner 主观取舍；若修复改变了非时间字段则报错，不自动编造决策。此策略有单元测试，**尚无成功生产 Run 对它的端到端证明**。

## Normal Live Run

使用已有真实杭州 trade-off Trip `7fc0911f-9d66-4e27-8109-9a497de5d7f4`、明确日期 `2026-10-20`、正式 Activity Semantics 和同 Trip/同版本的 1 条 `too_much_walking` 拒绝 Memory，另建独立新 Run；旧 artifacts 未改。

1. `25ffb4c1-fe9e-437e-9c35-849b2c5c7c7f`：到达 Planner，Memory count=1；模型第二次结构化尝试仍引用 allowed set 之外的地点 ID，`planner_invalid_output`，没有 Candidate/Ledger 校验或 Revision。此 Run 的 Intent 为 `optimize_route`，不能作为目标移除已完成的证据。
2. `93215d31-fffe-47bc-9870-f06cc4289561`：明确“删除绿茶餐厅·湖滨店”后，Intent=`remove_activity`，target ID 正确、无歧义；Goal、Memory、Activity Semantics 均进入 Planner。DeepSeek 返回 4 项显式候选和 5 条 Ledger，AMap 路线与确定性 Validator 已到达，但最终 `planner_constraints_unsatisfied`。Ledger 的 `remove-lvcha` 记录用 `satisfy_hard_goal`，只引用 `minimize_walking` 与 `pace` 两个软目标，未引用正式存在的硬目标 `max_walking_minutes=80`，触发 `decision_goal_basis_missing`。同一候选还出现 `intent_scope_activity_changed`、`time_overlap` 与 `route_travel_time_conflict`。无 PlanRevision。

两次连续正常 Live Run 因不同的结构化输出/决策依据问题无法生成 Revision，触发本轮停止规则；没有继续尝试改 prompt 或启动第三条 Run。机器可读证据保存在 [Closure artifact](../../backend/evals/results/decision_ledger_stage22/closure_live_20260927.json)。

## Ledger Validation

真实第二条 Run 的 Ledger 校验到达但未通过。删除活动的 target 与正式低优先级、`can_skip=true` 语义相符；它也正确引用了 soft Goal。失败点是 `primary_reason` 宣称满足硬目标但无对应硬目标依据。不能因为模型“差不多表达了少走路”就改写成 `improve_soft_goal` 并放行。新增活动有 provider candidate ID 和 `pace` 引用，但实际行程仍被作用范围与时间校验拒绝；本轮不评价它是不是最佳取舍。先前“步行没减却声称减少”的拦截继续保留。

## PlanRevision

两条 Closure Live Run 均没有生成 Revision；因此 `validated Ledger → pending PlanRevision` Exit Gate **未通过**。`difference_summary.decision_summary` 的既有持久化路径和前端“为什么这样调整？”区域未重设计，但本轮没有新的真实 validated summary 可供展示。

## Recovery Live Run

**未启动。** 用户要求 Normal Live 成功以后才能进入真实 Recovery；正常链尚未产生 pending Revision，故不跳过顺序。原有确定性 recovery unsupported-addition 测试不能冒充 `NavigationObservation → Disruption → Recovery PlanningRun` 的生产证据。

## Regression

最终 Linux/PostgreSQL 全量回归：**349 passed, 2 warnings**，退出码 0。Web：**94 passed**；TypeScript typecheck 通过。Windows 本机单独运行的 PostgreSQL 图测试曾因数据库未启动且 psycopg 与 Windows 默认 Proactor event loop 不兼容而失败；以完整 Linux/PostgreSQL 容器回归为正式结果。

## Remaining Risk

- DeepSeek 对动态 JSON Schema 的地点 ID enum 并不稳定遵守，最多一次结构化修复仍可能失败。服务端终审必须保留。
- 当前 `satisfy_hard_goal` 与 soft-goal evidence 的语义匹配仍依赖模型正确选择 reason；确定性校验会 fail closed，但生产成功率不足。
- 路线修复的系统归因有测试，缺真实成功 Run 佐证。
- Recovery provenance boundary 仍缺生产观察。
- 不因本轮回归通过宣称 Stage 2.2 COMPLETE；停止规则优先，等待下一条指令。
