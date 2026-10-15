# RoamSync Phase 0.5：开发基线、Provider 与 PlanningBrief 设计

日期：2026-10-12（Asia/Shanghai）。结论：**本地最小模型连接恢复，真实规划批次仍被传输中断阻塞；基线整合方案可审阅但未应用。Phase 1A 设计已完成，实施前仍须冻结并验收整合源码。**

本轮仅新增评测审计脚本、证据、设计报告及 handoff。未修改业务 app、正式 Trip、生产配置、迁移或依赖，未部署、切换/提交/清理 Git，未进入 Phase 1B/画像/节庆扩展。唯一新数据库为本轮带 owner label 的临时 PostgreSQL；原迁移仅作用于空隔离库，原 Graph 到 approval 停止，无 Accept/Reject，资源已精确删除。

## 1. 开发与运行基线

主要证据：`backend/evals/results/planning_quality_phase05_20261012/baseline_before.json`、`baseline_final.json`。包含当前 HEAD/dirty status、app/tests/eval/合成fixture/配置模板/Compose/构建文件/依赖锁定文件的逐文件 SHA256，实际安装包及 API/Worker 有效模型配置与依赖版本。真实 `.env` 不写入报告，不记录凭据值；有效设置脱敏，密钥仅记录是否存在。源码 manifest 与实际包版本分别保存，不能用锁文件代替运行依赖。

| 对象 | 本轮核对 | 证据边界 |
|---|---|---|
| 当前工作树 | HEAD `0b5010fe5a7b06dcec1ab7b159b5b337244247ae`，分支 `codex/roamsync-demo-release-20261007`；含既存 Companion/Android 等改动 | HEAD不代表dirty源码；真实批次绑定完整app/tests和eval哈希，自身无源码漂移 |
| `322f553` 干净参照 | 保留原完整绑定，实际检出app/tests与记录0不匹配 | 863项是该参照历史回归，不能继承到拟整合源码 |
| 最新 Companion 有效改动 | 相对322有10个Companion/配置/router app文件变化，包括新的evidence quality、最新companion_state目的地优先级修复 | 必须保留；不得整体回退Companion来匹配322 |
| 最新909项记录 | 原始clean-exit日志909 passed/2 warnings/77.10s；保存的当前源码171文件与本轮0不匹配；保存的被测镜像manifest逐项另核对 | 不重复称为本轮回归；历史manifest未覆盖语料及两个opening-hours JSON夹具；原镜像已不存在，无法现场复检内容 |
| API/Worker | 开始时各 **22个app文件不同/缺失**；收尾快照各23项，无源码挂载，镜像ID不变 | 首次盘点后、真实批次开始前另项新增companion_answer_reliability.py，尚未验收，不自动纳入建议基线；原工作树保留 |
| 配置/依赖 | 本地/API/Worker GLM `glm-5.3-flash`、high、90s、SDK retry0、输出预算20000；OpenAI2.54.0/httpx0.28.1/httpcore1.0.9相同 | 未发现这几个SDK版本差异可以解释本地代理失败；Python本地3.14 vs容器3.11，所有包版本见manifest |

历史909绑定缺失的JSON为 `backend/app/knowledge_corpus/hangzhou_reviewed_v1.json`、`backend/tests/fixtures/opening_hours/nanjing.json`、`zhejiang.json`。本轮新manifest补齐它们；不倒填历史验收声明。最新知识策略本身有质量门禁OPEN，909项测试不证明通用智能质量。

另项新增 `backend/app/companion_answer_reliability.py`，也未在909绑定内。它已存在于真实批次初始manifest，真实批次与baseline_final的app/tests完全一致；baseline_before未包含它，其余文件一致。`baseline_reconciliation.json`明确分离当前树与建议冻结版本：保留首次盘点已绑定app/tests，只在未来独立检出整合两个修复；原工作树中的新文件不删除、不覆盖。`baseline_final`和其中全树virtual proposal用于观察当前树，最终推荐的排除未验收并发新增文件的manifest以reconciliation为准。

推荐冻结manifest SHA256：`c50cd05fda98158a41cdd5fc7080029fb755f95382f60f9536dcbc7bc46aa688`；推荐四文件整合后manifest：`bbe2d4debf4d276d620611d6b85621738bcd8e649c1720f51c6efc3004e35270`。两者都是文件身份清单，后者没有测试或部署通过声明。

### 最小整合方案（提案，未应用）

以本轮首次盘点的冻结app/tests为底，保留全部已绑定有效Companion和现有候选编辑/路线/接受保护，只从322补入以下 **2个app文件与2个测试文件**：

