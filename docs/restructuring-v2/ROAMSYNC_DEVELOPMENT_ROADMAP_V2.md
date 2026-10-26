# RoamSync V2：共同基础与并行纵切路线图

日期：2026-10-15。第二轮修订候选，等待最终实施批准。本轮只读检查与文档修订，没有启动开发工作区、集成、迁移或部署。架构以[领域架构](ROAMSYNC_DOMAIN_ARCHITECTURE_V2.md)为准，启动门禁以[实施准备](ROAMSYNC_IMPLEMENTATION_READINESS.md)为准。

## 1. 相比第一轮的变化

- Phase0不只盘点和冻结：增加已有unknown/评分/估算标签修复、UTC/Trip当地日期修复、可信单owner、Android GPS与Draft复用早期spike。
- 将原Phase1–4重排为A内容即时服务、B连续助手、C自由规划正式旅行三条纵切；不是等内容全部完成才开始助手或草稿。
- 明确“探索默认首页、杭州集中区域首纵切、创建不默认LLM、预算可空、旧记录保留”作为原则接受，不反复开放讨论。
- 画像先显式保存/纠错，Evidence按实际入口跨线增量接入；不等所有正式规划完成。
- Q质量/Provider/真实模型/双端体验贯穿每个检查点，最终集成只是汇总门禁。
- 外部地图交接不强制Instant持久会话；GPS持续导航需要它，平台完成语义分别验收。
- P1异步正式化支持一次明确组合确认，不承诺跨Graph全链原子；P2短SQL原子方案暂备选。

## 2. DAG与关键路径

~~~mermaid
flowchart LR
 Review[最终方案与实施批准] --> G0[共同基础：源码身份/契约/可信字段]
 G0 --> F[unknown/估算与timezone修复]
 G0 --> NS[GPS真机可行性]
 G0 --> DS[Draft复用可行性]
 G0 --> A1[A1杭州探索/详情/收藏/地图]
 G0 --> B1[B1最小Context与稳定Session]
 DS --> C1[C1 Brief输入贯通]
 C1 --> C2[C2无Trip草稿生成/恢复]
 A1 --> A2[A2餐饮/住宿候选与真实路线]
 B1 --> B2[B2跨页多Topic与动作]
 A1 --> B2
 A2 --> A3[A3受控GPS Instant]
 NS --> A3
 B1 --> C3[C3正式化与旅程]
 C2 --> C3
 A2 --> C3
 G0 --> P[显式偏好/纠错]
 P --> B2
 P --> C2
 A1 --> E[收藏/反馈Evidence逐步接入]
 B2 --> I[整体真实旅程与发布候选]
 A3 --> I
 C3 --> I
 E --> I
 Q[Q持续契约/回归/真实质量] -.-> G0
 Q -.-> A1
 Q -.-> B2
 Q -.-> C2
 Q -.-> C3
 Q -.-> I
~~~

关键路径有两条：G0→A1→A2→GPS门禁→A3；G0→Draft复用门禁→C1/C2→C3。B1早期服务多条线，但先冻结Context就能用fixtures继续UI。unknown与timezone是基础验收阻塞，不等待整版首页。库存Provider属于独立外部依赖，不阻塞住宿POI；实时库存要求仍标不支持，不假结项。

## 3. G0共同基础（批准后首批）

