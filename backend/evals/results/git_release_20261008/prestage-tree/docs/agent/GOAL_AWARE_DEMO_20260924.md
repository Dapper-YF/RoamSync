# Goal-Aware Planning Demo Readiness

日期：2026-09-24  
范围：Demo Readiness Vertical Slice — Goal-Aware Planning

## 这周解决了什么问题

此前自然语言中的“轻松一点、少走路、18:00 前结束、不要大改”只会作为一段用户文本交给模型。系统没有独立的状态来说明用户真正要达成什么，也无法在候选方案生成后检查这些目标是否真的实现。

本次增加了 Goal-Aware Planning：用户目标成为结构化、可审计的 Planning Goals，进入 Planner 决策上下文，并在候选经过路线补全与确定性 Validator 后单独检查。

## Before

```text
自然语言目标只存在于 prompt
→ Candidate
→ Validator（只检查合法性）
→ 用户难以知道候选是否完成自己的目标
```

## After

```text
用户请求
→ Intent / PlanningGoals
→ Planning Context（含正式路线事实）
→ Planner
→ Route Enrichment
→ Deterministic Validator
→ Goal Satisfaction Check
→ PlanRevision
→ 前端 Goal Card
→ Accept / Reject
```

## 系统架构

- `PlanningGoals` 分为可确定性检查的 hard goals（结束时间、明确步行上限）与 soft goals（轻松节奏、少走路、保留既有活动）。
- `formal_route_facts` 复用已持久化的正式 RouteLeg：活动序列、路线时长/距离、步行负担、当天结束时间；不会重复调用地图 provider。
- Validator 仍只负责合法、可执行、安全；Goal Satisfaction Check 只负责本次用户目标，二者不混淆。
- hard goal 不满足时，系统仅将结构化事实反馈给 Planner 进行一次 bounded repair；第二次仍失败则返回 `goal_constraints_unsatisfied`，不会创建伪成功 PlanRevision。
- soft goal 只输出 before/after observation，不会阻塞用户审阅候选。
- `PlanRevision` 在既有 JSON `difference_summary` 中承载 `planning_goals` 与 `goal_satisfaction`，无需数据库迁移；API 与 Web read model 均会返回它们。

## Demo 操作步骤

```powershell
cd E:\Study\RoamSync
docker compose up -d --build
.\scripts\demo-preflight.ps1
docker compose exec api uv run --no-sync python -m app.goal_aware_demo --reset
```

打开：<http://127.0.0.1:3000/trips/00000000-0000-4000-8000-000000000002>

输入：

```text
请帮我调整 2026-10-20 当天的行程。我希望今天轻松一点，尽量少走路，
并且 18:00 前结束，现有活动尽量不要大改。
```

候选生成后展示 Goal Card，再演示“确认并应用”或“暂不采用”。现场演示建议选 Reject，随后执行 reset 可回到确定初始状态。

## 真实 Live Run 证据

已创建独立 trip `00000000-0000-4000-8000-000000000002`：

- 日期：2026-10-20；
- 5 个正式活动、4 条 AMap Route 2.0 路线；
- 0 条估算路线；
- 当前正式日程结束：18:12；
- 因而候选有明确的“18:00 前结束”目标空间。

2026-09-24 已完成真实生产链运行：

- Run：`f883140c-8d32-4d00-bd2b-83412d31b091`；PlanRevision：`edb2e727-594c-4777-9953-37b3db16e0ad`；状态：`awaiting_confirmation` / `pending`。
- Preflight：PostgreSQL、Tavily、AMap POI、AMap Route、DeepSeek、Docker `agent-worker` 全部通过，输出 `DEMO READY`。
- 实际经过 Intent、Planning Goals、正式路线事实、Tavily、AMap、DeepSeek Planner、Route Enrichment、确定性 Validator、Goal Satisfaction 与 PlanRevision；总 token usage 为 `52,653`。
- 候选通过 Validator；硬目标均满足：结束时间 `17:55`（要求 18:00 前），步行 `72` 分钟（上限 80 分钟）。
- 软目标保持诚实观察：活动 `5 → 4`，步行 `174 → 72` 分钟，保留 `3/5` 个原活动；不把这些观察伪装成确定性通过。
- 浏览器实测显示 Goal Card、候选差异和两个启用的确认按钮；未自动点击“确认并应用”，正式 itinerary 仍保持初始状态。

## 验证

- 新增 Goal extraction、route-fact propagation、end-before/walking satisfied/violated、单次 repair 边界、PlanRevision serialization 测试。
- 新增 Goal Card 的 satisfied / unsatisfied / partially satisfied 渲染测试。
- Linux/PostgreSQL 全量回归：`321 passed, 2 warnings in 42.59s`。
- Web：TypeScript、Vitest（91 tests）与 production build 通过。

## 已知限制

- “轻松节奏”“尽量少走路”“尽量不大改”只展示结构化 observable evidence，不伪造精确 PASS/FAIL。
- Stage 0 benchmark 仍保持独立历史证据，本次没有改写其 artifacts，也不表示 Stage 0 COMPLETE。

## 后续 Stage

1. 基于已保存的 Goal/Check 结果评估更细粒度的活动语义与 trade-off，但不在本次 Demo Readiness 范围内。

## 3 分钟 Demo Script

1. 打开 demo URL，指出原行程有 5 项活动、预计 18:12 结束和真实 AMap 步行 legs；说：“这是系统当前的正式计划，不是写死的候选。”
2. 点击“旅程总管”，输入 Runbook 中的完整请求并发送；说：“系统先把自然语言拆成持久化的目标，而不是只拼进 prompt。”
3. 等待候选出现，指出“本次规划目标”：18:00 前结束、步行不超过 80 分钟、轻松节奏、尽量少走路、尽量保留既有活动；说：“这些是 Planner 实际能看到的结构化决策状态。”
4. 指向“方案检查结果”：17:55、72 分钟、174→72 分钟、5→4 项及保留 3/5；说：“Validator 证明可执行，Goal Check 则单独证明硬目标是否完成，软目标只展示事实。”
5. 指向候选的新增/移出和时间安排；说：“系统不会自动改正式行程。” 点击“暂不采用”可演示拒绝，或点击“确认并应用”演示人工确认后写入。演示后执行 reset 命令恢复初始行程。
