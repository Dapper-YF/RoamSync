# RoamSync V2 领域与技术架构：第二轮修订候选

日期：2026-10-15，Asia/Shanghai。状态：**建议冻结，等待最终批准；未实施**。本文件替代第一轮目标架构中的冲突提案；原代码事实仍以[审计](ROAMSYNC_CURRENT_STATE_AUDIT.md)为准。ADR见[架构决策](ROAMSYNC_ARCHITECTURE_DECISIONS.md)，验证与启动门禁见[实施准备](ROAMSYNC_IMPLEMENTATION_READINESS.md)。

VERIFIED=代码/静态证据；MEASURED=已执行且限定范围的检查；TECHNICAL CONCLUSION=基于依赖的工程论证；CANDIDATE FREEZE=建议冻结；VALIDATION REQUIRED=尚需实现/运行验证；PRODUCT APPROVAL=产品负责人尚需批准。第二轮评审方向被接受，不等于实施授权。

## 1. 六项修正后的核心推荐

1. 新增InstantNavigationSession只用于应用内持续导航；普通外部地图交接只需RouteQuote及本地HandoffReceipt，不创建受控active GPS会话。正式NavigationSession的Trip/Execution非空约束保留。
2. DraftContext/DraftRun复用模型客户端、实体引用编解码、要求编译及可抽取的纯校验；不复制Planner/Graph/Validator，不给无日期草稿造假日期。
3. 创建与采用是不同授权范围，不要求两次点击。默认推荐可恢复的异步正式化协调：用户可一次明确确认“创建并采用这份方案”，只有内容与授权指纹仍一致才调用原Accept；变化则重审。跨网络、Graph和Accept不是一个现有原子事务。
4. ContextEnvelope明确分离物理位置、浏览区域/地点、讨论对象、只读上下文、操作请求，以及服务端解析的授权/正式约束。Read Context不授予写权限。
5. 来源/unknown修复提前到Phase0；数值是否存在、事实性质、时效及读取方式是正交字段，缓存不等于估算，实时查询不等于已核验真实售价。
6. 当前309文件manifest仍为可复现官方源码快照；待整合块逐项审查、新基线重测。首期受控单用户，owner由可信服务端边界确定；公开多用户/跨设备同步另设门禁。

## 2. 领域边界与组件

| 领域 | 权威数据/职责 | 可关联 | 不承担 |
|---|---|---|---|
| 地点与内容 | Place/ExternalRef、合法图片、来源、字段投影 | Provider、Favorite、候选快照 | 自造价格/评论/房源；同名自动合并 |
| 个人资料 | Favorite、显式Preference、Evidence、Feedback | Place、可选Trip/任务、来源 | 以浏览时长确定喜好；覆盖当前明确要求 |
| 对话情境 | 稳定AssistantSession、Topic、Message、Suggestion、Resolver | 只读引用、动作提案与授权凭证引用 | 万能中心对象、全量敏感历史读取 |
| 自由规划 | PlanningDraft、DraftRun、DraftInput/PlanSnapshot | Place、要求来源、可空日期 | 正式Activity/Execution/已接受Revision |
| 正式旅行 | 现有Trip/Preferences/DayPlan/Activity/Run/Revision | Place快照、执行、来源 | 强制搜索浏览建档 |
| 路线/即时导航 | RouteQuote；需要持续控制时InstantSession | 端点、模式、设备、观测 | 写正式Execution/Disruption/Recovery |
| 正式执行 | 原Execution/Navigation/Disruption/Recovery | Trip/version/活动对 | 用未接受草稿作为正式安排 |
| 编排 | 能力路由、确定性目标/权限、作业、校验 | 上述用例端口 | 模型直接批准正式写入 |

逻辑对象不等于各建一表。BrowseState/HandoffReceipt优先本地，内容字段与Quote可许可内缓存；Topic/Message初期可沿用JSON表示。最低持久增量按实际纵切落地：Place/ref/Favorite、Instant、Draft/Run及DraftPromotion。DraftPromotion就是正式化映射加状态/授权，不另造通用工作流中心。Preference/Evidence按显式管理和反馈查询需求逐步落表。

~~~mermaid
flowchart LR
 W[Web] --> API[FastAPI用例层]
 A[Android] --> API
 API --> Content[Place/收藏/内容]
 API --> Context[Session/Topic/ContextResolver]
 Context --> Read[只读能力端口]
 Context --> Target[确定性ActionTargetResolver]
 Target --> Grant[授权和版本检查]
 API --> Nav[即时路线/导航用例]
 API --> Draft[Draft/Promotion用例]
 Grant --> Formal[原正式Trip/Revision用例]
 Draft --> Core[共享生成输入/refs/纯校验]
 Formal --> Core
 Draft --> Jobs[有界作业与checkpoint适配]
 Formal --> Jobs
 Content --> Provider[地图/事实/授权报价端口]
 Nav --> Provider
 API --> DB[(PostgreSQL)]
 Jobs --> Model[现有ModelClient]
 Formal --> Execution[原执行/导航/恢复]
 A --> SDK[单一SDK Runtime与typed Binding]
