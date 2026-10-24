# RoamSync 产品转型统一缺口审计与分批收尾

日期：2026-10-24（Asia/Shanghai）。本报告区分源码事实、历史测量、本轮测量和未验收。
**初始产品结论 NO-GO；不批准生产部署。** 工程通过不代替用户目标达成。

## 1. 正式基线、并发边界与复用

- 开始时正式 `E:/Study/RoamSync` 为 `6b298ca`，另一对话仍在整合；本线程仅只读审计。
- 等“审查并改进 RoamSync Agent”完成整合回执后，正式冻结为
  `ea3ba833e6a77122c08c1c9327c18a346e3c48ef`，产品整合 `d37da85`，测试夹具修正 `f7fc455`。
- 由该正式 HEAD 建立 `E:/Study/RoamSync-product-closeout-20261024`、
  `codex/product-closeout-20261024`。本批不写正式工作树，不重复分支合并，不处理既有dirty文件。
- 正式 A/C 产品 `89b81e8`、A 最后审查 `a1e5946`、B 产品 `3f98303`/测试 `b393bfd`/
  交付 `f036d0a`已进入正式祖先；C `e102205`/`ba143a2`/`207c9b7`本已包含，不重复开发。
- 整合测量：后端主套1816、专库38；Web265、typecheck/正式标志build通过。
  仅引用 `docs/evidence/source-integration-20261024/validation.json`，不冒称本批重跑结果。
- 正式服务实时核对：Web/API/Worker/PG均退出，3000没有运行；没有“当前新版已上线”的结论。
  用户数据卷、正式 `.env` 和历史评测均保留。新真实测试只用新建synthetic测试库/独立端口。
- 原4个本地修改和2015个未跟踪文件的保全由整合任务记录；合入重叠文件恢复原始字节后部分
  tracked呈dirty，属于保全，不在本批覆盖。整合报告：`OFFICIAL_SOURCE_INTEGRATION_20261024.md`。

### 现有模块职责（VERIFIED 源码）

|模块|实际职责/事实来源|保留的边界|
|---|---|---|
|AI Assistant|`assistant_turn.py`会话快照/语义选择/恢复/持久化；`assistant_capabilities.py`咨询与读任务|单一语义决策；输入上下文不赋予正式写权限|
|Companion|`companion_runtime.py`、`companion_information.py`知识/证据/解释|普通咨询不创建Trip；不编造原始安排理由|
|Planner|`planning_graph_runtime.py`、`planning_graph.py`、`planning_run_repository.py`|原Graph/Validator/Revision/Accept继续拥有正式安排写入|
|未采用候选|`drafts/`、`conversation_candidate/`、`draft_promotion/`严格v2|生成不创建壳Trip；同Draft修改；展示hash/版本绑定；原子采用|
|正式行程|`database.py`既有Trip/Day/Activity/Route/ArrangementItem；`plan_revision_service.py`|正式更改必须版本校验/Validator/Accept，不让模型直接写库|
|条件|`assistant_memory.py`、`requirements.py`、`assistant_context.py`|当前有效值/撤销、来源quote/message、trip/topic/destination/personal范围|
|保存态读取|`saved_trip_reads.py`同一短RR READ ONLY快照/coverage/selected|独立限额2连接，5秒准入；不从调用者业务池嵌套借连接；不是公网所有权认证|
|图片/展示|`place_content/images.py`、`conversation_candidate/presentation.py`、Handbook|真实POI+provider+坐标关联审核Commons；相同PreparedPlan派生聊天与正式对象|

## 2. 去重后的统一清单

状态：**R**已实现且有相应真实证据；**T**只有工程证据；**U**真实模型不稳定；
**P**部分完成且有缺陷；**N**未实现；**F**明确失败。R仅适用于列出的场景，不表示普遍通过。

