# RoamSync 当前项目现状审计报告

审计日期：2026-09-21  
唯一审计对象：`E:\Study\RoamSync` 当前本地工作树  
方法：只读静态审计数据库模型、迁移、FastAPI、服务、规划图、React Web、Android、测试、Git 历史和项目 handoff。未修改现有业务代码、Schema 或配置。

## 审计结论先行

RoamSync 已不是单纯的行前攻略生成器。它已有一条真实的“正式 itinerary → TripExecution → NavigationSession → NavigationObservation → ETA/Slack → disruption → Recovery PlanningRun → PlanRevision → 用户确认”的工程闭环，数据表、服务、API、Android 观测上传和 Web 展示均可在当前工作树找到。

但它还不是“动态旅行体验系统”。当前自动执行感知几乎全部来自**活动之间的导航路段**；到达地点后的停留、喜欢/无聊、延长/提前离开、疲劳、心情、排队、拥挤、即时兴趣和旅行节奏没有成为可持续记录、判断与重规划的领域事实。`Activity` 仍是带单一计划时长的 itinerary 条目，真正的 execution lifecycle 仅覆盖到达、开始、完成/跳过，不覆盖体验期。

所以“导航中心化风险”是有代码证据支持的，但应精确表述为：**当前旅中自动闭环以导航延误可行性为中心；非导航旅行变化只存在手动事件/API 枚举，尚未形成相等成熟度的感知与决策闭环。**

## 一、按用户完整旅行流程的能力盘点

| 阶段 | 能力 | 当前状态 | 证据 |
|---|---|---|---|
| 行前 | 旅行创建、目的地/日期/预算/住宿输入 | **已实现** | `backend/app/main.py` trips API；`web/src/App.tsx`；Android `MobileApp.kt`。预算可选，数据库约束见 `database.py:Trip`。 |
| 行前 | 本次旅行偏好 | **已实现** | `TripPreferences`：节奏、兴趣、交通、每日时间窗、饮食、避开类别、步行上限、自由文本；`database.py:91-139`、`schemas.py:276-332`。 |
| 行前 | 意图识别、澄清 | **已实现** | `planning_intent_service.py` 规则/语义解析、范围落地、澄清和政策路由；`planning_graph.py:102-251`。115 条中文 intent dataset 是项目 handoff 记录的验证基线。 |
| 行前 | Destination/POI 检索与 Candidate 生成 | **已实现，依赖外部服务** | `destination_research.py`、`initial_places_service.py`、AMap adapter；`PlaceCandidate`/`SourceRecord` 持久化。候选有评分、标签、建议停留、来源，但不是个性化学习推荐。 |
| 行前 | AI itinerary 候选规划、确定性校验、人工确认 | **已实现** | `PlanningRun`、LangGraph、`openai_planner.py`、`plan_revision_service.py`；候选只有用户接受后才变更正式行程。 |
| 行前 | 行程/活动/路线编辑、跨日移动、路线重算 | **已实现** | `planner_repository.py`、`maps_service.py`、Web 时间线与地图。 |
| 行前 | 版本管理 | **部分实现** | `Trip.version`、`Activity.version`、`PlanningRun.base_trip_version`、`PlanRevision` 存在。项目 handoff 明确记录 P0：手工改 Activity 只增 Activity.version，旧候选只检查 Trip.version，可能覆盖新 duration；因此不能称完整防陈旧写保护。 |
| 旅中 | TripExecution / ActivityExecution / TravelEvent | **已实现（旧/手动执行核心）** | `trip_execution_service.py`、迁移 `0014_trip_execution.py`。用户可开始、暂停、恢复、到达、开始活动、完成、跳过、结束；每个动作写 execution 与 event。 |
| 旅中 | NavigationSession、真实/模拟 GPS Observation | **已实现** | `navigation_sessions`、`navigation_detection_states`、`observation_ingestion.py`；Android `navigation/NavigationRuntime.kt`、AMap source、outbox/upload policy。 |
| 旅中 | ETA、Slack、delay propagation、风险判断 | **已实现** | `navigation/delay_impact.py`、`execution_projection.py`、`event_detector.py`。对当前 ETA 向当前日未完成正式 itinerary 做确定性投影。 |
| 旅中 | Disruption | **已实现，但类型很窄** | `TripDisruptionEvent`、`disruption_service.py`。只持久化 `missed_time_window` 与 `itinerary_infeasible`，由导航观测连续风险/固定时间窗触发。 |
| 旅中 | Recovery Planning | **已实现为导航 disruption 的自动入口；方案能力部分实现** | `observation_ingestion.py:_ensure_recovery_planning_run` 自动创建 replan；`recovery.py` 枚举压缩活动/改变交通方式/保持计划。最终仍经 PlanningRun/PlanRevision/用户确认。 |
| 旅中 | 用户确认新方案 | **已实现** | `PlanRevision` 状态与 accept/reject；Web `RecoveryPanel.tsx`、Android assistant/plan approval。 |
| 旅后 | 体验反馈/复盘 | **完全没有** | 无 feedback/review/experience 数据表、API、组件或测试。 |
| 旅后 | 兴趣学习、长期用户偏好、历史行为学习 | **完全没有** | 无 `User`、跨 Trip profile、行为聚合或偏好学习作业。 |

