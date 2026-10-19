# 第一阶段 Formal Write Protection 集成评审

本报告仅评审正式安排写入保护，不是全产品或全后端架构验收。未创建新的架构
SSOT，不部署，不迁移生产库，不修改主工作树，不实施第二阶段。

## 集成来源与结论

- 正式源码：`E:/Study/RoamSync`，核查 HEAD 为 `25a62cb`，没有比修复基线更新的提交。
- 正式工作树已有修改：README.md、web/nginx.conf；另有原有未跟踪文件，均未导入。
- 隔离集成目录：`E:/Study/RoamSync-write-integration-20261019`。
- 分支：`codex/formal-write-integration-review-20261019`。
- 将 `7b67f68` cherry-pick 为 `f06a847`，没有冲突，两提交的树内容相同。
- 审查并非直接批准原提交：发现并先复现四类缺口，增加五项 PostgreSQL 回归，
  仅修改四个现有应用文件，增加25行、删除4行；formal_write.py本身不变。
- **READY：修正后的提交集合可安全进入正式合并；原7b67f68单独不足以作为稳定输入。**
  正式源码尚未包含任何本轮改动。建议采用7b67f68及本轮review补丁；也可直接采用
  集成分支（f06a847是7b67f68的等价cherry-pick），两种方式择一，避免重复导入。

## 新发现、归因与处置

| 严重程度 | 事实与归因 | 最小处理及失败证据 |
|---|---|---|
| P1 | Accept遇到缺失Preferences时，旧get_trip_preferences自动commit，释放Trip/Revision锁；在第一阶段保护下仍出现Accept200、并发新增201，新决定可被覆盖 | Accept持有Trip锁时补建Preferences，仅flush；随整个Accept提交/回滚。review-red-preferences.xml两项失败分别证明锁释放和补建未回滚 |
| P2 | 第一阶段新增no-op判断先于预算联动规范化，显式total_budget_fen=null在其已为空、daily_budget非空时被误判为空操作，改变旧API含义 | 将预算联动处理移到no-op判断之前；review-red.xml证明日预算仍为5000 |
| P2 | move先锁另一Trip的Day，再拒绝跨Trip操作，可形成两个非法请求交叉持锁。是既有局部锁缺口，削弱本次共同父锁规则 | 在日期行锁之前读取并验证不可变的Trip归属；保留404/422。review-red.xml真实PG外部行锁+lock_timeout证明原路径进入外部Trip |
| P2 | 第一阶段request_dynamic_replan新增Trip锁，把不存在旅行/执行的既有404改成409 | 先查询Execution身份，缺失保留404，再取Trip锁；review-red-missing-corrected.xml证明409回归 |

这些处理不改变正常规划、授权消费、路线算法或执行状态机。缺失Preferences属于
异常/旧导入数据边界，不新增第二份约束模型。并发删除发生在身份读后仍可返回冲突；
这与一个从未存在资源的404是不同情形。

## 写路径与锁审查

| 路径 | 实际保护及边界 |
|---|---|
| 活动新增/删除/字段更新/移动/排序 | main.py → planner_repository.py → protect_formal_write → Trip锁 → 子记录变更 → finish_formal_write一次提交；真实语义变化才推进Trip.version |
| 时间/路线重算 | 仍是原算法；入口包在同一保护中；间接改动活动时间、位置会推进相应Activity.version。并非只保护被点击活动 |
| Trip元数据/日期/归档/删除 | repository.py先取Trip锁；元数据使用原expected version；日期删除保护不变；重复归档不再增版。整Trip删除先锁关联AssistantSession再取Trip，匹配助手顺序 |
| Accept | 授权检查 → Trip → Revision → Run → Preferences → 活动/路线及执行投影；检查base_trip_version、最终验证、同一Revision重复采用；缺失Preferences现在不再中途commit |
| 候选创建/保存/拒绝 | 创建和保存先Trip再共享子对象/FK；拒绝先Trip再Revision。候选过程不因此推进正式版本 |
| Requirements/Preferences | 与Accept共同父锁，保留独立Preferences版本；不伪装成安排变更。当前要求在最终Validator重读，具体约束覆盖仍有独立缺陷 |
| Draft Promotion | 保留Operation授权锁 → Trip → Revision/Run等子对象；准备/重新确认仅能处理尚未采用、version=1的目标Trip，并撤销旧准备候选；不是第二条已采用行程编辑通道 |
| Execution/Navigation/恢复 | 需要跨子对象处理恢复的命令先Trip；纯导航刷新/动作通过单对象CAS提交，不在持有Navigation锁后再请求Trip；不把观测事实误认为正式计划修改 |
| 演示初始化/直接SQL | 普通正式编辑契约之外；不可拿它们当成产品修改入口。费用记录、缓存、对话历史和候选进度也不是正式活动写入 |