1. **目标/价值**：先让事实标签可信、源码可复现、后续三线能安全并行。
2. **范围/不做**：选定整合块、字段/身份/上下文/导航/草稿/错误/幂等契约，unknown和时区小修，早期GPS/Draft spike；不整包导入旧树、不删旧Trip、不扩服务或Agent数量。
3. **依赖**：最终实施批准；明确本轮dirty成果所有权；受控单用户范围、测试设备和Provider授权可用性。
4. **影响模块**：maps_service/schemas/types/UI；database.Trip.status；decision_context/planning_intent；Brief相关共享文件；NavigationSource/Runtime；migrations（后续串行）。
5. **契约**：PlaceRef/GeoPoint、EvidenceField四维、Read vs Action/授权、单owner、typed Binding、relative day Draft、Promotion operation、版本/幂等/错误。
6. **具体任务**：
   - G0.1冻结当前全范围dirty manifest/配置身份，区分历史Git HEAD与当前源；选定只读diff里的跨日/计划元要求修复。
   - G0.2unknown/评分/参考费用与实价分离，内部planning_estimate保留；既有Web/Android标签一致。
   - G0.3Trip.status用Trip.timezone当地日期，区分计划阶段与执行事实；跨午夜/归档状态验证。
   - G0.4Brief来源/否定/撤回编译块审查，保留当前Companion/天气/stream修复，形成可追溯small patch。
   - G0.5可信owner入口及旧数据scope，冻结legacy Session迁移顺序。
   - G0.6实际GPS最小真机切片；G0.7relative day Draft与纯规则复用最小切片，均隔离验证后再扩展。
   - G0.8批准正式化P1协议、共享fixture、基线任务测量与Schema顺序。
7. **档位**：Sol High核心，Luna MAX明确DTO/标签/测试，Astra Medium独立审边界；Sol Max仅确有重大阻塞升级。均为用户指定分工，不是本轮调度。
8. **测试/真实验收**：新小块相关回归；共享核心整合后完整后端/Web/Android；unknown fixture；时区边界；GPS真实设备；Draft mock与真实模型结果分别报告。旧版不能完成的任务记“不支持/失败”，不填虚假耗时。
9. **风险/回滚/完成**：跨树覆盖、估算nullable破坏预算、权限假成功；每块可独立退回flag/兼容adapter，保存旧数据。DoD为选定源码新manifest+新回归+契约签定；GPS/Draft未通过时对应主线受阻，不阻塞不依赖任务。
10. **并行/检查点**：unknown/时区与两项spike可在文件owner明确后并行；Brief/core合入串行；G0结束产出共同集成commit或受审完整snapshot标识，当前0b5010f不能独自充当此标识。

## 4. 主线A：杭州内容与即时服务

### A1 探索、详情、收藏、地图

- **用户成果**：零Trip/零LLM用户能在杭州选定集中区域找真实地点、看来源/合法图片、收藏、地图返回同Place。
- **范围**：Place/ref、独立search/detail/around、nullable字段、合法asset、Favorite与两端探索壳；不做全量评论、全球覆盖或预订。
- **依赖/模块**：G0字段/owner/Place契约；maps_service、new Place adapter、App/PlacesDrawer/MapCanvas、MobileApp/RouteMap/API；migration owner先合Place/ref/Favorite。
- **任务/契约**：A1.1身份与旧candidate映射；A1.2真实query/详情及来源；A1.3图片许可/缺图；A1.4Favorite幂等；A1.5Web/Android纵切；A1.6模型断路与Provider失败缓存。
- **档位**：Sol High身份/数据边界；Luna MAX页面与明确adapter；Astra Medium来源缺失独立审。
- **验收**：S01/S02/S10、H01/H03/H08/H12/H13；契约fixture与真实POI分别证据，正式业务表0新增。
- **风险/回滚/DoD**：许可/配额/缺字段；探索flag可退，收藏可读导出。DoD为一真实区域完整产品闭环，unknown可理解。
- **并行**：Provider+fixture先出，Web/Android可同步；B1只需稳定Place契约即可前进；检查点IA1。

### A2 餐饮/住宿候选与任意端点路线

- **用户成果**：附近吃饭/今晚酒店地点筛选→真实路线；模型坏了仍能用。
- **范围**：餐饮distance/reference cost/评分比较；住宿POI与日期保留；RouteQuote与external handoff；不保证无Provider的实价/开门/房源。
- **依赖/模块**：IA1、G0 Context最小规则、RoutingPort与CRS；maps route adapter、两端详情/路线UI；无需等待完整B2。
- **任务/契约**：A2.1around与筛选；A2.2真实路线端点化/来源时效；A2.3外部handoff本地Receipt；A2.4住宿日期人数/unknown；A2.5有商务授权才实现HotelQuote port。
- **档位**：Sol High路线/事实；Luna MAX列表比较/交接；Astra复核酒店人均与房价区分。
- **验收**：S03/S05/S10，H03/H12；阻断模型后仍可用；外部唤起不标GPS或到达；库存不支持如实展示。
- **风险/回滚/DoD**：报价商务依赖/路线过期；可关quote功能但POI正常，旧quote不更新伪时效。DoD为真实选择→路线/外部交接；不包含受控GPS完成声明。
- **并行**：B2动作提案使用A2 fixtures，C3预备依赖真实路线端口；检查点IA2。