## 二、核心领域模型、关系与生命周期

```text
Trip ──1:1── TripPreferences (本次规划偏好)
 ├──1:N── DayPlan ──1:N── Activity ──N:1── PlaceCandidate ──N:1── SourceRecord
 │                    └── RouteLeg（相邻活动的正式计划路线）
 ├──1:N── PlanningRun ──1:N── PlanRevision / CandidateRouteLeg
 └──1:1── TripExecution ──1:N── ActivityExecution / TravelEvent
                          └──1:0..1 live NavigationSession ──1:1 NavigationDetectionState
                                                        └──1:N TripDisruptionEvent
                                                              └──0..N recovery PlanningRun
```

| 实体 | 现在负责什么、创建/改变时机 | 生命周期与关系判断 |
|---|---|---|
| `Trip` | 目的地、日期、住宿、时区、预算、版本；创建/编辑/归档、接受 revision 时改变。 | `status` 是由日期/归档推导，并非执行状态机。`Trip.version` 是 itinerary 版本围栏，但存在上文 P0 漏洞。 |
| `TripPreferences` | Trip scoped 的静态规划配置。 | 不是 User profile，也非实时状态；其 `daily_end_time` 被导航 delay projection 作为当天边界。 |
| `DayPlan` / `RouteLeg` | 每日计划与相邻 Activity 的计划路线、距离、时长、交通方式。 | RouteLeg 是正式 itinerary 事实；revision 可替换它。 |
| `Activity` | 计划开始、单一计划时长、费用、位置、`planned/active/completed/skipped`、锁定、备注。 | 静态计划条目，不持有实际到达/开始/结束或体验数据。 |
| `PlaceCandidate` / POI | 来源可追溯的地点候选、标签、评分、建议时长、费用。 | 能成为 Activity 的地点来源；无开放时间、预约、室内外、拥挤/天气敏感度。 |
| `TripExecution` | 一次旅行执行聚合，当前日期/活动、暂停、实际开始/结束。 | `in_progress/paused/completed`。由手动 start 或导航 start 原子创建。 |
| `ActivityExecution` | 计划 Activity 的实际执行投影。 | `pending → arrived → in_progress → completed`，或 `pending/in_progress → skipped`；有 actual arrived/started/ended 与 delay。实现于 `trip_execution_service.py`。 |
| `TravelEvent` | 执行事实日志。 | 支持 arrived、completed、fatigue、weather_change、user_change 等事件类型；但后四类当前只由手动 `execution/replan` API 写入，没有观察器或对应状态模型。 |
| `NavigationSession` | 某个正式相邻 route leg 的版本化运行时投影，持有 ETA、剩余距离、观测序列、路线 revision、GPS/模拟来源。 | `active/rerouting` 唯一；可 arrived/completed/cancelled/superseded。正式 itinerary 更新会 supersede live session。 |
| `NavigationDetectionState` | 每个 session 的持久防抖/风险状态。 | 记录连续不可行次数、风险、最小 slack、影响的 Activity；让重启/并发不丢判断历史。 |
| `TripDisruptionEvent` | 去重后的宏观 disruption。 | 仅 `active/resolved/dismissed`；仅 `missed_time_window`、`itinerary_infeasible`，稳定 key 绑定 execution/itinerary/event/impact。 |
| `PlanningRun` | 初始规划或重规划任务，包含 intent、base Trip version、模型、进度、错误、worker lease、可选 disruption 引用。 | queued→researching/clarifying/planning/validating→awaiting_confirmation→accepted/rejected/failed。一个 active disruption 至多一个 active recovery run。 |
| `PlanRevision` | 保存前后快照、确定性校验、来源、差异及人工决定。 | pending→accepted/rejected/superseded；接受时事务内重新校验并更新正式 itinerary。 |

