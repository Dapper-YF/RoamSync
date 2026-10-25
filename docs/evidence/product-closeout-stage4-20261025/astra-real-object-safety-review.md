# 真实对象安全验收脚本静态复核

日期：2026-10-25。审查 verify_real_objects_stage4.py 与 restore_real_pending.py，并对照产品 accept_plan_revision 的实际写入顺序和数据库 session_factory。未执行脚本、数据库写入或 provider，未读取封存题。

初审结论：脚本有隔离基础，但尚不足以证明五项安全验收。随后按主代理授权修改两个外部脚本；下面保留初审发现，收紧结果见末尾。未执行数据库操作。

## 必须关闭的证明缺口

1. **rollback 未证明注入命中。** 只比较 after_fault 与 before，未断言 fail 钩子到达，也未验证 fault_result 是指定注入异常。提前校验/provider错误、随后重试成功也能形成假通过。应设置命中计数、专用异常并断言；必要时在故障点 flush 和读取事务内 delta，证明确实发生写后回滚。当前钩子位于活动 flush 后，但 RouteLeg 为 add 后未显式 flush，不能宣称是在路由 SQL 写后故障。
2. **fixed 未证明固定保护是失败原因。** validate_candidate_plan 的任意 invalid 即通过；缺少修改前 valid 以及固定保护特定错误码断言。当前按 scheduled_time 取首活动，未确保它属于候选实际修改目标。应从真实 revision delta 选择确实被修改的活动，并验证相应保护错误及状态不变。
3. **真实快照、模板和冻结未形成闭环。** restore 比较输入与新库，但不验证输入文件/来源的冻结期望哈希；verify 直接从固定模板克隆，却未比较模板与冻结快照/回执状态。应将 snapshot、restore receipt、runner、helper 的 SHA 固定，验证模板与各克隆的起始业务/Run/Revision内容全等，且 pending revision 唯一或使用冻结的明确 ID。初审时 safety-freeze.json 尚不存在，不能声称已核验其最终内容。
4. **并发只验证结果码组合。** 缺少按胜者断言最终精确 delta，不能据此排除失败方部分生效。首活动不一定被 Accept 修改；若其 Activity.version 未增加，两请求都成功可能是合法串行结果，却会误判失败。应选确实冲突的共同对象，或表单携带实际共享 Trip 版本；并记录锁等待、结果及与胜者相符的完整状态。

## 已确认的边界

- DB 目的地硬编码为本地 15435、agent_b_test，名称限制为隔离测试库，拒绝复用已有库；数据库名采用 psycopg Identifier。
- 每例 session_factory.configure 指向对应克隆 engine，API get_session 使用同一 factory；未发现正式库写入路径。官方 .env 只读取 provider设置，数据库URL在导入产品前已覆盖。
- source hash 与首次加载 frozen 比较，逐例前后检查；HEAD 当前仅启动时核对，runner/helper 本身未被当前脚本验证。
- state 涵盖 Trip、DayPlan、Activity、TripArrangementItem、RouteLeg、TripPreferences、PlanRevision、PlanningRun；不能笼统说所有正式表。Accept 还可能涉及 execution/navigation/disruption 表，当前新模板若为空应明确验证这个前提或扩大状态比较。
- duplicate 同时检查两次 accepted 与全量所列状态相等，能支持这些表上的重复采用幂等；stale 在明确表单改动后要求 StalePlanningRunError 和状态不变，证明范围比 fixed 的附加原因断言更完整。
- 所有判断仍为运行前静态审查，不是测试通过结论或产品 GO。

## 外部脚本收紧结果

1. restore 要求显式 snapshot SHA、产品 commit/app SHA；验证捕获元数据一致、pending 唯一，新库内容与捕获内容逐行全等。独占创建 receipt，记录输入文件 SHA、helper SHA 和内容 SHA。
2. 最终 safety-freeze 同时绑定 snapshot、receipt、runner、helper、commit/app SHA。runner 核验 receipt 来源及内容摘要，再只读逐行比对模板和每个克隆；逐例检查所有冻结文件以及首次 manifest 身份不变。
3. rollback 使用 InjectedAfterWrites 专用异常、命中计数、故障点 flush 和事务内全表快照，断言目标活动确已改变；存在候选路由时还要求 route delta 与数量。只有专用故障后所有映射表完全回滚、随后正常接受成功才通过。
4. 每例从真实候选选取确有地点/日期/时间/时长/费用变化的未锁定既有活动，要求当前候选 validation valid。fixed 要求锁定后出现 execution_activity_changed 且 details.activity_id 精确对应目标，再比较状态未变。
5. 并发请求携带共享 X-Trip-Version，保留两个实际锁等待者证据。Accept 胜出时记录其生产 commit=False 流程 flush 后的完整事务状态，再提交；最终全表状态必须与该事务快照完全相等，表单 note 未生效。表单胜出时除目标 note、目标/Trip 版本各加一及其 updated_at 外，所有映射表逐字段不变。时间戳仅允许这两个既定对象更新，要求不倒退。
6. 状态比较扩大到 Base.metadata 全部映射表；捕获之外的表必须初始为空，避免把未捕获执行/导航状态隐含当作已验证。异常保存 passed=false 和失败类别，禁止 Python -O 关闭断言。

两脚本以 compile(source, ..., 'exec') 完成纯语法检查，未 import/运行其顶层代码，未创建库、恢复数据、执行模型或验收。尚未通过运行验证。

## 主代理运行前须提供

先冻结真实捕获快照（tables 含 trips/source_records/place_candidates/day_plans/trip_preferences/activities/route_legs/trip_arrangement_items/planning_runs/plan_revisions；assistant_sessions 可存在但不复制）。顶层必须包含 git_commit 与 app_sha256，且恰好一个 pending revision；候选须确实修改至少一个未锁定 planned 活动。不能为满足前提构造或改写候选。若前提不满足，应获取另一个真实开发链路对象并说明来源。

先运行 restore，必填参数：--snapshot、--database roamsync_agent_b3_stage4_safety_template_test、--snapshot-sha256、--product-commit、--app-sha256、--receipt（全新路径）。restore receipt 生成后再制作最终 safety-freeze.json，避免 receipt 与 manifest 循环依赖。

最终 safety-freeze.json 必填字段：

- product_commit：当前产品完整 commit。
- app_sha256：按 runner app_sha 算法计算的 backend/app 所有 Python 文件摘要。
- snapshot_path、snapshot_sha256：真实捕获 JSON 绝对路径和完整文件 SHA256。
- restore_receipt_path、restore_receipt_sha256：restore 回执绝对路径和完整文件 SHA256。
- runner_sha256：最终 verify_real_objects_stage4.py 完整文件 SHA256。
- restore_helper_sha256：最终 restore_real_pending.py 完整文件 SHA256，必须与回执一致。
- revision_id：捕获中唯一 pending revision 的 UUID 字符串。
- snapshot_provenance：真实浏览器/模型/地图运行、捕获时间及来源证据说明。

应在最后一次脚本修改后才生成 freeze；执行前模板与五个目标库名固定，任何目标库已存在都会拒绝。此脚本不是封存20轮 runner，也不应重用封存数据库。

边界：完整状态断言只覆盖 Base.metadata 映射表，未声明外部 checkpoint/content schema 的全库无副作用。fixed 额外 validation 是直接验证当前候选的保护错误；真实采用仍另外经过生产 accept 校验。精确表单并发断言刻意严格，额外合法业务副作用也会导致验收失败而非被静默忽略。