### A3 受控GPS即时导航

- **用户成果**：餐厅/景点直接应用内导航、取消、恢复；无Trip也可用。
- **范围**：Instant状态/设备互斥/幂等终态、持久StopIntent、SDK walk/drive；不改正式Navigation FK或恢复算法。
- **依赖/模块**：GPS spike通过、IA2、Binding契约；Instant服务/SDK Runtime/Source/observation adapter；跨设备尚不支持。
- **任务/契约**：A3.1状态/CAS/设备槽；A3.2真实GPS/权限；A3.3start ack与晚回调；A3.4断网取消/进程死亡；A3.5正式导航切换与回归。
- **档位**：Sol High状态/SDK；Luna明确UI与测试；Astra独立并发复核；Sol Max用于重大运行阻塞。
- **验收**：S04/S08，H02/H07/H14；GPS真机、模拟、外部分列；Instant正式Execution/Disruption/Recovery零写；原正式延误恢复全链保持。
- **风险/回滚/DoD**：Key/签名/权限、simulated观测误入正式、旧callback；停止新start但终止/读状态始终可达。GPS证据缺失则部分完成，不能external替代验收。
- **并行**：Backend session和Android可在golden binding后同步；核心状态owner一人；检查点IA3。

## 5. 主线B：连续智能助手

### B1 最小Resolver、稳定Session与legacy兼容

- **用户成果**：从探索/详情进入同一助手，位置与讨论对象清楚，当前明确要求保留。
- **范围**：ContextEnvelope最小读、ActionTarget与授权分离、Topic/session owner、旧trip_id检索adapter；不摊平全部历史。
- **依赖/模块**：G0契约与trusted owner；assistant service/routes、companion context/contracts/state、两端助手VM/Panel；legacy FK由Schema owner串行执行。
- **任务/契约**：B1.1read budget/敏感字段allowlist；B1.2action唯一目标与版本；B1.3scope先于SET NULL检索迁移；B1.4旧Run/SSE恢复；B1.5topic局部预算隔离。
- **档位**：Sol High权限/session；Luna明确UI/reader spy；Astra独立CASCADE与授权复核。
- **验收**：S09/H04/H11；杭州位置/南京浏览/苏州只读Trip，询问是否加入不写；同名目标拒绝、无关数据不读、删除Trip不删global。
- **风险/回滚/DoD**：null trip旧session混入global、历史泄漏；关新global创建但新历史保留，legacy回退读取不跨scope。DoD完整跨页查询，正式写只经独立guard。
- **并行**：不等A1全完，可用冻结Place fixtures；检查点IB1。

### B2 结构化推荐、跨页动作与降级

- **用户成果**：一句需求→可打开真实Place卡→地图/导航/草稿；返回上下文一致。
- **范围**：Suggestion解析Place、ActionProposal、消息/选择version、模型失败基础入口；不增加自治Agent数。
- **依赖/模块**：IB1、IA1/IA2真实能力或对应fixture；Companion ports、App全局壳、Android助手；正式操作guard仍统一owner。
- **任务/契约**：B2.1structured cards与身份；B2.2旧响应丢弃；B2.3明确用户要求来源与撤回；B2.4模型断路/SSE取消终态；B2.5南京Place与苏州Trip跨城可行性建议。
- **档位**：Sol High复杂路由；Luna页面/明确测试；Astra独立上下文污染案例。
- **验收**：S03/S05/S09/S10，H04/H08/H11/H13；真实模型输出与正确事实分开，未解析Suggestion不能直接导航。
- **风险/回滚/DoD**：模型猜目标/Topic预算泄漏；保留非模型路径，动作提案flag可退。DoD真实多轮与并发返回不串对象，不必要澄清可测。
- **并行**：显式偏好可同步接入，C1消费相同编译契约；检查点IB2。

