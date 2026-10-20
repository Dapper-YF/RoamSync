# RoamSync 完整闭环修复与集成验收（2026-10-20）

本报告针对隔离候选版本，不代表正式仓库已合并或已部署。最终判定与测试计数见文末。

## 基线与本轮修复

开始时主仓库HEAD为25a62cb；原开发分支干净，HEAD8c52664。本轮在同一开发工作树
建立codex/natural-assistant-closure-20261020，未复制或重做A—E。主仓库README.md、
web/nginx.conf与1856个未跟踪文件均保留；初次差异交集为空，见integration-preflight.json。

提交依赖：正式写保护评审1ce7e5d → A2f2def5 → B7468363 → C739ef56 → Ded6ea2d →
E38e2524 → 交付8c52664 → 本轮998a383、bca55f6、cb1f88b、0cad41d；最后的证据/报告提交另列。

根因并非一个多余的右括号：

1. assistant_service用Router的planning_request全文替代了原用户消息；重写的枚举、
   括号说明和日期变成了确定性解析器的权限与范围输入。
2. planning_intent_service的“保留…”正则捕获“）”，没有先检查是否有名称内容，
   就送进子串身份匹配并形成activity_not_found澄清。
3. 旧建议交接和当前正式安排是不同证据来源，不能继续让系统产生的改写冒充用户原话。

998a383：已采用、当前消息授权的灵活安排修改以原消息创建PlanningRun；Router改写只
作为消息诊断字段保存，不进入该次运行的用户请求。老客户端与显式建议交接路径保留。
活动引用进入匹配前去边界装饰、拒绝纯格式片段；真实未知名称仍澄清，真实代词歧义不
猜测。星期预约按真实日期、锁定状态和时段唯一定位；多个预约仍澄清。未改动日期从
修改范围中排除，日期不是一个虚构活动。留白交给原有安排约束检查。

bca55f6：未绑定Trip的新自然对话不再向Router列举未选择的历史Trip，防止创建请求
误用旧旅行；旧客户端历史选择行为不变。有限编辑的授权错误按422拒绝，而非500。
“玄武湖还是备选，不要排进去”进入已有受控修改，Web携带对应授权，不创建PlanningRun。

cb1f88b：展示候选活动已有的reason，让用户在采用前看到实际取舍；没有另加模型调用。
流式测试改用自己创建的会话ID，不再把“恢复最近会话”误当成空数据库。原有单消息、
流式事件顺序、只调用一次、重试幂等断言全部保留，没有清空历史数据来制造通过。

0cad41d：真实失败记录暴露终态仍无限轮询；先有web-polling-red失败，再停止明确
终态的定时器。Web最终195项通过，真实同Trip恢复六秒只查询一次Run，未改变Graph。

## 修复前后的证据

证据目录：docs/evidence/natural-assistant中的closure-*.xml，及
docs/evidence/natural-closure-20261020。

| 回归 | 修前 | 修后 |
|---|---|---|
| 原始完整请求经过错误Router改写 | closure-red：用户原话丢失 | closure-grounding/intent-final：原话、第二天范围、固定预约身份正确 |
| 纯括号、引号、列表片段 | 被当成未知活动 | 无虚构身份；带装饰真名和未知真名仍分别定位/澄清 |
| 星期预约、第一天别动 | 3项失败，closure-scope-red | 唯一预约定位；双预约澄清；只修改第二天 |
| 未选择旧Trip、错误操作授权 | 2项失败，closure-context-red | 18项通过，closure-context-green |
| 备选重申及Web授权 | PG和Web均失败 | closure-optional-green、web-optional-green通过 |
| 候选取舍可见 | web-reason-red失败 | web-reason-green通过 |

原失败全文保存在test_natural_handoff_closure.py，与2026-10-19浏览器输入相同。
撤销/放宽后不复活旧要求、跨天范围、晚到旧候选、失败回滚与重复Accept继续由已有
complex_requirement_intents、effective_requirements、formal_write及arrangement测试覆盖。
这不等于硬性max_walking_minutes最终Validator缺口已修复。

## 真实浏览器与模型：所有尝试都保留

模型为配置中的glm-5.3-flash，地图AMap，真实Edge/Chromium、API18019、Web3019和专用
live测试库。原模型代理失败的隔离直连设置沿用，未修改生产配置。预约只来自合成用户
陈述，地图只核实地点及路线，不是实际订票或开放时段保证。

