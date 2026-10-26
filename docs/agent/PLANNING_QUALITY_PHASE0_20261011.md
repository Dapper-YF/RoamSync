# RoamSync 规划决策质量 Phase 0 — 2026-10-11

状态：**工程评测入口可用；运行版本未对齐；真实模型质量评测被外部 Provider 阻塞。**

本轮新增 eval、合成场景、评测测试及报告，未修改业务 app、迁移、前端、Android、生产配置或生产 Trip。保留工作树原有改动；没有部署、Git 切换/提交/清理、Agent、向量库或 RAG 语料扩充。临时 PostgreSQL 均已清理。Phase 0 到此停止，不进入 Phase 1。

## 1. 真实版本核查与标准基线建议

证据目录：`backend/evals/results/planning_quality_phase0_20261011/`。完整文件哈希、函数变化和代码 diff 见 `version_close.json`；测试执行时的绑定为 `version_bound.json`，此前快照也保留。收尾发现并核对了同日另项 Companion 验收，未将旧报告当作最近验收。

| 对象 | 实测结果 | 结论 |
|---|---|---|
| 当前工作树 | HEAD `0b5010fe5a7b06dcec1ab7b159b5b337244247ae`；分支 `codex/roamsync-demo-release-20261007`；有既存改动和未跟踪文件 | HEAD 不能代表实际源码，必须绑定 manifest |
| API | 镜像 `sha256:60723c02c240875e3956744440ab19ea609dcf8ca31b6668a00845b57c2ef7a5`，容器 `0a91a3adc7c6`；10-01 创建，10-11 启动 | 不是 10-08 的独立验收应用源码 |
| Worker | 镜像 ID 前缀 `5a219e84f4a6`（完整 ID 见 JSON），容器 `e15e78ade495`；10-01 创建，10-11 启动 | 应用源码与 API 同一旧版本；未部署本轮代码 |
| 当前 vs 运行 | API、Worker 各 **21 个应用文件不同/缺失**；运行内盘点 94 个 `.py/.json`，无源码挂载 | 会影响候选修改、执行保护、Companion 行为与来源处理 |
| 最近按时间的独立验收 | 10-11 Companion 策略验收；HEAD同当前，dirty tree；原始日志891 passed/2 warnings/66.31s，独立Linux/Python3.11/空PG17迁移0034 | verification仅绑定13个选定文件，且当前companion_provider.py、companion_knowledge_strategy.py共2项不匹配；缺完整app/tests manifest，不能宣称整个当前源码绑定891项 |
| 最近完整绑定的干净参照 | 应用 commit `322f55334d16e8cacec60e5e6c126d61cfcca122`；真实目录 `E:\Study\RoamSync-planner-reliability-final-20261008` 存在；HEAD `54b8888754448615e9310bc20ba085349ffc9c4f` 为文档 checkpoint | 独立检出 app/tests 与保存 manifest **0 不匹配** |
| 当前 vs 干净参照 | 11 个 app 文件不同，加既存 Companion 测试、本轮 eval 测试和两个上下文/意图测试差异 | 863项干净参照结果不可移植成当前工作树全量通过 |

10-08干净参照的原始 XML `candidate322f553_clean_full_confirm.xml` 为 863 项/0 failures/errors/skips。首次全量的 1 个导航失败也被保留，原始时序未记录，不能宣称波动消除。该版本真实 Provider 门禁失败与本轮新失败是两次独立观察，均不能替代质量评测。10-11最近验收原始证据为 `companion_knowledge_strategy_20261011/verification.json` 和 `backend_final.log`；其891项属另项回归记录，本轮没有重跑全量。另有正在生成的 `companion_real_quality_20261011` 对话评测产物，不是本轮Planner四组对照或完整源码验收，不移植其质量结论。

**建议标准基线**：以有干净检出和完整绑定的 `322f553` 作为 Planning/Validator 核心参照；当前既存 Companion 策略改动作为显式 overlay，其891项回归证据已存在，但须补完整源码绑定。本轮实际结果绑定当前工作树 manifest，而不声称已经切换到322或当前全量891通过。本轮不覆盖工作区、不合并、不部署；后续选择开发基线后，应在独立检出中引入本 eval 并重跑，同一 manifest 绑定源码、测试、镜像和运行配置。当前树还缺322的两个上下文/意图修复，直接把dirty HEAD定为标准会丢失已验收保护。