## 6. 主线C：自由规划与正式旅行

### C1 Brief来源贯通与公共规划核

- **用户成果**：用户说过的明确要求真正进入规划输入，且能解释作用域。
- **范围**：审选phase1a纯Brief编译、Formal/Draft binding adapters、公共input parts/refs/pure rules；不复制Graph或放松正式Validator。
- **依赖/模块**：G0跨日/元要求整合、Draft spike；planning_brief候选、assistant、planning graph/runtime/run repo、openai_planner；共享文件单owner。
- **任务/契约**：C1.1来源/否定/撤回；C1.2target binding；C1.3formal输入差分；C1.4规则小步提取；C1.5消费者fixture；函数级清单见架构§4。
- **档位**：Sol High复杂依赖；Luna既定测试；Astra独立证据与优先级。
- **验收**：Brief可追到真实user turn；明确要求不掉；旧Formal schema/Validator/Memory/候选编辑/Recovery全回归；新版不能继续以旧“Brief不影响输入”测试作为目标通过。
- **风险/回滚/DoD**：旧树覆盖新Companion、需求误升硬约束；小块patch与配置回退，正式原入口保持。DoD共享边界实际复用、没有两份同义规则。
- **并行**：可与A1/B1同步，但assistant/graph改动由对应owner串行合入；检查点IC1。

### C2 无Trip结构化草稿

- **用户成果**：南京三日日期未定也可预览、保存、修改、取消、恢复，多次试不建Trip。
- **范围**：relative-day DraftInput/PlanSnapshot、Draft/Run作业与CAS、coverage、两端旅程草稿页；不调用假的正式Trip。
- **依赖/模块**：IC1公共核与独立输入；Place/source fixture；Draft repository/job adapter/UI。
- **任务/契约**：C2.1无日期输出schema；C2.2作业领取/lease/deadline；C2.3取消令牌/晚结果；C2.4自动保存和retry；C2.5coverage与未核实事项；C2.6模型故障手动读写。
- **档位**：Sol High模型/作业；Luna页面与已定fixture；Astra独立reviewable语义。
- **验收**：S06/S12、H05/H09；正式表零写；无假日期/营业库存保证；mock机械结果和真实模型质量分别记录。
- **风险/回滚/DoD**：异步旧结果覆盖、规则分叉；关新生成但草稿仍可读/取消。DoD真正独立恢复/取消链，而非只会话文本。
- **并行**：Web/Android用shared snapshot，显式偏好已有接口即可接；检查点IC2。

### C3 正式化、历史兼容与自然旅程页

- **用户成果**：保留草稿、只创建旅行、创建并采用都清楚；一次组合确认可用；失败后知道已创建/未采用。
- **范围**：推荐P1协调、DraftPromotion授权/状态、动态事实预备、formal materialize adapter、原Accept guard、历史兼容；不先做P2大事务重构、不自动删旧Trip。
- **依赖/模块**：IC2、IB1、IA2、正式化spike通过；Trip/Run/Revision/Accept共享核心、job、两端旅程；迁移串行。
- **任务/契约**：C3.1preparation与semantic hash；C3.2三动作与grant；C3.3分阶段目标映射；C3.4accept/cancel线性化与对账；C3.5幂等/断点恢复；C3.6legacy用途待确认展示；C3.7创建Trip不默认LLM。
- **档位**：Sol High事务/授权；Luna明确UI与故障测试；Astra独立接受边界；重大阻塞才Sol Max。
- **验收**：S07/S08/S11/S12、H06/H07/H09/H10/H14；每个提交后注入故障、Accept前取消、回包丢失、stale/changed→needs_review；已有Trip失败不暗删；原formal回归。
- **风险/回滚/DoD**：全链假原子、授权漂移、重建Trip；关新promotion但已有operation可取消/读/恢复；DoD组合意图可审计且恢复状态准确，P2仍仅备选。
- **并行**：UI可先fixture，不能并行修改Accept/Run/Graph；检查点IC3。

