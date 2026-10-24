# A 对 B3 scoped read 的只读整合审查

日期2026-10-24；受审提交 `41a4f91d3f94f1c3671689f5e963336e99a774ad`，独立树 `E:/Study/RoamSync-agent-read-b3-20261024`，产品祖先89b81e8。此审查不接收产品代码、不改B文件、不额外运行测试。B的154/84及真实对照仍是B测量，A不借用为统一验收。原产品整体NO-GO不变。

## 阻断接收的发现

1. **P1：新增夹具与统一回归不兼容（VERIFIED静态契约冲突）。** `backend/tests/test_b3_saved_trip_reads.py:22`断言DATABASE_URL的库名必须以roamsync_agent_b3_开头；`scripts/run-isolated-tests.py:78`的主套固定roamsync_test_write_protection，且不会排除该测试文件。统一命令执行到使用sessions的测试即会在fixture断言处失败。这不是安全误用，两个名称都是明确隔离测试库。应复用既有 `_database_safety` 验证，保留APP_ENV、官方模式拒绝、独立test token与checkpoint同库校验；不可跳过这些测试或删安全门换绿。
2. **P2：标称同一Trip版本的快照未取得一致性读取（INFERRED并发可达，未运行竞态）。** `saved_trip_reads.py:125`先读Trip.version，138读counts，153读活动，159以后读事项；engine在database.py:851没有设置repeatable-read，默认PostgreSQL READ COMMITTED每条语句独立可见已提交数据。即使同一事务，也可能旧version/counts配新activities/items。活动数量不变的时长/时间修改尤其可能complete=true却标签错误。Companion `companion_context.py:55,72`的理由查询又依当前Trip.version，而非捕获快照版本，网络期间另一次Accept可能把新理由拼到旧活动。建议短事务一致性快照，或读取前后版本复核、界定所有事实版本、对变化保守失效；不要用跨网络锁解决。理由至少绑定同一captured version并验证该活动状态。

## 已检查但未作总体保证的部分

- reader只发SELECT且autoflush=false，不导入写入/规划/Accept服务；选择ID在目标Trip/日期内核对。是读取引用，不赋予候选采用权限。
- selector与Companion传递同一detached对象，子任务保留itinerary_purpose；无选择不按列表第一项猜身份。
- 多于limit的覆盖和同名歧义会明确不完整；没有把100项截断宣称全行程不存在其他项目。
- overview/saved_values走保存值确定性投影，original_rationale保留历史读取目的；这不证明模型正确选择purpose或完整表达全部复合要求。
- 快照dataclass的字典虽未深层冻结，对消费者主要使用deepcopy；本轮未发现具体外部写权限提升，不等于公网所有权已解决。

已将以上两点发给B，等待其在自身隔离树修复并提交新SHA。**41a4f91暂不接收，不部署。** 后续须检查变更及标准统一套件兼容，再执行统一回归；不得把旧89b81e8的1792+38绑定到新产品源码。B正在进行的新公开真实before/after只能按实际结果另列，不能当新的未见保留题。


## 对4a8dcb374cc992a8fff4f7c9d6508ab028e3724d的后续复核

原P1修复：fixture复用_database_safety，兼容统一明确测试库并保留正式库拒绝。原P2一致性修复：独立连接首条SQL前设置REPEATABLE READ，然后SET TRANSACTION READ ONLY；活动/计数/事项/偏好同一MVCC快照。async连接、事务和reader均有上下文管理，异常/取消路径对应真实PG反例；理由和notes绑定捕获Trip版本，不再以当前理由拼接旧快照。版本前后复核只作过期提示，执行status不增Trip.version的限制明确保留。

A核对了B `final-regression-source.json` 与XML：exit0/source_unchanged=true、252 tests/0失败错误跳过；其中164个app文件原始哈希与4a8dcb3的Git换行规范等价，无差异。A未重新跑测试，也未称其为全量统一回归。B称公开开发六轮before1/6→first5/6→final6/6，仍为作者判定与公开开发题，不替代独立保留题。

**新增P2：嵌套借用同一有限连接池存在池饥饿（INFERRED调度反例，未执行并发负载）。** semantic_turn在29行SELECT AssistantSession FOR UPDATE取得外层连接，60行调用loader；saved_trip_reads.py在同一个engine上再次connect，直到回到68行才提交外层事务。生产database.py未覆写pool参数；本地实际安装SQLAlchemy AsyncAdaptedQueuePool签名为pool_size=5,max_overflow=10,timeout=30s。如果15个独立请求分别先取得15条外层连接，再都等第二条，均可能等到30秒超时。现有fixture用NullPool，连接归还测试无法证明有限池容量安全。不能仅增大pool_size掩盖。应消除持有外层连接时嵌套借用同池的循环等待，例如先释放短会话事务、借独立快照后再按session签名CAS复核；若采用独立有界读池/准入，须明确全进程连接预算及取消释放。A已发给B，未直接改其源码。

另一个接口限制：capture阶段SavedTripReadStale发生在semantic_turn主try之前，经ValueError转换成AssistantToolError；新增后段needs_retry捕获不覆盖该入口。不得声称每个过期入口均返回typed needs_retry；可通过统一捕获修正或准确记录边界。

当前结论：原两项阻断的修复已核对，但4a8dcb3仍未接收/部署，等待连接容量和入口错误边界处理后的固定新SHA。整个产品NO-GO，A产品BASE继续89b81e8。


## 对3f983039b07f1b960beba5a5b5677c16f1ca81e5连接边界的只读复核

独立NullPool读取通道替代从业务池嵌套取连接。准入发生在创建engine之前，每事件循环最多2条，排队5秒上限；短RR READ ONLY捕获后关闭连接、dispose引擎并在finally释放准入。应用单事件循环/进程条件下预算为业务池默认15+读取2，Worker另计，不把多进程总数说成17。静态看原循环等待已消除；新增真实PG测试以业务池size2/overflow0且两调用方都占用时并发读成功，另覆盖准入等待取消。A未额外运行这些测试，等待B最终完整记录。

本次窄连接边界未发现新的接收阻断；不是吞吐、长期资源稳定性或总体发布批准。B当前完整重跑需要修正一个旧policy测试的查询观察范围：独立引擎不再被原engine实例监听，须保留全部原禁用查询断言，仅扩大事件观察范围。该测试变更应有最终提交及源码身份；不得把未提交测试变化绑定到3f全部源码。

B报告3f的新公开六轮为5/6，其中一轮模型顶层trip:{candidate:null}被严格schema拒绝；保留原文，不extra-ignore、不重采样刷分。4a8的6/6是历史开发测量，不属于3f结果。A仍未合入/部署，待最终提交/完整证据后作接收审查；产品整体NO-GO。
