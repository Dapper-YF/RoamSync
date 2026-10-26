# RoamSync V2 实施准备与启动门禁

日期：2026-10-15。状态：**方案可审查/任务可拆分，等待最终批准；未启动业务实施**。候选契约见[架构](ROAMSYNC_DOMAIN_ARCHITECTURE_V2.md)，理由见[ADR](ROAMSYNC_ARCHITECTURE_DECISIONS.md)，依赖见[路线图](ROAMSYNC_DEVELOPMENT_ROADMAP_V2.md)。

## 1. 当前源码身份和测试证据

| 项目 | 当前可声明 | 不能声明 |
|---|---|---|
| 官方源/分支 | E:/Study/RoamSync；codex/roamsync-demo-release-20261007；HEAD0b5010f | HEAD代表全部10月15日dirty成果 |
| 本轮hash复检 | 上轮309源码/测试/构建配置文件零漂移 | 所有未来整合源码已冻结 |
| 最近实测回归 | 上轮后端1002/2warnings、Web132/typecheck/build、Android35实际rerun；源绑定见旧证据 | 本轮重跑了相同全量测试、真实GPS已过 |
| 本轮负向探针 | 既有隔离image禁网：无日期formal candidate失败、input TypeError；codec往返true；0DB/0模型 | 新Draft无日期生成已实现/通过 |
| 本轮SDK静态检查 | 缓存SDK JAR walk/drive/startGPS/start/stop符号；缓存Manifest没有定位权限 | 新APK安装、签名/Key/权限/实际GPS验收 |
| 15树差分 | 双向文件hash/缺失方向/增删行及行尾等价；选定可靠性/Brief patch供审阅 | 代码已经合并、旧树所有质量已验收 |
| 数据与运行 | 本轮无业务代码/Schema/配置/正式数据写入、无合并提交部署 | 未来迁移/上线已获授权 |

基线有两种身份：B-audit是当前工作树完整manifest与上轮实测；B-integrated是批准后选定小块整合、重新测试并记录的共同基线。后者现在不存在；不能为它填一个旧commit。未来开分支须基于B-integrated或有明确隔离用途的B-audit spike，不因当前HEAD相同省略dirty内容。

## 2. 待整合修复的精确优先级

角色是建议代码所有者，尚未分配给具体人/会话。差分数据见[evidence/round2/integration-differences.json](evidence/round2/integration-differences.json)，只读patch不应用。

| 块 | 来源与实际改动面 | 所有者/影响 | 新测试与合入门禁 |
|---|---|---|---|
| I-Facts，P0 | 当前maps.search_amap_places、schemas/TS/Kotlin、PlacesDrawer/Inspector/推荐卡；无旧树“已修复”假设 | DATA维护字段，端UI owner展示，Schema owner审DTO；Planner估算数值保留 | unknown/明确0/estimate/cache/stale/人均房价fixtures；客户端反序列化；正式预算原测试；真实样本核验 |
| I-Timezone，P0 | database.Trip.status:80–88，UTC→Trip.timezone；Web journey/Android显示消费者 | FORMAL + 两端owner；不修改实际执行记录 | 杭州00:01/UTC前日、其它时区、归档优先、起止日；计划阶段不冒充真实完成 |
| I-CrossDay，P0 | 54b8888 decision_context：+12/-1行；test_decision_context +42行 | FORMAL；非目标日execution指针保留为只读/保护 | 跨日current/navigation/first_impacted、unknown指针仍拒绝、outside scope不可编辑；全formal regression |
| I-PlanMeta，P0 | 54b8888 planning_intent_service：+9/-0；test_planning_intents +39行 | FORMAL；元要求词法识别在真实别名匹配后 | “其他日期安排不变/整体三天框架”、同名真实活动优先、未知地点仍澄清；intent+full regression |
| I-Brief，P0审查/C1接入 | phase1a：新planning_brief.py233行/测试461行；contracts +15/-4、state +3/-1、assistant +21/-3、graph +17/-1、runtime +4、run repo +12、planner +3/-1 | FORMAL拥有编译/binding；CONTEXT拥有assistant/contracts；只选函数块串行合入 | source excerpt/否定/撤回/版本/hash/目标绑定、current request优先、未知Suggestion不升正式ID、stream/forecast/Companion回归；不整文件覆盖 |
| I-Weather/Event/News，后续候选 | phase1b1/b2/b21/closeout独有weather/events/event_text/updates/recommendation_claims及正式核心变化 | DATA+FORMAL共同审查，受单owner整合 | 无本轮整合保证；先评估是否服务当前纵切，真实Provider/时间scope/来源授权独立验证，不抢占G0 |
| I-Knowledge/Facts原阶段 | 官方已存在相关模块，原分支不是祖先 | DATA；模块与调用可复用，不等于整个原提交已合并 | 按当前真实调用与来源回归，不能重新整包cherry-pick制造冲突 |

