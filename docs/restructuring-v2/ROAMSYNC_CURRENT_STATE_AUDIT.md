# RoamSync 当前状态审计

日期：2026-10-15，Asia/Shanghai。状态：第一轮只读审计完成；V2 未冻结、未实施。

第二轮修订说明：本文件保留第一轮事实与实测范围，不把旧测试冒称本轮重跑。后续只读复检309文件零漂移，补充函数/事务依赖、15树双向差分、缓存SDK/Manifest和禁网无日期兼容负向探针，见[第二轮回应](ROAMSYNC_REVIEW_ROUND2_RESPONSE.md)与[实施准备](ROAMSYNC_IMPLEMENTATION_READINESS.md)。目标设计以修订架构为准：external交接不必持久Instant，组合正式化可一次确认且默认多事务恢复；第一轮目标取舍不再作为现行规范。

## 证据口径与范围

- **VERIFIED／代码事实**：本轮读过的源码、Git、实际命令与测试；文件行号属于本轮工作树，会随以后修改变化。
- **MEASURED／实测**：本轮运行结果。测试成功仅证明测试覆盖范围；不推导模型质量、真实定位或产品价值。
- **HISTORICAL／历史待复核**：已有报告与模型结果。可证明记录存在，不自动继承其通过状态。
- **HYPOTHESIS／设计假设**、**RECOMMENDED／推荐方案**、**OPEN／未决问题**：均不表示已实现。

官方目录为 `E:\Study\RoamSync`，依据 `AGENTS.md:5`，本轮以其当前磁盘源码为主。聊天目录 `C:\Users\Dapper\Documents\多智能体旅游规划` 是另一 Git 仓库：main、HEAD `ea03b29`，只有早期规划模块，不能作为最新系统。

本轮没有修改业务源码、Schema、正式数据库数据、部署配置，没有合并、提交或切换分支，没有请求真实模型。允许的写入为本组文档、脱敏证据和测试构建产物。正式服务只请求 health 和无效/不存在 ID 的 GET；不读取真实聊天和旅行正文。

证据目录：[evidence](evidence/)。`source-and-worktrees.json` 保存309个源码/测试/构建配置哈希和15个工作树盘点；`image-source-binding.json` 保存镜像绑定；`backend-test.log` 为本轮隔离后端日志；`readonly-http.json` 为正式服务只读检查。测试结论另见 `verification.json`。

## 1. 工作树与成果是否集成

官方活跃分支 `codex/roamsync-demo-release-20261007`；HEAD `0b5010fe5a7b06dcec1ab7b159b5b337244247ae`。文档写入前 Git status 有150条既存修改/未跟踪项。HEAD 是10月8日发布记录，不等于10月15日磁盘源码。保留所有原有改动。

| 工作树 | HEAD简写 | 是官方HEAD祖先 | 盘点脏项 | 对官方核心源码的字节差异/独有文件 | 结论 |
|---|---|---|---:|---|---|
| RoamSync | 0b5010f | 是 | 150 | 基准 | 当前官方磁盘源码 |
| closeout-20261014 | 0b5010f | 是 | 277 | 42 / 13 | 不可视为已合并 |
| phase1a-20261012 | 0b5010f | 是 | 244 | 40 / 2 | 不可视为已合并 |
| phase1b1-20261012 | 0b5010f | 是 | 249 | 42 / 4 | 不可视为已合并 |
| phase1b2-20261014 | 0b5010f | 是 | 254 | 47 / 7 | 不可视为已合并 |
| phase1b21-20261014 | 0b5010f | 是 | 261 | 47 / 9 | 不可视为已合并 |
| planner-reliability-clean | 26e33f7 | 否 | 1 | 提交核心差异2个文件 | 尚未整体合并 |
| planner-reliability-clean-v2 | 4a523b7 | 否 | 1 | 提交核心差异2个文件 | 尚未整体合并 |
| planner-reliability-clean-v3 | 322f553 | 否 | 1 | 提交核心差异4个文件 | 尚未整体合并 |
| planner-reliability-final/release | 54b8888 | 否 | 0 / 0 | 提交核心差异4个文件 | 修复仍有缺口 |
| release-20261008 | 8ee7dbf | 是 | 1 | 提交核心差异0 | 历史发布参照 |
| release-final-20261008 | 0b5010f | 是 | 0 | 提交核心差异0 | 干净历史参照 |
| tourism-knowledge | 5023a28 | 否 | 0 | 非祖先但已有对应模块 | 功能集成不等于提交合并 |
| travel-facts | 5f9f5e5 | 否 | 0 | 非祖先但已有对应模块 | 功能集成不等于提交合并 |