| 文件 | 必须补回的修复 |
|---|---|
| `backend/app/decision_context.py` | 请求第三天时仍保留全局current/navigation/first_impacted指针引用的其它日期为只读上下文；禁止把非请求日期划成可编辑；真正未知指针仍失败 |
| `backend/app/planning_intent_service.py` | 真实活动别名匹配后，将“其他日期安排不变”“整体三天（日期范围）框架”识别为计划元要求；未知场所仍澄清，不能吞掉实际同名活动 |
| `backend/tests/test_decision_context.py` | 补4个跨日引用/未知执行指针回归 |
| `backend/tests/test_planning_intents.py` | 补5个计划框架/真实活动别名优先级回归 |

具体差异已保存 `integration_proposal.patch`，方向为**当前→322四文件**；最终推荐拟整合每个文件哈希为reconciliation的 `recommended_integrated_manifest`。它只用于审阅，**没有执行git apply，没有整合测试结果**。四文件当前没有需额外保留的后续代码差异；应用前仍须检查当前哈希是否与本轮绑定一致，避免并发编辑覆盖。

必须原样保留的现有共同能力（当前与322的这些文件一致）：`assistant_service.py`待确认候选绑定；`candidate_edit.py`候选Revision身份/内容hash/正式版本检查与非目标日期保留；`openai_planner.py`语义引用及候选编辑输入；`planning_graph.py`执行保护、候选路由和预算；`candidate_route_service.py`保护活动路线；`navigation/execution_context.py`执行不变量；`plan_revision_service.py`接受前事务重验与执行不可变保护；`planning_run_repository.py`候选存储边界；`planning_explanation.py`预算变化包含保留活动。不得“为对齐”替换成10-01运行镜像中的旧实现。

执行顺序建议：将当前受审文件精确保存到独立目录/检出 → 核验与新manifest一致 → 应用四文件补丁 → 新空隔离PG迁移及完整回归 → 重新跑同一Deterministic/Mock/真实注册集 → 输出同一manifest绑定的测试、依赖和镜像。原工作树、Demo和数据不动。863/891/909都不能作为这份拟整合源码的通过数。

运行环境对齐单独进行：开发eval继续使用本地进程及隔离DB；拟整合版本经验收后再构建单独测试镜像，确保API/Worker同源码、同锁定依赖、同配置语义。原生Windows评测用loopback代理，容器代理使用可到达宿主机的地址；不能把127.0.0.1复制进容器当宿主机。生产替换须另有备份、旧镜像/config及回滚方案并取得发布授权，本轮不执行。

## 2. 有限 Provider 排查

执行策略：最多2个无DB最小请求，SDK retry0、30s请求超时；成功后只运行一次现有24例批次，首错误停止。没有探测生产Planning API，没有读取私人Trip，没有修复生产代理或修改 `.env`。

`phase05_audit.py probe`使用原 `build_model_client`/`create_model_response`，记录HTTP请求派发/响应头阶段及完整脱敏异常类型链，不捕获Authorization、响应headers或隐藏推理。

| 请求 | 结果/阶段 | 可以断言 |
|---|---|---|
| 原生Windows原配置 `host.docker.internal:7897` | 6.497s；请求派发后、响应头前失败，HTTP status未收到；`APIConnectionError→RemoteProtocolError→RemoteProtocolError` | 本地该代理路径不可用；不是JSON解析失败，也无证据证明模型拒绝 |
| 同客户端，仅进程覆盖 `127.0.0.1:7897` | 1.242s；HTTP200，stream完成/stop，JSON ok=true，139 tokens | 本地最小模型连接恢复，生产配置没改；不能外推长请求或容器稳定 |

两次均256输出预算/low/JSON Schema指导→GLM json_object/stream。正式评测使用原high/20000，temperature1.0/top_p0.95，schema语义引用、一次原格式修复、有界Graph纠错全部保留。GLM通过Chat Completions，预算字段为max_tokens；非GLM使用Responses/max_output_tokens。没有使用另一SDK、另一模型或缩小正式预算来“通过”。first成功证明当前正式格式至少可执行一次，不证明后续稳定。

本地/API/Worker原有效base_url、模型、预算、超时和关键SDK一致，原代理字符串也一致，但其网络命名空间不同。无HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY进程变量。无法据此排除宿主代理、网关或上游服务中断。没有调整预算/reasoning/请求格式做额外试验，不能宣称20000或high导致中断。

## 3. 真实规划24例恢复结果