同一Trip的上述正式写入由父锁串行化，避免Activity/Run外键和接受候选之间的逆序。
非法跨Trip移动已在接触外部Trip的Day锁前拒绝。专项测试覆盖同Trip双向移动、删除
selected_activity外键引用活动、双Accept、编辑/Accept两个先后方向的实际PG等待。
这不等于证明所有SQL、跨Trip共享缓存、任意组合永不死锁；没有进行生产负载测试。

### 状态前后比较

formal_write.py按数据库回读结果比较所有Activity列（排除version/时间戳）、DayPlan列
（排除时间戳）、RouteLeg列（排除重建ID/calculated_at）。活动按身份映射，日期按ID，
路线按day/position稳定排序；JSON对象键排序，数组顺序保留。当前列类型中没有发现
导致漏判的序列化碰撞；时间、顺序、决定来源、名称、备注、路线模式/几何均参与。

不是持久化快照或同步系统。Trip.version仅在语义差异时推进；Activity原有no-op局部
版本行为保留。路线重算相同事实仅产生新ID/计算时间时不推进Trip版本。Accept代表
一次采用决定，仍按原有规则推进版本。当前比较的代价是每次编辑线性扫描Trip活动和
路线；适合当前短途规模，不能据此声称大行程性能已验证。

### 事务与外部请求

必须明确：目前仍有持锁外部I/O。手动add/delete/move/order/route调用原地图算法，
缓存未命中会在Trip行锁及原事务内等待地图；create_planning_run的可选语义解析可能
调用模型；绑定Trip的assistant_service也可能在Trip/Preferences锁内继续模型对话。
save_plan_revision(enrich_routes=True)也会持父锁补路线，正式Graph持久化当前传False。
Accept本身使用已存候选路线和当前数据库事实最终验证，没有新增模型/地图调用。

本轮保留这些安全但延长等待的边界，不临时释放锁后继续盲写，不引入跨事务工作流。
列为P2性能/可用性风险。第二阶段处理地图查询的读写分离；模型对话事务缩短应另行
约束和验证，不能把本轮结果解释为“无锁内网络请求”。

旧get_trip_preferences的缺失行自动提交行为在其他历史调用处仍存在，本轮仅封住
会直接破坏正式采用原子性的Accept入口。不把所有候选/对话命令在异常旧数据下的
事务原子性一并宣称通过；后续不得将这个读侧修复函数当成事务内无副作用的查询。
例如候选创建遇缺失Preferences仍可能提前提交，但其旧base_trip_version不能绕过
修正后的Accept版本检查。该边界需在相应候选/对话改动时单列，而非继续扩张本次修复。

## API与重试契约

- 请求体、路径、响应模型保留。手动写接口增加可选正整数X-Trip-Version。
- 携带版本：旧页面提交返回409；已有Activity version检查继续有效。
- 不携带版本：等待Trip锁期间正式版本改变会返回409；如果前一请求已经提交后才
  读取版本，后来的盲写只能被视为操作当前结果。无法识别所有延迟提交的旧意图。
- 当前Web/Android没有因此自动获得全局旧页面保护；本轮不修改它们。编辑后Trip
  版本推进可能令客户端缓存过时，下次有版本编辑需刷新，不能自动重放冲突请求。
- 重复Accept使用同一Revision返回200而不再应用；活动新增依赖既有地点去重，
  相同新增重复409；更新/移动保留活动版本，删除重复404。没有新增请求账本，
  不承诺原HTTP响应重放或任意请求exactly-once。响应丢失后先读取当前结果。

## 验收证据

使用新建容器roamsync-write-integration-pg（PostgreSQL17-alpine），tmpfs、仅loopback
随机端口，不挂生产卷。主测试库roamsync_test_write_protection；Promotion使用同容器
promotion_test；收藏单独使用同容器roamsync_test。所有模型/地图密钥清空，外部路线
使用确定性测试替身。PG行锁、FK、并发连接、提交/回滚是真实执行。

命令（PowerShell7，在本工作树）：