前五个开发树的统计范围为 backend/app、backend/tests、web/src、Android main/java，排除编译缓存；行尾不同也计入差异，因此差异数不能当缺失功能数。后面的“提交核心差异”来自提交比较，口径不同；完整清单见 JSON。

**VERIFIED**：正式目录已有 `tourism_knowledge/`、`travel_facts/` 及调用适配器。phase1a 等独有的 `backend/app/planning_brief.py` 与相关测试不在官方目录；closeout 独有 `planning_weather.py`、`planning_events.py`、`planning_event_text.py`、`planning_updates.py`、`recommendation_claims.py` 等也未集成。只读取了这些能力的接口/关键片段和交接摘要，没有对独立树做完整验收。

**VERIFIED**：对比54b8888，官方 `decision_context.py:14` 缺少保留非目标日期执行指针并标记 `outside_requested_scope` 的修复；`planning_intent_service.py:664` 缺少“其他日期安排不变”等计划元要求识别。历史 Phase0.5 提案与现存差异吻合，但本轮未应用，也未把这些独立树的旧测试数带入官方结果。

本轮测试镜像209个 app/tests/migrations 文件与本地匹配；运行 API/Worker 各138个 app/migrations 文件匹配。该检查不涵盖生产Web资产、evals或运行环境全部设置，不能宣称全服务字节绑定完成。

## 2. 产品入口和调用链

### Web

`web/src/main.tsx` → BrowserRouter → `App.tsx:72`。默认/未知路径转 `/trips`；`/assistant` 也转旅行列表（86）。主要页面只有旅行列表、新建/编辑旅行、Trip规划工作台及开发监控/对话页。

1. **无 Trip 对话已存在**：`TripListPage` 顶部“旅程总管” → `AiPlannerPanel`（App:160，不传 tripId）→ `getAssistantSession(undefined)` → POST `/api/v1/assistant/sessions`，`trip_id:null` → Companion。
2. **显式建档**：`CreateTripPage` 搜索城市和住宿 POI → `repository.createTrip` → POST `/api/v1/trips` → `repository.create_trip:40` 同时创建 TripPreferences 和每日日计划。偏好另行保存；前端已有保存失败保留Trip ID、重试偏好避免再建档测试（App.test.tsx）。
3. **地点探索入口依附行程**：Trip卡片 → PlannerPage → `PlannerSidebar`“加入地点” → `PlacesDrawer` → `/trips/{id}/places/search` → 地点“确认加入” → DayPlan Activity。`App.tsx:524` 的抽屉以“加入第几天”为目标，无独立目的地内容首页。
4. **地图是行程地图**：App:521 `MapCanvas` 接收当天 Activities、Trip center、住宿和 RouteLeg。JS API画点/线，无 Web GPS导航控制；加载失败展示示意 fallback，不能视为真实地图降级。
5. **正式规划**：工作台 `AiPlannerPanel key={trip.id}`（525）→ 助手 session → PlanningRun → worker → Graph → Revision → 用户 Accept → 刷新工作台。面板最近修复能恢复 session.latest_run_id，并校验其Trip（AiPlannerPanel:88–119）。
6. **执行/恢复**：`useExecutionProgress` → `ExecutionStatusCard`、`ActivityExperienceCard`、`DisruptionDetailCard`、`RecoveryPanel`。能展示并操作正式旅行执行；Web未提供真实应用内导航。