|ID/优先级|用户需求/收益|状态|实际源码|已有证据与剩余工作|
|---|---|---|---|---|
|01/P1|普通景点咨询直接回答|U|assistant_capabilities.py / companion_provider.py|P0/P1历史真实咨询；需新南京案例，不能套创建流程|
|02/P1|地点比较后继续问位置/玩法/同日|F|assistant_capabilities.py validate_decision/read_tasks|A fresh-chain-final-5漏复合任务；存在泛化澄清，需同对象多目标验收|
|03/P1|条件新增/修改/撤销不丢失|P|assistant_memory.py / requirements.py|B2条件回归、P1真实更正/刷新；跨南京话题回成都及同行主体仍未充分验收|
|04/P1|不重复问已有城市/日期|P|assistant_turn.py / assistant_operation.py|有效条件已投影；复杂作用范围与selector遗漏仍可能失败|
|05/P1|保存态第三天/同名/选中活动|U|saved_trip_reads.py / companion_context.py|B3最终公开5/6，读取值/coverage改善；第2轮schema失败|
|06/P1|原安排理由不编造|R|companion_context.py / saved_plan_notes.py|B3真实缺理由明确告知；版本/覆盖有限，不代表所有历史数据都有理由|
|07/P1|严格协议失败有界恢复|F→本批修复候选|assistant_capabilities.py|原B3多余trip字段失败；只恢复已有保存态纯读，其他协议错误仍拒绝|
|08/P1|要求有事实支持而非工具调用成功|P|assistant_practical.py / companion_evidence_quality.py|有参考价格/菜单缺口/审核断言门；未形成全链四状态支持投影|
|09/P1|少走路包含园内/接驳负担|F|assistant_practical.py walking_followup / validator.py|路段硬上限已核对，不证明园内/坡阶/行动适配；旧无证据保证必须重验|
|10/P1|忌口需实际菜品/配料支持|F|assistant_research.py / companion_answer_reliability.py|没有逐店菜单核验；免责声明可掩盖其他保证的已知漏洞本批封闭，非通用解法|
|11/P1|预算参考不等于最终账单|P|assistant_practical.py / draft_promotion/preparation.py|口径兼容算术已复用；硬预算未知会阻断，缺全消费证据|
|12/P1|POI身份真实且歧义可恢复|U|place_content/provider.py / draft_promotion/preparation.py|A同题after-8两真实POI成功；fresh链仍有身份/模型/provider失败，需重验原问题|
|13/P1|真实路线失败不抹掉其他答案|T|assistant_capabilities.py route_answer/answer_with_capabilities|P0复合失败保留结果；B3合成路线失败保留第三天，非真实provider故障验收|
|14/P1|实际候选地点/时间/午餐/路线|R局部/U新链|drafts/contracts.py / conversation_candidate/service.py|A真实候选1133m/16min；4次有效fresh链失败，不能借局部成功当完整黄金路径|
|15/P1|候选局部延长保留其他条件|R局部|conversation_candidate/commands.py / drafts/timing.py|A同Draft park120→150、street180→150、午餐60；仅所测duration修改|
|16/P1|交换顺序/只改第2天|P|conversation_candidate/commands.py / planning_intent_service.py|v2候选局部patch目前主要duration；更广局部编辑/多天保护需补验，禁止声称全支持|
|17/P1|采用指向用户看过的版本|T+R局部|binding.py / draft_promotion/atomic.py|版本/hash/过期/并发/回滚工程证据；A真实一次采用，不代表新集成fresh链|
|18/P1|“继续讨论”不Reject|R局部|ConversationCandidate.tsx / HandbookJourney.tsx|A/C UI真实回退保留；用户明确adopt才写正式|
|19/P1|P2聊天介绍候选而非空确认|R局部|ConversationCandidate.tsx / presentation.py|已有真实两站图文与局部改候选；旧metadata路径仍说明未生成，需新链不触发P3|
|20/P2|P1我的安排完整时间轴|R局部|HandbookJourney.tsx / JourneyReview.tsx|A 1440/390/320实绘照片和时间轴；不是新集成截图|
|21/P1|真实照片与POI一致且有许可|R有限覆盖|place_content/images.py / reviewed_images.json|13原片/26变体审核、宽窄CC0；范围有限，缺图降文字；普通聊天topic图不能当精确POI图|
|22/P1|聊天/正式页面同源与刷新|R局部|presentation.py / draft_promotion/materialize.py / arrangementApi.ts|A采用/刷新/同Trip修改成功一次；本批新黄金路径待验|
|23/P1|已保存行程自然改时/局部保护|P|planning_intent_service.py / formal_write.py|保护预约/锁定/执行；scalar时长仍可能映射replan，旧assistant_arrangement入口需单列审计|
|24/P1|网络I/O不持业务长事务|T|planning_graph_runtime.py / draft_promotion/preparation.py|A2快照/CAS；test_graph_network_transactions.py等，需HTTP取消全链补验|
|25/P1|Worker身份/接管/陈旧写阻断|T|planning_claim.py / agent_worker.py|test_worker_ownership.py与A2真实PG；不重复建设租约机制|
|26/P1|澄清答案和恢复原子|T|planning_graph.py / planning_run_repository.py|A2澄清专项；不借旧checkpoint完成证明任意新会话成功|
|27/P1|并发读取与资源释放|T|saved_trip_reads.py|B3真实PG有限池占满/取消/MVCC反例；多进程总连接与长期负载未验|
|28/P0公网前|用户/Trip完整访问隔离|F|repository.py list_trips / integration_runtime.py|目前本机集成token，不是用户认证/归属矩阵；不能公网发布|
|29/P1|Web/API/Worker同版本|F运行层|compose.yaml / scripts/start-roamsync.ps1|正式服务停止；本批只起隔离环境，不生产部署，不以源码合入当运行升级|
|30/P1|动态重规划必要性和差异|P|trip_execution_service.py / experience_replanning_service.py|既有执行/恢复及正式写保护测试；新产品场景F仍需真实模型链|
|31/P1|独立未见多轮质量评测|N本批待验|backend/evals / 本批外部private-eval|不复用B3公开6轮或C旧题，不挑重采样最优结果|