收尾源码一致性限制：测试时 `version_bound.json` manifest=`52087a968591f581ad84a970055853d0734603ba510dda938ea83c8e2c35eb3c`；收尾 `version_close.json` manifest=`5701e0c5d4245459f8be2314ae7e60c39e3c1fc757bd8847f4aa557df1e41347`。app/tests唯一差异为另项工作更新的 `companion_provider.py`。最终Mock批次自身无源码漂移，但其结果属于测试时快照；收尾树不能继承全部测试声明。收尾另项任务的 `roamsync-real-quality-test-*` 容器仍在运行，不属于本轮清理范围。

以下是 21 个运行差异文件的行为分类；每项具体 diff 和变化函数均保存于版本 JSON：

| 文件（backend/app/ 下） | 行为影响 |
|---|---|
| assistant_service.py | 绑定待确认初始候选，局部编辑不再无条件扩成全程 |
| candidate_edit.py（运行缺失） | 待确认候选基底、跨日期保留和版本检查 |
| openai_planner.py | 把候选编辑上下文和保留域传给原 Planner，保留非目标日期 |
| planning_graph.py | 加载候选基底；扩展执行保护检查；候选预算差额记录 |
| planning_run_repository.py | 持久化候选编辑边界及相关验证 |
| planning_intent_service.py | 日期/旅行设定与真实活动引用的区分；当前还缺独立版本的修复 |
| plan_revision_service.py | 候选编辑范围、接受前重验、执行不可变活动检查 |
| candidate_route_service.py | 路线计算纳入执行保护活动 |
| navigation/execution_context.py | 判断何时必须应用执行不变量 |
| planning_explanation.py | 预算差额计算包含被保留的正式活动 |
| companion_context.py | 既存 Companion 上下文策略变化 |
| companion_contracts.py | 既存知识策略/解释元数据契约变化 |
| companion_evidence_quality.py（运行缺失） | 既存证据质量评价辅助模块 |
| companion_graph.py | 既存知识策略选择与证据观察逻辑 |
| companion_information.py | 知识需要策略和目的地处理变化；也含旧/新城市边界差异 |
| companion_provider.py | 既存模型知识策略/依据元数据行为变化 |
| companion_runtime.py | 既存知识策略配置传递 |
| config.py | 新 Companion 策略配置；不代表运行镜像具有该能力 |
| travel_goal_router.py | 既存 Companion 路由规则变化 |
| travel_facts/official_collector.py（运行缺失） | 官方来源采集基础设施；不能据此推断 Planner 已使用 |
| travel_facts/source_review.py（运行缺失） | 来源审查基础设施；不能据此推断正式规划已核验动态事实 |

重点一致项：`companion_state.py` / PlanningBrief、`decision_memory.py`、`destination_research.py`、`external_facts.py` / Planning 天气采集、`planning_context.py` 与运行文件哈希一致。功能缺口因此不能仅归因于这几项部署落后。当前 `decision_context.py` 与 322 不同，是独立验收的跨日执行上下文修复差异。

有效配置核查（不记录密钥值）：本地/API/Worker 均为 GLM `glm-5.3-flash`、Planner high、90 秒、SDK retries=0、Ledger shadow、Open-Meteo、allow_map_estimates=false；Intent max。Worker 显式 Research low；API 未设置该变量，源码默认 low，因此此处未发现有效行为差异。当前本地 Companion 策略为 selective，旧运行源码没有新增策略契约，不能用配置名称推断功能一致。

## 2. 安全、可复现的评测入口

实现位于 `backend/evals/planning_quality/`，命令和边界见其中 `README.md`。

复用链路：原 `build_planner_input` → `PlannerEntityBindings` → `OpenAIResponsesPlanner.generate`/原解析 → `build_planning_graph` → 原路线富集 → 原 Validator/Goals/Ledger → `save_plan_revision` → approval interrupt。使用现有 `BenchmarkTrace`，没有复制第二套 Planner 或校验器。