### Android

`MainActivity.kt:19` → RoamSyncViewModel → `MobileApp`。`RoamSyncViewModel.kt:18` AppScreen为 TRIPS/DETAIL/ASSISTANT/CREATE/NAVIGATION，默认TRIPS。详情底栏为“行程/地图/预算/总管”（MobileApp:约58），底栏只出现在DETAIL。

- 首屏 `TripsHome` 可直接打开助手；`restoreAssistant:171` 在 trip为空时创建/恢复无Trip会话。
- 打开旅行 → `openTrip:88` → `loadTrip` 并行请求trip/days/budget/execution-progress → 详情。
- 新建 → `createTrip:274` → 城市精确匹配 → createFullTrip → 详情。Android表单要求非空有效预算（280），而后端预算允许null、Web可无预算，已有产品语义不一致。
- 详情地图 → `RouteMap.kt:27` WebView高德地图；底部地点调用 `uri.amap.com/marker`（约83）是外部地图地点标记/唤起，不证明已开启导航或到达。
- 执行卡 → `startNavigation` → `/trips/{id}/navigation/start` → `bindRuntime` 使用正式前后活动坐标 → SDK calculate → `NavigationExecutionScreen`“开始模拟导航”（MobileApp:208）→ Runtime上传观测 → 后端进度/恢复。
- 离开导航页与结束导航不同；`cancelNavigation` 停止SDK并取消服务端会话。导航页轮询5秒，临时失败保留上次服务端状态。旋转/进程重启后的SDK、权限与持久化outbox完整恢复尚未真机验收。

**结论**：助手后端与首屏入口已经部分独立；搜索/地图的用户体验仍主要服务正式行程；不存在独立收藏、真实图片详情、附近发现完整闭环。不是“所有操作必须先建Trip”。

## 3. 创建记录的可达来源

| 记录 | 当前写入路径与调用者 | 创建时机/保护 | 对污染的判断 |
|---|---|---|---|
| Trip | main:212 → repository.create_trip:40；Web新建、Android createFullTrip、其他API调用者 | 明确POST；API未见通用创建幂等键 | 重试/直接脚本可能新增；未查真实行，不归因 |
| Trip复制 | main:764 → repository.duplicate_trip:157；列表复制；assistant reuse | 用户操作或确认工具 | 每次复制确实产生新Trip；不一定是污染 |
| Trip助手创建 | assistant_service.confirm_action:453 → create_trip:490 / duplicate_trip:482 | prepare_action只存待确认；accept后写入，applied_actions防重复 | 不是普通闲聊暗建Trip；问题是规划预览被要求先建档 |
| DayPlan | repository:49 创建Trip时按日期生成；日期扩展:139；duplicate:241；assistant shift:447 | 正式Trip日期范围；seed直接写 | 没有独立草稿DayPlan |
| PlanningRun | planning_run_repository:45/104；main:356；assistant:412/510；trip_execution_service:210；experience_replanning_service:64；observation_ingestion:369 | 所有run.trip_id非空；明确规划守卫；自动恢复有触发去重 | 每次正常重试可建新Run，不必建新Trip |
| PlanRevision | planning_run_repository.save_plan_revision:173/216，经Graph persist节点调用 | 同Trip/base版本；旧pending superseded；路由增强和Validator | 候选持久化不是正式安排 |
| TripExecution | trip_execution_service.start_trip_execution:266/307；main:430；navigation/start:79隐式调用 | 一个Trip一个Execution；启动导航可同事务创建Execution | 这是有正式Trip的执行，不是无Trip旅行 |
| NavigationSession | session_service.create_navigation_session:114/162；main:467；start_navigation:41 | execution进行中、正式相邻RouteLeg、当前版本、唯一live会话 | 完全不能直接导航到独立POI |
| Seed | demo_seed:145/258/371 三套固定ID演示；seed_demo CLI --reset；main:1086 /demo/reset；demo相关脚本 | reset路径仅development/test；Compose当前APP_ENV=development | 能写演示Trip，不能从历史名称认定其它记录来自seed |
| 测试/评测 | tests中TestClient create/reset与直接ORM；evals/planning_quality/run.py:155/161 | 本轮隔离roamsync_test；评测有isolated目标校验 | 测试脚本若误连正式库会污染；未认定过去已发生 |
| 启动 | main lifespan:164只yield/dispose；production Dockerfile CMD alembic→uvicorn；worker/checkpoint init独立 | 没发现应用启动自动seed Trip | 不能把列表多归因于初始化 |