复用 `planning_quality.isolate/run`，冻结Phase0四组fixture和合成候选/天气/资讯/路线，只换真实模型；不是实时Tavily/AMap/天气发现验收。独立loopback端口57092的tmpfs PG完成原迁移到0034，使用InMemorySaver。资源owner和container ID见 `real24.resource.json`。

| 例 | 结果 | 观察 |
|---|---|---|
| culture/repetition0 | 32.964s模型完成；awaiting_confirmation/pending，原Validator valid，Formal指纹不变 | 选museum→park→festival→mall；文化类别占0.5，理由提及兴趣、晴天及资讯有效日期；Ledger unavailable，不能以理由证明因果或validated依据 |
| shopping/repetition0 | 3.114s模型请求失败，`PlannerProviderError/planner_unavailable`；原始类型链`RemoteProtocolError→RemoteProtocolError`；Formal指纹不变 | 未有完整候选/Revision，不当成“不喜欢购物”或质量失败 |
| 后续22例 | 未执行，首错门禁终止 | execution_notes逐例列出，包括兴趣其余重复及全部天气/日期/资讯对照 |

共 **24注册、2尝试、1成功、1失败、22未执行；2次模型请求，0 SDK retry，未触发额外格式修复/Graph纠错**。批次源码变化列表为空。`real24.json`保留Planner实际输入/输出、schema和prompt哈希、attempt、Trace、Validator、正式指纹；`execution_notes.json`保留细分统计及未执行名单。退出1是批次未完成的正确结果，不强行改成成功。

失败发生在原Planner `_create_response` await阶段，3.114s不是90s超时；本批次没有HTTP事件hook，因此精确HTTP状态/收到多少stream片段未记录。结合原model_client流消费代码，原始RemoteProtocolError与流中断相容，**属推断而非已证实的服务器根因**。没有响应错误码/traceback阶段时，不能区分代理、上游或服务端中断。原成功、原失败全部保留，未重试拼成全成功。

四组均无完整A/B＋三重复，不能报告兴趣敏感性、晴雨差异、节庆差异或过期资讯排除能力提高。首例理由的事实声明仍需独立核验；输出“日期元数据核对有效”不是服务端验证的证据。没有UI→正式采用E2E。

清理结果：精确匹配本轮container ID/name/label后删除 `roamsync-phase0-eval-4ae1cba6d6c5`，tmpfs丢弃，文件保留；未操作原四个服务或任何其它任务资源。

## 4. Phase 1A字段级设计（仅设计）

### 当前断点

`companion_contracts.py:234`定义PlanningBrief；`companion_state.py:126`从用户turn和持久化Suggestion构建；`assistant_service.py:310/358`进入ToolRouter。但`:413`创建PlanningRun只传Router重述请求/选中day/activity；`schemas.py:747`没有Brief字段；新旅行确认分支`:511`更换成通用请求。`planning_graph.py:288`建立DecisionContext，`openai_planner.py:322/451`投影正式输入，均未完整投影Brief。因此当前JSON存AssistantSession并不等于Worker或Planner可见。

### 契约与字段

沿用PlanningBrief，增加兼容的schema_version及有界来源字段；新增字段默认空，历史Run保持旧语义。不另建Agent、Memory服务或持久化表，不传完整history。原PreferenceStatement只有text/source_turn_id/conversation scope，现阶段字段名confirmed不保证每项有清晰确认状态；原Suggestion状态采用单调rank，负反馈可能仅discussed，**不能反推出用户取消了must_do**。

| 业务字段 | Brief建议表示 | DecisionContext/Planner投影与边界 |
|---|---|---|
| 明确偏好 | confirmed_preferences：有界statement；可选归一化category/value | user_requirement_context.preferences；仅有explicit/confirmed的本轮有效项作为偏好，推测项标proposed |
| 明确不喜欢 | avoidances：独立negative statement及目标scope | avoidances；“不太喜欢”与“绝对不要”保留强度，不能靠旧Suggestion rank覆盖负反馈；与must_do冲突澄清 |
| 必去 | 沿用must_do＋candidate_interests，绑定用户明确must_do turn | required_entities；先通过现有身份/范围grounding，未匹配则澄清，禁止把Suggestion ID直接当candidate_N/Activity UUID |
| 旅行目标 | 新travel_goals bounded statements | 现有Goals可表达的项通过确定性adapter进入同一个planning_goals；其它目标进入语义偏好，不伪造新的硬校验能力 |
| 旅行节奏 | 新pace_request，枚举relaxed/balanced/intensive或未解析，保留原文来源 | 与现有TripPace一致；使用现有soft pace，形式化时间窗/执行保护不变 |
| 会话确认建议 | candidate_interests：user_confirmed/user_liked等状态＋suggestion_ref | confirmed_suggestions；确认想去仅是候选意向，不等于正式Revision接受；没有明确必去不能升级must_do |
| 待澄清 | 沿用open_questions，增code、blocking、related_statement_refs | blocking项在Router/Run创建前停止；低影响未知项显示unknown，不补造答案 |
| 来源/确认 | 每个statement增statement_id、source_session_id、source_turn_id、role=user、excerpt/digest、confirmation、polarity、scope、supersedes_refs | requirement_provenance；服务端从保存user turn验证，assistant模型生成文字不能当确认来源 |
| 身份/绑定 | 外层envelope：brief_id/schema_version/session_id/authorization_turn_id/target_trip_id/base_trip_version/payload_sha256 | 各层保留相同binding；声明来源与地图/正式活动身份分开，禁止跨Trip/session引用 |