**删除的重复建设任务**：第二套候选模型、另建长期记忆、重建正式Accept、重建已保存行程快照、
重写照片管线、再造Worker租约、全新规划器/额外审计Agent流水线。现有实现保留，只补已证实缺口。

## 3. 最小开发顺序与分批门槛

1. 本批：封闭保存态selector协议波动的受限恢复及免责声明断言绕过；相关授权/取消/超时反例。
2. 冻结源码：全套隔离PG工程回归；真实A/B/C黄金路径和图片/路线；独立新题只执行一次并保留失败。
3. 依失败分批：复合读目标/指代保留、真实POI生成阻断；候选顺序和多天局部修改；要求支持投影。
4. 新完整连续链、版本冲突与HTTP取消；再独立Astra复核。最终GO需每一关键用户目标均完成。
5. 公网身份隔离另为上线硬门。生产部署不在本次授权，正式区合入也须说明源码与验收范围。

要求支持的最小后续设计：复用现有`requirement_records`和`read_tools.decision_support`，按
`requirement_ref/entity_ref/fact_kind/scope/source_id/retrieved_at/valid_until/status`投影。
status为supported/insufficient/unknown/conflict；仅同对象、同事实类型、同口径、在有效期的证据
能支持要求。路段时长只能支持路段耗时；人均参考只能初筛；缺菜单不能证明忌口；规划分配的
结束时钟只证明候选算术，不证明营业/排队/现场可行。本批不引入未实现的四状态成功声明。

## 4. 后端架构审计（静态，不创建通过SSOT）

|规则项|规则来源/路径|验证方式/实际事实|结论|
|---|---|---|---|
|请求分层|AGENT_ARCHITECTURE.md；main.py / repository.py / database.py|FastAPI路由、DTO、SQLAlchemy；部分main直接调用repository，非所有业务都有独立service|部分|
|DI/事务|database.get_session / assistant_turn.py|Depends短session；planning snapshot提交后外部I/O；独立读取RR|源码确认，运行待本批|
|响应契约|schemas.py / main.py exception_handler|DTO成功对象，422 detail、冲突detail对象；没有统一全局envelope/分页|不把现状冒称全局统一|
|参数/异常|Pydantic / FastAPI HTTPException|参数校验框架原生；部分领域异常映射422/409，无完整系统异常统一层|部分|
|访问控制|integration_runtime.py / repository.list_trips|本机token与合成owner；全Trip列表没有用户过滤|公网阻断|
|配置/日志|config.py / assistant_reliability.py|Pydantic Settings；execution_summary允许字段诊断，无原文provider日志|静态确认；新修复不记录私密输出|
|健康/DB|main.py /health/live、/health/ready|ready Depends(session)执行SELECT1，失败503|本批启动后测量|
|路由/中间件|main.py include_router / integration_runtime.py|沿用assistant/arrangement/content路由，不为本批增加全局包装层|源码确认|

