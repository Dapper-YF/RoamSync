# A2 规划短事务与并发保护设计（用户已批准，实施中）

起点：6a65ece3acc3ea9a32087c11a2cbbe05173862dc；正式源码及3000仍未变。新隔离树E:/Study/RoamSync-reliability-a2-20261022，分支codex/reliability-a2-20261022。

## 目标与责任

第一优先是去掉规划模型/路线请求期间的数据库事务与Trip行锁，同时保持正式写保护、版本、Validator和Accept。B为主线，拥有一次语义决策和operation交接、条件投影、复合任务及创建闭环；A只拥有事务/并发与Worker可靠性。C负责真实产品流程与封存新保留题。所有实现、合成写入均在隔离资源中；不部署、不写正式数据库。公网前必须解决身份、Trip/session所有权P0，本轮不宣称公网安全。

## 已核实根因及真实范围

1. planning_run_repository.create_planning_run先锁Trip，再await resolve_planning_intent；后者读ORM实体后可调用semantic_provider.extract。已有双连接探针在await期间得到55P03。直接API会传模型provider。
2. commit=False调用方包含AssistantSession锁、刚创建且未提交的Trip和确认receipt；自动恢复调用方还有Navigation/Disruption/Execution事实。直接在repository提前commit/rollback会破坏原子性，另开只读session也不能读取尚未提交的新Trip。仅移动一行lock_trip不能解决这些入口。
3. save_plan_revision默认在Trip/Run锁后enrich_candidate_routes；resolve_route_result不仅调地图，还读取/写RouteCache。**正式Graph.persist目前显式enrich_routes=False**，通常已在validate节点补路线；不能将默认分支的问题误称为全部正式Worker都在persist中网络等待。默认分支仍须安全，Graph.validate的读事务/缓存写跨网络也需要分清处理。
4. TripPreferences.version独立于Trip.version。仅比较Trip版本无法证明期间条件不变。Accept已有Trip/Revision/Run/Preferences锁和有效条件校验，应保留。
5. Worker已有15秒心跳。仍存在租约清理不核对持有者、DB轮询异常可退出、失联回收边界；不是简单延长lease即可解决。

## 推荐方案

采用三阶段：短只读快照 → 无事务网络阶段 → 短锁与复核写入。

- 网络输入必须是脱离ORM/session的服务端快照；模型只接收一次已经认可的目标与有效条件。A不增加第二次决策，B负责operation语义。
- 独立API入口先读Trip/偏好/目标实体快照，结束只读事务，再执行B的语义准备。网络返回后，按固定顺序锁Trip，再偏好/Run及相关事实，复核Trip版本、偏好版本、目标仍属于Trip及事件状态。变化时返回现有冲突语义，不自动覆盖或重新解释目标。
- commit=False原子调用必须先在调用方事务外准备operation；进入持锁创建后只能确定性校验/grounding和写入。尚未提交的新Trip使用已授权当前操作和内存快照，不在其锁内再调用模型。A/B对齐接口后再落地参数，不把客户端上传的resolution当授权。
- 已与B对齐：B的resolve_planning_intent新增内部prepared_draft: SemanticIntentDraft|None；存在时不extract、不重选目标。A在planning_preparation.py定义服务端frozen PreparedPlanningIntent，绑定trip_id、原user_request、entry_point、selected_day_id/activity_id、base_trip_version、preferences_version与draft；create_planning_run接受prepared_intent。直接API使用B的async load_planning_intent_snapshot(session, trip_id, payload)->PlanningIntentSnapshot与async resolve_planning_intent_snapshot(snapshot,payload,*,semantic_provider=None,prepared_draft=None,default_planning_intent=None)->PlanningIntentResolution。Snapshot由frozen Trip/Day/Activity/Candidate/active execution date组成，不含Session或ORM lazy load；A在同一短读事务补读TripPreferences.version，结束事务后才调用无session resolver。写入时重load当前snapshot、复核双版本，再用已有draft重新grounding。B先单独交付helper实现，A接入；接口已对齐不等于代码已完成。
- 路线补全拆成服务端节点快照与路线证据准备；底层网络请求不携带正在持锁的session。缓存读取/写回各用短事务，缓存冲突不能回滚正式业务事务。路线返回后重锁、检查正式版本/有效条件与Run状态，才保存revision。既有Graph无网络persist和Draft promotion确定性原子路径保持原子。
- 不通过提前提交调用方事务、不加宽地图估算、不跳过Validator/Accept、不增加第二套Planner解决等待。