statement_id由服务端基于session/turn/字段/序号生成；每项不超过1000字、最多30项，Suggestions最多10，来源turn最多60，保留原有上限并增加总payload限制。excerpt只包含声明相关的用户原文，不传assistant prose或全聊天。scope限定本会话/本Trip/请求日期；不用此机制建立跨旅行用户画像。

### 六段数据流及校验责任

1. **Companion→Brief**：只使用已保存Suggestion/用户turn；授权只能来自明确Planning用户turn。CompanionResult保持`planning_handoff=None`，provider不能写授权、身份或确认状态。显式目的地优先级修复保留。缺失/重复/其它session建议必须澄清。
2. **AssistantRouter→PlanningRun**：Router可选择工具和重述请求，但不能删改/重新生成可信Brief；server验证后将immutable envelope作为`create_planning_run`内部可选参数。公共PlanningRunCreate不允许客户端随意注入session证据。使用现有trigger_snapshot命名空间`planning_brief`/binding并合并，不覆盖candidate_edit/recovery/decision_context_summary。
3. **创建旅行确认路径**：pending_action保留prepared Brief digest及来源；用户确认旅行后，服务端绑定新Trip/version，再创建Run。禁止`:511`的通用请求替代丢掉Brief。确认旅行设置不等于确认行程，更不将建议当正式Activity。改期/复用Trip需重新校验目标绑定。
4. **PlanningRun→PlanningGraph**：resolve节点从Run存储加载并验证绑定与payload hash，放入context_data的受控只读字段；可在现有checkpoint保存投影。不要在worker执行时重新读取“最新”AssistantSession重建需求；retry使用原snapshot并重验版本，clarification作为显式新用户来源变更不能静默改变快照。
5. **PlanningGraph→DecisionContext**：既有builder增加纯函数投影`user_requirement_context`＋来源/冲突清单；复用原Goals/Memory，保留formal/route/execution/protected scopes。语义实体通过原intent grounding和PlannerEntityBindings，不新增identity registry；Suggestion/raw_mention只能用于查询或待解析意向，不能扩大正式可编辑范围。
6. **DecisionContext→Planner Input**：白名单投影statement/ref/value/status/source和冲突resolution，保留formal_preferences与effective_request_preferences分别可观察；结构化refs经原resolver转成request-local引用。Trace记录brief_id/hash/字段数/映射/未解析项；Revision差异保留这次快照来源，不收集隐藏推理，也不把模型reason自动改为validated。

Brief独立payload hash不能替换Recovery trigger_fingerprint、candidate_edit snapshot_hash或正式Trip.version；clarification/重试要分别保留原请求与显式新增用户声明的来源。Phase1A实施前需按现有AGENT_ARCHITECTURE变更控制更新“Brief仅Router输入”的契约及正/负例，不能仅加透传字段就宣称新hard Goal门禁已验收。

priority和冲突解析不得交给ToolRouter自由编造：

- 正式Trip的日期/预算/版本、活动执行/锁定保护、确认边界优先于所有Brief。要求修改这些正式设定，走既有显式设置/确认流程或澄清，不能用偏好覆盖硬约束。
- 对可以在本候选中调整的软偏好：最新当前明确请求 > 当前会话已确认用户声明 > 正式TripPreferences默认值 > proposed建议。只改变本Run的effective view，**不写TripPreferences**，并记录胜出/被覆盖statement refs及原因。
- 同优先级互斥或不同scope无法比较时澄清；新的明确取消可用supersedes记录替代旧must_do，不能默默从单调status判断。must_do与avoidance、预算/时间/执行保护冲突保留双方证据，不能自行删除低优先级声明掩盖矛盾。
- `scope/day`不能匹配时不进入当前有效要求；stale/另一session/另一Trip绑定拒绝，不默认继承。自动导航/体验Recovery没有Brief时沿用原权威事实；用户Brief不能替代Execution事实。

