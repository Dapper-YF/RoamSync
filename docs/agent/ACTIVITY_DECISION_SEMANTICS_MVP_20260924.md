# Activity Decision Semantics MVP — 2026-09-24

状态：**Activity Decision Semantics MVP COMPLETE**（限定为本阶段的语义持久化、可见性和确定性保护 Exit Gate；不等于 Planner 已擅长所有取舍）。真实运行的失败和 Agent 弱点均原样保留，未进入 Stage 2.2。

## 修改前的问题

Activity 已有 `duration_minutes`、`schedule_locked`、`category` 与 `importance`（`low` / `normal` / `high` / `must_do`），Trip Preferences 有兴趣类别；但没有正式的 `can_skip`、最短体验时长和字段来源。`schedule_locked` 约束时刻，不表达活动价值。Planner 能看到一部分 `importance`，Validator 未按活动价值和最短时长阻止无声牺牲。

## Activity Semantics Model

- 沿用既有 `importance` 枚举；`high` 在界面显示“比较想去”，不新建重复枚举。
- `can_skip` 默认 `true`；`must_do` 自动推导为 `false`，显式矛盾请求被拒绝。
- `minimum_duration_minutes` 默认为 `null`，只通过用户显式创建/编辑成为硬约束，不能超过当前计划停留时间。
- 每个字段独立记录来源：`user_explicit`、`user_confirmed`、`system_default`、`unknown`。本版 API 创建/编辑可产生 `user_explicit`；不让模型生成或修改该来源。

## Persistence

迁移 `20260924_0034_activity_decision_semantics.py` 添加五列与数据库 Check Constraints；已有 `must_do` 行回填为不可跳过。旧数据未指定的最短时长保持 `null`。`ActivityResponse`、创建/编辑 API、正式行程读取、复制 Trip 和 PlanRevision 接纳时均保留语义。Alembic 在 Linux/PostgreSQL 测试库和生产数据库均已到 `20260924_0034`；真实 eval trip 经 API 写入、刷新、复制后仍能读出语义与来源。

## Frontend

原 Activity 详情编辑页可设置重要程度、是否可跳过和最少停留时间；必去时禁用可跳过。详情与行程时间轴使用中文产品文案显示“必去”“需保留”“至少 X 分钟”。不展示内部 enum。Web 类型检查通过，Vitest 92 项通过（原有 React `act(...)` 提示未阻断测试）。

## Decision Context Integration

统一 `decision_context` 增加 `activity_decision_semantics`，同时在正式行程投影中携带重要程度、可跳过与最短停留。来源按字段展示。`must_do` 未被错误加入时间锁定的 protected 集合：时间可调整，活动不可删除。单元测试确认 Goals、Memory、Semantics 与 Recovery execution context 同时存在。

## Planner Visibility

Planner JSON 输入独立包含 `activity_decision_semantics`，现有 editable Activity 列表也携带 `can_skip` 与 `minimum_duration_minutes`。指令说明活动价值与时间锁定的区别。真实 Run `4d7ea3d3-e390-4d20-8be0-f7198ed78736` 的持久化 `before_snapshot.decision_context` 同时含 `pace=relaxed`、1 条拒绝 Memory、4 条正式 route facts，以及美术馆 `must_do / can_skip=false / minimum=60 / user_explicit`。DeepSeek 生成的说明也明确识别美术馆 `must_do` 与停留下限。没有保存完整 prompt 或模型私有推理。

## Deterministic Protection

候选校验增加：`activity_must_do_removed`、`activity_cannot_be_skipped`、`activity_minimum_duration_violated`。对 `must_do` 和不可跳过活动，必须以原 Activity ID 和同一地点出现在候选中；最短停留不能被压破。锁定、已执行等原有事实仍由现有执行约束保护。候选协议没有修改 `importance`、`can_skip`、`minimum_duration_minutes` 的字段，Planner 无法自行改变正式语义。Linux/PostgreSQL 集成测试覆盖删除、最短时长违反与合法缩短；真实 Recovery smoke 中省略必去活动得到 `activity_must_do_removed`。

## Goal + Memory + Semantics

单元测试和真实 Run 都证明三者并存。Run `4d7ea3d3-e390-4d20-8be0-f7198ed78736` 从同一 Trip、同一目标日和同一正式版本检索到上一版拒绝 Revision `206fdcd6-33a9-4170-a6c4-b1f0434d3d8e`（`too_much_walking`），同时携带本次 `pace=relaxed` 与活动语义进入 Planner，随后完成 AMap 路线、Validator、Goal Check 和待确认 PlanRevision。

## Live Trade-off Scenario

独立 eval trip：`7fc0911f-9d66-4e27-8109-9a497de5d7f4`，目标日 `2026-10-20`，5 项正式活动、4 条真实持久化 AMap Route 2.0 路段。美术馆为 `must_do / can_skip=false / minimum=60` 且未锁定时间；餐厅 `low / can_skip=true`；雷峰塔 `high / schedule_locked=true`。所有语义经正式 API 写入，不伪造路线。

