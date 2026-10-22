# RoamSync 工程审查 A · 2026-10-22

结论：已建立可追溯产品源码基线；A 工程改进在独立工作树实施，正式 3000 未部署、正式数据库未修改。架构整体为**不通过公网验收**；本地单用户功能仍可用。本文不是“全部架构通过”的 SSOT。

## 1. 正式状态与基线

统一 `BASE_SHA=f116ada6d6d46db7aeb48c29c8d5b45da379be00`，分支 `codex/release-baseline-20261022`，工作树 `E:/Study/RoamSync-baseline-20261022`。其产品父提交为 `6b298caddb79125991bfc5183ddeefc09029f31c`。正式目录当前在 `codex/journey-handbook`，不是 10 月 21 日报告中的旧 `c1edec9`。

10 月 21 日七项功能已由祖先 `1fab037` 固化，之后有 `9a8897a` 安排界面、`5cd52ce` 独立打算、`2291486` 实景照片、`5137428` 地点参数修复；因此既不能回退到旧 HEAD，也不能把整条 NO-GO 实验分支当成已验收产品。

本次初始快照：3,133 个 tracked/untracked 文件，450,467,533 字节；清单逐文件 SHA256、原文件副本、Git diff/index/status 在 `E:/Study/RoamSync-audit-evidence-20261022/`，不进入 Git。`.env` 仅在私有清单记录哈希；没有提交密钥、数据库备份或真实会话。未使用 reset、clean、覆盖正式文件或删除数据。

正式剩余 4 个 tracked 修改：README.md、.env.example、backend/scripts/quality_runtime.py、web/nginx.conf。另有未跟踪评测输出、报告、图片、临时输入、历史脚本等。全部保留。官方 Web 使用 `nginx.local-product.conf.template`，不是这份有本地修改的 nginx.conf；quality_runtime 是隔离评测入口，未参与正式镜像。以上无关修改不纳入产品基线。

**VERIFIED**：官方只读 `scripts/verify-roamsync.ps1` 在原目录通过；API/Worker 各 224 文件原始字节 SHA256 完全相同，GLM 配置及两个健康端点通过。364 个产品/构建文件与 HEAD 统一换行后相同，汇总 LF SHA256：

`772a651705b23a8cb1e49d6382fdc269787a76432877dffd7231fe54434b7259`

机器证据：`docs/evidence/engineering-a-20261022/source-manifest.json`、`runtime.json`、`baseline-verification.json`。历史 Oct 21 manifest 只有 219 条，而最终报告称 222；219 条均验证进入 `1fab037`，混合换行条目通过原始备份交叉核对。**不能把这份历史 manifest 宣称为最终 222 条完整证明**。当前实际 224 文件重新核验补足运行源码证据；旧 Web 多阶段镜像没有保留前端输入，当前 Web 源码溯源还依赖发布记录，后文改进解决今后的这一缺口。

基线曾暴露新的复现缺陷：干净 checkout 的 pytest 收集失败，因为既有测试导入的 `evals/assistant_capability_cases.py` 留在未跟踪状态。A 提交 `f5803b04ee2bfee5eb39c0f41060d693281d668a` 仅补齐这份 72-case 合成夹具；B/C 仍从统一 BASE 起分支，最终验收必须包含这个 A 依赖提交。产品源码基线与测试基础设施修复不能混称为同一个验收结论。

## 2. 十大问题（按严重度）