### 目录责任

|路径|职责/以后放什么|禁止|来源|
|---|---|---|---|
|backend/app/*routes.py、main.py|入参/响应和领域错误映射|模型直接提交正式安排；把网络重试隐藏成成功|FastAPI惯例+业务|
|backend/app/assistant*、companion*|有范围的语义/只读/证据与呈现|根据网页授予写权、猜用户所有权|业务|
|backend/app/planning*、draft_promotion/|已有规划、验证、事务、CAS|越过Validator/Accept；持网络长事务|业务|
|backend/app/*repository.py、database.py|SQL/ORM与版本锁|生成用户回答、HTTP语义包装|SQLAlchemy惯例+业务|
|backend/app/place_content/|canonical地点、图片许可及体验来源|错地点照片、生成图冒充实景|业务|
|backend/tests、evals|隔离回归/明确质量测量|生产库、覆盖历史失败、把Mock当真实验收|业务|

代表路径`GET /api/v1/trips`：main.py路由→Depends(get_session)→repository.list_trips→
AsyncSession.scalars(select(Trip))→TripResponse。缺少用户filter和分页；小读端点不强加无收益service。
`GET /health/ready`直接SQL SELECT1属于健康探针，不是领域业务绕层。
复用FastAPI routing/DI/validation/exception hooks、SQLAlchemy sessions/MVCC、Alembic migration。
自定义Candidate绑定/hash解决用户所见版本、planning_claim解决Worker身份、saved_trip_reads解决
一致性/连接预算、assistant_reliability解决请求总预算；均有实际调用，不新添重复wrapper。

运行证据包：依赖`backend/pyproject.toml`/uv.lock、Web package.json/pnpm-lock.yaml；隔离工程命令
`python scripts/run-isolated-tests.py --output <新目录>`，拒绝正式.env、正式卷和宿主PG端口。
生产启动命令仅记录`scripts/start-roamsync.ps1`，本批不执行。
本批运行命令、端口、健康/SQL、响应样例与错误日志写入外部evidence/runtime及最终证据索引。
架构关键访问隔离未通过，因此**不生成/更新BACKEND_ARCHITECTURE_SSOT.md，不提交通过架构基线**。

## 5. 测量规则、历史和本批证据

- C独立密封严格2/20（有效2/19），保留取证无效记录；不读取旧私有题调参。
- B3公开开发最终5/6；中间6/6与最终schema失败同时保留，不替换最终结果。
- B定向254、正式整合1816+38/Web265只证明各自测试范围。
- A已有真实局部成功和4次有效fresh失败同时保留；runner异常final-3单列无效。
- 本批定向首轮58通过/2测试错误（冻结ContextEnvelope错误赋值、过短deadline的调度假设），
  修正测试后111通过。未修改产品断言迎合失败；完整工具输出留在本会话，后续XML/log存外部目录。
- 外部证据根`E:/Study/RoamSync-product-closeout-evidence-20261024`；任何新输出不得覆盖旧文件。
- 当前本批实测及最终结论待追加；没有测试或没有真实服务的项目保持未验收。

## 6. 本批交付状态

审计已建立、两个针对缺陷的修复正在验证。尚未合入正式区、尚未部署；黄金路径、独立题和最终
Astra复核未完成前不标记整体完成。最终必须列明用户目标失败、候选/保存状态、图片身份/路线原文，
按GO/PARTIAL/NO-GO判定；真实用户目标未完成即业务失败，即使安全拒绝正确。