真实运行序列保存在 [normal_tradeoff_live_20260924.json](../../backend/evals/results/activity_decision_semantics_stage21/normal_tradeoff_live_20260924.json)：首次 Tavily 暂不可用；Run `50e92070-f4ba-4396-928a-da54ef096232` 生成合法待确认方案并因步行仍多而被拒绝；Run `285da322-ab92-4792-a39c-484f5b628aa8` 读到 Memory，但未满足 18:00 硬目标，正确返回 `goal_constraints_unsatisfied`、无 Revision；之后的软目标 Run `4d7ea3d3-e390-4d20-8be0-f7198ed78736` 走完整生产链并留下待确认 Revision。网页研究偶发 `planner_research_invalid_output` 的中间失败亦保留，不计为 Agent 取舍失败。

## Candidate

最终有效软目标候选：Run `4d7ea3d3-e390-4d20-8be0-f7198ed78736`，DeepSeek `deepseek-flash`，36,266 tokens；Revision `4d812876-a325-4dad-be6e-acb62cc396ce` 为 `pending`，未自动 Accept。候选显式列出 4 项，锁定的雷峰塔由系统隐式保留，实际最终仍是 5 项。Validator `valid=true`、`errors=[]`；Goal Check 对 relaxed pace 为 `not_evaluable`，不伪称数学证明“更轻松”。

## Trade-off Evidence

美术馆保留 90 分钟，满足用户显式最少 60 分钟；非跳过语义得到遵守。低优先级餐厅未删除，5 项活动均保留。餐厅由 70→75 分钟，河坊街由 75→100 分钟；真实步行 174→174 分钟、结束 18:12→18:37。模型说明称控制连续步行负担，但路线数字没有改善，这是 **Agent 取舍与解释忠实性弱点**，不能算本轮目标达成。硬目标 Run `285da322-ab92-4792-a39c-484f5b628aa8` 的 18:19 候选被 Goal Check 拒绝，显示安全边界有效；不把它算作 Planner 成功。

审计时还发现旧 Goal Check 忽略隐式保留的固定活动，使“候选 4 项”被误写成“实际只剩 4 项”，且可能漏算最晚结束时间。已最小修复并加回归测试；旧 Revision 的错误观察保留但不再作为最终 count 证据。新的真实 Run 正确显示 5→5。

## Validator

Linux/PostgreSQL 集成测试通过；有效真实 Revision 的 Validator `valid=true`。它证明候选合法，不证明 relaxed pace 或步行改善。Recovery smoke 用 `enforce_execution_invariants=true` 校验省略美术馆的候选，返回 `activity_must_do_removed`。

## Recovery Integration

独立 Recovery smoke trip `6a8f28f7-de67-4629-bc26-dca006f5e53a` 由正式复制 API 创建，Execution 为 `in_progress`。在生产 API 容器内使用真实数据库 context 调用统一 Decision Context 和 `build_planner_input`：`execution_state` 可见、5 项语义可见、美术馆 `must_do / false / 60` 可见、路线事实可见；不调用模型，也不声称 Recovery 生成了优质方案。确定性恢复校验拒绝省略必去活动。

## Tests

- Python 编译：通过。
- 后端 Decision Context / Planner / Goal Check 纯单元测试：32 passed。
- ActivityCreate 契约纯单元测试：通过。
- Web 类型检查：通过。
- Web Vitest：92 passed。
- Activity 持久化和候选 Validator 集成测试：Linux/PostgreSQL 全量回归通过。

## Regression

历史基线为 `329 passed, 2 warnings`。Docker Desktop 恢复后按要求执行 `docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test`；最终 **337 passed, 2 warnings**，退出码 0。Web **92 passed**、TypeScript typecheck 通过，生产 Web 构建成功。生产预检最终 `DEMO READY`；中途 Tavily 可用性波动已单独分类，未改 Provider 或 fallback。

## Known Limitations

- 当前 `high` 沿用数据库命名，界面显示“比较想去”。
- `minimum_duration_minutes` 不从研究资料或 LLM 推断为硬约束。
- Activity Semantic Diff 暂未加入 PlanRevision difference summary；UI 当前只展示正式 Activity 的语义。
- soft `pace=relaxed` 目前只提供观察性结果，不定义武断通过阈值；真实候选保留了全部 5 项且未减少步行。上一版 `too_much_walking` 反馈虽然可见，模型仍未有效响应。此为后续 Stage 2.2 的问题，不在本轮修复。
- 本轮 Recovery 是真实执行上下文的 Planner input / Validator smoke，不是完整 Recovery model live run；本阶段不要求 Recovery candidate 成功。

## Next Stage Recommendation

本阶段停止开发。下一阶段可研究 Decision Ledger / Travel Trade-off Intelligence，重点是让 Agent 对已可见的 Goal、Memory 与 Activity Semantics 做有证据的取舍，并核对解释与真实 route diff；不要把本次安全边界通过误读为 Agent 已具备成熟的取舍能力。