关键定位（当前工作树）：`assistant_service.py:310` 构建Brief，`:358` 进入Assistant路由上下文；`openai_planner.py:322` 投影正式Planner输入，`:169` 调用原模型；`planning_graph.py:136` 编排，`:704` 收集天气/搜索；`destination_research.py:62` 投影搜索结果、`:99` 使用来源；`decision_context.py:13` 汇集决策上下文；`decision_ledger.py:81` 校验依据；`planning_run_repository.py:173` 保存候选Revision。这些位置与eval捕获共同证明数据路径，不能仅凭函数存在推断选址有效。

正式 Graph 会持久化 Run/Revision，无法直接当作生产只读函数。最小解决方案是 **eval 专属隔离包装**，本轮不改业务 composition root：

- `isolate.py` 创建唯一名称/ownership label 的 PostgreSQL17 容器，随机 loopback 端口，tmpfs 数据目录，不挂生产卷、不加入生产 Compose 网络、不启动 API/Worker/Web。
- 只给空隔离 DB 执行现有迁移到 `20260924_0034`，创建 eval ownership marker。`run.py` 在导入 app.database 前校验 DB/user、端口、隔离标志、业务/Checkpoint URL 和 ownership marker；生产 54329 等端口被拒绝。
- 每例有独立合成 Trip、候选、Run；InMemorySaver 存 Graph checkpoint。到 pending Revision/approval 停止，不执行 Accept/Reject。隔离正式 Trip/version/day/activity/route 指纹必须不变。
- 网络 POI/天气/检索/路线替换发生在 eval 进程的测试端口，标注 synthetic。Validator/Graph/Planner 的规则、解析和确认边界未修改。不能把 synthetic route 当真实 AMap 验收。
- 清理前核对精确容器 ID/name/owner，仅删除本轮资源；`.resource.json` 保存退出和清理结果。原有四个服务未被重建、重启或替换。进程强杀可能留资源，应按库存和 owner 检查，禁止批量清理。

## 3. 四组注册对照与执行结果

`fixtures.json` 有 4 对/8 个变体。地点、天气、活动资讯均为明确标注的合成数据，不是杭州真实事实；标签用于评测，不成为新的业务约束。

| 组 | 唯一条件 | 保持不变 | 预期 |
|---|---|---|---|
| 文化/购物 | interest_categories | 城市、日期、预算、候选池、路线、请求 | 选中类别体现兴趣，理由能追到用户目标 |
| 晴/雨 | 一组一致的小时预报（降雨概率＋天气码） | 其他条件 | 不适宜露天体验减少，保留可行目标 |
| 节庆/非节庆 | 旅行日期（11-01/11-08） | 同一活动11-01有效窗口、其他条件 | 日期外不声称活动举行；常规使用场所不是自动错误 |
| 有效/过期资讯 | 资讯时间封套（发布时间＋有效区间） | 标题/正文/URL、旅行日期、其他条件 | 过期活动不能成为当前活动依据 |

天气的两个字段是一个天气条件，资讯的日期组是一个有效性条件；本评测不估计其中单个时间字段的独立因果效应。UUID 仅用于隔离行身份，比较使用固定 fixture key。

| 层次 | 执行结果 | 可得结论 |
|---|---|---|
| Deterministic | 8 例完成；四组 Planner 输入均变化；固定候选池排序均不变 | 证明输入可见，不证明模型使用 |
| 查询/研究投影 | 兴趣对会改变 broad search；日期/天气/资讯有效性不改变查询；有效/过期元数据投影到 Research 时均变成相同 title/url/content | 必须记录所有 broad/focused 查询；只看最后 focused query 会漏掉兴趣差异 |
| Mock 原 Graph 正对照 | 初版固定 museum/mall，8/8 pending＋Validator valid＋formal fingerprint不变 | 原流程接通，不计智能得分 |
| Mock 原 Graph 负对照（最终） | 固定 park/festival，8/8 同样通过；排序、选中地点/顺序/时间、可见理由均不随变量改变；Ledger unavailable | 雨天、非有效日期、过期活动反例没有独立动态事实门禁；不等于真实模型必然这样选 |
| Real Model＋冻结事实 | 注册每变体3次，共24例，变体顺序交替平衡；实际首例1次Provider请求即失败 | 没有完整 A/B 或重复结果，不能评估真实质量 |
| 真实 UI→正式采用 | 本轮未执行 | pending Revision 不能冒充 UI E2E/正式确认通过 |

