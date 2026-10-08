# RoamSync Agent Intelligence Audit

审计日期：2026-09-23。范围只限当前工作树中的真实实现；未修改任何生产代码。本审计把「能存储、能校验、能展示」与「模型会据此做选择」严格分开。

## 结论先行

RoamSync **算一个受约束、确认门控的旅行规划 Agent 系统（L2，局部 L3）**，不是单纯 CRUD，也尚未是强自主 Travel Agent。它的核心 LLM 能理解部分请求、基于结构化 trip context 生成候选行程、在有外部检索时作目的地研究，并把候选交给确定性路线/预算/时间校验和用户确认。

真正符合 Agent 边界的主体是 **1 个主规划 Agent**（`OpenAIResponsesPlanner.generate`，经 `PlanningGraph` 调度）。若将具有独立目标的对话入口也计入，可称为 **1 个受限会话/工具路由 Agent**（`AssistantRouter.decide`）；它只选择固定工具并由程序执行，不是旅行决策 Agent。`OpenAIStructuredIntentParser` 是单次结构化理解组件，不具备工具、自主循环或长期状态，不单列 Agent；`destination_research.research_destination` 是主 Agent 的固定子步骤而非独立 Agent。

因此当前不宜对外称为 **Multi-Agent System**。准确表述是：**LangGraph 编排的单 Planner LLM + 有界 LLM 辅助组件 + 强确定性旅行执行/校验系统**。

## 边界分类

| 组件 | 分类 | 为什么 |
|---|---|---|
| `OpenAIResponsesPlanner.generate` + `build_planner_input` | Agent（一个主规划 Agent） | 有目标、结构化上下文、LLM 推理输出候选方案、一次校验后可修正、候选须经人确认；工具选择不自主。 |
| `OpenAIResponsesPlanner.answer` | 同一 Agent 的问答模式 | 对正式行程作受限自然语言建议；不产生计划决策。 |
| `AssistantRouter.decide`（`assistant_service.py:143`） | 有界工具路由 Agent / 入口代理 | LLM 从有限 `ToolDecision` 中选工具；程序核验并执行。没有旅行计划工具调用循环。 |
| `OpenAIStructuredIntentParser.extract`（`openai_intent_parser.py:47`） | Tool / LLM parser | 单次 JSON 语义抽取，仅在规则 parser 不确定时 fallback；没有独立目标、工具或记忆。 |
| `research_destination`（`destination_research.py:94`） | Tool / 固定 research subroutine | LLM 从固定网页结果中抽取地点，再由程序固定调用地图 POI；主图决定它何时发生。 |
| `PlanningGraph`、`agent_worker` | Orchestrator / Infrastructure | 固定 DAG、队列 lease、checkpoint 和中断恢复；不自行决定目标或策略。 |
| `validate_candidate_plan`、`repair_route_schedule`、`enumerate_recovery_options` | Deterministic Service | 时间、路线、预算、执行不变量和恢复搜索空间由规则计算。 |
| `resolve_planning_intent`、`_decide_intent_policy` | Policy（含可选 LLM parser） | 默认规则路由、grounding、确认/澄清授权边界。 |
| PostgreSQL 的 `PlanningRun`/`PlanRevision`/`TravelEvent` | Data store；部分 Working/Episodic memory | 只有少数记录被后续 prompt 读回；数据库本身不是 memory intelligence。 |
| `AiPlannerPanel`、`RecoveryPanel` | UI | 展示进度、候选、证据与确认；不推理。 |

## 当前 Agent Loop（按实际代码）

```text
用户消息 / 导航不可行 / 继续体验导致不可行
  -> 固定 API 与 policy 创建 PlanningRun
  -> PlanningGraph.resolve_intent_node
       [程序] build_planning_context、固定 Tavily/Open-Meteo 查询
       [规则，必要时 LLM parser] intent grounding / clarification policy
       [固定条件] destination research + AMap POI
  -> [LLM] OpenAIResponsesPlanner.generate：一次候选 itinerary JSON
  -> [程序] AMap route enrichment + 时间/预算/执行不变量 validator
  -> 不合法时 [固定图] 最多一次把 validator errors 回送给同一 LLM 修正
  -> [程序] 保存 PlanRevision，用户在 UI 接受/拒绝
  -> [程序] accept 后更新 formal itinerary；执行系统记录事件
  -> [程序 detector] navigation / experience impact 仅在不可行时再唤醒 recovery run
  -> 回到同一个 Planner；没有质量 critic、偏好学习或策略更新闭环
```

