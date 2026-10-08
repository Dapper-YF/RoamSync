# RoamSync Agent Intelligence Upgrade Plan

日期：2026-09-23。此文件是能力路线图，不是 Phase 2 implementation 任务单；本轮不实施。

## 原则与边界

保留当前确定性核心：formal itinerary、route facts、time/budget validators、version fencing、执行状态和用户确认继续作为唯一事实与写入边界。LLM 不直接保存行程、不自行宣称路线/营业事实、不替代 validator。

增强的 Agent 职责是：理解目标与不确定性、选择何时补充信息、形成可比较的旅行策略、在硬约束内作主观取舍、给出能追溯的说明。只有当任务拥有独立目标、上下文、工具和 evaluation 时，才拆专门 Agent；不要把 weather/fatigue/navigation state provider 包装成 Agent。

## Roadmap

| Stage | Solves | Why this is Agent capability | Exit evidence |
|---|---|---|---|
| 0. Agent Evaluation Foundation | 不知道是否变聪明 | 评价目标与决策质量，而非 API 正确性 | benchmark baseline、trace、rubric、release gate |
| 1. Decision Context / Goal Model | 本轮 prompt 取代旅行目标 | Agent 必须围绕可演化目标取舍 | structured goal + context completeness score |
| 2. Travel Trade-off Intelligence | 合法方案不等于好旅行 | 在不可兼得时选择保留什么是核心 Agent 工作 | utility/constraint ledger、recovery benchmark 提升 |
| 3. Bounded Tool-use / Information Seeking | 固定调用工具 | “我缺什么信息、要查什么”属于 Agent 判断 | tool precision/recall、failure fallback |
| 4. Dynamic User State + Feedback | fatigue/行为不进入策略 | Agent 必须消费带置信度的实时事实 | state-aware recovery win rate |
| 5. Multiple Candidates + Ranking | 只有一个不可比较方案 | 显示不同目标策略并可由用户选择 | labelled alternatives、override/plan churn 改善 |
| 6. Critic / Reflection | 只验合法性 | 评估体验语义和解释忠实度 | critic agreement、bad-but-valid catch rate |
| 7. Memory + Learning | 历史记录不影响下一决策 | 从本趟事件/决定提炼可用经验 | retained preference evidence、repeat-error下降 |
| 8. Proactive Decision Policy | detector 有、决策策略弱 | 在合适时打扰用户或静默是 Agent policy | proactive interruption precision |
| 9. Conditional specialization | 过早 multi-agent | 只有独立可评估职责才值得分工 | comparative eval 证明优于单 Agent |

## Stage 0 — Agent Evaluation Foundation（P0，先做）

解决：现有 `backend/evals/run_intent_eval.py` 只覆盖 115 个 intent/grounding 例与 smoke；它不能回答候选行程是否更符合偏好或 recovery 是否更好。

Agent/系统/用户分工：系统固定 scenario facts、hard constraints 和 trace；LLM 输出受 schema 限制的 decision/candidate；评审者标注体验与解释 rubric；用户研究参与者只做模拟选择或真实选择标注。所需工具：离线 fixtures、fake map/search/weather providers、可复现实例 runner。前端：不必先暴露。

交付设计：把审计文档中的 14 类 scenario 建成 golden cases；每例设 expected facts、must preserve、may change、must ask、tools expected/forbidden。收集 Constraint Violation、Goal Satisfaction、Preference/Must-do Preservation、Clarification Precision、Tool Precision/Recall、Recovery Quality、Explanation Faithfulness、Hallucination、Override、Churn。将 hard metrics 自动化；主观质量双评审。没有 baseline 和阈值，后续 prompt/模型/graph 改动不得声称 intelligence upgrade。

## Stage 1 — Decision Context / Goal Model（P0）

解决：`TripPreferences` 是静态偏好，`importance` 只是一项活动字段，无法表达「本趟旅行想要什么」。

