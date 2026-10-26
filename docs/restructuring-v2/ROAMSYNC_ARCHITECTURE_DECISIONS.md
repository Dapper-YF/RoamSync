# RoamSync V2 架构决策记录（ADR候选）

日期：2026-10-15。以下状态均区分“原则接受”“建议冻结”“待技术验证”“待产品批准”；没有已获实施授权的声明。目标契约只以[领域架构](ROAMSYNC_DOMAIN_ARCHITECTURE_V2.md)为准；本文件记录理由与否决方案，不建立平行规范。

## ADR001：按职责解除Trip依赖，首期可信单owner

**状态**：业务原则已接受；owner实现待验证/实施批准。

背景：正式版本/执行真实需要Trip，城市与住宿POI/Companion已经可独立。当前没有User/tenant鉴权，不能把客户端owner_id当身份。

决策：探索/收藏/路线/即时导航/草稿独立；正式Trip保留。首期可信入口确定唯一server owner，忽略/拒绝客户端伪造归属；控制访问范围与server凭证分开于owner标识。仅配置常量owner不等于有公网认证。新数据带可信purpose/origin，实验库隔离。

替代：万能User/Context聚合根会重造中心耦合；所有FK nullable会弱化真实业务约束；即刻公网多租户扩范围。均不推荐。

后果/门禁：所有新API有owner校验契约，公共Provider内容和私有收藏权限区分；公开多用户和跨设备同步另需鉴权/授权/会话/迁移验收。旧未知归属记录不公开、不猜owner。共同基线与trusted ingress实现前不宣称身份安全完成。

## ADR002：即时持续导航独立；external不伪装会话

**状态**：建议冻结，GPS可行性待真机验证。

证据：database:563/567，session_service:114，Android NavigationBinding、AmapNavigationSource:71/82；缓存Manifest缺定位权限，SDK JAR符号存在不证明运行。

决策：RouteQuote适合路线展示；外部地图使用本地Receipt；只有受控GPS持续任务持久Instant。复用同一SDK Runtime/路线Provider、纯CAS/sequence机制，正式session FK/恢复原样。Instant状态ready/starting/active/rerouting/suspended及明确终态；持久StopIntent、device槽互斥、终态幂等、迟到观测无权复活。Instant不写TripExecution/Disruption/Recovery。

替代比较：泛化旧session nullable字段改动遍及ExecutionSubject/恢复/Android，回归面高；新父表/子binding迁移过重；只有external不能满足应用内GPS最终要求。

代价：新增持久生命周期与双binding adapter；收益是正式可信边界不弱化。若GPS spike失败，A1/A2 external继续，但A3未验收；不拿external/模拟替代真机。设备槽的服务端持久实现需spike验证，避免先建设跨设备调度平台。

## ADR003：Draft复用小公共核，不复制正式全栈

**状态**：建议冻结目标；复用可行性待spike。

证据：build_planner_input:322、CandidateActivity:1128、validate_candidate_plan:64、Graph节点；本轮空日期负向探针。纯codec已可复用；phase1a编译与正式bind/load混在模块中。

决策：Draft day_index/可空dates与PlaceRef、独立DraftRun；共享候选/要求/证据投影、ref domain与JSON解析、纯schedule/budget/route规则；Formal/Draft adapters分别装配，原正式wrapper和硬约束入口保留。Graph不整体复制，Draft仅编排共享生成步骤+独立存储/取消/coverage。

否决：隐藏正式Trip、假日期、把所有正式Run改nullable、复制一套Validator。纯文本预览也不满足结构化恢复。提取顺序先一个规则让Formal调用同实现并回归，再扩Draft；不一次性抽象完整FormalContext。

后果：新增DTO/adapter而非双套业务规则；reviewable不代表日期营业/价格/预约验证。若共享提取无法保持formal差分，停止相关扩展并缩小spike，不用关闭正式保护换复用。

## ADR004：组合意图与多事务正式化

**状态**：P1建议冻结；失败Trip展示需产品批准；授权/事务guard待验证。第一轮“两承诺必两点击”及未经验证全链原子声明撤回。

证据：repository.create_trip可commit=False；create_planning_run仍调用intent解析；Graph自建多个session并commit；save_plan_revision:249、accept_plan_revision:660分别commit；approval interrupt与checkpoint跨边界。

决策：保留草稿/create_only/create_and_adopt三种行为。create_only不默认LLM。采用前形成真实日期PreparedPlan/coverage/content hash；用户可一次组合确认，授权绑定确切内容/事实/约束，不覆盖后台自由重生成。

P1默认：持久DraftPromotion同时为操作状态/授权/映射；分阶段T1建Trip、T2正式candidate、T3原Accept语义及guard；中断按引用/状态对账，重复不再建档；实质变化或失效转needs_review。Trip已明确创建但采用失败时可见保留，不自动删除。

P2备选：一切网络/模型在事务外，短SQL段建Trip/candidate/Accept原子应用；需拆save/accept内部commit和Run解析/持久化，全部正式回归。禁止把Graph/Provider/checkpoint纳入长事务。

取舍：P1触及核心较少、适合早交付，承认部分完成状态；P2最终状态整洁但核心回归风险高。单次点击是UI/授权语义，二者都可实现，不由事务数决定。待真实任务证明P1部分状态显著伤体验后才升级P2。

线性化：Apply与Cancel在同一受审授权/Accept边界竞争；Cancel先提交则不采用，Accept先提交则返回已采用并提供正式修改。现有Accept缺promotion guard，不能把本ADR当已实现保证。完成反馈丢失按accepted事实和授权消费对账，不再次生成。