真实 feedback loop 是「执行事实 -> 确定性不可行检测 -> 再规划 -> 用户确认」，不是「Agent 观察体验质量并自行反思」。用户拒绝被写入 `PlanRevision.status`，但生成 prompt 不读取 rejection reason（因为没有结构化 rejection reason），所以不构成 learning。

## 决策视野：context inventory

| 类别 | AVAILABLE（确实送入 Planner） | PARTIAL | MISSING |
|---|---|---|---|
| Trip / preference | 目的地、日期、住宿、预算、时区、pace、兴趣、交通、日窗口、餐饮偏好、avoid、最大步行、自由文本（`planning_context.py:12`; `openai_planner.py:276`） | 目标仅隐含在偏好字段 | trip-level success/experience objective、must-do 语义和优先级模型 |
| Formal plan | 各天、活动、地点坐标/类别、时长、费用、status、locked、importance，候选 POI | importance 被输入 prompt，但不是 validator/恢复选择的正式优先级 | 预约/开放时段/最小体验时长的结构化事实 |
| Money / route | 已花、剩余、计划费用；候选后 AMap 路线和时间校验 | LLM 初次规划拿不到实际 route legs，只能坐标推断 | 交通拥堵、停车、无障碍、实时票价 |
| World facts | 每 run 固定 Tavily + Open-Meteo；research 产物入 prompt | 查询问题固定，天气未见转成可执行活动约束 | opening hours、预约可用性、排队、运营状态、事实 freshness policy |
| Execution reality | frozen/protected/mutable，导航 disruption、experience time-shift（触发时） | `TravelEvent` 历史并不整体输入；fatigue/weather/budget dynamic request 的 details 只是拼成自然语言 | 可靠的实时位置/饥饿/情绪/体力、confidence/expiry |
| Prior decisions | answer mode 读取最多 6 runs、2 revisions；assistant session 保留十条消息 | plan mode 不读拒绝/接受原因及历史表现 | decision rationale、rejection label、跨 Trip 用户行为 |

结论：Planner 的视野对「正式行程 + 静态偏好 + 候选地点」已达到可用，但对「旅行正在发生什么、哪些体验更值得保留、过去为何被拒绝」很窄。

## Capability Matrix

L0=不存在；L1=接口/prompt/概念；L2=部分实现或固定流程；L3=真实可用 Agent 能力；L4=有反馈、评测、鲁棒性。