### Activity 是否真正拥有 execution lifecycle？

**部分拥有，但 execution 不是 `Activity` 本身的完整生命周期。** 真实 lifecycle 在分离的 `ActivityExecution`；`Activity.status` 又被同步写为 active/completed/skipped，形成双重状态。

| 目标状态 | 当前表达能力 |
|---|---|
| planned | `Activity.status=planned` / `ActivityExecution=pending`。 |
| traveling | 没有 Activity 状态；只能从 active `NavigationSession` 的 from/to activity 推断。 |
| arrived | `ActivityExecution=arrived` 且 `actual_arrived_at`。 |
| experiencing | 最接近 `ActivityExecution=in_progress` 与 `Activity.status=active`。 |
| extended | **没有。** 修改 `Activity.duration_minutes` 会改计划，不保留“实际延长”事实。 |
| completed | 已实现，有 `actual_ended_at`。 |
| skipped | 已实现。 |
| abandoned | **没有。** 最接近 skipped，但不能说明发生在体验中、原因或已投入时间。 |

`plan_revision_service.py` 把 completed/skipped 视为 frozen，arrived/in_progress 视为 protected；这正确保护历史和当前事实，但当前没有“体验期产生的偏好/时长改变”作为可控 revision 输入。

## 三、系统实际主闭环及到达后行为

### 已实现的规划闭环

```text
用户输入/assistant message
→ PlanningRun
→ intent resolution + 必要澄清 + 候选地点/外部事实
→ LLM 仅生成受约束候选
→ route enrichment + 确定性校验（时间、预算、来源、范围、受保护活动）
→ PlanRevision
→ 用户 accept/reject
→ 单事务正式 itinerary 更新
```

证据：`planning_graph.py` 固定节点图；`openai_planner.py` 的受限地点/日期输出；`plan_revision_service.py` 的 validate/accept；`planning_run_repository.py` 的持久边界。

### 已实现的导航恢复闭环

```text
Android AMap/模拟运行态
→ ObservationOutbox 上传 NavigationObservation（sequence + itinerary/route revision）
→ 后端 CAS 接收、持久 NavigationSession
→ 用当前 ETA 对未完成正式活动传播 delay，算 slack
→ 防抖 event detector
→ 仅 macro disruption 写 TripDisruptionEvent
→ 幂等创建一个 recovery PlanningRun
→ 同一候选/校验/用户确认机制
→ accepted revision supersede 旧 live NavigationSession
```

证据：`android/.../NavigationRuntime.kt`，`navigation/observation_ingestion.py`，`delay_impact.py`，`event_detector.py`，`disruption_service.py`，`plan_revision_service.py`。这是真实的导航中心闭环，而非仅数据结构。

### “用户到达景点之后”发生什么