~~~

继续模块化单体、FastAPI/SQLAlchemy/PostgreSQL/Alembic、React、Kotlin/Compose和现有模型/作业技术。事务内投影优先；必要异步消费才使用同库Outbox，event_id幂等。不得用浏览事件隐式创建Trip或硬偏好。共享端口不意味着先重写全部底层框架。

~~~mermaid
erDiagram
 OWNER ||--o{ FAVORITE : owns
 PLACE ||--o{ FAVORITE : references
 PLACE ||--o{ EXTERNAL_REF : resolves
 OWNER ||--o{ ASSISTANT_SESSION : owns
 ASSISTANT_SESSION ||--o{ TOPIC : discusses
 TOPIC ||--o{ MESSAGE : contains
 OWNER ||--o{ PLANNING_DRAFT : owns
 PLANNING_DRAFT ||--o{ DRAFT_RUN : generates
 PLANNING_DRAFT ||--o{ DRAFT_PROMOTION : explicitly_requests
 DRAFT_PROMOTION o|--o| TRIP : creates
 TRIP ||--o{ PLANNING_RUN : plans
 PLANNING_RUN ||--o{ PLAN_REVISION : proposes
 TRIP ||--o{ DAY_PLAN : schedules
 DAY_PLAN ||--o{ ACTIVITY : contains
 PLACE o|--o{ PLACE_CANDIDATE : optional_mapping
 TRIP ||--o| TRIP_EXECUTION : executes
 TRIP_EXECUTION ||--o{ NAVIGATION_SESSION : formal_navigation
 OWNER ||--o{ INSTANT_NAVIGATION_SESSION : independent_navigation
~~~

旧PlaceCandidate和Revision里的UUID保留；canonical_place_id可空。Place外部身份唯一(provider,namespace,provider_place_id)，歧义不按同名/坐标直接合并。所有地图端点明确GCJ02/WGS84；图片、评分、人均、票价、营业安排、此刻开门、指定日期房型报价各有独立语义。

## 3. R01：即时导航的最小性与状态

### 哪些场景需要持久会话

| 场景 | 最小对象 | RoamSync知道什么 | 不能声称 |
|---|---|---|---|
| 只看路线 | RouteQuote | 本次端点/模式/来源/时效 | 已开始导航 |
| 外部地图交接 | RouteQuote+本地HandoffReceipt | 尝试跳转/成功发出Intent，用户返回 | 受控GPS active、持续导航、自动到达 |
| 应用内持续GPS | 持久InstantSession+本地Runtime binding | 当前控制会话、版本/序号、取消/恢复、最新有效观测 | 断网后服务端仍拥有最新手机状态 |
| 模拟验证 | 测试namespace的会话/fixture，source=simulation | 测试状态与合成观测 | 用户真实移动或正式恢复事实 |

因此不为每个外部跳转写Session。持久Instant的必要性来自进程死亡后辨认活动任务、断网取消可靠重试、去重启动、服务端CAS和用户明确结束；若只交接外部地图，这些理由不足。Web本期外部交接不宣称受控GPS。跨端可以不同能力，但完成语义一致。

Instant字段：server owner、device_id、起终点GeoPoint快照、可选destination_place_id、travel_mode、quote/evidence snapshot、status、state_version、route_revision、accepted_sequence、runtime_generation、最新观测时间/来源、started/ended/lease、终止reason。没有TripExecution、活动对或itinerary_version。SDK来源模拟与GPS严格区分；生产即时会话不触发正式Disruption/Recovery。

~~~mermaid
stateDiagram-v2
 [*] --> ready: 创建有效quote的受控会话
 ready --> starting: 用户start命令/取得设备槽
 starting --> active: SDK真实启动ack且定位模式核验
 starting --> failed: 明确失败
 starting --> cancelled: 取消获胜
 starting --> suspended: ack超时/结果不明
 active --> rerouting: 申请新route_revision
 rerouting --> active: 当前revision算路成功
 rerouting --> active: 失败保留仍可用旧路线并提示
 active --> suspended: 失联/本地进程恢复待核验
 suspended --> starting: 显式恢复同会话并重验
 ready --> cancelled
 ready --> expired
 suspended --> cancelled
 suspended --> expired
 active --> completed: GPS到达证据或用户手动确认
 active --> cancelled
 rerouting --> cancelled
 active --> failed
 completed --> [*]
 cancelled --> [*]
 failed --> [*]
 expired --> [*]
~~~

active必须SDK GPS启动证据；SDK方法调用返回不等于导航回调确认。失联只标状态未知/suspended，不称手机已停止。租约到期停止接受旧写，设备恢复后先停旧runtime再重绑；不是服务端能远程保证物理SDK已停。

设备互斥与终态协议（候选冻结）：

- 一个device同一SDK槽只能绑定一种Instant或正式Itinerary任务。切换先显式停止旧任务；即时任务不得静默覆盖正式session。分布式槽/lease的持久表示在最小验证后决定，单例Kotlin对象不足以处理服务重启。
- 设备槽的claim/renew/release在短事务以lease/generation CAS完成；绑定session时统一device槽→session，禁止持锁再调用原Trip/Execution/Accept用例，避免破坏原Trip→Execution→Navigation锁序。正式start需后续用例时先提交可过期reservation，调用失败按同operation释放；期间取消/超时按token补偿。route请求在事务外，完成以session/state/route_revision token CAS；晚结果无权覆盖。
- 新正式/即时GPS客户端都须走同一SDK槽adapter。旧formal start API产生业务导航投影，不等于拥有设备GPS控制权；缺device binding的旧客户端不能被新系统标成已受控GPS，兼容能力与槽冲突必须在V-NAV验证，不在旧API里静默猜设备。
- start/cancel/complete用action_id+body hash幂等。同action重放返回原结果；相同终态的新重复cancel/complete返回当前终态并标replayed；冲突终态返回409 terminal_conflict，不把cancelled改completed。
- 本地取消立刻停止SDK、generation失效、持久保存StopIntent；服务端成功前显示“本机已停止，结束状态待同步”。重启先重放StopIntent，禁止自动恢复该导航。GPS遥测outbox可latest-value，终止命令不可被latest-value丢弃。
- SDK启动后ack丢失，重试同session/action；不得新建任务。start与cancel竞争由服务端CAS决定；本地即使稍后收到start成功，也按StopIntent停机并确认取消。
- 进程死亡恢复先读server终态、StopIntent和当前device binding，再确认模式/权限/quote新鲜度与用户恢复意愿；不得只按“最近Trip”自动导航。
- 外部HandoffReceipt只有attempted/dispatched/failed/returned/user_reported_completed等本地交接状态，永不投影成GPS active/completed；手动报告须注明来源。
- 步行、驾车分别验证；transit缺逐向SDK能力时保持路线/外部模式，不调用驾车冒充公交。

VERIFIED：AmapNavigationSource.calculate固定calculateDriveRoute（71），startSimulation调用startNavi(2)（82）；NavigationRuntime.outbox在内存中。缓存合并Manifest仅INTERNET与receiver权限，没有定位权限；缓存SDK JAR含walk/drive/startGPS等符号，但符号存在不证明签名、Key授权、运行或权限成功。源码回调缺少可核验的逐请求token关联，旧callback污染新binding是待验证风险，不能仅依赖Runtime generation宣称已解决。详见round2/sdk-static-inspection.json。

**VALIDATION REQUIRED，最早Phase0**：真机测试签名/Key、权限拒绝与降级、真实起点、步行/驾车GPS与回调、连续rebind晚回调、旋转/后台/进程死亡、断网取消、同设备正式/即时切换。当前没有运行这些测试；测试动作与预计改动见实施准备。

## 4. R02：Draft复用边界与函数级改动面

MEASURED（禁网、无DB/模型）：正式CandidateActivity拒绝day_date=null；build_planner_input在无date的day上抛TypeError；PlannerReferenceCodec往返成立。该负向探针证明原路径不兼容，不证明Draft可以生成。原Graph每节点自己建session并读Trip，不能直接灌入假的TripContext来称独立。

| 当前函数/模块 | 真实依赖 | 最小复用/提取 | 必须保留的正式边界 |
|---|---|---|---|
| planning_context.build_planning_context:13 | Trip/Preferences/DayPlan/预算/Execution读库 | FormalContextAdapter保持；新DraftInputAdapter只读Draft/Place/明确要求 | 不让Draft调用补偏好/执行状态读写 |
| openai_planner.build_planner_input:322 | dated days、decision_context、trip/preferences、formal IDs | 提取有界候选池/偏好与证据投影公共小函数；分别Formal/Draft assembler | 原函数兼容包装，原formal prompt/schema差分验证 |
| OpenAIResponsesPlanner.generate:118起 | FormalGraphState、允许日期、formal resolver、snapshot | 共用model_client、JSON规范化/错误转换/有界一次纠正策略；增加Draft adapter | 不复制整个provider类与Graph |
| PlannerReferenceCodec:10 | 普通JSON，request-local UUID refs | 原样复用并测试unknown ref失败 | 模型不能发数据库身份 |
| PlannerEntityResolver.schema/resolve | activity_N/candidate_N、日期枚举、正式活动语义 | 提取通用ref domain检查；Draft输出day_index与PlaceRef，Formal仍day_date | 不放宽现有SemanticPlannerOutput日期/活动域 |
| phase1a planning_brief.enrich_brief/project_requirements | 部分纯编译；bind/load锁Trip/run/version/AssistantSession | 选取纯来源/否定/撤回/软要求编译；binding做Draft/Formal两adapter | 不能直接把bind_brief目标改nullable，不能整包覆盖最新Companion |
| plan_revision_service.validate_candidate_plan:64 | ORM读取/正式日期/锁定/执行/范围/预算/来源/路线 | 从已有规则中小步提取正数/重复/时间不重叠/预算汇总/route completeness等纯函数 | 正式ownership/version/冻结/保护/预约/范围检查仍只由原formal入口强制执行 |
| candidate_route_service.enrich_candidate_routes:28 | Trip Days/Activity/PlaceCandidate、完整正式保留活动 | 提取端点RoutingPort与纯route attachment；DraftRouteAdapter不访问Trip | 受保护正式活动仍纳入完整路线 |
| candidate_schedule.repair_route_schedule:11 | CandidateSnapshot、date、formal活动/冻结 | 只在证实等价后共享分钟计算/有界时间修复核，不先泛化整函数 | 修复后必须重跑相应Validator |
| planning_graph / runtime.invoke_compiled_graph:43 | run.trip_id、节点session_factory、interrupt/commit | 不复制整Graph；Draft编排只调用共享生成步骤/校验和独立run存储 | 原formal图、checkpoint namespace及Accept节点不被Draft绕过 |
| planning_goals.check_goal_satisfaction:91 | dated snapshot/正式route与scope | 提取适合relative day的纯目标比较核 | 不把未核实事实当目标已满足 |

公共边界控制在三类：GenerationInputParts（候选/要求/来源）、RefDomain/输出解析、PurePlanRules（schedule/budget/route结构）。可逻辑分组而不强制三个新服务；提取一个规则就让原Formal入口调用同一实现并跑差分，禁止复制另一套相似Validator。纯规则所需数据先由各adapter装配，不能从公共模块反向import Trip ORM/HTTP/Graph。

DraftInput包含destination、duration、day_index、可空dates、明确要求源/作用域、Place快照和Facts。DraftPlanSnapshot使用draft_activity_ref/day_index/PlaceRef，不复用formal CandidateActivity或把ordinal映射到虚构日期。正式化才按用户明确起始日期绑定真实day_date与Trip-owned identity，并重新校验时效事实/路线。

DraftRun状态queued/running/succeeded/failed/cancelled；input_version/hash、lease/attempt、取消token、输出snapshot/规则版本。只有当前input_version且未取消才CAS发布。作业领取/超时复用现有机制的可抽取部分，不创建新通用队列平台。取消在模型不可中断时仍阻止晚结果发布；retry新Run，重放相同幂等键同Run。Checkpoint只是执行基础设施，Draft/Run才是产品恢复真源。

Draft reviewable=结构、身份及已执行的规则可审阅，必须附ValidationCoverage：passed_rules、blocked_rules、not_checked、evidence_snapshot_refs、ruleset_version、evaluated_at。没有日期时营业/预约/日期相关路线/报价必须not_checked，不称正式可执行。

~~~mermaid
stateDiagram-v2
 [*] --> draft
 draft --> generating: DraftRun
 generating --> reviewable: 当前version结构校验可审阅
 generating --> draft: 失败/取消且需求保留
 reviewable --> draft: 改需求version加一
 reviewable --> promotion_requested: 用户明确正式化意图
 promotion_requested --> promoted: 已有目标Trip且结果可查
 promotion_requested --> reviewable: 未建档前取消/失败
 draft --> archived
 reviewable --> archived
 promoted --> archived
~~~

**VALIDATION REQUIRED**：无日期合成3日方案真实模型与mock分别运行、规则差分、formal prompt/schema/accept回归、Run取消/重启/晚结果/幂等、正式业务表0写入。当前未执行新Draft实现，不能宣称完成。

## 5. R03：三种正式化行为与两个工程方案

### 既有事务证据

| 边界 | 当前实现/提交点 | 能推出什么 |
|---|---|---|
| Trip创建 | repository.create_trip:40支持commit=False；assistant.confirm_action:453最后commit | 单纯建档可在调用者事务中组合 |
| Run创建 | create_planning_run:45含resolve_planning_intent，可能语义模型；commit/flush可选 | commit=False不代表整个函数纯数据库 |
| Graph | plan_node:431前后commit；validate_node:489自建session并做路线I/O | 长任务不是一个SQL事务 |
| Revision落库 | save_plan_revision:173，249无条件commit；Graph persist_node:603调用 | candidate持久化与后续Accept分事务 |
| 用户确认 | approval_node:646 interrupt，runtime用Command resume | 已有可靠可恢复确认边界 |
| Accept | accept_plan_revision:498锁Revision/Run/Trip、重校验；660commit | 正式应用本身原子；不能外部套begin就把前序Graph纳入事务 |
| Checkpoint/后续状态 | _execute_planning_run独立Saver和session，更新pending_interrupt另commit | checkpoint与业务提交也需要恢复/对账，不是全链原子 |

第一轮“确认后Trip+候选同事务”和“复合操作可直接调用原服务单事务”的无条件表达已撤回。

### 三种用户行为（业务语义不等于点击数）

- **保留草稿**：自动保存/显式保留，只写Draft/Run，无Trip。
- **只创建旅行**：确认目的地/日期/可空预算→幂等Trip+Days/Preferences，不自动LLM规划、不开执行、不自动Accept。草稿可保留来源关联，后续用户另选采用。
- **创建并采用当前方案**：用户看到绑定真实日期的具体PreparedPlan及ValidationCoverage、来源缺口和预算影响，明确一次组合确认。授权只覆盖该draft_version、content_hash、日期、约束及事实指纹；不是批准后台自由重生成任何计划。

无法合并确认的情况：方案未显示、缺必需日期/目标/预算冲突选择、校验阻塞、内容或价格/路线/约束发生实质变化、未知敏感授权、授权过期/撤回。可以不增加点击：准备过程异步完成后，显示一张可确认的完整计划，用户一次“创建并采用”。失败/变化才需要新确认。

### P1：可恢复异步正式化协调（默认推荐）

1. promotion-preview先在Draft域绑定日期并取动态事实/真实路线，形成PreparedPlan+semantic content hash+短期prepared token；不写Trip。不得给缺失酒店库存补保证。
2. 用户选择action=create_only或create_and_adopt；服务端保存DraftPromotion（同时作幂等映射与授权记录），包含owner、source/version、prepared/content/evidence hash、allowed_action、target metadata、授权时间/失效/撤回、operation状态。
3. worker验证授权/版本后，T1明确创建一个正式Trip，并将target_trip_id与operation状态一起提交；这个Trip已经由用户明确批准，不是假隐藏Trip。
4. 在事务外获取需刷新数据；不调用LLM自由改写“当前方案”。将相同语义确定性映射到正式candidate，使用受审的materialize adapter；创建Run/Revision必须符合formal状态与来源规则。原Run创建包含模型/intent，不能未经适配直接塞进T1。
5. T2持久化formal pending Revision与operation引用；即使现有save函数内部commit，也必须避免operation映射落在提交后的无记录窗口；小范围提交所有权/原子映射修复是此方案前置验证，不称现成能力。
6. 只在canonical semantic hash一致、证据有效且无新增阻塞时消费同一授权，T3在锁定operation→revision→run→trip的确定顺序下重新校验并调用原Accept语义。授权消费/取消竞态必须进入同一受审接受边界；现有裸Accept没有这个guard，须先验证最小改动。
7. 成功后operation=applied；若接受已提交而进度/回复丢失，对账读取revision accepted和已消费授权后完成operation。不能因响应失败再建Trip或再生成方案。
8. 如果内容实质变化、指纹过期、条件缺失，转needs_review，展示差异，不自动采用；原组合确认不授权新的模型方案。

指纹规则：semantic content hash覆盖稳定Place身份、真实日期、活动顺序/时间/时长、交通模式、已显示的费用性质/值、正式约束与明确要求版本；新分配Trip/Activity UUID和非语义说明文字不改变它。evidence fingerprint独立记录来源身份/关键事实值/适用时间与quote身份，retrieved_at本身不等于事实更新；刷新不得仅改时间冒充新鲜。任何关键值/适用范围改变、quote失效或新增阻塞都needs_review；若仅同一允许证据的无语义重新获取，必须记录等价判定与时效重检，不悄悄更换用户批准的可售报价。实际归一化/等价规则要用golden fixtures验证。

此方案复用现有作业与正式Accept，端到端为可恢复多事务，不承诺全有或全无。优点是早可落地、失败可解释；代价是可能留下“已创建，方案未采用”的明确Trip及operation，需要可见状态和恢复。

### P2：预备完成后短数据库原子正式化（备选）

所有Provider/LLM/路线/相对日转真实日期与预检都在事务外完成；一次用户确认后，在一个短事务中重验prepared有效性，创建Trip/来源候选/DayPlan，创建确定性formal Run/Revision，调用原正式Validator与Accept核心并写operation结果。网络请求不允许进入事务。

前置改动：save_plan_revision与accept_plan_revision拆无commit核心+旧API兼容wrapper；create_planning_run拆语义解析/持久化，禁止在原子段调用解析模型；锁序、异常rollback、约束、导航supersede与拒绝Memory边界回归。未经执行这些验证，P2只是设计，不是当前可组合能力。日期/事实过期时abort再预备，不能在锁里等待Provider。

优点：最终SQL状态原子，不留部分Trip；代价：触及已有可信核心更多，容易回归。**暂不以P2作为首个正式化实现**；P1门禁通过后，如用户任务证明部分状态明显伤害体验，再评估P2。技术细节无需用户在两个低层方案之间反复选择；默认P1，产品只需批准失败时可见Trip语义与组合按钮范围。

### 失败、取消和恢复契约

| 时点/事件 | P1状态与恢复 | P2状态与恢复 |
|---|---|---|
| 动态事实/路线预备失败 | 保留Draft，preview_failed；无Trip | 同左 |
| T1前取消 | operation cancelled，无Trip | 原子提交前取消令牌获胜则不写 |
| T1后任务失败 | trip_created/failed，显示Trip已建、方案待处理；同operation重试，不自动删除 | 最终事务前失败无Trip；事务失败rollback |
| 内容变化/校验失败 | needs_review；pending候选不可自动Accept；Trip可保留/归档 | rollback；刷新prepared后重新确认 |
| 重复提交/响应丢失 | owner+operation+key/hash唯一，查同operation/Trip/Revision | 相同key取同结果；body变409 |
| Apply与cancel竞争 | 以锁内授权消费提交为线性化点；撤回先提交则阻止Accept；Accept先提交则返回“已采用”，提供另行正式修改 | 相同授权竞争原则 |
| worker/进程重启 | 按持久operation引用及正式版本恢复；不按文本重推用户意图 | 查询command结果，禁止重复建档 |
| checkpoint落后/状态更新失败 | 对账Accepted事实/操作授权；重放幂等步骤 | 结果记录与业务同事务，返回可恢复 |

授权可撤回不等于已接受行程能无版本回滚。P1取消后已创建Trip保留，用户可明确归档；不自动删除或误标为测试。Promotion状态建议requested/preparing/trip_created/materializing/awaiting_apply/needs_review/applied/failed/cancelled，带stage和目标引用；状态枚举以实际持久步骤再冻结。

## 6. R04：Read Context、Action Target与授权严格分离

~~~typescript
type ContextEnvelope = {
 schema_version: 2;
 request_id: string; view_id: string; topic_id: string;
 physical_location?: { point: GeoPoint; observed_at: string;
   accuracy_m: number; source: 'gps'|'browser'|'user_pin' };
 browse_context?: { area_ref?: string; place_ref?: string; selection_version: number };
 discussion_subject?: { kind: 'place'|'destination'|'draft'|'trip'; ref: string };
 read_context_requests?: { kind: 'trip'|'draft'|'place'; ref: string;
   purpose: 'compare'|'summarize'|'feasibility'; requested_fields: string[] }[];
 action_request?: {
   kind: 'create_trip'|'create_and_adopt'|'modify_trip'|'start_instant';
   target_ref?: string; expected_version?: number; proposal_id?: string;
 };
};
// 上述是客户端请求/线索，不是权限。
// 以下仅由服务端owner/目标Resolver/授权存储生成。
type ResolvedAction = {
 owner_ref: string; target: { kind: string; id: string; expected_version?: number };
 permission: string; authorization_ref: string;
 input_hash: string; allowed_effects: string[]; expires_at?: string;
};
type FormalConstraintSet = {
 target_trip_id: string; itinerary_version: number;
 preferences_version: number; protected_refs: string[];
 execution_snapshot_hash?: string; constraint_source_refs: string[];
};
~~~

ActionTargetResolver先验证可信owner和对象可访问性，确定唯一目标、合法版本/operation，批准动作只来自显式命令或确认记录。模型可建议引用，但不能通过read_context、discussion_subject或猜Trip ID触发写入。普通建议不默认创建PlanningRun；Read Resolver选择最小字段，并保留选择/拒绝理由。

位置、浏览、讨论各有source，不设全局“最后城市”覆盖。view/topic/selection_version/request_id共同拒绝晚响应覆盖；查询缓存按subject/时间/条件键，不仅按城市名。Topic切换重新选择约束，不携带旧预算；正式硬约束由目标Trip读出，不由客户端可编辑字段覆盖。

新增契约用例：
1. physical杭州、browse南京酒店、只读苏州Trip同时在场：南京房价query不得继承苏州预算。
2. “南京这家适合加进苏州行程吗”：允许最小只读苏州日期/路线约束作可行性比较，返回跨城成本/风险，不创建Run/Activity；明确“加入”后另做目标/权限/候选确认。
3. 南京详情旧response与助手新选择并发返回：selection_version旧者不得替换新Place/动作目标。
4. Topic从今晚住宿切到下周Trip：明确局部预算不跨任务；显式长期偏好可作为软默认且可解释。
5. 同名/同城多个Trip且action目标不唯一：不写、不猜；一次集中澄清。
6. 无关Trip/聊天不得被查询或送模型；reader spy断言允许表/对象/字段，缺身份返回拒绝而非补读。
7. 伪造owner/授权ref/旧expected_version/跨Topic proposal均不能写入。

## 7. 稳定助手与旧CASCADE迁移

VERIFIED：database.AssistantSession.trip_id为CASCADE（793），get_or_create_session按trip_id查询（assistant_service:180），confirm会改绑定。只将FK改SET NULL会使被删Trip的旧会话混入“trip_id is null取最近”的全局检索，仍有串用风险。

推荐最小迁移：原表显式增加scope=legacy_trip|legacy_unbound|global、可信owner与schema_version，新global行trip_id必须null；旧有Trip行标legacy_trip，原本无Trip的创建前会话标legacy_unbound，保留最新run。先改检索按owner+scope+明确session/topic，再改旧FK为SET NULL；legacy目标删除后仍legacy_trip并有已删target tombstone，不能变global或legacy_unbound。新增Topic映射存原trip_ref/显示快照和删除标志；消息内容尽量原地保留，明确继承话题才引用，不把所有历史注入模型。

兼容旧POST /assistant/sessions 的trip_id=null时，只能选同owner的legacy_unbound创建前会话；不能选已删Trip后trip_id变null的legacy_trip，也不能按“最新null”拿到新global。新版恢复global按owner+scope+明确ID。旧pre-trip reset限legacy_unbound，不能因FK置null就允许清空原Trip历史；legacy scope来自可验证迁移来源，不由客户端设置。

迁移ledger记录session旧trip/新scope/映射；旧来源/拥有者不明记录不公开。新global行不会受Trip删除级联；删除Trip后只读context失效、未消费Action撤销、latest_run按原SET NULL处理，助手与收藏不丢。先前旧客户端调用以兼容adapter访问legacy话题，不允许旧global查询命中其它scope。FK切换顺序、混版本读/写、Trip删除回归、失败恢复与不丢历史均待副本验证；本轮不改Schema。

## 8. R05：可测试事实字段契约与Phase0修复

~~~typescript
type EvidenceField<T> = {
 value: T | null;
 value_status: 'present'|'unknown'|'conflicting'|'unavailable';
 nature: 'provider_assertion'|'estimate'|'user_report'|'unknown';
 freshness: 'fresh'|'stale'|'unknown';
 served_from: 'live_provider'|'cache'|'stored_snapshot';
 evidence_refs: string[];
 retrieved_at?: string; provider_observed_at?: string;
 valid_until?: string; estimate_method?: string;
};
type PriceValue = { amount_fen: number; currency: string;
 unit: 'per_person_reference'|'entry_ticket'|'room_night' };
type HotelQuote = {
 quote_id: string; place_ref: string; check_in: string; check_out: string;
 occupancy: { adults: number; children_ages: number[]; rooms: number };
 room_type: string; amount_fen: number; currency: string;
 taxes_and_fees: { included: boolean; details: string };
 cancellation_terms: string; availability: 'available'|'unavailable';
 provider_ref: string; retrieved_at: string; valid_until: string;
};
~~~

present不等于已证实实际售价，live_provider不等于此刻可售；freshness只表示声明的时效规则范围。rating unknown=value null，不补0。category_cost保留内部planning_estimate并注明estimate_method，不把它填进PriceValue实查字段。只有明确来源声明零票价/对应单位，才可显示“门票免费”，不能由estimate=0推出整段体验免费。unknown不能按0排序成最便宜。legacy记录缺来源时显示“参考估算/评分来源待核验”，不批量改历史数值或猜真实0分。

场景字段能力：当前真实POI可查身份/地址/坐标/分类与可能存在的rating/photos/人均参考；缺失就是unknown。餐饮是否开门、当天菜价/排队/口味满意度无对应可靠来源时只能候选线索，不能保证。住宿POI/人均参考不提供入住日房型库存；没有授权报价接口就不创建HotelQuote，显示待核实/外部核实入口。评论无授权源不合成。营业公告与实时开门、天气预测与实测、路径估算与真实GPS均分开。

Phase0小改动包（批准后执行）：maps_service.search_amap_places的rating归一化与source/nature字段；schemas与TS/Kotlin可空/性质契约；PlacesDrawer/Inspector/推荐卡分字段标签；保留旧Planner estimated_cost_fen的数值输入与Validator语义。旧DTO兼容不是把所有estimated_cost变nullable导致预算校验失效。新增价格语义与unknown不回填正式历史。

最小fixture矩阵：missing/空数组/非法rating、明确0、类别estimate=0/8000、Provider票价0、有/无photos、缓存fresh/stale、查询成功但字段缺失、相互冲突来源、人均误入房价、无报价库存。断言显示来源/估算/过期/未知；正式计划成本回归不变；actual_price永不由category estimate或LLM填充。

## 9. API草案（候选冻结，旧API兼容）

写命令使用可信owner+Idempotency-Key/body hash；state_version与正式itinerary_version分开；401/403预留给可信访问门禁，不声称现有API已鉴权。错误detail={code,message,field_errors,retryable,request_id}，SSE另有终态契约。

| API | 主要输入/输出 | 边界 |
|---|---|---|
| GET /places/search、/places/{id} | 明确area或near、PlaceRef、EvidenceField、分页 | 无Trip/LLM；统一外部身份/缺失态 |
| PUT/DELETE /me/favorites/{place} | 幂等Favorite | owner由可信边界，不采信body owner |
| POST /routes/query | 明确GeoPoint/CRS/mode/time→RouteQuote | 仅路线，能力标签route_display/external/gps_supported |
| 客户端external-handoff | RouteQuote→HandoffReceipt | 不调用受控Instant start；不自动到达 |
| POST /instant-navigation-sessions | quote、device→ready | 仅应用内受控GPS/隔离测试模拟；正式表0写入 |
| POST /instant-navigation-sessions/{id}/actions | start/start_ack/cancel/complete、version/action_id | 设备互斥、终态幂等、取消持久 |
| POST .../{id}/observations、/route-refresh | sequence/revision/time/source→CAS结果 | 不向正式observations混发Instant |
| GET /instant-navigation-sessions/current | device及可信owner | 恢复前核对StopIntent，非自动续航授权 |
| POST /assistant/sessions、messages[/stream] | owner scope/topic、ContextEnvelope、message_id | 稳定session与逐请求最小读/动作授权 |
| POST /planning-drafts、/{id}/runs | relative days/可空dates、Brief、version/hash | 纯Draft；取消/恢复/重试不建Trip |
| POST /draft-runs/{id}/cancel | action_id、expected state | cancel token+阻止晚发布；不假称原formal Run已有取消API |
| POST /planning-drafts/{id}/promotion-preview | 明确日期、source version→PreparedPlan/token/coverage | 只读预备，不创建Trip |
| POST /planning-drafts/{id}/promotions | action=create_only|create_and_adopt、prepared授权/key | 返回operation，不承诺已采用或全链原子 |
| GET /draft-promotions/{id}、POST .../cancel | 操作状态/各目标引用、撤回 | 对账恢复、取消线性化点；失败不默删Trip |
| POST /trips（增强） | 明确目的地日期、可空预算、幂等 | create_only无默认LLM；创建并规划需显式组合意图 |
| 原Run decision/Revision Accept | 原版本/验证+受审授权guard | 保留显式用户控制，不由模型猜目标 |
| /me/preferences、/experience-feedback | scope/source/纠正/撤回 | 显式优先、行为软证据 |
| /lodging/quotes（授权后） | 日期人数房型→真实HotelQuote | 无Provider则unavailable，不产假quote |

新DTO先用共享golden fixtures/OpenAPI验证两端，旧数组API由adapter兼容，不全面改envelope。HotelQuote为将来能力，不是当前接口已接通。建议不为概念对称增加通用Context表或每领域独立Agent。

## 10. 双端/Agent数据流与兼容

~~~mermaid
sequenceDiagram
 participant C as Web/Android
 participant B as Backend
 participant P as Provider
 participant J as Draft/Promotion Worker
 participant F as 原Formal Accept
 C->>B: 无Trip搜索/详情/收藏
 B->>P: 真实字段查询
 B-->>C: PlaceRef与来源/unknown
 C->>B: message+read context+action request
 B->>B: 最小读Resolver/独立ActionTargetResolver
 B-->>C: 建议或待确认动作
 C->>B: Draft生成/恢复
 B->>J: DraftInput与版本
 J-->>C: reviewable与ValidationCoverage
 C->>B: promotion-preview绑定真实日期
 B->>P: 动态事实/路线重取
 B-->>C: PreparedPlan及指纹
 C->>B: 一次明确create_and_adopt授权
 B->>J: 持久operation（P1）
 J->>B: 分阶段创建Trip与formal pending
 J->>F: 同内容授权+正式版本重校验
 F-->>C: 已采用 或 needs_review/失败可恢复
~~~

内容与路线不依赖模型。Agent只能经能力端口读最少数据/提出结构化Suggestion，Place解析成功才能进入详情/地图/导航。正式操作需真实目标/授权/版本；候选接受仍是可信核心。模型失败不阻断地点搜索、收藏、地图和可用导航模式。

保留：正式Trip/DayPlan/Activity/Run/Revision、Validator/Accept-Reject、candidate edit、Execution/Slack/Disruption/Recovery、Memory来源、SSE终止与事实时效。调整：入口、nullable/source展示、Brief编译、Context/Topic、幂等、timezone计划状态。新增：独立Place纵切、Instant、Draft/Run/Promotion。旧来源不明Trip不删；迁移按扩展→验证→兼容切读→受控收缩。

## 11. 冻结与验证状态

业务原则（无Trip探索/导航/草稿、内容与助手平等、正式边界/历史安全）经第二轮原则接受，不再列为开放争议。以下技术选择为候选：Instant最小模型、公共Draft规则边界、P1正式化、Read/Action分离、事实正交字段、受控单owner及明确集成块。GPS、无日期Draft复用、promotion授权/事务/取消、legacy FK迁移都未执行实现验证。

共同基础→A内容即时服务/B连续助手/C自由规划正式旅行并行纵切，Q质量贯穿；依赖/owner/门禁详见[路线图](ROAMSYNC_DEVELOPMENT_ROADMAP_V2.md)与[实施准备](ROAMSYNC_IMPLEMENTATION_READINESS.md)。本轮到文档修订为止。
