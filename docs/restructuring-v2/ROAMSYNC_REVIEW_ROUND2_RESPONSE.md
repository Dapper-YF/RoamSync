# 第二轮联合评审逐项回应

日期：2026-10-15。结论：接受总体方向；完成第三轮方案修订候选，**未冻结、未获业务实施授权**。本文件是评审意见的回应，不是把ChatGPT意见自动写成已实现能力。

标记：VERIFIED代码/静态证据；MEASURED实际执行；TECHNICAL CONCLUSION工程论证；CANDIDATE FREEZE候选冻结；VALIDATION REQUIRED待运行验证；PRODUCT APPROVAL待负责人最终批准。

## 1. R01—R06逐项处理

| 意见 | 接受/修改/反对 | 理由与证据 | 已完成修订 | 尚需验证/批准 |
|---|---|---|---|---|
| R01 独立导航 | **接受，并收紧持久化最小性** | 正式session非空Trip/Execution；Android固定驾车、只模拟；缓存Manifest没有定位权限 | external只RouteQuote+本地Receipt；GPS持续会话才Instant；补starting/suspended、device互斥、终态幂等、StopIntent持久重试 | 真机Key/权限/walk/drive/重绑/进程死亡；共享Runtime不是已完成保证 |
| R02 Draft复用 | **接受不复制；修正“复用现有输入构建”应为提取公共核** | build_planner_input:322依赖dated days、formal context；CandidateActivity.day_date必需；Validator读ORM/执行 | 函数级复用矩阵、三个小公共边界、relative day schema、Formal/Draft adapters、coverage | Draft真正无日期生成/作业恢复/取消/0Trip写、规则差分、旧正式全回归 |
| R03 正式化 | **接受；撤回第一轮过早的原子性推断** | Graph节点各建session且commit；save_revision:249、Accept:660独立commit；checkpoint另存 | 三种行为；P1可恢复异步默认/P2预备后短SQL事务备选；一次明确组合确认；变化重审；分阶段失败/取消/对账 | 授权消费/取消线性化、mapping提交窗口、Accept guard、P2核心拆分均未执行 |
| R04 上下文 | **接受** | 当前只有单destination且session按Trip；read对象可能被错误用作动作目标 | physical/browse/discussion/read requests/action request/server authorization/formal constraints分层；最小读allowlist | 六项指定场景+伪owner/旧授权/跨Topic反例，需新实现测试 |
| R05 事实语义 | **接受，提前到共同基础；本轮只完成修复方案** | maps:239 missing rating→0，252/508类别estimate，PlacesDrawer零值→免费/实时标签 | EvidenceField的存在/性质/时效/读取方式正交；legacy显示不猜，内部估算保留；餐饮住宿字段能力和fixture矩阵 | 需批准后改DTO/展示/归一化并回归，当前业务缺陷未修复；酒店报价无接口 |
| R06 源码/owner/时区 | **接受** | 309文件与上轮相同；15树双向差异；Trip.status:83用UTC；当前无账户授权 | 新只读diff、集成优先级/owner/测试门禁；受控单owner可信边界；时区修复进G0 | 尚无整合后新基线/commit；owner守卫/时区补丁尚未实现；多用户/跨设备另门禁 |

## 2. 我保留的工程判断

### 2.1 不能把“复用”理解为强行兼容原Formal接口

R02目标合理，但当前规划输入、模型schema、输出resolver、route enrichment、Validator都包含日期和正式对象依赖。本轮禁网负向探针确认空日期会被拒绝/抛异常。推荐复用模型传输/refs/纯规则与明确要求编译，分别装配Draft和Formal输入；反对给草稿补假日期或伪Trip以换取表面复用率。这会稍增adapter，但避免污染正式语义。无日期生成仍待spike，不把静态分析当实现通过。

### 2.2 一次确认并不要求全链原子，也不授权采用新方案

接受R03的体验纠正。明确用户可一次批准“创建并采用当前显示方案”；不接受在后台模型重新生成、内容变动后仍沿用该授权。默认P1分阶段可恢复，失败可出现明确已创建Trip但未采用；这是需要产品批准的可见状态。P2只在Provider预备结束后做短SQL事务，必须先拆当前内部commit/语义解析。反对把网络、checkpoint、Graph和Accept包进长事务。

### 2.3 external handoff不值得默认增加服务端会话

R01有条件接受新增Instant正确，但若用户仅打开外部地图，RoamSync既不能控制持续GPS也不能自动确认到达，持久active Session会制造错误状态。推荐本地Receipt；只有应用内持续控制才持久Instant。审计、成本或用户历史如需持久外部操作记录，可以另存明确handoff事件，不赋GPS状态。

### 2.4 Phase0不应膨胀成实现全部V2基础设施

支持事实小修/可信契约/两项早期spike提前；不建议在Phase0就建全套Place、全局session迁移、Draft和device分布式调度。G0交付选定基线、兼容字段修复、最小接口与可行性证据；其余由三条可用纵切带动。否则只是把大重构改名为Phase0。

## 3. 其余决策不再重复开放