扫描范围为活跃 app、tests、scripts、evals/planning_quality，排除results内历史源码副本，后者不是额外运行入口。规划Graph复用、DayPlan/Activity手动编辑和候选接受会写已有对象；没有额外Trip构造。外部HTTP客户端和历史人工SQL无法仅由仓库证明，仍为OPEN。

## 4. Trip依赖矩阵

| 能力 | 当前事实/证据 | 分类 | 推荐解除方式 | 影响与风险 |
|---|---|---|---|---|
| 城市/住宿POI查询 | main:232/246 `/locations/*` 无Trip | 已独立 | 复用地点端口，保留兼容路由 | 不把住宿POI当报价库存 |
| 候选地点搜索 | main:892先get_trip取城市；Provider函数本身只需query/city | 当前接口导致，可彻底解除 | `/places/search` 显式area/near | Place身份、category和来源契约要先冻结 |
| 普通对话/推荐 | AssistantSession.trip_id可空；assistant:287 Companion | 已独立，部分能力仍受数据限制 | 全局体验+逐请求作用域 | 地点建议不一定是可导航Place |
| 无Trip规划 | PlanningRun.trip_id非空database:164；Graph state trip_id；assistant:405 | 临时技术限制，可解除预览依赖 | 真正DraftContext/DraftRun | 不放松正式Revision/执行不变量 |
| 正式多日规划/版本 | Trip/DayPlan/Activity/Revision、accept_plan_revision:498 | 业务必需 | 保留 | Validator、预算、预约、活动锁不可丢 |
| 收藏 | 活跃models/routes未发现Favorite/Bookmark/User | 能力缺失，可独立新增 | owner+Place收藏 | 不能拿喜欢Suggestion替代收藏 |
| 独立路线查询 | maps_service.resolve_route_result:319用PlaceCandidate/RouteCache；无任意端点公开API | 当前接口/实现导致 | RoutingRequest端点化 | 真实与估算、坐标系、有效期要明确 |
| 独立导航 | database:563/567双非空FK；session_service:114核对正式路线 | 现有导航业务必需；独立导航是新边界 | 新InstantNavigationSession | 两套状态语义，统一客户端能力契约 |
| 正式执行/恢复 | TripExecution唯一Trip；disruption/recovery与版本、活动冻结有关 | 业务必需 | 保留；即时导航永不触发正式recovery | 恢复后旧导航superseded、新会话再启动 |
| 偏好 | TripPreferences；conversation PreferenceStatement(scope=conversation)；DecisionMemory拒绝反馈 | 局部偏好业务必需；长期偏好缺失 | 分层Preference/Evidence，显式作用域 | 不把旧Trip预算注入他城即时询价 |
| 地图 | MapCanvas只读Activity；Android RouteMap用day/trip | 当前UI设计导致 | MapViewport接受Place/Route，与Trip可选适配 | 地图fallback不能冒充Provider结果 |
| 事实/知识 | TourismKnowledge independent；TravelFact为typed subject；execution subject含Trip | 已独立或业务必需 | 复用数据端口，扩展实用内容 | 接口/小语料不代表全面真实数据覆盖 |

## 5. Agent会话、上下文与要求持久化