需要的 decision context：trip-level intent（旅行目的、体验优先级）、must-do 与证据/可协商性、预约/固定窗口、预算模式、pace/walking tolerance、coverage、住宿锚点、当前执行状态、facts 的 `observed_at/confidence/expires_at`、当前 decision scope、previously rejected reasons。只汇总与本轮相关的信息，避免原始 DB dump。

LLM：把自然语言目标映射为可确认的 goal hypotheses，识别冲突与缺口，提出高价值澄清。确定性系统：字段/来源/版本/硬约束验证；不允许 LLM 把推测变事实。用户：确认或修正 must-do、预算与默认策略。工具：仅用于补齐具备明确 provenance 的事实。前端：显示“这次优先级/已知约束/尚待确认”，让用户看到并编辑 Agent 依据。

评价：Goal Satisfaction、context completeness、must-do conflict clarification。成功标准不是多存字段，而是 benchmark 中不同 goal profile 导致可解释、正确不同的方案。

## Stage 2 — Travel Trade-off Intelligence（P0）

解决：目前面对西湖延长、晚饭、博物馆和固定演出时，只有 prompt 直觉加合法性检查。

设计：建立 decision ledger：hard constraints（预约、不可移动、正式执行事实、预算 cap）；soft objectives（must-do value、兴趣匹配、体验时长、步行/疲劳、费用、覆盖、变更最小化、天气适配）；每项输入都标注来源和可信度。先由确定性层枚举可行 edit/search space；LLM 解释和提出策略，或由确定性 scorer 排名，二者都必须产出 `keep/change/drop/why` 的结构化依据。

LLM 做主观/语义判断和冲突说明；系统计算 route/time/budget/预约合法性与标准化候选特征；用户在冲突不可自动消解时选择；工具补事实。前端：逐项展示“保留/缩短/替换”的目标和硬约束依据，明确不确定项。评价：Recovery Quality、Must-do Preservation、Unnecessary Change Rate、Decision Consistency。 

## Stage 3 — Bounded Tool-use / Information Seeking（P1）

解决：`_collect_external_facts` 固定查询，`research_destination` 与 AMap 是 graph 固定子步骤。

设计：定义少量 typed tools（destination search、official opening/reservation、weather、POI、route、budget/execution context），每个有成本、freshness、失败语义、允许 scope。Agent 只输出 tool request / rationale，policy 校验，再执行；不把网络内容当 instructions。设置最多调用轮数、白名单、fallback 与 caching。

LLM 判断信息缺口和查询目标；系统执行、验证、缓存、给 provenance；用户在高成本或隐私敏感查询前确认；前端显示“为什么查询、查询到什么、未知什么”。评价：Tool-use Precision/Recall、fact grounding、provider-failure graceful degradation，而非调用数量。

## Stage 4 — Dynamic User State + Feedback（P1）

解决：fatigue/weather/budget 现在多是 trigger 名称或 details 字符串；实际 skip/extend 并未成为完整 decision state。

设计：state providers 产生 `fatigue/hunger/mood/pace/walking tolerance/crowd tolerance/budget pressure` 的证据记录（source、observed_at、confidence、expiry、user-confirmed）。不把这些 provider 叫 Agent。事件 summarizer 把执行事实转成决策相关摘要；低置信状态触发澄清而非强行重排。

LLM 消费状态、决定是否需要澄清并权衡；系统负责采集、失效、不可变执行事实；用户可纠正状态和接受/拒绝调整；工具可提供天气/排队等外部事实。前端：轻量“现在感觉/节奏”控件和清楚的事实来源。评价：state-aware scenario win rate、误触发率、expiry compliance。

## Stage 5 — Multiple Candidates + Ranking（P1）

解决：单 snapshot 无法暴露 trade-off，用户只能接受或拒绝。