| Capability | Level | Agent/System | Evidence | Main limitation / failure example | Priority / direction / evaluation |
|---|---:|---|---|---|---|
| Goal understanding | L2 | Agent + context | `build_planner_input` 输入需求、偏好、预算 | 目标是本轮 prompt；没有显式体验质量/旅行目的。西湖多留 60 分钟时无正式保留优先级。 | P0：结构化 trip goal；Goal Satisfaction、Must-do Preservation |
| Intent recognition | L2 | Policy + parser | `resolve_planning_intent:216`，模型 fallback `:404` | 大量规则，模型只在 unsupported/低置信时用；非语言策略理解有限。 | P1：扩展 eval slice；intent/grounding accuracy |
| Clarification | L2 | Graph + policy | `clarify_node`，最多两轮 | 只问缺字段/歧义，不问高价值取舍。模糊“轻松”不会量化步行/覆盖偏好。 | P0：value-of-information clarification；precision/recall |
| Context construction | L3 | Infrastructure | `build_planning_context:12` | 丰富但缺动态状态、预约、决策历史。 | P0：decision context contract；context coverage rubric |
| World-state understanding | L2 | Tools + Agent | 固定 web/weather、POI、route enrichment | 外部事实并非按缺口选择；开放/排队/实时状态缺失。 | P1：fact provenance/freshness；hallucination rate |
| User-state understanding | L0 | — | `fatigue` 只是 `TravelEvent` 类型/trigger | 没有 fatigue/hunger/mood/pace confidence、expiry。 | P0：dynamic state provider；state accuracy/expiry tests |
| Reasoning | L2 | Main Agent | 单次 structured plan + prompt constraints | 无显式分解、目标排序或可审计权衡。 | P0：decision record + rubric |
| Planning | L2 | Main Agent | `generate:191` 一次 itinerary JSON | 有一次 validator repair，不是迭代候选规划。 | P0：candidate generation/ranking；quality win-rate |
| Replanning | L2 | Graph + Agent | execution trigger 与 replan context | 仅把不可行事实/自然语言带入；没用价值保护策略。 | P0：recovery policy；Recovery Quality |
| Tool use | L2 | Graph controlled | `_collect_external_facts:459`、research、route enrichment | 工具确实被用，但顺序和时机写死。 | P1：tool trace；tool usefulness |
| Tool selection | L0 | — | 无模型 function-calling / select tool loop | 即使缺预约/营业信息也不能决定查询。 | P1：bounded tool planner；precision/recall |
| Information seeking | L1 | Fixed pipeline | 固定 destination query + 关键词 focused query | 查询不依赖 uncertainty，失败不能换策略。 | P1：query planner；fact sufficiency |
| Multi-step autonomy | L2 | Orchestrator | graph: resolve->plan->validate->review | 流程多步但图预定义；不是 Agent 自主分解。 | P2：仅在 benchmark 证明需要后扩展 |
| Proactive behavior | L2 | Deterministic detector + Agent consumer | navigation observation / `ensure_experience_recovery` | detector 能唤醒，Agent 不评估天气、疲劳、预算趋势。 | P1：event policy；interruption precision |
| Working memory | L3 | PlanningRun/checkpoint | state、LangGraph checkpoint、current context | 有效于单 run；不能形成策略。 | Maintain；resume integrity |
| Trip episodic memory | L1 | DB | execution/events/revisions 已存 | plan prompt 基本不消费历史。 | P1：curated episodic summary；reuse quality |
| Preference modeling | L2 | TripPreferences | `database.py:91`，进 prompt | 静态、自填；没有从行为更新。 | P1：evidence-backed preference hypotheses |
| Learning | L0 | — | 无 model/policy 更新或行为到决策闭环 | 多次跳购物、拒方案不改变下一次。 | P2：offline learning first；override rate |
| Trade-off reasoning | L1 | Prompt only | importance/预算/偏好输入，instructions 要解释取舍 | 没有评分函数或对比。恢复 `enumerate_recovery_options` 忽略 importance/optional，因为数据未构造。 | P0：utility + hard constraints；preference preservation |
| Multi-objective decision | L1 | Prompt + validator | 时间、预算是硬校验；偏好在 prompt | 体验、疲劳、步行、覆盖、天气无法统一权衡。 | P0：objective ledger；Pareto/rubric |
| Candidate comparison | L0 | — | 每 run 只持久化一个 snapshot | 用户看不到 experience/coverage/budget 策略差异。 | P1：2–3 labelled alternatives; win rate |
| Reflection / critic | L1 | Validator only | invalid plan 回传一次 errors | 只检查合法性；「合法但赶」不被语义评估。 | P0：separate quality critic；critic agreement |
| Uncertainty handling | L1 | Error handling | provider errors、research unavailable、schema validation | 不表达事实置信度或让用户在关键不确定性下选。 | P1：uncertainty contract; calibrated abstention |
| Explanation | L2 | LLM + deterministic summary | per-item reason；`describe_plan_changes:5`；UI evidence | `reason` 是生成文本，非因果决策记录；可能事后合理化。 | P1：fact/goal links；faithfulness audit |
| Feedback integration | L1 | Execution constraints | experience/navigation facts进入 recovery | 接受/拒绝、skip、实际 pace 不系统输入。 | P0：feedback schema + context selector |
| Adaptation | L1 | Dynamic replan API | `request_dynamic_replan:176` | 触发内容是 request 文本，非动态状态决策模型。 | P1：state-to-policy benchmarks |
| Safety / confirmation | L3 | Policy + UI | approval interrupt、version fencing、validator | 强在写入安全；不等于决策质量。 | Maintain；unauthorized-write=0 |
| Observability | L2 | Infrastructure | status/progress/token usage/provider, PlanningRun | 无决策 trace、工具效用、quality outcome telemetry。 | P1：decision/tool traces |
| Agent evaluation | L1 | Intent eval only | `backend/evals/run_intent_eval.py` 115 cases；planner smoke | 没有 plan/recovery quality benchmark。 | **P0**：scenario benchmark + rubric |