```powershell
./backend/scripts/run-write-integration-review.ps1 -Evidence focused-final
./backend/scripts/run-write-integration-review.ps1 -Full -Evidence windows-full
./backend/scripts/run-write-integration-review.ps1 -Favorites -Evidence favorites
```

证据目录：docs/evidence/write-integration-review/。原有阶段一证据继续留在write-protection/，
不冒充本轮重跑。review-red-missing.xml曾指向不存在的路径，其404没有证明作用；
只使用纠正到/execution/replan后的review-red-missing-corrected.xml作为回归证据。

| 本轮重新执行 | 结果 | JUnit证据 |
|---|---|---|
| 原27项 + 新增5项PG专项 | 32 passed，0 skipped；12.841s | focused-final.xml |
| Windows/Python3.14.3全量 | 1274 passed，1 skipped；101.272s | windows-full.xml |
| Linux/Python3.11.16全量 | 1274 passed，1 skipped；75.514s | linux-full.xml |
| 按要求库名补验收藏并发 | 1 passed，0 skipped；0.559s | favorites.xml |

全量唯一跳过仍是收藏测试的库名保护；它已在同一隔离容器的独立roamsync_test库
单独执行通过，不能把全量的skip直接写成pass。全量包括Planning Graph12项、
Planning Runs15项、Trip Execution9项、Activity Experience Recovery20项、
Navigation Sessions9项、Observation Ingestion8项、Navigation Start6项等；
没有新的失败。健康测试对隔离ASGI应用/live与/ready实际请求通过。
两项既有Starlette弃用警告保留，Windows额外有事件循环策略弃用提示。

这只是代码、确定性模型替身和数据库工程验收；没有真实模型、实时地图、浏览器
或Android新增体验验收。源文件hash、主仓库保留文件hash、测试计数、运行镜像ID
记录于verification.json。运行镜像只提供Python3.11依赖，app/tests/evals来自集成工作树
的只读挂载；生产镜像/容器不被重建或替换。

## 保留的独立缺陷与第二阶段输入

1. **P1：max_walking_minutes最终验证覆盖不完整。** 前轮focused-third.xml保存反例。
   planning_goals.py区分本次步行目标与历史标量，Graph的目标检查不能代替接受时
   对新约束的完整重验证。阻止宣称“所有步行硬限制已兑现”；后续真实规划验收必须
   单列步行目标的生成前后变更测试。不阻止正式写入隔离或路线查询/时间修改分离，
   本轮不改约束算法。
2. **P2：路线重算挤掉留白。** maps_service.recalculate_day_route从前项结束+路线时长
   推算未锁定后项开始；planner_repository._recalculate_schedule_from_saved_route也会
   压紧后续时间。前者有地图I/O，后者使用已保存路线，无网络也可能侵入留白。
3. **P2：长事务与旧客户端边界。** 见上文；不能通过自动重试或释放保护消除冲突。

第二阶段可依赖：父Trip写锁、语义版本推进、间接活动版本、旧候选409、Accept原子性
和幂等、Requirement独立版本以及本轮32项真实PG回归。第二阶段首先以路线查询不改变
活动时间/顺序/用户留白的失败回归切入，明确查询结果与主动时间调整的不同权限。
保存正式路线事实仍须遵守已有版本保护；异步查询返回必须检查版本，不得覆盖新编辑。
用户明确要求调整时间时才改变安排；需检查固定活动/预约、缺失路线和跨日情况，并为
失败及旧响应添加回滚/拒绝证据。不要提前引入混合精度表、前端、Android或Planner上下文。

## 有限架构验收说明

复用FastAPI参数/响应校验、Depends(get_session)、SQLAlchemy事务及PostgreSQL行锁。
本次自定义formal_write装饰器仅保护现有提交型命令，不是通用工作流或新业务层。
main.py承担HTTP与异常映射，planner_repository.py承担既有SQL/业务编辑，
plan_revision_service.py承担最终验证/采用；既有repository层混合响应组装的耦合不在本轮重构。
新增测试文件负责评审反例，脚本/证据只负责隔离复验，不具产品写权限。

全应用统一响应封装、分页、授权产品化、生产启动/日志/外部服务负载不在本轮验收范围。
没有401/403新契约，也不把本地单用户边界当成多用户安全。未验收项不记录为通过，
不生成全后端架构SSOT。本报告的READY只针对这一组可合并的写入保护改动。