**VERIFIED**：`assistant_service.get_or_create_session:180` 按 trip_id 查最近会话，null亦如此；没有owner或全局唯一约束。确认创建/跨Trip操作会把原session.trip_id改成目标（417、506），必要时给原Trip复制一份历史（503）。这是“按Trip恢复会话”的实现，不是独立稳定全局会话加显式任务关联。

会话messages JSON持久化，Companion投影保存source_turn、Suggestion稳定ID和互动；`companion_state.project_conversation:44`保留最近30条偏好、单一destination，模型近期上下文12轮。`PreferenceStatement`（contracts:222）仅conversation作用域；Trip偏好是局部保存，拒绝Memory按Trip/day/version过滤（test_decision_memory）。没有用户长期画像管理、账户隔离、跨目的地偏好证据归属完整实现。

`CompanionContext`（contracts:256）有current_destination、trip_summary、saved_trip_preferences，**没有明确 physical_location、browse_target、discussion_target 三种独立字段**。`CompanionContextReader:21` SELECT且禁autoflush，按need选择Trip/偏好/行程，不自动修复数据，这是值得保留的边界。天气明确城市覆写已有目的地已有回归，但不能推出杭州定位+南京浏览+苏州预算组合正确。

`PlanningBrief` 建立在对话和Suggestion（state:126），传给助手ToolRouter（assistant:357）并存messages（422）。正式创建后自动initial_plan的请求为通用“根据已保存日期预算偏好生成”（510）；Graph启动（planning_graph_runtime:47）不携带独立Brief；规划输入测试 `test_planning_quality_eval:70` **刻意断言加入Brief/history不改变输入**。部分原始要求可通过字符串和TripPreferences进入规划，不等于完整结构化Brief贯通。这是实际信息损失风险，而不是缺一个新Agent。

原解释与新解释已区分：accepted/current版本和validated Ledger才能给original rationale（companion_context:约69）；saved_plan_notes是受版本保护的保存说明/重建上下文，不应冒充已验证理由。Ledger默认为shadow，不能称已通过严格推理来源验收。

## 6. 导航真实边界

| 能力 | 当前可确认状态 | 不得推导的完成状态 |
|---|---|---|
| Web地图路线 | AMap JS点线、真实RouteLeg几何；fallback示意 | 浏览器持续真实导航 |
| Android外部地图 | RouteMap marker URI ACTION_VIEW | 返回外部APP后知道是否到达 |
| Android SDK | build.gradle.kts固定SDK11.2.100；AmapNavigationSource反射计算驾车路线 | 行程mode=walk/transit会正确对应SDK |
| 模拟导航 | AmapNavigationSource:约91 startNavi(2)，NavigationSource只声明startSimulation；MobileApp显式模拟入口 | 真机GPS步行/驾车导航已完成 |
| 定位权限 | 主Manifest只声明INTERNET，未找到应用侧动态定位授权流程 | 合并SDKManifest后的有效权限或用户授权已验证 |
| 起点 | VM bindRuntime取正式from Activity坐标 | 用户当前位置→第一站/餐厅 |
| SDK模式 | calculate永远calculateDriveRoute，未根据input.travelMode分派 | walk/transit语义一致 |
| 会话开始/取消 | atomic start/resume、版本预期、唯一live；cancel已有测试 | SDK和服务端任何网络失败下完全一致 |
| 观测 | sequence、version、route_revision、去重、debounce/持久detector、outbox | 连续后台定位及进程死亡可靠上传 |
| 路线刷新 | main:559明确绑定UnavailableRoutingProvider，503 routing_not_configured | 服务端实时路线刷新已接真实Provider |
| 恢复 | observation→Slack/delay→Disruption→去重RecoveryRun→Revision→Accept，accept使旧导航superseded | 用户接受后SDK自动接新路线已真机验收 |

现有正式导航的Activity/RouteLeg UUID不是直接FK，而是trip/version/活动对稳定身份（database:569注释）。不能通过简单nullable Trip把它泛化：所有detector、execution subject、恢复和Android binding仍假定正式执行。