增删行是规范化文本diff，字节hash另存；行尾等价单列。15树最新双向清单包括官方有而旧树没有的文件，所以数值与第一轮单向统计不同。它说明差异，不自动说明哪个版本更好。

选定Brief包不是整包批准：bind_brief/load_brief带target_trip_id/base_version，Draft需adapter；新C1测试不能沿用旧测试“Brief不改变prompt”的断言作为目标。最新Companion/forecast/stream必须保留，分块review解决冲突。

## 3. 共享文件owner和修改协议

| 文件/函数域 | 唯一owner角色 | 消费者怎样改 | 防冲突门禁 |
|---|---|---|---|
| database.py、migrations、公开schemas/generated models | INTEGRATION/SCHEMA | 提交字段/约束变更请求+fixture，不各自起Alembic head | 版本号串行、增量DDL、前后兼容 |
| assistant_service/routes、CompanionContext/contracts | CONTEXT-B | FORMAL提供Brief/Promotion port；DATA提供结构化Place port | 不多树同时改相同路由/模型字段 |
| planning_graph/runtime/run repository | FORMAL-C | Draft adapter/共享生成步骤小patch | 每块新formal+checkpoint回归 |
| plan_revision_service.validate/accept、candidate_edit、执行/恢复 | FORMAL-C | NAV/Promotion提纯规则/guard变更 | 版本/保护/取消线性化必须review |
| maps_service/Provider parsing | DATA-A；Routing接口由NAV-A共同审后DATA合入 | 端点请求/错误/CRS fixtures | 不在UI或Agent另写Provider事实归一化 |
| Android NavigationRuntime/Source/Binding | ANDROID-NAV | Backend给冻结DTO，产品页只调用port | 同一SDK槽所有权、旧回调、source隔离 |
| web/App.tsx与全局助手壳 | WEB | A/B/C通过组件接口提交增量需求 | 单owner整合，避免三线重写App |
| Android MobileApp/ViewModel/API models | ANDROID-PRODUCT | A/B/C同义需求/golden models | 与导航VM职责明确，不各自fork全局状态 |
| Preference/Evidence | PERSONAL | 给Resolver/Brief provider接口 | 不并发改两个消费核心 |

owner是代码责任而非另建服务/Agent。正式工作区共同基线和接口版本未确定前，不派多线实现；可审查设计与mock但不当真实交付。

## 4. 可以排入首批的任务及条件

“可排入”表示设计边界足够具体，**仍须最终批准、分配owner和隔离基线**，不是本轮开工指令。

| 任务 | 准备度 | 启动前还需什么 | 不应等待的依赖 |
|---|---|---|---|
| G0 unknown/评分/估算标签小修 | 可启动的明确小任务 | 批准、DATA/UI owner、当前source hash、fixture | 不等新首页/完整Draft/GPS |
| G0 timezone/跨日/元要求选定修复 | 改动面明确，可逐块整合 | FORMAL review、隔离DB、按候选hash核对 | 不等全部旧工作树成果 |
| V-NAV真机spike | 验证任务可启动；GPS功能未就绪 | 真机、可用签名/Key、用户授权定位、独立测试session、批准最小SDK变更 | 不等完整A1/B2 |
| V-DRAFT复用spike | 验证任务可启动；无日期功能未就绪 | FORMAL/Model owner、纯规则测试夹具、隔离Draft存储/有界真实模型预算授权 | 不等完整旅程UI/画像 |
| Place/事实/Context/Binding golden fixtures | 契约足够做合成实现 | 共同schema review/version、明确synthetic标签 | 不等所有Provider可用 |
| A1 Web/Android探索原型/非模型纵切 | 可并行准备，真实交付依赖G0/Place API | UI owner、冻结Place与unknown fixture；实际API阶段再接真实Provider | 不等C3或酒店库存 |
| B1 Resolver最小读/Action分离 | 可实现确定性核心，迁移另门禁 | owner contract、只读/写作用域fixtures | 不等完整A1内容UI |
| 显式Preference保存/纠错 | 独立任务设计足够 | scope/source/owner契约，用户管理入口 | 不等所有正式规划完成 |
| C1选定Brief公共编译 | 可review/分块实施 | 现源码与候选diff审查、CONTEXT/FORMAL单owner协调 | 不整包引Weather/Event |

暂不能直接扩展：A3受控GPS产品（先V-NAV）；C2完整Draft（先V-DRAFT/C1）；C3正式化（先V-PROMOTE）；legacy FK切换（先V-SESSION副本演练）；实时HotelQuote（先商务授权与真实Provider）；公开多用户/跨设备（范围另批准）。