设计：最多生成 2–3 个同样合法、策略标签不同的候选，例如 Experience-first、Reservation-first、Budget-first；每个都带相同 decision ledger 的 objective score 与不确定性。不要用三个同质方案凑数。先由确定性层筛选合法方案，再由 Agent 解释差异、必要时请求选择。

LLM 生成/说明有意义的策略差异；系统去重、校验、计算特征；用户选择偏好策略；前端用紧凑比较视图呈现保留、舍弃、费用、步行、风险与未知。评价：用户 override rate、plan churn、strategy differentiation、pairwise preference win rate。

## Stage 6 — Critic / Reflection（P0，和 Stage 2 可并行设计）

解决：当前 review loop 只把 validator error 回到同一 planner；合法的“30 分钟博物馆+20 分钟午饭+连续赶五点”会通过。

设计：建立与生成分离的 quality critic 输入：候选、decision ledger、route/time facts、目标、最小体验标准、变更摘要。critic 不可写 formal plan，只输出结构化 issues、severity、evidence、recommended replan focus。先固定 rubric 和离线评测，避免同模型自我认可即上线。

LLM 评估语义体验和 explanation 是否有证据；系统校验 hard facts、阻止 critic 越权；用户只在真实价值冲突处选择；前端展示可操作的质量告警而非模型内心独白。评价：bad-but-valid catch rate、critic-human agreement、false alarm rate、explanation faithfulness。

## Stage 7 — Memory + Learning（P1/P2）

先实现 memory，再谨慎谈 learning。Working memory 已有，不重做。补 trip episodic/decision memory：每次接受、拒绝、跳过、延长、提前离开都形成简洁、来源明确的 summary；记录 rejection reason（可选）、结果和是否被下一 run 使用。Preference memory 只从重复且有置信度的行为形成 hypothesis，例如“连续三次主动延长博物馆”，必须可见、可撤销、不可覆盖用户显式设定。

LLM 选择与当次相关的有限 memory，不能盲塞历史；系统保存 evidence、recency、confidence、privacy/retention 边界；用户可查看、修正、删除 inferred preferences；前端显示“我基于哪些过往选择这样判断”。评价：memory retrieval relevance、重复错误下降、用户更正率。跨 Trip/模型训练/自动策略学习属于 P2，必须先通过离线 counterfactual 与安全审查。

## Stage 8 — Proactive Decision Policy（P1）

保留 deterministic detectors（这是正确架构），但定义 Agent 消费事件的 policy：何时仅提示、何时生成候选、何时请求确认、何时静默。导航不可行和 experience impact 现已具备良好入口；天气、预算趋势、疲劳只能在有可靠 state/fact 时加入。LLM 不能直接打扰用户，需 policy 根据 urgency、confidence、expected value、notification budget 决定。

评价：Proactive Interruption Precision、missed critical events、user dismissal rate。前端应始终指出触发事实与不执行的选项。

## Stage 9 — Only then assess specialization

默认保持一个 Planner Agent 加 typed tools/state providers。只有以下任一模块同时满足独立目标、独立上下文、独立工具、独立 evaluation，且 benchmark 证明解耦更好，才考虑专门化：

- Information-seeking agent：以事实充分性、citation grounding、tool efficiency 评估；
- Plan critic：以 human agreement / bad-plan catch 评估；
- Preference-memory curator：以 retrieval relevance / correction rate 评估。

Weather、fatigue、navigation 应仍是 tools/state providers，除非它们取得上述四项独立边界。不要为了简历拆出 WeatherAgent、FatigueAgent、NavigationAgent。

## Suggested sequencing

先做 Stage 0 的基准与 trace，再定义 Stage 1 的 goal/context contract，同时设计 Stage 2/6 的 trade-off ledger 和 critic rubric；接着才以 benchmark 驱动 Stage 3–5。Stage 7–9 需要已有的 decision record 和 outcome 数据才有价值。每个阶段都以“是否改善同一批 travel scenarios”作为门槛，而不是以新增表、节点或 prompt 数量作为完成条件。