| 原决策 | 第二轮处理 | 当前状态 |
|---|---|---|
| D01/D02 | 探索默认、进行中任务快速恢复、杭州集中区域首纵切 | 原则接受；具体区域边界按真实覆盖采样冻结 |
| D03/D04 | Instant有条件接受；Web外部与Android原生分验收 | 候选ADR002；GPS技术门禁未过 |
| D05 | 独立Draft，不复制正式全栈 | 候选ADR003；复用spike未过 |
| D06 | 不强制两次点击；组合授权+P1默认/P2备选 | 候选ADR004；产品失败状态与工程协议待批准/验证 |
| D07 | create_only不默认LLM；create_and_plan必须明确请求 | 原则接受，不再讨论默认暗启动 |
| D08 | 稳定session/Topic、逐请求最小读/动作隔离 | 候选ADR005/008 |
| D09 | 预算可空且任务隔离 | 原则接受，兼容Android表单需批准后修 |
| D10 | 受控单用户，可信server owner；公开/跨设备另门禁 | 本轮范围已接受；不是已实现鉴权 |
| D11 | 酒店POI先行，实时报价/库存/预订独立外部依赖 | 原则接受，不能以POI价冒充房价 |
| D12 | 来源/许可/缺失明确，内部估算不冒充实价 | 原则接受，G0修复待实施 |
| D13 | unknown旧Trip原样保留，不自动判测试或删除 | 已接受安全边界 |
| D14 | 逐块审查旧成果，优先可靠性/Brief，不整包merge | 候选ADR007；尚未集成 |
| D15 | 先显式保存/纠错，再保守Evidence | 原则接受 |
| D16 | 按类型留存，精确期限OPEN | 真正产品待定项，未编期限 |
| D17 | 旧版不支持记失败/不支持，不造耗时 | 原则接受，测量未执行 |
| D18 | 模块化单体，不加不必要服务/Agent | 原则接受 |

真正剩余问题集中在[OPEN_DECISIONS](ROAMSYNC_OPEN_DECISIONS.md)，不再把18项全部列为用户待选。

## 4. 第三轮要求的八类证据覆盖

| 要求 | 本轮交付 | 已有事实/测量与未执行界线 |
|---|---|---|
| 1 Instant最小状态/SDK/隔离 | 架构§3、ADR002、V-NAV计划 | 缓存JAR符号/Manifest静态检查；实际GPS未跑 |
| 2 Draft函数依赖/最小公共核 | 架构§4、function-dependencies.json、V-DRAFT | 负向日期兼容探针与codec往返执行；Draft成功路径未实现 |
| 3 两种正式化编排 | 架构§5、ADR004、V-PROMOTE | 当前commit/session/interrupt源码已复核；两种新方案均未跑 |
| 4 Read/Action/授权分离 | 架构§6、Context用例矩阵 | 当前缺口已由代码确认；目标Resolver尚未实现 |
| 5 AssistantSession CASCADE | 架构§7、迁移文档R2修订 | 旧FK/检索事实已核对；scope→检索→SET NULL次序待副本验证 |
| 6 POI/估算/未知/过期契约 | 架构§8、G0事实包fixture、ADR006 | 当前错误显示已确认；标签/DTO未改 |
| 7 基线/准确差分/优先级 | readiness、round2 snapshot、15树双向diff、选定patch | 当前309文件零漂移；候选patch仅供审阅未应用；新共同基线未建立 |
| 8 DAG/并行/检查点 | 修订路线图G0+A/B/C+P+Q | 产品/任务设计完成，不表示已开工作区 |

## 5. 本轮验证记录

**VERIFIED**：官方branch/HEAD与前轮一致；309源码/测试/构建配置hash零漂移。15工作树双向核心差异记录每文件两侧hash、增删行、缺失方向与行尾等价；与第一轮单向统计口径不同，不能比较数量当成果增减。优先4个可靠性文件、9个Brief相关文件另有只读patch和exact hash。

**MEASURED**：在既有隔离测试镜像、network=none、无DB/模型/Provider调用下：CandidateActivity空date校验失败；build_planner_input空date抛TypeError；request-local codec往返true。只验证既有路径限制和基础机制，不把失败算Draft实现通过。

**VERIFIED（缓存产物范围）**：SDK JAR 11.2.100含walk/drive/startGPS/start/stop符号；合并Manifest缓存仅INTERNET和receiver权限。没有新安装APK、运行真机、请求定位权限或实际导航。API签名/生命周期/Provider Key仍待验证。

上轮后端1002/2warnings、Web132/typecheck/build、Android35是**最近已测基线**，本轮未重跑全量；因源码零漂移可作为同快照参考，不能转成“第二轮新测”。本轮未修改业务代码、Schema、配置或数据，未合并/提交/部署。

证据在[evidence/round2](evidence/round2/)；主索引见[实施准备](ROAMSYNC_IMPLEMENTATION_READINESS.md)。

## 6. 冻结与实施结论

建议冻结核心设计及G0验证任务书，继续保留GPS、Draft复用、promotion授权/事务、旧FK迁移为技术门禁。当前达到“可明确分配任务和审查改动面”，尚未达到“新实现已经验证”。最终用户批准前不启动业务编码、多线开发、正式迁移、历史清理、合并或部署。