## 7. 显式偏好与反馈：跨线增量

P1显式scope/source/纠错CRUD可在G0后开始；P2收藏和用户体验Feedback在A1后接入；P3保守推断要有用户同意和真实证据价值。Trip预算、某晚预算与全局软偏好分开；Current明确要求优先软推断但不越过正式保护。不复用拒绝DecisionMemory作为长期画像，不用停留/浏览时长直接硬推断。

相关模块：Preference/Evidence/Feedback、Context选择器、Brief compiler、我的页；档位Sol High数据/纠错，Luna明确UI/测试，Astra独立证据强度。验收H10/H11，撤回后生效、来源能解释、无关任务不读；风险隐私/误推断，关inference保留显式管理。DoD是用户可管理且不串任务，不是点击画像标签演示。与A/B/C通过port并行，核心消费改动归共享owner。

## 8. Q持续质量与检查点

| 检查点 | 必须交付的可用纵切 | 自动/真实验证 | 失败时其它线怎样继续 |
|---|---|---|---|
| G0 | 既有页面不误报事实，新契约/可复现基线 | unknown/timezone、集成回归、GPS/Draft spike分结果 | GPS失败不阻止A1/B1；Draft失败不阻止内容 |
| IA1 | 搜索→详情→收藏→地图返回 | shared DTO+真实POI/图片许可+双端 | B/C用versioned fixtures，不能对用户假交付 |
| IA2 | 找餐厅/酒店地点→真实路线/外部交接 | 真实路线/时效、无模型、住宿unknown | GPS入口仍关，外部不冒充GPS |
| IB1/IB2 | 连续助手→真实Place/动作提案 | 三城矩阵、最小读、真实多轮/失败SSE | A规则入口照常，formal修改继续原路径 |
| IC1/IC2 | 要求保留→无日期草稿→恢复 | formal差分、零Trip写、真实/合成模型分栏 | 既有正式Planner继续，promotion入口关 |
| IA3 | 无Trip真机GPS→取消/恢复 | walk/drive/权限/断网/进程死亡+formal恢复回归 | 不过则GPS未完成，不扩大完成声明 |
| IC3 | 三种正式化→原Accept/失败恢复 | 故障点/授权/版本/取消/对账、真实来源重验 | 失败operation可见保留，不影响探索 |
| I终验 | 14条硬门禁+12场景+用户价值 | 当前freeze真实双端/Provider/模型/隐私/回滚 | 未过门禁不称全产品完成，部署另批准 |

测试通过、模型输出成功、独立业务质量可靠、产品可用四列分别结论。每阶段使用真实Provider有界smoke与未执行声明，不到最后才查SDK/房源。真实模型失败/不完整纳入分母，不用mock分数冒充质量。非模型能力始终断路验证。

产品测量在G0建立任务/设备/网络/可用Provider基线；旧版不支持S04/S06就记录不支持，无完成耗时，不能编成“减少多少分钟”。新版对支持任务测完成率/操作/重复澄清/满意决定时间/控制感，预注册阈值在基线后批准。逻辑门禁零越权/零暗建档不是性能数据。

## 9. 并行所有权与合入规则