真实调用使用配置的 GLM/high/20000输出上限，现有 GLM 路径 temperature=1.0、top_p=0.95；SDK retries=0，保留原有一次格式修复和有界 Graph 修正，未暴露 seed，不能保证确定性。首例出现 `APIConnectionError`，cause=`RemoteProtocolError`，生产异常映射 `planner_unavailable`。按注册门禁停止，**1例尝试、0例成功、23例未执行**；没有追加 Provider 探测或宣称网络根因已经定位。`real.json`、`real_execution_notes.json` 和资源库存保留失败证据。此后只增强 eval 观察字段并验证 Deterministic/Mock，没有再次调用真实模型。

最终固定负对照雨天 outdoor_share=1.0，过期资讯仍包含 festival 场所，并保留明确“安排文化节”的负对照理由；原 Validator 为 valid。此结论是 **确定性约束缺口**，不是模型推荐质量评判。活动场所的合法 POI 身份不能证明某活动当天存在。

测试：`focused_final.xml` **163 passed / 13 Python3.14兼容性弃用警告**；最终 eval 定向 `eval_final.xml` **13 passed**。没有把这些结果算成新的863全量验收。一次中间负对照运行期间我补充了 eval 测试，源稳定性防护正确将其标为 incomplete（变化仅本轮测试文件）；原始文件保留，冻结后 `mock_final.json` 重跑8/8，源码变化列表为空。

## 4. 决策观察与五项能力基线

每例保存：用户请求/Goals/TripPreferences、真正进入 Planner 的结构化输入、原始外部事实、候选来源/合成provider identity与UUID映射、排序、选中/排除地点、可见理由、Validator/Goals/Ledger、待确认候选差异、Graph Trace、正式指纹。排除项没有结构化理由，逐项标记 missing，不补写事后理由。Brief 原始字段不直接进入 Planner 的投影回放也保留；本 eval 不假造 Router 端已经执行过。

“实际使用外部事实”在此区分**已提供给模型**与**理由/选择已由该事实支持**。前者可通过输入捕获确认；后者需要事实验证及反事实对照，不能因为 payload 存在就报告“已使用”。

| 能力 | 已获取信息 | 已进入Planner | 已影响选择/约束 | 有真实运行证据 |
|---|---|---|---|---|
| 个性化 | TripPreferences/当前Goals可获取 | 输入投影已验证 | 兴趣由LLM取舍；仅证明兴趣会改变发现查询，未证明最终选择 | Deterministic/Mock有；真实模型选址无；没有长期画像验收 |
| 天气 | 旅行日期原始天气可获取 | 四组对照输入捕获已验证 | 无室内外/时效正式门禁；雨天负对照可通过 | Mock约束反例有；真实天气驱动选择无 |
| 节庆 | 搜索可能发现活动文字 | raw facts可见，缺活动实体和有效期筛选 | 日期未改变发现查询；无有效期匹配约束 | Mock日期反例有；真实发现、核验和推荐无 |
| 资讯 | raw search可保留日期元数据 | Research投影丢失日期；有效/过期投影相同 | 无过期活动排除门禁；查询时间不代表发布时间 | Mock过期反例有；真实最新资讯使用无 |
| 依据追踪 | Goals/Memory/source/reason已有基础 | 决策上下文可见 | Ledger shadow；身份核对不等于声明蕴含；排除理由缺失 | Mock Ledger unavailable；真实逐项validated依据无 |