| 记录（2026-10-20 UTC文件名） | 结果及分类 |
|---|---|
| natural-assistant/web-live-00-18-32-118Z | 原措辞、原轮次、同一Trip完整链通过，包含缩短停留、真实路线、Accept和恢复 |
| natural-closure/web-live-00-22-29-936Z | 创建请求错指未选择旧Trip，被422拒绝；之后补软件回归并修复 |
| natural-closure/web-live-00-27-16-895Z | 明确排程后Planner Provider连接失败，正式安排保留；外部可用性失败 |
| natural-closure/web-live-00-32-40-502Z | 创建阶段AMap超时502；之后独立可用性检查200/status1，未伪造POI |
| natural-closure/web-live-00-35-39-904Z | 候选采用与恢复完成，但旧浏览器断言过强，见下文 |
| natural-closure/web-live-00-41-01-109Z | 最终候选版Planner连接失败，未产生可采用方案；外部可用性失败 |

以上表格用简写，实际文件前缀为web-live-2026-10-20T；natural-closure目录全称为
natural-closure-20261020。最终再验记录在文末指定，不以多Trip分段拼接代替全链。

旧断言强制duration<110，但原话是“12:30以后”并非“必须12:30且必须先博物院”。
00-35轮实际保留总统府14—15点，使用AMap39分钟路线，博物院15:39开始、110分钟；
模型reason明确解释改到预约后以保留时长。late-start-accepted-counterexample.json是
旧测试预设方案的反例，不是Validator允许预约重叠的证据。没有改用户输入或Validator。

新的assert-natural-adjustment同时检查：博物院唯一、起点不早于12:30、停留5—110分钟、
固定预约时间/时长、真实非估算AMap路线、相邻结束+路线不晚于下一活动。缩短在前或
改到预约后都要满足这些检查。3项独立测试证明真实改序可通过、110分钟挤进预约前被
拒绝、估算路线被拒绝。原全链另检查采用前正式快照不变、首日留白及未排程决定/来源
不变、刷新恢复与390宽视口。不能删除这些检查来提高成功率。

same-trip-restored.json另用同一个已接受Trip验证了改序方案的持久化恢复、真实路线
数学、桌面/390手机操作及无横向溢出，附截图。它明确标记为同Trip恢复续验，不冒称
最后一轮从咨询开始的全链一次通过。00-41轮已经运行修正后的断言，但被模型网络
失败阻断，因此仍需未来同脚本完整复验，不用首次成功或续验替代此项。

有限真实服务回归：finite-live-d84a5309-b0cd-401e-b24f-02b5137632b9.json，6项通过。
文化咨询、比较、兴趣表达不创建Trip/Run；时长修改和取消是确定性服务，不冒称6次
模型成功；含糊“刚才那个”得到澄清且保存结果不变。逐项输入、输出、授权、时长、
运行轨迹和保存快照均在记录中。首轮探针误以latest_run_id判定新建Run、并误传编辑
授权；finite-live-regression.json保留。最终按当前消息run_id检查，真实500另经回归修复。

## 集成审查与工程边界

| 检查项 | 实际路径/证据 | 结论 |
|---|---|---|
| 分层与参数边界 | assistant_routes、ContextEnvelope → assistant_service → 原PlanningRun；arrangement_routes → arrangement_service → ORM | 沿用FastAPI/Pydantic和已有服务，无通用工作流 |
| 精确时间唯一来源 | TripArrangementItem有限字段/0037；schedule_item同事务创建Activity并关联 | 不维护第二套日程，未排程不补默认时长 |
| 身份、取消与转换 | write_item、cancel_activity_choices、bind_accepted_items；PG关系/转换测试 | 固定/已发生活动不能被简单取消；来源保留 |
| 候选最终安全门 | plan_revision_service Accept先Trip/Revision/Run，最终Validator及candidate_item_errors | 保留版本、约束和幂等，未采用不改正式结果 |
| 锁与回滚 | formal_write、测试错误注入/并发组合 | 复用已有锁顺序，没有新锁层；网络持锁风险另列 |
| 路线与留白 | GET route及route_time_separation，已有安排Validator | 查询不排时；复杂协调须采用候选 |
| 配置与运行 | 专用tmpfs PG、runtime脚本、health/ready | 不加载生产DB；只读Provider配置入内存 |
| HTTP合同 | 资源型JSON、Pydantic422、404、版本409；错误授权422回归 | 无新统一响应包装；不承诺所有500均有统一正文 |
| 身份认证 | 当前本地单所有者边界 | 未验收公网多用户401/403隔离，不能公开部署 |
| 可视化与写入 | NaturalAssistant版本化请求、409不重放、候选reason/路线展示 | 与对话指向同一结果，不另存用户决定 |