到达动作可以被手动记录为 `ActivityExecution.arrived`；开始游玩、完成和跳过也可记录，且前端/Android 有执行进度展示。但系统随后**不会**：自动测停留时长、询问体验、判断喜欢/无聊、感知体力/情绪、比较实际与计划停留、由到达后状态自动触发 replan，或学习用户。

当 ActivityExecution `arrived/in_progress` 时，当前设计主要把它保护起来，避免候选计划改变当前活动；下一段导航可以从当前活动到下一个未完成活动开始。也就是说，到达后关注点从“路线”暂时断开，却未被“体验”领域接管。

## 四、导航中心化判断

结论：**是，当前旅中自动化能力明显导航中心化；但行前规划/编辑仍有成熟独立模块。**

支持判断的事实：

- 2026-09-15 至 09-16 的迁移连续新增 `navigation_sessions`、`trip_disruption_events`、`recovery_planning`、`navigation_observations`；当前 Git log 的最近工作也围绕 navigation Phase B。
- 后端有独立 navigation 包：session、observation ingestion、execution projection、delay impact、event detector、disruption、recovery、start navigation、provider。
- Android 有 AMap navigation source、privacy gate、simulation、outbox、上传策略；Web 有 `ExecutionStatusCard`、`DisruptionDetailCard`、`RecoveryPanel`。
- 自动进入 Recovery PlanningRun 的唯一实现入口在 `observation_ingestion.py`，其 user request 明确是“导航执行事实表明当前正式行程已不可行”。

相反，activity experience、dwell-time deviation、interest change、fatigue/mood/hunger、queue/crowding、weather continuous monitor、pace evolution 没有相同层级的实体、观察器、决策器、UI 或测试。`TravelEvent` 虽枚举 fatigue/weather_change/user_change，`request_dynamic_replan` 也可手工写事件并创建 replan，但它们不是自动感知闭环。

## 五、面向动态旅行体验方向的复用评估

| 现有能力 | 可复用性与需要抽象的边界 |
|---|---|
| `TripExecution` / `ActivityExecution` / `TravelEvent` | 可复用为执行事实基础，但应避免继续让 `Activity.status` 与 execution 双写。TravelEvent 是最接近通用 `ExecutionEvent` 的现有结构。 |
| NavigationSession / Observation | 可保留为“现实执行感知模块”，而不是产品中心；Observation 已有来源、时间、版本、序列、置信边界。 |
| ETA/Slack/delay propagation | 可保留为一种 `Travel State Change` 的确定性影响计算器。不能泛化为体验判断本身。 |
| Disruption / detector | 去重、防抖、版本围栏、事实快照均可复用；但当前 event taxonomy 仅能表达导航不可行，需从 navigation-specific macro disruption 扩展到通用 replanning trigger。 |
| Recovery Planning | 候选→校验→人工确认链条很适合复用；`recovery.py` 已有“压缩 Activity”这个体验方向的雏形，但依赖 `minimum_duration_minutes`，正式 Activity 没有此字段，所以当前 search space 未能由真实 itinerary 充分供给。 |
| PlanningRun / PlanRevision | 应保留。它们是最有价值的产品安全边界：模型提出建议，确定性验证，用户确认，事务化接受。 |
| Candidate / Intent / Planning Graph | 候选来源和澄清框架可保留；Graph 的 context 需能接收用户状态与体验事实，而不只是 TripPreferences、预算、route 和外部 facts。 |

## 六、Activity 模型专项检查