补充边界：Companion历史与Brief在Assistant路由上下文可获取，但直接改变它们不会改变当前Planner投影；Router可能先生成Goals，本轮未把这一间接路径冒充Brief完整传递。Decision Memory有同trip/day/version决策反馈基础，没有跨旅行用户画像，也未证明实际游玩行为改变下次规划。AMap的POI可给候选地图身份，路线富集与Validator可约束时间/路线可行性；本轮冻结身份和路线，因此只验证原接口与约束流程，不声称新鲜POI、真实交通或兴趣选择已通过。

## 5. 为什么现有测试不够，以及如何理解决策边界

既有测试多证明参数传递、格式解析、引用身份、SQL/Graph流程、预算时间约束和确认权限。Mock已经替模型决定输出，不能检验模型是否读懂兴趣，或是否正确处理过期活动。Validator通过表示满足其实际编码规则，不表示推荐适合用户或事实正确；负对照就是“合法但差”的具体实例。

单变量对照让其它条件保持稳定，才能把变化归因于兴趣/天气/有效日期。若同时改城市、预算和候选池，换景点无法说明兴趣有效。重复和变体顺序平衡用来观测组内波动，不能把一次偶然差异当改善。真实批次未完成时必须保留未执行项，不能以可用样本挑选胜例。

输入事实、发现候选、排序、最终选择和依据是五个不同环节。事实被传入但排序不变可能仍由LLM在最终选择时使用；反之选址变化也可能只是模型随机性。必须同时观察输入和输出，结合重复结果、目标与已核验事实，才能给出因果边界内的解释。

模型的推荐理由也是模型输出，可能是合理措辞或事后解释。长度、引用存在、地点名在摘要出现，都不能证明声明正确。需要将理由绑定用户Goal/Brief来源、有效时间内的事实ID/来源、真实候选差异，再独立核对；没有排除理由就标缺失，不能替模型补理由。

LLM负责语义提取/工具决策、研究筛选、活动取舍/顺序/时长和理由。服务器确定性部分负责引用身份、权限/活动保护、日期范围、路线时间、时间窗、预算估算、部分明确Goal、版本冲突、Revision及显式确认。模型不能授权保存；服务器现有规则也不能自动保证兴趣匹配、雨天适用性和活动时效。

## 6. Phase 1 最小修改范围（建议，未执行）

1. 先选定干净源码/overlay及manifest，恢复Provider门禁后复跑已注册24例，不部署也能测冻结事实敏感性。
2. `assistant_service.py`、`planning_run_repository.py`/既有JSON元数据、`planning_graph.py`、`planning_context.py`/`decision_context.py`、`openai_planner.py`：建立来源明确的PlanningBrief字段贯穿；原有确认权限保持。不要传整段历史替代结构化上下文。
3. `planning_graph.py`、`destination_research.py`与现有Travel Facts adapter/policies：按需求生成日期感知查询，保留发布时间/有效窗口，将已解析的事实与普通搜索摘要分开；天气/活动声明进入候选选择和验证。新增字段需遵循现有架构变更证据规则。
4. `decision_ledger.py`、现有schema和`planning_explanation.py`：补逐项事实引用与排除/取舍记录，先有评测证据再考虑扩大enforced范围。不要用关键词匹配替代事实蕴含检查。
5. 在同一fixture、同一模型配置及重复策略下比较Phase0/Phase1。先检查合法性，再检查目标匹配/事实有效/理由依据；不要为提高分数放宽Validator。

本轮不新增长期用户画像；也不把一次行为学习问题混入Brief/动态事实接入阶段。

## 7. 必须复用与禁止重复建设

必须复用原LangGraph、Planner/ModelClient、语义引用resolver、Intent/Goal流程、路线富集、Validator、PlanRevision/accept事务、Decision Memory、TravelFactService及其时效/权威策略、Tourism Knowledge公共接口、BenchmarkTrace/现有eval机制。

禁止第二套Planner/Graph/Validator、模型自授权保存、另建Agent或事实判断黑箱、重复造长期Memory、向量库/语料扩展、为评测修改正式数据或部署到Demo。未来UI E2E应运行在明确隔离的完整服务环境，不能把本轮Mock/冻结事实真实模型测试升级描述成生产旅行质量已验收。

Phase0交付：**可复现工程基线和明确能力缺口已建立；运行版本一致性尚未通过，真实智能质量仍未验收。**