### 最小实现范围与测试

| 文件 | Phase1A建议修改 |
|---|---|
| companion_contracts.py / companion_state.py | 兼容Brief字段、来源与确认/负反馈及supersedes投影；保留最新目的地修复 |
| assistant_service.py | server可信Brief传递；pending_action/确认旅行、新Trip绑定；Router不能自行授权 |
| planning_run_repository.py | 内部可选envelope验证、不可变snapshot合并、retry相同来源检查；沿用现有JSON列，无新表 |
| planning_graph.py | 从Run装载、校验并传入context，trace及clarification合并 |
| decision_context.py / openai_planner.py | 字段白名单、来源和冲突/effective preference投影，原语义refs保留 |
| planning_goals.py（必要时） | 仅复用现有可表达Goal字段的确定性adapter；不新造must_do事实或降低规则 |
| 现有tests / planning_quality eval | 扩Brief单变量fixture及输入捕获、隔离Graph回归；不替换Planner |

`planning_graph_runtime.py`无需额外传入未验证session历史，Graph读取已绑定Run即可；数据库schema/迁移、plan_revision_service/Validator、Destination Research、Travel Facts、画像与语料不在本次最小范围。若未来决定将新must_do/avoidance转为新的hard Goal，必须另走架构变更控制，不冒充本Phase1A输入贯通已实现确定性约束。

最小测试集：

1. Deterministic：八类字段逐项投影与来源保持；旧Brief/无Brief兼容；来源伪造、跨session/Trip、stale/hash错、未解析Suggestion被拒；同名场所不能误绑定；负反馈/取消必须可追踪。
2. Mock原Graph/隔离DB：plan_trip和新Trip确认两入口；Run snapshot与Planner实际wire逐层相同；worker重启/retry不读取新history；trigger_snapshot保留candidate_edit/recovery；正式指纹不变，pending批准边界不变。
3. 冲突/执行回归：当前请求覆盖正式软偏好但不持久化；预算日期/未知活动必须澄清；跨日current/navigation只读、非请求日期保留、stale Revision拒绝；未确认Suggestion不能进入hard must_do。
4. Real原Planner：同一pool/模型配置三重复，除Brief字段外保持输入；先记录wire、组内波动和逐项目标/理由来源，不能把Mock或输入变化当真实选择改善。沿用24例入口，不重建另一Planner。
5. 后续隔离UI→Revision→显式Accept：独立验收用户确认边界，不用本轮pending Revision替代。

## 5. 证据绑定与进入条件

Phase05新增脚本 `backend/evals/planning_quality/phase05_audit.py`：bind无模型/业务写入；probe最多2个模型请求且无DB。真实批次仍用原isolate/run。fixture、业务源码和eval哈希均在证据中；`baseline_before`为运行前、`baseline_final`为收尾，新脚本本轮有观察字段完善，**本任务**没有修改业务app/tests及原run/isolate。并发新增文件另记，后续用reconciliation推荐manifest冻结独立基线，用real24内manifest绑定该次模型结果，不能倒换源码。本轮定向 `focused.xml` **18项/0失败错误跳过**，只属当前测试选择，不是拟整合全量回归。

复现时使用新的结果文件名，保留旧失败。连接验证成功才运行批次；代理仅传给子进程env，命令示例：

```powershell
& .venv/Scripts/python.exe -B -m evals.planning_quality.phase05_audit bind --output evals/results/NEW/baseline.json
& .venv/Scripts/python.exe -B -m evals.planning_quality.phase05_audit probe --output evals/results/NEW/probe.json
# 核对probe batch_gate后，临时设置代理并恢复原进程环境：
$originalProxy = $env:PLANNER_PROXY_URL
try {
  $env:PLANNER_PROXY_URL = 'http://127.0.0.1:7897'
  & .venv/Scripts/python.exe -B -m evals.planning_quality.isolate --mode real --repetitions 3 --output evals/results/NEW/real24.json
} finally { $env:PLANNER_PROXY_URL = $originalProxy }
```

本轮停止真实评测后不执行这些命令重复探测。

进入条件：**可以审阅Phase1A设计和整合补丁；尚不能宣布可信整合开发基线或真实质量门禁通过。** 实施前至少在独立检出整合四文件并获得新的全量绑定回归；动态效果验收还需长规划传输恢复后完整24例重复批次。设计/纯输入工程可以和外部传输问题区分，但不能在不稳定运行版本上宣布上线或个性化能力改善。本轮到此停止。