## 7. 内容与事实质量

**VERIFIED**：`maps_service.search_amap_places:196` 使用真实POI，但 `_cost_for_category:508` 给餐饮8000分等类别默认值；duration也是类别建议；缺失rating在239变0。photos在231仅转“有图片”tag，没有输出图片资产。`PlacesDrawer`把零费用显示“免费”，统一页脚“高德POI·实时数据”。估算规划成本与实查人均/门票/房价必须分开，unknown不能变免费或0星。

`search_amap_location_pois:114` 提供住宿搜索与可空rating，已有独立查询基础；无入住日期、人数、房型、税费、取消条件、库存/报价适配器。不能宣称“今晚有房且某价格”。旅游语料是少量杭州reviewed JSON；检索接口/BM25/embedding口不等于完整目的地内容产品或生产向量检索。

TravelFacts已有身份/时间/authority/freshness/缺失/冲突语义（models、policies）；Companion实际fact tool（companion_facts:284）主要开放forecast/opening要求，没有餐饮实价和酒店库存。天气经城市验证、官方营业安排对特定场馆和日期，均不代表实时实际开门、可入馆或全城覆盖。

外部能力核查（2026-10-15）：[高德POI官方文档](https://developer.amap.com/api/webservice/guide/api-advanced/search)列出搜索、周边、ID详情、可选photos/rating/cost字段；这些不能提供指定日期房型的可售库存保证。[高德导航官方API](https://a.amap.com/lbs/static/unzip/Android_Navi_Doc/com/amap/api/navi/AMapNavi.html)区分路线计算和导航控制，应逐模式验收。[Open-Meteo条款](https://open-meteo.com/en/terms)区分免费非商业接口与商业订阅，并要求数据署名；数据来源入口需要保留。账号实际配额、图片再发布/缓存许可、酒店商务准入尚未查控制台，均为OPEN，未编造费用。

## 8. 质量与实测基线

| 层级 | 本轮证据 | 判断 |
|---|---|---|
| 后端测试 | 独立Compose项目 `roamsync-v2-audit-20261015`；空tmpfs PostgreSQL；现有迁移仅测试库；1002 passed/2warnings/50.90s | MEASURED，通过已覆盖行为 |
| Web | pnpm test 21文件132项；typecheck通过；build通过，React act警告 | MEASURED，不等于真实浏览器Provider闭环 |
| Android | 首次UP-TO-DATE后明确以test task --rerun重跑；35tests/0fail/0error/0skip | MEASURED，JVM测试；无真机GPS验收 |
| 正式健康 | live/ready200；Web healthz200；非法UUID422；不存在Trip404 | MEASURED，只读；ready实际SELECT1 |
| 镜像绑定 | 测试209、API/Worker各138文件均匹配 | VERIFIED，限所列目录 |
| 当前真实模型输出 | 本轮0真实模型调用 | 未验收 |
| 历史模型 | streaming-release summary：合成无DB GLM完成、首答3.3049s；既有真实评测/盲评/失败记录 | HISTORICAL，不是本轮时延/质量基线 |
| 业务质量 | Companion历史报告仍记录事实错误、动态声明遗漏、截断、部分降级自然性；closeout树也有OPEN | 未关闭；没有当前独立人类真值评分 |
| 产品价值 | 操作次数、重复输入、满意决定耗时、控制感 | 未测，先建立基线 |

当前1002测试并不包含官方目录没有的独立树新增测试。测试规模增长和旧特定缺陷缺失可同时成立。历史生产绑定计数与本輪138使用不同目录范围，不能直接比较大小。

## 9. 后端架构专项核查

不是本轮后端架构全面验收通过；不生成 `BACKEND_ARCHITECTURE_SSOT.md`。

| 规则项 | 来源/文件 | 验证方式与结果 | 是否通过 |
|---|---|---|---|
| 分层/DI | FastAPI main.py、get_session；业务service/repository | 多数路线→service→SQL；main:892直接读Trip；repository兼有领域逻辑 | 部分；不是严格controller-service-repository统一分层 |
| 参数验证 | Pydantic schemas、Query；main:212/232 | 422指明trip_id路径字段，本轮HTTP证据 | 通过该路径 |
| 原子接受 | plan_revision_service:498；AGENT_ARCHITECTURE | 锁Revision/Run/Trip，重新验证、版本检查、正式保存 | 已有隔离回归通过；保留 |
| 会话DI/事务 | database.get_session；assistant locked_session:191 | FastAPI依赖、with_for_update；stream迭代器自己管理DB生命周期 | 已覆盖测试，长期锁时延需监控 |
| 中间件 | main/config静态检查 | 未发现全局请求ID/统一middleware管道；同源nginx代理 | 未验收统一观测要求 |
| 全局错误 | main局部HTTPException；assistant_routes.respond:33 | 错误detail有str/dict/list；无统一全局严重错误契约 | 不通过统一错误要求 |
| 分页/响应 | main list_trips:221裸数组；schemas对象 | 未分页；无全局success envelope；SSE有独立事件 | 不符合“统一分页”，无需为一致重写所有成功体 |
| 认证/授权 | models、routes无User/owner授权依赖 | 当前本地单用户原型 | 多用户/公开发布未验收 |
| 配置 | Settings/SecretStr、.env.example、Compose | 可配置Provider超时/重试/worker；配置与默认开发模式须在部署阶段复核 | 静态验证；实际密钥/授权不输出 |
| 日志 | maps_service.logger.info；agent_observation/progress | 有工具/阶段日志，缺统一请求/用户范围观测验收 | 部分 |
| 迁移/数据库 | Alembic；ready SELECT1；隔离全链迁移 | 空测试库升级成功，正式库只读ready200 | 通过测试范围，不证明回滚迁移 |

目录责任表：

| 目录 | 主要责任/后续允许 | 禁止内容 | 来源 |
|---|---|---|---|
| backend/app/main.py、*_routes.py | HTTP参数、错误映射、DI、调用用例 | 新增复杂业务判断/直接混入Provider模型解析 | FastAPI惯例+目标边界 |
| *_service.py、repository.py | 现有业务事务；逐步明确服务与持久层责任 | 格式化前端页面、LLM自行批准写入 | 业务封装 |
| database.py、migrations | 持久约束和串行Schema演进 | Provider调用、UI状态路由 | SQLAlchemy/Alembic惯例 |
| planning_*、plan_revision_* | 正式规划/候选/版本校验 | 即时推荐强制创建Trip | 业务封装 |
| companion_* | 对话需要、推荐、证据投影 | 自授正式变更权、把建议ID当PlaceID | 业务封装 |
| navigation/ | 正式执行导航/检测/恢复；共享纯算法 | 无Trip导航写正式Disruption/Execution | 业务封装 |
| tourism_knowledge/、travel_facts/ | 检索与类型化事实/来源/时间 | 把搜索摘要自动视为权威价格/库存 | 业务封装 |

最小真实只读链：GET `/api/v1/trips/{trip_id}` → main:260 Pydantic UUID → repository.get_trip:68 → AsyncSession.get → ORM → TripResponse.model_validate；不存在→局部404。统一响应/全局异常层不存在，不画出虚构层。

| 响应场景 | 证据/结果 | 验收 |
|---|---|---|
| 列表成功/空列表 | main:221裸数组；未读正式旅行列表，隔离test_trips覆盖列表 | 类型实现存在；统一分页未实现 |
| 详情成功 | test_trips读新建fixture断言200 | 隔离测试通过；未摘录私有正式正文 |
| 创建/更新 | test_trips 201及版本冲突；App.test保存重试 | 隔离测试通过 |
| 校验错误 | readonly-http.json，422 detail列表字段loc=[path,trip_id] | 实测 |
| 401/403 | 没有鉴权端点契约 | 未实现，不伪造响应 |
| 404 | 本轮未知UUID，404 detail="trip not found" | 实测 |
| 500 | 没有正式服务故障注入 | 未验收全局错误格式 |

框架原生复用：FastAPI路由/Depends/OpenAPI、Pydantic校验、SQLAlchemy会话/约束/事务、Alembic迁移；LangGraph承担可恢复任务。自定义包装：AssistantRouter（工具决定）、TravelGoalRouter（权限之前路由）、CompanionContextReader（只读权限）、FactService（authority/时间）、Revision Validator（硬约束）、RoutingProvider（SDK/服务解耦）、model_client（多Provider协议）、assistant_stream（request-local SSE）。均解决实际边界；不能为了“精简”统一删掉。建议统一错误码/请求观测，但不强制新增每一层包装类。

运行证据包：backend依赖 `uv sync --frozen`；官方Dockerfile生产先 `alembic upgrade head` 再 `uvicorn app.main:app --host 0.0.0.0 --port 8000`；**本轮不运行该生产命令**。部署入口由AGENTS指定Start-RoamSync.cmd。本轮安全命令为 `docker compose -p roamsync-v2-audit-20261015 -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test`。核心配置键：DATABASE_URL、LANGGRAPH_DATABASE_URL、AMAP_REST_KEY、PLANNER_PROVIDER/API_KEY/BASE_URL/MODEL、worker deadline与lease；见模板，不能把可选Tavily/天气配置当全部核心必需项。数据库成功为ready SELECT1；标准业务日志静态格式 `amap poi search success query_length=%s results=%s`；测试日志含预期unique live-session冲突，不能误报生产事故。当前无本轮实测的统一请求日志/全局500日志。

## 10. 最根本的问题与优先顺序

1. 入口把产品框成行程工作台；内容体验未成为第一类入口（App:72/524、MobileApp底栏）。
2. 无Trip结构化规划缺失，草稿承诺与正式建档混在同一流程（database:164、assistant:405/510）。
3. 全局会话身份随Trip迁移，情境只有单destination而非定位/浏览/讨论/操作目标（assistant:180/417/506、contracts:256）。
4. 地点身份是Trip-owned candidate，跨页面收藏、即时决策缺少统一Place（database:374/396）；没有收藏/长期偏好模型。
5. 独立导航不存在，真实模式与行程mode尚不一致；server route-refresh未接Provider（nav session:114、AmapNavigationSource、main:559）。
6. 来源、估算、unknown显示混淆，附近餐饮/住宿可信交易数据缺口（maps:239/252/508、PlacesDrawer）。
7. Brief已经生成但没贯通正式规划输入；部分跨日修复还在别的树（test_planning_quality_eval:70、对54b8888 diff）。
8. 测试、Provider输出、质量和产品价值被历史阶段完成措辞混淆；当前仍缺真实导航/人类质量/操作基线。
9. 脏工作树和未集成阶段难以复现；多用户权限基础缺失。未来并行前应冻结源码，不用“多个目录同HEAD”证明已合并。
10. 日期状态与真实执行混在展示语义里；`database.py:80–88` 的Trip.status按UTC日期推导而非Trip.timezone，Asia/Shanghai午夜边界可能错一天。需明确按当地日期的计划阶段与真实执行状态，增加时区/跨午夜契约验收。

推荐顺序与设计分别见[产品定义](ROAMSYNC_PRODUCT_2_0_DEFINITION.md)、[架构](ROAMSYNC_DOMAIN_ARCHITECTURE_V2.md)、[迁移](ROAMSYNC_DATA_LIFECYCLE_MIGRATION.md)、[路线图](ROAMSYNC_DEVELOPMENT_ROADMAP_V2.md)。[未决项](ROAMSYNC_OPEN_DECISIONS.md)是第二轮评审议程。本轮到此不实施。