目录职责保持：app服务处理目标和事务；ORM/迁移持久化；tests验证；Web组件呈现与
显式授权；e2e只编排合成用户及验收；scripts只准备隔离环境。没有新中间件、数据库、
API系统或框架。架构技能用于这次定向审查，不把未覆盖公网身份验证的结果写成全景
BACKEND_ARCHITECTURE_SSOT，也不产生“商业级架构全部验收”的声明。

迁移复验migration.json：在独立roamsync_arrangement_migration_test执行0036→0037→
0036→0037，旧Trip及两天数据保持。仅空新表降级；填入事项后downgrade会删除数据，
这是必须备份/导出后决定的生产回退风险。本轮无生产迁移、回滚或数据删除。

## 性能、失败分类与未解决风险

小样本有限检查：文化咨询11307ms、地点比较10883ms、兴趣陈述66ms、简单时长80ms、
取消32ms、含糊澄清7819ms。简单编辑轨迹没有新Planner。30次一秒PG采样观察到最多
1个锁等待、最长活跃事务年龄10.49秒；这不是死锁证明，也不能解释为全流程无争用。
最终长链的请求时长、轮询量和Planner/路线阶段另由其requests及real-run-observations
记录。观察到的阶段数不等同于准确Provider计费请求数；缓存/重试必须分别看轨迹。
00-35轮记录39个API请求、12次Run/候选读取；两个Provider失败长链各约97次轮询，
因此补上终态停止。首次成功Run记录2次Planner、2次路线处理阶段，包含修复/缓存，
不能称为两次实际地图计费查询。计费级总数未独立采集，不报精确数。

| 级别 | 风险/限制 | 处理 |
|---|---|---|
| P1独立正确性缺陷 | max_walking_minutes最终验证不完整 | 本轮不承诺硬性步行上限；有此验收需求时先独立修复 |
| P2可用性 | 实际模型连接及AMap超时出现过 | 正式状态保留，失败留痕；有限成功不等于稳定成功率或SLA |
| P2并发延迟 | 绑定对话、部分旧编辑、候选保存的网络仍可能持锁 | 静态确认、采样留痕；后续定向移出I/O，不扩建异步平台 |
| P2信息边界 | 新地点网页研究Provider本轮未配；开放/预约未全面核验 | 不把未知当可用，不新增查询平台 |
| P2兼容性 | 旧无Trip版本请求不能识别所有延迟提交 | 新Web携带版本；原接口边界明确保留 |
| P2范围 | 单城市、日期明确1—3天；任意指代、跨城/日期未知和Android未新验收 | 不扩大本轮完成声明 |

## 最终验证、状态与合并前提

最终Windows：1335 passed、1 skipped（closure-windows-final.xml）；Linux隔离集成
工作树同样1335 passed、1 skipped（linux-review-full.xml）。Web195 passed、0 failed
（web-final-release.json），tsc/build通过；浏览器验收判定器另3项Node测试通过。
收藏专项独立库1 passed（closure-favorites.xml）。唯一skip仍为特定库名的收藏并发，
未运行时不算通过。Windows第一次全量与专项误并行使全库只读快照断言失败，证据
closure-windows-full.xml保留；串行通过后另发现旧流式测试复用会话，修正测试身份隔离
后最终全量通过，没有削弱其断言、清空其他会话或改生产恢复会话语义。

**总体PARTIAL，暂不标记READY FOR INTEGRATION。** 原始意图阻塞已修复，且原措辞的
同Trip完整浏览器链曾通过；当前工程回归及隔离集成候选可以评审。但最终版本的完整
自然链复验仍因真实Provider失败没有得到一次完整绿色记录。原链成功、修复代码、
真实局部采用、恢复续验、单元测试与最终产品验收是不同证据，不互相冒充。

已在独立E:/Study/RoamSync-natural-closure-review-20261020中从正式25a62cb快进整合到
cb1f88b，无提交冲突，随后追加0cad41d及证据提交；主仓库未提交路径及未跟踪路径与新增改动无重叠。Linux从该
隔离工作树运行，而不是直接在主仓库试合并。最终还会快进追加证据提交，代码不再变化。

下一步只需要在模型/地图连接可用后，重新执行同一e2e/natural-assistant-live.mjs；
无需再增加产品功能、业务对象、提示规则或降低Validator。只有该次全链和核心回归
满足GO后，才建议正式源以--ff-only整合这个提交链；执行前仍须重新核对HEAD和本地改动。

正式源始终E:/Study/RoamSync；本轮不合并其
分支，不部署、不迁移生产库。任何推荐合并均须保留原有未提交文件，先准备0037备份
及API/Web配套发布，并重新核对HEAD。开发/集成工作树不替代正式源码目录。