## ADR005：最小Read Context与独立Action Resolver

**状态**：建议冻结，新增实现/测试待批准。

证据：当前CompanionContext单destination，assistant按trip_id恢复并变更绑定；read权限已有SELECT-only基础，值得保留。

决策：physical、browse area/place、discussion、read requests、action request分别输入；owner/permission/唯一目标/version/授权由服务端独立Resolver生成，正式约束从目标对象读取。模型引用/只读Trip不授写权。view/topic/selection_version阻止晚响应覆盖；默认不读取无关敏感历史。

否决：全局last-city、将所有Trip读上下文当操作对象、默认当前Trip预算到所有查询、全历史拼prompt。提出“是否加入苏州行程”允许只读可行性，不意味着加入已授权。

门禁：六个评审指定场景+跨owner/旧授权/跨Topic/版本反例；reader spy验证最小读取。普通查询少澄清，正式目标不唯一确定性阻断。

## ADR006：事实四维字段；内部估算不被误用

**状态**：原则接受，契约建议冻结；G0小修待实施。

证据：maps missing rating→0、类别默认cost；Drawer零值→免费、统一实时；LocationPoi路径已可空rating，说明不是必须全端用0。

决策：value_status、nature、freshness、served_from四维分开；来源、检索时间/可空provider观察时间、有效期和估算方法记录。内部planning_estimate数值继续服务预算/Validator，但UI和推荐不能称实际价格。旧未标来源不自动改值；未知实价不能按0排名。报价字段必须绑定单位/日期/人数/税费/取消条件/Provider。

替代：把全部cost改nullable会破坏当前预算链；统一“参考”也掩盖实查/缺失差异；有检索来源就称实时可售不成立。酒店POI、人均参考不是HotelQuote；无授权接口只提供候选核实。

门禁：missing/非法/明确0、estimate=0、cache stale、字段缺失、照片缺失、房价人均混用fixtures；两端显示一致，原预算回归保持。图片评论许可与Provider配额需真实确认，不靠模型补。

## ADR007：当前源身份与逐块整合

**状态**：基线事实VERIFIED；共同新基线尚未形成。

当前官方源309文件与上轮零漂移，HEAD仍0b5010f；旧测试1002/132/35属于该上轮快照，非本轮新测。15树双向hash/hunk差分保存；相同HEAD不代表dirty相同。

决策：优先facts/timezone、54b8888跨日/元要求两个app+两个test小块、phase1a Brief来源编译/绑定审查。Weather/Event/热度/资讯等仅候选资产，不因存在就整包导入V2。保留最新Companion/stream/forecast代码，逐函数新测试与manifest。批准后先共同冻结基线，再从它开工作区。

否决：旧树整体copy、把HEAD作为最新源、继承旧阶段测试数、顺手git add全部/merge全部。Trip计划阶段按Trip.timezone，真实执行另列；timezone补丁必须UTC跨日回归。

## ADR008：旧Session先分scope再解CASCADE

**状态**：建议冻结，副本迁移待验证。

证据：AssistantSession.trip_id CASCADE；按trip_id/null取最近会话。单独改SET NULL会把已删Trip历史误当global。

决策：增加显式scope/owner/schema_version与legacy topic/tombstone映射；先上线按owner+scope+session/topic的读写，再切FK为SET NULL；新global trip_id=null，legacy被删target仍legacy。原消息尽量原地保留，不全量复制为全局对话；新global会话/收藏不受Trip删除级联。

scope具体区分legacy_trip、原本无Trip的legacy_unbound和新global。旧null检索和pre-trip reset只允许legacy_unbound，禁止被删Trip的会话因FK为null被误选或清空；来源迁移ledger决定scope，客户端不能改。

代价：兼容窗口检索adapter与映射ledger；收益：保护旧会话/run恢复与删除语义。未知owner数据不公开。回滚先flag/新读路径，不恢复CASCADE再删除V2历史。取消未消费proposal、混版本客户端和重复迁移必须测。

## ADR009：三条纵切与持续质量

**状态**：组织原则接受，任务分配/实施待批准。

决策：G0共同基础，A真实内容即时服务、B连续助手、C自由规划正式旅行并行；P显式偏好/Evidence跨线，Q每次合入验证。共享Schema、assistant、Graph、Accept、AndroidRuntime和各端全局壳各有单owner；他线经port/golden fixture提出变更。

相对第一轮：不等A完才B，不等全部Trip完才偏好，不最后才发现GPS/Draft不成立。每线交付用户能用的纵切。未ready依赖用synthetic标记fixture、真实入口关闭，不假交付。真实测试、模型输出、独立质量、产品价值分别结论。

## ADR010：历史与隐私边界

**状态**：历史安全原则已接受；精确留存期限OPEN。

来源不明Trip一律legacy_unknown，不按名称/日期/内容推测试。新实验server purpose+隔离库；不把正式失败状态当自动删除理由。精确位置、终止命令、聊天、引用证据、草稿、正式快照、图片缓存各按用途/许可最小保留，期限待产品批准；未同意行为学习不默认采全量行为。

该ADR不授权本轮清理任何记录。注销/删除/备份与被引用证据的处理必须有可审计、可恢复或明确不可恢复的用户选择。

## 冻结记录方式

最终批准应记录文档hash/版本、批准范围、仍开放的技术门禁、首批任务和owner。实现spike可能要求受控ADR修订，不擅自弱化正式约束。没有批准记录之前，所有“决策”均为候选，不执行迁移/合并/部署。