| 概念 | 状态 | 当前最接近物 |
|---|---|---|
| 预计停留 | **已实现** | `Activity.duration_minutes`、Candidate `suggested_duration_minutes`。 |
| 最短/最长停留 | **只有 recovery DTO，正式模型没有** | `RecoveryActivity.minimum_duration_minutes` 是纯 DTO；`Activity` 无 min/max。 |
| 重要性/优先级 | **没有** | 无字段。 |
| flexibility | **部分** | `schedule_locked` 只表达固定开始/不可自动顺延，不是整体 flexibility。 |
| 缩短/延长 | **部分** | 规划候选能改 duration，recovery DTO 能压缩；没有实际延长/缩短事件、理由、原始对比。 |
| 跳过/替换/移动日期 | **已实现/部分** | skip 执行；PlanRevision replace；Activity move API。 |
| 预约/开放时间/固定开始 | **仅固定开始** | `schedule_locked`；没有 reservation 或 opening-hours 模型。 |
| 体力消耗、室内外、天气/拥挤敏感度 | **没有** | 无字段/约束。 |
| 用户为何前往/推荐理由 | **部分** | CandidatePlanActivity `reason` 和 POI description/source；正式 Activity 无 personal purpose。 |
| 用户兴趣预测 | **没有** | rating/tags 是地点属性，非用户预测。 |
| 实际到达/开始/离开、实际停留 | **部分** | `ActivityExecution` 的三个时间可推算停留，但没有显式 actual duration、修正、体验阶段事件。 |
| 用户体验评价 | **没有** | `Activity.note` 不等于评价。 |

## 七、用户建模能力

当前没有 `User`、长期 UserPreference、UserTravelState 或跨旅行学习。

`TripPreferences` 是**本次旅行的长期/预先声明式约束**：兴趣类别、节奏、交通、时间窗、餐饮、避开类别和最大步行。其设计并未直接混入 fatigue/mood 等动态值，因为这些值尚不存在；但 `pace/max_walking_minutes/free_text_requirements` 很容易被误用来承载临时状态，且没有值来源、观测时间、可信度或过期时间。

动态 User State（兴趣变化、体力、疲劳、饥饿、心情、预算压力、步行/排队/早起/拥挤接受度）均未持久化。预算有 actual expense 与 planning budget，但不是用户主观预算压力模型。

## 八、当前前端/移动端产品体验

| 用户动作 | 当前体验 |
|---|---|
| 创建旅行 | Web/Android 可输入目的地、日期、预算，Web 可进一步填住宿和偏好。 |
| 查看/编辑计划 | Web 按日时间线、地图、路线、候选地点；可改时间/时长/费用、拖拽、跨日移动、跳过/完成。 |
| 开始旅行/导航 | Android 可“开始/继续执行导航”，服务端原子创建或恢复 TripExecution + NavigationSession；Web 显示 execution progress。 |
| 导航过程 | Android 有 AMap/模拟 source、路线视图与 observation upload；handoff 说明 Phase B 曾以 display-only polling 为边界，而当前工作树已加入 navigation runtime/upload，需以当前代码而非旧 handoff 为准。 |
| 到达之后 | 能记录 arrived/start/complete/skip；**没有**“继续待一会”“提前离开原因”“喜欢/无聊”“累了”的显式体验流程。 |
| 临时加入地点 | Web 地点抽屉/搜索和 AI 调整可用；AI 改动仍需确认。 |
| 调整今天节奏 | 可手工改单项或发自然语言 replan；没有“放慢/加快今天节奏”的动态 User State 控件。 |
| 了解系统为何改计划 | Planning/Recovery UI 展示 candidate reason、差异、validation/source；导航 disruption UI 展示影响活动、slack、检测时刻和 recovery 状态。对非导航变化没有同样的解释界面。 |

## 九、技术债与架构风险