## Travel trade-off stress test：西湖多待 60 分钟

情境：西湖多待 60 分钟，余下咖啡店、博物馆、晚饭，19:30 演出。

当前系统会把真实结束边界、locked/active/completed、路线和预算带入 validator；若触发 experience impact，`ensure_experience_recovery` 仅在确定性投影已 infeasible 时启动。主 Planner 可从 prompt 看见活动 `importance`，但没有正式的 `must_do/can_skip/minimum_duration/reservation/opening_hours/fatigue` 决策契约；`navigation.recovery.enumerate_recovery_options` 只有压缩已具备 `minimum_duration_minutes` 的活动、换交通、保持计划，且调用处未构建这些旅游价值字段。

所以当前系统能拒绝不合法时刻表，或让 LLM 生成一个合法后续方案；**不能可靠回答「该删咖啡、缩短博物馆、保留晚饭还是保护演出，为什么」**。这正是“生成合法方案”而非“高质量旅行取舍”。

## Memory audit

| Memory type | Status | 是否被后续 reasoning 使用 |
|---|---|---|
| Working memory | 有效 | `PlanningGraphState` / checkpointer / current `planning_context` 被当前 Planner 使用。 |
| Trip episodic | 存在但弱 | `TravelEvent`、`ActivityExecution`、revision 在 DB；只被执行不变量/特定 recovery 使用，非完整历史理解。 |
| Semantic preference | 静态、部分有效 | `TripPreferences` 被每次 prompt 使用；来源主要显式配置。 |
| Long-term user | 缺失 | preferences 复制到 reuse trip，不是跨 Trip profile。 |
| Decision memory | 存在但无效 | `PlanRevision` 有 status/reason；plan mode 不读 rejection reason（也没有字段），不影响选择。 |

## 哪些“智能”实际是 deterministic system

- Slack、时间传播、路线时长冲突、预算上限、版本 fencing：`validate_candidate_plan`、`candidate_schedule.py`、navigation detector。
- 自动恢复唤醒：`navigation/observation_ingestion.py:333` 与 `experience_replanning_service.py:20` 的不可行检测和去重。
- 用户确认、并发 lease、checkpoint、revision 版本安全：graph/runtime/repository。
- 活动状态、延时、继续停留、提前离开：`trip_execution_service.py`。

这些是项目优势，应保留为事实与安全边界。Agent 应在其上做价值判断、信息缺口判断、候选比较和清晰解释，而不能替代它们。

## 当前与目标架构图

```text
CURRENT
UI (AiPlannerPanel / RecoveryPanel)
  -> API + deterministic intent/policy -> PlanningRun + LangGraph
      -> fixed web/weather -> fixed LLM research -> fixed AMap POI
      -> single Planner LLM -> deterministic route/validator -> user confirmation
      -> formal itinerary -> execution facts -> deterministic infeasibility detector
      -> same Planner LLM (recovery)

TARGET (do not implement in this audit)
Facts/tools/state providers -> versioned Decision Context + Goal Model
  -> bounded Planner Agent: decide information gap, generate 2–3 strategies
  -> deterministic feasibility + utility scorer -> Critic (semantic quality, grounded)
  -> user choice/confirmation -> execution facts + feedback summarizer
  -> memory selector -> next Planner decision
                 \-> benchmark/eval harness and trace store
```

## Benchmark design (design only)

每例都应固定输入、允许事实、禁止行为和可判定 rubric；运行时记录 selected tools、candidate set、hard-constraint result、decision trace 和 explanation links。