| 排名 | 严重度、问题 | 证据与根因 | 新旧归属 | 处理 |
|---|---|---|---|---|
| 1 | P0：公网缺少 Trip/会话主体隔离；身份边界随运行模式消失 | `database.py:34` Trip 无 owner；`saved_intentions.py:86` 按客户端 session_id 列表查询；`main.py:199` 仅 local/isolated 模式安装认证；默认隔离 API 无凭据创建返回 201，正式直连 401/跨源 403 | 既有单 owner 设计；0038 新表延续边界，不是新引入的多租户保证 | 禁止据此公网发布；需统一主体依赖、owner 外键/查询作用域、迁移和跨用户反例；本轮不冒改业务模型 |
| 2 | P0：测试与迁移入口可能误用非测试库 | 原无 conftest；`config.py:10` 默认 development 与具体库；普通 API 测试会写库及 demo/reset，个别夹具才检查名称；本地 dotenv 也可另设 checkpoint 库 | 既有债；近期新增专库夹具仅局部防护 | A 已增加收集前及迁移前门禁、checkpoint 固定、每次全新隔离项目 |
| 3 | P1：规划事务/行锁跨模型与路线网络请求 | `planning_run_repository.py:61` 先 lock_trip，`:82` await resolve；`:195–205` 锁 Trip/Run 后 enrich_routes；`candidate_route_service.py` 中 await provider。合成双连接探针得到 55P03 | 既有正式写保护路径；后续扩展增加等待时间 | 保留为高优先级根因修复：读取快照、释放事务、外部工作、重锁并校验 itinerary/requirements/operation；不能盲目 commit 提前释放正式写保护 |
| 4 | P1：发布与回归证据没有完整绑定干净源码和 Web 产物 | 未跟踪必要夹具造成真实 collect error；旧核验只比 API/Worker；健康不能证明 Web 输入、资源或镜像归属；历史 219/222 缺口 | 长期债，Oct21 新夹具引入新的复现断点 | A 补夹具、源码哈希测试记录、构建 manifest 和实际容器产物核对；旧镜像无 manifest 明确拒绝认证 |
| 5 | P1：Worker 失联恢复与租约归属不完整 | `agent_worker.py:25` 只回收非空过期租约，`:55` 无 owner 条件清理，`:71` 轮询 DB 异常可退出；Compose restart=no。`planning_progress.py:29` pulse 未核对 claim token | 既有债 | 已确认存在每 15s 心跳，**不能仅因 300s lease/360s deadline 判重复执行**；仍需唯一 claim fencing、故障恢复与并发失联实验 |
| 6 | P1：多份条件状态无法一致撤销或影响 Research | `assistant_memory.py` clear slot 不清 browsing_city；conversation_memory、ContextEnvelope、Trip requirements、draft requirements 分别存在；Research 正常生成输入未完整带有效条件 | Oct21 记忆/语义升级新增或放大；Trip requirements 债更早 | B 主责修复；A 不并行改同一文件。撤销必须有 tombstone，区分当前旅行与稳定偏好 |
| 7 | P1：新旧语义路由并存、Planner/Worker 再解释 | `assistant_service.py:408` legacy 锁后继续 router；`:697/731/757` 多次 decide；`planning_graph.py` 入口 resolve 后研究成功又 resolve；已有 CurrentTurnModification 仅覆盖受限修改 | 多轮历史兼容债，Oct21 避免 split-decision 的补丁只解决一条链 | 保持明确写授权和 Validator；后续以服务端版本化 operation 交接逐步收敛，先测调用次数，不另加决策 Agent |
| 8 | P1：90s 逻辑超时不能取消底层同步 HTTP 线程 | `external_facts.py:114`、`maps_service.py:359` to_thread(urlopen)；SSE `assistant_stream.py:144` cancel 仅取消 await；单请求 socket 有超时，但线程可能继续，重复重试可放大在途请求 | 同步工具旧债与 Oct21 外层预算组合产生的新可靠性缺口 | 需受限异步 transport/并发配额/剩余预算向下传递；当前未测线程高压上限，不能称无泄漏或无后台请求 |
| 9 | P2：观测覆盖不均、数据与契约持续增长 | 新 consultation 有 allowlisted execution_summary；legacy/Worker 仍 print 异常类，部分 fallback吞错；session JSON 的 messages/applied_actions 持续增长；成功对象/数组与 detail 字符串/结构化错误并存 | 大部分旧债；新增 receipt、memory、diagnostics 放大单行JSON更新成本 | 保留单次关联ID，逐步结构化 Worker/规划日志；历史消息分页/归档要维持幂等键，不能直接删 receipts；不全局包响应破坏客户端 |
| 10 | P2：备份、回滚与测试操作依靠多份历史脚本 | 多种固定端口/固定 DB、重复脚本、tag 备份但不总是独立文件导出；API 启动自动 migrate、Worker依赖初始化；旧镜像不等于 schema 可回退 | 既有债 | A 新增一次性无网络恢复核验；保留旧镜像ID与本地tag；数据库回滚不可在有新写入后盲目恢复旧dump，须单独迁移/恢复方案 |