## 其他方案与取舍

- 只把lock_trip下移：成本低，但read事务、commit=False上层锁和旧快照仍在，拒绝作为完成方案。
- 独立读取session包住现有resolver：可隔离一部分API连接，但网络期间仍占该session事务，也解决不了未提交Trip可见性；不能单独作为根因修复。
- 全面改成新的任务/状态库：迁移与整合风险大，本轮不采用。

## 第一提交的验证矩阵

在全新tmpfs PostgreSQL，用Event控制模拟provider暂停，不靠sleep猜测：

1. 同输入旧版在模型等待期间第二连接NOWAIT得到55P03；新版第二连接可获取Trip锁，数据库pg_stat_activity不出现对应网络阶段idle in transaction。
2. 网络暂停时另一连接合法修改Trip；新版返回后拒绝旧结果，不创建基于新版本但使用旧语义的Run。
3. 仅修改TripPreferences而不变Trip.version，也拒绝旧条件结果。
4. 候选路线暂停期间同样可取得Trip/Run锁；期间取消Run、改正式行程或条件，返回后不落过期revision。
5. 两个并发保存只产生合法revision序号与一个有效pending候选，旧pending状态不被乱改。
6. commit=False包含的新Trip、会话receipt和Run：最终异常时一起回滚；成功时一次提交，网络阶段不提前泄漏业务写入。
7. 导航/体验恢复唯一索引、重复消息、刷新/重试、Accept/409及取消边界不回退。
8. provider失败/取消后无遗留行锁，连接池占用回收；同输入记录等待时长与锁获取结果，不把模拟网络时间当真实模型提速。

先保留失败反例，再实现，再执行相关事务/创建/采用/恢复套件；稳定后执行全量主/专库及Web回归。前后对照保留输入、旧/新SHA、源码指纹和原始输出。

## 后续Worker提交（第一提交验收后）

每次claim唯一持有者身份，心跳、进度、失败、最终写入和cleanup必须验证本次claim；旧Worker不能续约/清理新Worker的lease或提交候选。先评估复用worker_id中的claim身份是否足够，不能仅把cleanup加where就宣称端到端fencing完成。DB短暂故障有有界backoff，任务异常应被收集；进程停机取消/等待在途任务，过期回收须有双Worker与旧任务复活反例。需要修改Graph写边界时先与B对齐；不同时盲改其语义节点。

## 四项统一产品门槛

1. C独立封存新20题；B冻结前不可阅读/运行。目标至少16/20基本可用，且零未经核实的关键安全/可行性保证；这是阶段目标，不是普遍可靠性证明。旧公开题只可用于回归。记录出题/审查身份，不冒充独立人类盲评。
2. 真实连续咨询→检索→建议→创建→候选→采用→修改→刷新→异常恢复；合成候选只能证明UI/Validator链，不能代替模型全链。
3. 每项修复保留相同输入旧新原文、工具参数/调用次数、持久状态与耗时，不只汇总测试数。
4. A收到冻结B/C后重新执行工程回归、接口/旧客户端与完整真实浏览器验收；达到门槛后才评审部署，本轮仍不直接部署。

## 当前完成状态

已完成代码追踪、分支隔离和责任/门槛同步；尚未修改任何产品源码。用户已批准设计，接口已与B对齐；实施计划见PLANNING_RELIABILITY_A2_IMPLEMENTATION_20261022.md，不把本文当成实现或验收通过证据。

新统一门槛已另存QUALITY_GATE_V2_20261022.md；C已封存20题与预先评分规则，SHA256=8bb1a83faa83659cf6ceb95745e29934922629012c176061b986dba23bef7da2。A/B不读取题面；C旧版公开流程环境为独占roamsync_product_c2_baseline_test，3044/18044，保留题另分配独占库。