| Scenario | Input + available facts | Expected key behavior | Forbidden | Main metrics |
|---|---|---|---|---|
| 首次规划 | 日期、兴趣、预算、POI/route facts | 生成可行且偏好覆盖方案 | 编造营业信息 | goal/preference satisfaction, violation rate |
| 模糊需求 | “轻松点，想看看艺术” | 只问高价值澄清或明确默认 | 未问就假定 must-do | clarification precision |
| 时间冲突 | 两活动同一时段 | 保留 hard appointment、提出明确取舍 | 静默删除 hard constraint | constraint violation |
| 多待 60 分钟 | importance、演出预约、最小体验时长 | 给策略并解释删/缩/保留 | 只机械整体后移 | recovery quality, must-do preservation |
| 疲劳 | state source、confidence、expiry | 降低步行/密度，若置信低先确认 | 把 trigger string 当完整诊断 | adaptation rubric |
| 饥饿 | 时间、附近餐食、预约 | 优先补给并重排后续 | 忽略当下状态 | user-state responsiveness |
| 天气变化 | forecast/provenance、室内备选 | 查询/引用相关事实、提出替代 | 把旧预报当确定事实 | tool precision, grounding |
| 严重排队 | queue estimate、预约窗口 | 比较等待成本与活动价值 | 盲目跳过 must-do | trade-off consistency |
| 固定预约 | 19:30 ticket、不可改 | 保护预约并最小化其他变更 | 移动/删除预约 | must-do preservation |
| 预算压力 | actual spend、余量、候选成本 | 给出预算优先选项 | 承诺未知总价 | budget compliance |
| 两高价值冲突 | 两个 must-do、不可兼容事实 | 解释冲突并让用户选择 | 虚假兼容 | clarification/value trade-off |
| 用户拒绝方案 | rejection label：太赶/不想购物 | 下一方案减少相同问题 | 重复同类方案 | override rate, plan churn |
| 信息不足 | missing opening/reservation fact | 选择必要工具或不确定性澄清 | 幻觉补全 | tool recall, hallucination rate |
| 工具失败 | weather/map/search timeout | 降级、说明缺口、避免无依据承诺 | 伪造结果或崩溃 | graceful-degradation score |

指标定义：Constraint Violation Rate（硬约束失败比例）；Goal/Preference/Must-do Preservation（场景标注目标的达成率）；Unnecessary Change Rate（未被事实或目标支持的正式活动改动比例）；Clarification Precision/Recall；Tool-use Precision/Recall（人工标注何时必须/不该查询）；Decision Consistency（等价输入策略稳定性）；Recovery Quality（保留价值 - 变更成本 - 剩余不可行）；Explanation Faithfulness（解释的每个主张可链接到输入事实、目标或明确推断）；Hallucination Rate；User Override Rate；Plan Churn；Proactive Interruption Precision。暂不能自动判定的体验质量、trade-off 与解释忠实度，采用双评审 1–5 rubric + 分歧仲裁，并保留案例证据。

## 优先级结论

最大问题不是 validator 不够多，也不是先拆更多 Agent。前三个架构问题是：

1. **没有结构化 Goal / Decision Context / 用户动态状态**：Planner 看到了数据，但没有可比较的旅行成功标准。
2. **单候选、单次生成，没有显式 utility、比较或 semantic critic**：合法不等于体验好。
3. **工具使用固定、反馈和 rejection 没有进入下一次决策**：系统有事实，但 Agent 不能主动补信息或从结果改善。

最强五项：受限结构化候选生成；行程 context 构建；目的地检索到 POI grounding；确定性可行性/安全护栏；用户确认和执行事实触发的恢复入口。

最弱十项：目标模型、动态用户状态、trade-off、multi-objective、candidate comparison、critic/reflection、tool-selection autonomy、有效 episodic/decision memory、learning、Agent quality evaluation。

是否重构 Planning Graph：**不需要先整体重构**；保留 graph 和 validators，逐阶段在其内增加明确的 decision-context、bounded tool policy、candidate/ranking、critic nodes，并用 benchmark 证明价值。是否需要真正 memory：**需要，但先做 trip-level curated decision/feedback memory，不先做泛化向量库**。是否需要 critic：**需要，P0**。是否需要 multi-candidate planning：**需要，P1，优先 2–3 个策略标签**。是否需要 tool-selection autonomy：**需要，P1，且必须 bounded、可评测、可回退**。