## 5. 最小验证任务书与断言

所有以下V-*都是**待执行计划**，本轮只有负向兼容/静态探针。预计改动面不是承诺工期或实际新增文件。

### V-NAV：受控GPS可行性

- 输入：一台真实Android设备、两对真实端点、GCJ02、walk/drive各一次；正式旅行与即时fixture分别绑定；不使用用户正式旅行写入做实验。
- 预计改动：NavigationSource增加真实start模式、AmapNavigationSource按mode选route与回调token、Manifest与runtime权限、privacy gate、typed binding、持久StopIntent。现SDK JAR已有符号只是可调查入口。
- 断言：隐私同意和定位授权前不启动；拒绝时路线/外部降级；GPS mode使用真实位置、走路不调用驾车；收到真实启动ack才active；旧route回调不污染新binding；同device不能双Runtime；stop后无晚观测复活；杀进程/断网取消重启先StopIntent；服务端正式表零写。
- 证据：APK/source/hash、设备系统/权限状态、模式、Key仅记录是否配置、SDK回调与原生导航可见行为、服务端会话/取消/观测摘要；不存真实连续轨迹或凭据。实际GPS与simulation分栏。
- 通过后才扩A3；失败如Key/权限/SDK模式问题由ANDROID owner报告，不改Provider版本或正式恢复来掩盖。

### V-DRAFT：无日期与公共核

- 输入：固定已解析Place池、duration=3、dates=null、同一组明确要求/预算，所有price/fact带真实或synthetic性质，synthetic不能算真实质量。
- 预计改动：DraftInput/PlanSnapshot adapter、GenerationInputParts/RefDomain/最小PurePlanRules、DraftRun存储/作业小切片；原Formal wrapper保留。函数级范围见架构§4。
- 断言：day_index1..3，无虚构日期或Trip行；候选ID皆允许refs；时间/预算/路线结构规则两路径同fixture一致；formal protected/locked/ownership/version仍执行；DraftRun中断重启可恢复，cancel阻止晚结果，retry不重复Trip；not_checked营业/报价/预约不会显示已通过。
- 分层：先mock证明机械恢复/规则；有界真实模型证明能产无日期schema，不把mock结果计生成质量；独立人工评可用性。模型调用和用量须另有明确测试范围，不自动无限实验。
- 通过标准：同一公共函数由Formal和Draft调用且差分解释清楚；不能复制另一套Validator通过；真实成功与失败都保留。

### V-PROMOTE：P1协调、授权与故障恢复

- 输入：已审阅Draft/version、真实日期PreparedPlan/content/evidence hash；create_only/create_and_adopt/keep三种意图；隔离测试库。
- 预计改动：DraftPromotion状态/映射/授权；provider preflight；deterministic formal materialize adapter；save_revision映射提交所有权；原Accept入口的授权guard/锁序；不扩整个Graph事务。
- 故障注入点：preflight前后、T1建Trip提交前后、T2candidate提交前后、T3授权消费/Accept前后、API回包丢失、worker/checkpoint晚更新、重启。
- 断言：预备/keep无Trip；create_only无Run/LLM；combo只有semantic hash完全相同才可用原授权；费用/路线/日期/约束实质变化needs_review；双提交同operation/Trip；cancel先提交则禁止Accept，Accept先提交则返回已采用；失败既有Trip保留且状态真实；final accepted→operation对账，无第二Trip。
- 必须验证：现save/accept内部commit使哪些操作能共事务、哪些必须最小拆分；不得只mock commit就声称SQL原子。P2只在独立短事务原型/旧正式全回归成立后再考虑。

### V-CONTEXT：只读与动作分离

- 预计改动：ContextEnvelope、Read/Action Resolver、topic/view版本、最小reader、authorization adapter；模型只给候选引用。
- 断言：杭州定位/南京酒店/苏州Trip；南京地点“是否加入苏州”可只读建议但0写；明确加入后唯一Trip/可达性/版本校验；并发旧response不能覆盖；切Topic旧预算消失；同名多Trip一次澄清不写；reader spy确认无关历史未查未送模型；伪owner/伪grant/旧proposal失败。
- 通过才合B1动作路径；普通查询无需不必要的Trip确认。

### V-SESSION：legacy scope与CASCADE副本演练