1. **导航领域已成为唯一成熟的自动 trigger。** `TravelEvent` 的其它 trigger 只是手动 API，并未与 detection、disruption、recovery 同等接通。
2. **Activity 计划与执行状态双写。** `Activity.status` 和 `ActivityExecution.status` 容易产生真源/并发语义问题；特别是 active/in_progress 的对应关系。
3. **Activity experience 空洞。** 现有 actual timestamps 只能说明发生时间，不能说明为什么变化、感受如何、是否愿意改变余下路线。
4. **Recovery abstraction 仍紧绑 navigation deficit。** `TripDisruptionEvent` 类型、`impact_snapshot` 和 recovery run 创建文本都由 ETA/slack 定义；天气、排队、兴趣、疲劳只能绕过该模型走手动 replan。
5. **正式模型与 recovery DTO 脱节。** `recovery.py` 支持 `minimum_duration_minutes/optional`，但 Activity 无对应字段，导致压缩/跳过搜索空间不能以正式数据完整生成。
6. **防陈旧候选保护不完整。** `PROJECT_STATE.md` 记录的 P0 Activity.version vs Trip.version 漏洞仍未关闭。
7. **导航真实度边界必须继续诚实标注。** 当前有 Android AMap/模拟和上传代码，但 routing provider 的生产 adapter 仍有 `UnavailableRoutingProvider` 占位；不得将之描述为完整商业 turn-by-turn 导航能力，除非完成真实设备/服务验证。

## 十、CURRENT_STATE_SUMMARY

1. **当前产品定位**：受确认的 AI 行程规划与旅中执行原型；旅中自动化目前以导航可行性恢复为核心。
2. **真正跑通的核心闭环**：候选规划→校验→确认→正式 itinerary；以及导航 observation→ETA/slack→disruption→recovery PlanningRun→候选确认。
3. **最成熟的 5 个能力**：正式 itinerary/路线/预算；意图澄清与候选规划；确定性校验和 PlanRevision 审批；版本化导航观测/ETA/slack；去重 disruption 与 recovery 排队。
4. **最明显缺失的 5 个能力**：体验期 lifecycle；动态 User State；体验反馈/学习；非导航 trigger 的自动感知；Activity 的 min/max/优先级/体力/环境约束。
5. **导航模块实际占比**：在旅中“自动检测→自动发起重规划”能力中占主导，且是唯一完整自动事实来源；在全产品中仍与行前规划、编辑和审批并列为一个大子系统。
6. **到达之后有什么**：arrive/start/complete/skip、实际时刻、保护当前活动、可开启下一段导航；没有体验感知与持续适配。
7. **User State 有什么**：只有 Trip scoped 预设偏好与客观预算/执行数据；没有用户动态状态或长期画像。
8. **Activity Execution 有什么**：独立 ActivityExecution 与 TravelEvent，能够记录到达、开始、结束、跳过及延误；但没有 extended/abandoned/experience feedback。
9. **可保留代码**：PlanningRun/PlanRevision 审批边界、TripExecution/TravelEvent 事实层、导航作为执行感知、delay impact、防抖/去重、Candidate/intent/Planning Graph。
10. **最需要重新设计**：以通用 Execution Event、Travel State Change、Replanning Trigger 取代导航专属 disruption 的中心地位；补齐 Activity experience lifecycle 与动态 User State，同时解决 Activity/ActivityExecution 双写及 stale revision P0。

## 主要证据索引

- 模型与约束：`backend/app/database.py`（Trip、Preferences、Activity、Execution、Navigation、Disruption、PlanningRun、PlanRevision）。
- 执行：`backend/app/trip_execution_service.py`。
- 导航/观测/延误：`backend/app/navigation/{session_service,observation_ingestion,delay_impact,event_detector,execution_projection,start_navigation}.py`。
- 恢复：`backend/app/navigation/{disruption_service,recovery}.py`、`plan_revision_service.py`。
- 规划：`planning_graph.py`、`planning_intent_service.py`、`planning_context.py`、`openai_planner.py`。
- UI：`web/src/components/{ExecutionStatusCard,DisruptionDetailCard,RecoveryPanel}.tsx`、`web/src/App.tsx`；Android `navigation/NavigationRuntime.kt`、`ui/MobileApp.kt`。
- 当前已知边界与验证：`docs/handoff/PROJECT_STATE.md`、`docs/handoff/LATEST_HANDOFF.md`；测试目录包括 navigation、delay impact、recovery、trip execution、planning 的针对性测试。