另外，C 已独立发现探索搜索仍跳到旧 `/`（现已是助手入口）；属于 Oct22 产品路由升级遗留，C 正在处理，不能用 A 后端测试通过代替前端验收。

## 3. 分层、职责与最小请求追踪

| 规则项 | 规则来源 | 文件与实际证据 | 结果 |
|---|---|---|---|
| 框架路由与校验 | FastAPI/Pydantic | main.py、assistant_routes.py；合成 POST 缺必填字段 422，loc 精确到字段 | 通过 |
| 请求 → 服务 → SQL 分离 | 业务封装 | assistant_routes → assistant_service → ORM；main.py 仍 1,136 行，repository 直接含业务与网络协作 | 部分通过 |
| 正式写入口与版本保护 | AGENT_ARCHITECTURE / formal_write | Trip先锁；Accept重验Trip/Revision/Run/Requirements与Validator；既有专库反例仍在运行 | 局部通过，持锁网络不通过 |
| DI / 会话生命周期 | FastAPI Depends / SQLAlchemy | get_session；SSE 在 iterator 内拥有 session；lifespan dispose engines | 通过本次追踪范围 |
| 认证与授权 | local integration 业务约束 | integration_runtime 条件安装，single owner，而非 Trip owner模型 | 本地通过；公网不通过 |
| 全局错误/响应一致性 | 现有 API 合约 | 422/404/401/403含不同 detail 形状；无统一系统500覆盖证明 | 未完全验收 |
| 配置与秘密 | Settings / Compose | API/PG loopback、token secret server端，env未入Git；默认密码和模式仍有债 | 本地约束通过；公网不通过 |
| 日志可观测性 | execution_summary / progress | consultation关联ID、失败分类、阶段耗时持久化；legacy/Worker覆盖不足 | 部分通过 |