- 数据：合成legacy_trip、原本无Trip的legacy_unbound、新global null session、多个同城Trip、pending Action、accepted/active Run、已删除target、unknown owner。真实数据副本如使用须另行授权/脱敏；本轮不复制私有数据。
- 预计改动：scope/owner字段、legacy topic mapping/ledger、查询adapter先行、FK SET NULL后行、Action撤销。
- 断言：删Trip不删global；legacy_trip被置null仍保持scope，不能被新版global或旧版pre-trip null检索/reset命中；只有legacy_unbound可旧创建前reset；旧会话/run能恢复；未消费Action对被删目标失效；重复迁移不多消息/映射；新旧客户端兼容窗口明确；回滚不丢V2消息；未知归属不公开。
- 只在隔离库演练，Schema owner串行执行；通过不自动授权正式迁移。

### V-FACTS / V-TIMEZONE / V-BASELINE

- V-FACTS：missing/非法rating、明确0、estimate0、cache fresh/stale、POI字段缺失、人均≠房价、无库存无Quote；用户只见与性质一致标签，模型断路仍查。内部estimated_cost数值与预算/路线安全回归保持。
- V-TIMEZONE：Trip当地00:01与UTC前日、end_date边界、归档优先、无执行记录；预算date/天气date与UI保持明确时区，不批量改历史日期。
- V-BASELINE：批准后核对selected patch hash；逐块整合→当前全量隔离回归→两端type/build→需改变的真实Provider案例→新源码/镜像/配置binding；留下失败和准确范围，不能只升级测试数。

## 6. 迁移、并行与发布门禁

1. **G-APPROVAL**：最终批准候选契约/首批范围；当前未满足。
2. **G-OWNER/BASE**：owner角色分配、B-integrated或spike隔离manifest、共享fixtures版本；当前角色表已有、实际分配/新基线未完成。
3. **G-FACTS**：unknown与timezone/局部预算语义回归；当前仅方案。
4. **G-GPS/G-DRAFT**：最早验证，分别阻断A3/C2扩展，不阻断无依赖纵切。
5. **G-PROMOTE/G-SESSION**：SQL/授权/取消与迁移副本证据；当前未满足。
6. **G-PROVIDER**：许可/配额/来源/缓存/实查字段；酒店Quote独立，不以普通Key存在证明可售权。
7. **G-REAL**：每纵切真实模型/Provider/双端/质量/失败记录；四层结论分开。
8. **G-DATA/RELEASE**：正式备份恢复、迁移/发布的明确批准另行办理。本轮批准方案也不自动批准清理、合并或部署。

首期受控单用户并不授权公开运行；server owner和访问token不含在客户端可自填的ownership字段中。多用户/跨设备需独立身份、授权、并发/同步策略验收。隐私留存精确期限未定前，不启用全量行为或连续位置历史采集。

## 7. 建议的安全验证命令（未来执行，非本轮新测）

原完整后端命令须使用新的明确隔离Compose project和tmpfs测试库：

~~~powershell
docker compose -p roamsync-v2-readiness-check -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test
~~~

先确认compose.test.yaml目标未漂移、无正式DB/volume引用；本轮不执行上述命令。Web按改动运行pnpm test/typecheck/build；Android :app:testDebugUnitTest --rerun及实际GPS单独真机验收。迁移演练仅隔离库，旧test中含demo reset，禁止直接指向正式数据库。

## 8. 本轮证据索引

| 文件 | 证明范围 |
|---|---|
| [round2/snapshot.json](evidence/round2/snapshot.json) | HEAD/309文件零漂移、未做新全量/GPS/Draft成功验证 |
| [function-dependencies.json](evidence/round2/function-dependencies.json) | 当前函数行号范围与静态call列表，不是运行call graph |
| [worktree-core-differences.json](evidence/round2/worktree-core-differences.json) | 15树四个核心目录双向文件hash、缺失方向、规范化diff统计 |
| [integration-differences.json](evidence/round2/integration-differences.json) | 选定4可靠性/9Brief文件精确hash和增删行 |
| [可靠性只读patch](evidence/round2/reliability-review-only.patch) | 当前→候选差异，未应用 |
| [Brief只读patch](evidence/round2/brief-review-only.patch) | 当前→phase1a候选差异，未应用；不可整包覆盖 |
| [sdk-static-inspection.json](evidence/round2/sdk-static-inspection.json) | 缓存JAR符号与合并Manifest权限，不是GPS证明 |
| [draft-compatibility-probe.json](evidence/round2/draft-compatibility-probe.json) | 禁网纯兼容负向探针，无DB/模型 |
| [上轮verification.json](evidence/verification.json) | 最近1002/132/35等实际测试范围，未冒称本轮重跑 |
| [上轮source-and-worktrees.json](evidence/source-and-worktrees.json) | canonical源码manifest与第一轮单向盘点 |

当前结论：可在批准后按明确任务书启动G0小修、两项spike和契约/纵切工作；不得把剩余技术门禁写成已通过，也不得在最终批准前开始业务实施。
