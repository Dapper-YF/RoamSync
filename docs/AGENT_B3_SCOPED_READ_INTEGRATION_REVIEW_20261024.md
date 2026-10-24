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