| 目录 | 唯一主要职责 | 以后放什么 / 禁止放什么 | 来源 |
|---|---|---|---|
| backend/app/*routes.py | HTTP 参数、依赖、错误映射 | 放协议适配；不放模型策略或长SQL事务 | FastAPI惯例 |
| backend/app/*service.py | 用例编排及业务一致性 | 放版本与权限校验；不把HTTP响应包装混入底层 | 业务约定（目前并非全部遵守） |
| backend/app/*repository.py、database.py | SQL和持久化 | 放短事务与实体；不在锁后访问外部模型 | SQLAlchemy惯例，存在违反 |
| backend/app/planning*、companion* | 现有有界执行图与读回答图 | 保持单一正式写链；禁止新增第二套时间表/Planner来遮掩故障 | AGENT_ARCHITECTURE |
| backend/app/place_content、travel_facts | 供应商身份、缓存、事实适用性 | 原始资料不变成系统指令或已核实当前事实 | 业务约定 |
| backend/tests、evals | 合成回归与真实模型评测 | 夹具入Git，真实私有会话/大结果外置；禁止默认生产连接 | A门禁与既有评测约定 |
| web/src/data | 版本化API与SSE协议适配 | 不做第二套业务授权 | 前端惯例 |
| scripts、compose.test.yaml | 运行、核验、隔离测试 | 显式项目、输出证据；禁止官方数据 reset/clean | 工程约定 |
| docs | 契约与经验证报告 | 不包含密钥/数据库内容/未脱敏会话 | 仓库AGENTS |

最小读请求 `GET /api/v1/trips/{trip_id}`：main.py 路由将 UUID 与 Depends(get_session) 校验后交 repository.get_trip；SQLAlchemy SELECT；TripResponse 负责输出。不存在的合成UUID返回404 detail。Trip 主体所有权未在这条查询链实现。Assistant咨询则从 assistant_routes → send_message → semantic_turn 读取/提交快照，再无事务执行已批准工具，最后锁会话比较 signature；这是比旧路由更好的现有边界，应复用其模式而不是增加包装层。

| 真实请求场景 | 状态与响应 | 证据 / 限制 |
|---|---|---|
| readiness | 200 `{"status":"ready"}` | 隔离18036、官方8000均只读 |
| list | 200 数组 | 隔离合成库；当前接口无分页参数，不能宣称统一分页已通过 |
| detail | 200 TripResponse | 隔离合成旅行 |
| create | 201 TripResponse | 仅隔离18036；同时证实默认模式未安装认证 |
| empty list | 200 `[]` | 隔离新旅行 planning-runs |
| invalid input | 422 `detail:[{loc:[body,...],...}]` | 缺 title/start_date/end_date 等必填字段 |
| unauthorized / origin denied | 401 /403 结构化 detail | 正式8000无token、3000跨源，只读请求未返回用户资料 |
| missing | 404 字符串 detail | 隔离未知旅行 |
| severe system500 | 未验收统一契约 | 不向正式服务注入故障，不新增伪造演示路由 |

框架复用：FastAPI依赖/参数校验/异常hook、Pydantic schema、SQLAlchemy session/ORM、Alembic migration、LangGraph checkpoint。自定义封装中 formal_write、capability边界、provider身份适配有明确业务用途；observation、diagnostics、context/memory多套投影需要收敛，但不能未经迁移直接删。当前超大模块（行数）：planning_intent_service1292、schemas1258、main1136、assistant_service917、database857、planning_graph810、openai_planner805、planner_repository733、plan_revision_service726。建议先缩小网络/持久化边界，再按用例拆模块，而非把同一逻辑平移到更多“Manager”。

## 4. 性能、降级和安全判断

从已保存的合成/回放证据去重取68个 execution_summary：总时长中位16.779s、最大54.030s；selection中位3.832s（68项），answer11.446s（63项），companion15.323s（50项），images2.751s（21项）。这些阶段嵌套、样本不同，**不能相加**，也不是本轮无偏生产分布。来源：`historical-latency.json`。主要可见成本在模型选择与回答，图片有额外等待；本轮没有改变模型、90s预算或生成次数，不声称咨询变快。

现有降级实情：Tavily失败时目的地初始规划 fail closed，仍会出现 `planner_research_unavailable`，不能为过验收开启地图估算；已有路线/事实的独立读组件可保留兄弟结果；图片失败不必拖垮已验证文本；模型失败受两次answer预算控制。工具选择、网页snippet选择、Research生成、Companion内部need仍可能多次模型调用，两个answer预算不等于整回合只有两个模型请求。独立网络分组已并行；候选路线仍串行，且每个 provider 线程取消不彻底。

外部网页在提示中声明为不可信，引用只能选择既有source/snippet，写授权回到当前用户原文与Validator/Accept；这降低网页指令直接获写权限的风险，**不是提示注入完整证明**。当前未运行全量对抗注入和跨用户矩阵。图片只读URL检查与坐标/名称绑定保留；图库覆盖有限。新旧客户端有字段版本、Trip/Activity/requirements CAS和preview guards，但没有全局发布代次/最低客户端能力协商；因此不能认为旧Android/Web所有新字段往返都已证明安全。

轮询不是无限无条件：TravelAssistant只在working状态2.5秒轮询，useExecutionProgress只在活动导航/恢复任务且页面可见时刷新。剩余风险是失败任务无法终止、无backoff或同一恢复任务租约失联，而不是简单“所有轮询都该删除”。SSE有15秒keepalive、断开cancel和rollback保护；单个回合队列上限2048，端到端断网后的外部线程收敛仍需专项压测。

历史规则确有累积：travel_goal_router句式授权、planning_intent_service日期/范围修复、answer lexical句子移除、literal memory assist、CurrentTurnModification恢复都在补局部症状。根本方向应是保留一个经服务端校验、有版本和来源的operation交接，一个有效条件投影和一个事实引用结构；逐条迁移旧路径，保留反例。继续叠禁词、第二次模型“审判”或第二套Planner会增加解释冲突和成本。

## 5. 价值、风险和成本排序及本轮实现

| 类别/优先 | 任务 | 价值 | 风险/成本 | 本轮 |
|---|---|---|---|---|
| 立即 P0 | 测试与测试迁移 fail closed；每次新DB/项目 | 防误写、可复现基础 | 低/中 | 实施 |
| 立即 P1 | 发布源码/镜像/Web资源绑定、补必要夹具 | 防旧HEAD/漂移/虚假绿灯 | 低/中 | 实施 |
| 立即 P1 | 备份真实恢复及指纹比较 | 证明能恢复而非仅有dump | 低/小 | 实施 |
| 稳定 P1 | 规划网络移出短事务，返回后重验 | 并发正确性与响应 | 高/大，需写路径矩阵 | 待后续专轮 |
| 稳定 P1 | claim token/失联恢复/DB故障backoff | 重启与多Worker可靠性 | 中/中，需checkpoint故障实验 | 开放 |
| 稳定 P1 | 有效条件与Research一致性 | 直接改善回答决策 | 中/中 | B主责 |
| 稳定 P1 | 搜索入口/安排复核/恢复体验 | 避免用户链路断点 | 中/中 | C主责 |
| 稳定 P1 | 可取消异步HTTP与在途限流 | 取消/超时负载收敛 | 中/中 | 开放 |
| 公网前置 P0 | owner隔离、认证强制、默认配置加固 | 公网数据安全 | 高/大、需迁移 | 暂不开放公网 |
| 暂缓 | 大规模Agent/服务拆分、RAG或新状态库 | 证据尚不足 | 高/大 | 不实施 |

本轮三项改进的具体边界：

1. `tests/_database_safety.py` + conftest：必须显式 APP_ENV=test、PostgreSQL且库名有独立test词段，拒绝URL query覆盖、正式local-product模式与checkpoint异库；在导入app/创建engine前失败；固定未导出的checkpoint fallback，防dotenv绕路。Compose及新runner在Alembic前也执行同一门禁。不能把库名检查当成数据库权限沙箱；推荐入口进一步保证新项目、无外部网络/host mount/端口、tmpfs，主/专库一次分配。既有业务断言未放宽；仅将两个夹具的loopback检查换成明确专库名，容器网络不再被错误拒绝。
2. backend与web构建manifest：只写文件名与SHA，不存环境密钥；Web manifest在public root之外，静态资源另带原字节hash。verify-release.py同时比较当前源码、build attestation与容器实际文件；官方verify脚本将此作为门禁。Web Docker上下文排除.env类本地文件，避免未记录dotenv改变Vite构建。旧镜像不会被无证据认证。
3. verify-backup.py：只读已有dump和预期指纹，创建随机名、network=none、无端口、tmpfs的独立Postgres；恢复时不使用clean，不访问正式库；比较全部表并清理自己创建的容器。镜像回滚与schema回滚仍是不同步骤，不会自动恢复正式数据。

## 6. 复现与验收记录

正式启动契约仍是官方 `Start-RoamSync.cmd` / `scripts/start-roamsync.ps1`；本轮未调用。依赖由backend `uv sync --frozen`、web `pnpm install --frozen-lockfile`和Dockerfile固定lock安装。正式Web3000/API8000/PG15432、原volume均保留；隔离测试不发布数据库端口。

推荐回归：`python scripts/run-isolated-tests.py --output <新的证据目录>`，它总是构建当前源码、创建新tmpfs库、执行全量主套件与独立promotion/favorite套件，记录每阶段退出码、测试镜像ID、文件SHA和运行前后是否漂移。

恢复核验：`python scripts/verify-backup.py --dump <外置database.dump> --expected <production-before.json> --output <新JSON>`。发布只读核验：`python scripts/verify-release.py --output <JSON>`；隔离候选可显式指定API/Worker/Web容器名，`--no-worker`只证明API/Web文件绑定，不代替Worker运行验收。

| 检查 | 实测 | 范围与失败保留 |
|---|---|---|
| 原官方核验 | API/Worker各224 + readiness/healthz通过 | 只读原目录，legacy Web输入未独立重建证明 |
| 干净BASE旧Compose | 收集失败缺capability_cases | 失败未算通过；A单独补夹具 |
| 新runner初稿 | 1371通过/2失败/52夹具错误；专库51通过 | 主库名与复用专库夹具不匹配，修正调度，非产品逻辑放宽 |
| A最终完整回归 | 主1452、专25通过，source_unchanged=true | `a-final-tests`；同一测试源码、全新tmpfs数据库，针对性17与主套件重叠，不累加 |
| 安全门禁最终针对性 | 17通过 | 包括真实pytest收集前拒绝和dotenv checkpoint绕路 |
| 备份恢复 | 32表全部一致，23.032s | 最新handbook备份；独立容器恢复并已清理 |
| 规划锁探针 | 55P03 | 合成隔离库，在intent await期间Trip行被锁，非实际模型延迟基准 |
| HTTP合约 | 200/201/422/404；正式无token401/跨源403 | 写入只在隔离18036合成库，正式请求只读 |
| A Web构建 | 最终228通过、类型及生产构建通过 | 初次227通过/1旧测试5s超时；复验暴露无public目录，修复后构建成功；失败日志保留 |

本轮性能对照是工程可靠性指标：干净基线由无法收集变为完整可运行；恢复从“有备份”变为32表内容核验；发布从“API源码+健康”扩展到Web输入/实际产物。没有改模型和产品路径，没有可声称的回答速度提升。

## 7. 开放项与 B/C 最终整合

B/C必须保留统一BASE，交付提交、修改文件、测试边界和未通过真实案例。A将审查冲突，重新执行最终树的后端主/专库、Web测试/类型/构建、版本/幂等/失败恢复、真实模型与供应商关键链和旧客户端兼容检查。单分支绿灯不授权正式部署。

当前已接收B至35f8e6b、C至207c9b7，在独立整合树执行验收；**尚不具备整体发布条件**：B的20题保留集整体NO-GO，空旅行初始规划外部研究失败仍OPEN，旧新客户端全面兼容未证明，公网权限隔离未通过。所有最终候选均保留在独立工作树；本轮不部署、不迁移/清理正式数据库。整合验收的最终证据另附本文后续章节。

## 8. A交付文件与提交

A分支 `codex/engineering-a-20261022`：`f5803b0`补必要合成夹具；`cc32e0b`测试隔离及门禁；`7eea683`构建来源与备份核验；`28f614f`拒绝停止容器冒充运行验收、剔除镜像附带Nginx样例；`dfb3da8`规范化跨工作树文本换行，防止相同配方因CRLF/LF产生假漂移。

16个实现文件：backend/Dockerfile、evals/assistant_capability_cases.py、scripts/write_build_manifest.py、tests/_database_safety.py、conftest.py、test_database_safety.py、test_assistant_research_postgres.py、test_formal_write_protection.py；根compose.test.yaml；scripts/run-isolated-tests.py、verify-backup.py、verify-release.py、verify-roamsync.ps1；web/.dockerignore、Dockerfile、scripts/write-build-manifest.mjs。未修改Agent决策/Planner、前端产品组件或数据库schema。

可移植证据在docs/evidence/engineering-a-20261022；原始失败、完整日志/JUnit、初始3133文件副本和私有清单在外置证据目录。测试报告不承诺生产模型效果；旧Web缺构建输入证明仍如实保留。构建来源证明只覆盖所列app/migrations/Web资源与配方，不能替代第三方依赖供应链审计、运行配置认证或服务启动验收。