| 角色/未来工作区 | 拥有范围 | 共享边界/约束 | 档位 |
|---|---|---|---|
| INTEGRATION/SCHEMA | 共同基线、migration head、owner/DTO/golden版本、合入清单 | 所有DDL串行；禁止整目录合并/复制旧文件 | Sol High |
| DATA-A | Place/Provider/字段来源、真实数据smoke | schemas/database提交给Schema owner，不能私改正式候选语义 | Sol High+Luna MAX |
| WEB | Web探索/地图/收藏/草稿/全局壳 | API先冻结；App.tsx多线需求由单Web owner合入 | Luna MAX |
| ANDROID | Android产品壳/SDK adapter/权限/Runtime | 单NavigationRuntime owner；API models由契约owner生成/审 | Sol High导航+Luna UI |
| NAV-A | Instant用例/RouteQuote/CAS/设备槽 | 正式Navigation/Recovery纯核变更须Formal owner审 | Sol High |
| CONTEXT-B | Session/Topic/Resolver/动作权限/Companion输入 | assistant_service/contracts单owner，Brief/Promotion以port接入 | Sol High |
| FORMAL-C | Brief绑定/公共Planner核/Draft/Promotion/Accept guard | planning_graph/runtime/repo/Validator共享所有权唯一 | Sol High |
| PERSONAL | Preference/Evidence/Feedback及管理接口 | 不直接并发改Resolver/Brief compiler | Sol High+Luna |
| QUALITY | 契约、回归、真实失败证据、源码绑定、用户测量 | 不顺手修核心；问题回原owner；人工业务质量独立 | Luna MAX，Astra关键复核 |

角色是待批准分配的代码所有权，不表示已创建这些会话或有人已接单；并发数量由可用人力/工具决定，不要求一次开9个工作区。契约未冻结先做可丢mock/原型，不启动互相猜接口的多线编码。

合入顺序：G0选定源码→小修/契约→Schema新增→Provider/API兼容→UI消费者→真实纵切。共享Graph/Accept每次小块新回归，不整包合并Brief旧树。schema只有一个head；各worktree独立测试库，绝不共用正式roamsync项目/volume。增量记录base commit+完整dirty manifest+锁文件/配置身份+测试范围，不能只记0b5010f。

依赖未完成：给消费者versioned golden fixtures和capability=unavailable，生产flag关闭；接口变更先升级fixtures并通知owner。合并冲突回owner做函数级审查，不由多会话分别“修好”同一核心。版本/授权/schema变化需ADR与Agent v1 change-control更新。

## 10. 14项硬验收映射（未来门禁，非本轮全通过）

| ID | 断言 | 主检查点 |
|---|---|---|
| H01 | 无Trip搜索/浏览/收藏/助手 | IA1/IB1 |
| H02 | 无Trip直接导航且不暗建正式对象；外部/GPS分别标识 | IA2/IA3 |
| H03 | 模型不可用基础内容/地图/路线仍可用 | IA1/IA2，每次Q |
| H04 | 杭州/南京/苏州位置预算/对象隔离 | IB1/IB2 |
| H05 | 草稿可恢复，未正式化不建Trip | IC2 |
| H06 | 明确Trip后原版本/Validator/Revision/Accept-Reject保留 | IC1/IC3 |
| H07 | 正式导航delay→disruption→recovery→accept不回归 | IA3/IC3 |
| H08 | 内容→助手→地图→返回Place身份一致，晚response不覆盖 | IA1/IB2 |
| H09 | 重复规划不增正式Trip；promotion幂等 | IC2/IC3 |
| H10 | 历史/偏好可管理；旧unknown不误删 | IC3/P/I |
| H11 | 行为软推断不能盖当前明确要求/正式硬约束 | IB2/C1/P |
| H12 | 价格/路线/营业/库存有来源；未知过期诚实降级 | G0/IA2/Q |
| H13 | Web/Android核心语义一致，平台capability差异明确 | 所有检查点 |
| H14 | explore-only、nav-only、完整规划执行均可用 | I，分别举证 |

## 11. 相对复杂度与停止条件

G0跨树整合、B1上下文/迁移、A3 SDK一致性、C3事务授权均高风险；A1/C2中高；事实标签/显式偏好中等但须保护预算与来源。酒店库存为外部依赖高不确定。没有工期/完成日假设。

停止对应依赖扩展的条件：GPS spike不成立、Draft复用导致formal差分无法解释、授权取消线性化不成立、owner来源不可信、Provider数据许可缺失。停止该功能实现扩展不妨碍其它独立纵切继续；严重争议未解决不冻结整个方案。发布候选仍需新源码/镜像/配置绑定与用户批准，当前只等待最终实施批准。
