# D：共同基点契约复核与正式工作区验收准备

日期：2026-10-26（Asia/Shanghai）。结论：**HOLD；整体 NO-GO**。
本文件是 D 独立契约复核，不是最终独立评分，也不证明整个后端或产品通过。

## 审查对象与证据分级

- 工作树：`E:/Study/RoamSync-closeout-d-review-20261026`。
- 分支：`codex/closeout-d-review-20261026`。
- 共同 WIP：`8e53fd68d91720f1cf1674a97483e67f9bff8bf3`；审查开始工作树干净。
- 已读取本树 AGENTS、架构契约、PROJECT_STATE、并行收尾方案、`docs/handoff/LATEST_HANDOFF.md`。根目录没有 `LATEST_HANDOFF.md`，以 AGENTS 指定的 handoff 路径为准。
- 已读取外部公开 `E:/Study/RoamSync-stage6-evidence-20261025/astra-batch3-review.md`，历史各次 LIMITED ACCEPT 仅限当时具体修正；regression11 仍明确保留预算声明漏项 HOLD。
- **MEASURED**：本轮仅执行 4 个公开、无 DB 的函数探针，2 符合预期、2 不符合预期。未运行 pytest、模型、地图、浏览器、数据库或服务。没有访问 sealed cases/rubric；没有新增未见题或重复采样评分。
- **VERIFIED/static**：以下源码行号均属于共同 WIP；后续 worker commit 需要重新定位。静态边界检查不等于运行验收。
- **历史转述，未独立执行**：handoff 的后端 2164 项、13 失败、40 跳过；11 个 snapshot fixture 缺字段、另两个分类问题。不能把历史结果算入本轮通过数。
- 未操作正式源码、正式或测试 DB、部署和 Obsidian；产品/测试零改动。提交仅含本 review 文档；探针及原始结果保留在允许的外部 D 证据目录。

## 当前阻断与最小复现

### D-P1-01：预算上下文排除只认前缀，实际服务费被漏掉

定位：`backend/app/read_calculations.py:26`、`:118`、`:121`。

`_budget_role` 只在金额前文本做后缀搜索。sum 的 separate_context 分支没有验证完整声明的前后文，却直接从费用覆盖义务中排除金额。

最小公开输入：`门票45元，午餐38元，另付超预算10元服务费，合计多少？`。
proposal 为 sum，items 仅 `门票45元/4500fen` 和 `午餐38元/3800fen`。
实际 `status=computed,sum_fen=8300`，第三段被记为
`role=budget_context_not_a_cost,source_quote=另付超预算10元服务费,position=17`。
这不是完整费用合计；结尾“仅列出项目”的免责声明不能纠正漏掉用户明确提出的收费。
预期：在当前有限语法下返回 needs_clarification，或经过明确费用绑定后才计算；不能把该段判作预算声明。

最小修正建议交 B：只有整个子句符合支持的预算声明时才可进入 separate_context；前缀、数值、后缀均消费完整，未知费用/关系仍是覆盖义务。不扩展乘除、自动换算或写预算权限。
本轮未实施，修改后证据待 B。正例 `预算120元，门票45元，午餐38元，合计多少？` 仍应计算83；负例 `另收五分服务费` 应局部澄清，本轮这两项符合预期。

### D-P1-02：景点数量被时长兜底正则误收

定位：`backend/app/saved_operation_bindings.py:48`–`:53`；上游传播在 `backend/app/planning_intent_service.py:1247`–`:1253`。

最小调用：`bind_duration_change(SimpleNamespace(raw_text='增加2个景点'),0,[],1)`。
实际 `(None,'duration_expression_unsupported')`；预期时长分类器返回 `(None,None)`，交原有数量/规划路径处理，不表示本请求可直接写入。
原因：无合法时长匹配时，第51行第一个正则分支仅要求动作后接数字，不要求时长单位；issue 进入 inherited_ambiguities。
这是分类器实测失败，未执行完整 Planning 链。

最小修正建议交 C：区分数量与真正不支持的时长，不可简单删除所有失败兜底。保留“刻钟”、多数量、冲突/混合操作和无唯一目标时的澄清；合法分钟/小时必须继续精确绑定目标、基线和版本。本轮未实施，修改后证据待 C。

### D-P2-03：开放时间子任务的能力修复受名字修改副作用限制

定位：`backend/app/read_references.py:164`–`:193`，特别是189行；调用后仍有原始校验 `backend/app/assistant_capabilities.py:485`–`:505`。

静态观察：只有完整、唯一指代的 opening_hours 表达式进入窄修复；且仅当 `changes.names` 存在才补空 capabilities。已正确给出 literal name 的任务、复合依据问题等不会自动获得这一修复。不能据此宣称所有开放时间子任务完整。
handoff 的复合任务分类失败本轮没有独立运行，标为**未验收**，不推断所有此类表达式都失败。

交 B 的契约要求：允许的补全须绑定同一当前子任务和唯一服务端主体；保留 parent request 供解释但不能让另一子句的地点、能力或授权覆盖本任务。禁止去掉未知关系/route 参数、吞掉否定或假设来使任务“通过”。每次 bounded 修复须保留前后对象、理由、尝试次数和完整后置校验。

## 可暂时保留的有限契约边界

以下 **LIMITED ACCEPT 仅指静态实现边界与已列探针**，不是本轮运行验收或整条链通过。

| 契约 | 当前源码依据 | 后续必须补齐的正反证据 |
| --- | --- | --- |
| 费用覆盖与精度 | read_calculations.py:53、:69、:97、:121；严格整数fen、完整原始请求覆盖、单位缺口、来源唯一性 | 原子金额、同额不同项目、重复同源、合计与分项、中文费用/分角块、汇率/优惠/范围/纠正/否定、各自计价基准；预算完整声明 blocker 必须先关闭 |
| 子任务输入不被短 quote 截断 | assistant_capabilities.py:943、:1060、:1161；计算使用 original_request，解释保留 task_context | 截短45/38不能漏22；独立 monetary sibling 当前可能使整体计算澄清，属于局部性限制，不能以放松完整性修复；超时仍展示已验证计算及独立读结果 |
| 地点不是模型自行确认 | conversation_candidate/service.py:69 清掉模型ID；:133–:152 从服务端检索唯一同城地点并检查 identity/freshness/expiry | A 必须用真实新城市成功轨迹及同名/跨城/缺失/过期/provider失败负例；零个或多个候选不能猜第一项；旧真实对象克隆不能代替新地点生成 |
| source片段不补授权 | conversation_candidate/commands.py:45–:113；bind_generation_source只允许generate、唯一当前父子literal span并再次validate_command | 同字不同位置、引述/否定/假设/未来采用、历史span、modify/adopt/discard均不能从父句获新增权限；保留父子span和完整后置检查 |
| 生成城市与目的地绑定 | conversation_candidate/service.py:186–:192；模型城市冲突被拒绝 | “南京…玄武湖”不能把景点升级为城市；字面语法未知时明确缺口，不能宣称通用地理消歧 |
| scope精确diff | planning_goals.py:205–:249；用现有Revision review检验目标分钟、保留活动字段、完整review及route mode；planning_graph.py:291–:293重绑定比较 | 修改候选、审阅、讨论、明确采用、回读连续链；未知兄弟、跨日活动、锁定对象、过期版本/ordinal、模式改变、漏掉改动均拒绝；路线ID/freshness刷新与业务内容差异分别记录 |
| 条件来源和日期 | assistant_operation.py:231–:255；短action quote之外独立检查当前date声明和拒绝receipt | 歧义/无效/合法新日期与旧slot冲突，独立读和引用中的日期，不得回退旧日期或擅自写memory；撤销/部分重加按value+subject+scope保持来源 |
| 照片身份和降级 | place_content/images.py:34–:58；provider id+stable id+name+city+坐标及本地asset检查；web/src/components/PlacePhotos.tsx:6–:21逐图来源/历史说明和onError降级 | 同名错ID/错城/坐标、缺文件、网络失败、切图、刷新、保存卡片；provider_unavailable允许已有审核图不证明当前营业；参考历史图片不是现场验证或新许可审计 |

架构建议交主对话整合：继续保持 Planner→Revision→Validator→Accept 为正式规划写入主链；本轮不建议新业务表、公开写端点或第二套接受通道。对本轮尚未提供的 A/B/C diff，不能提前断言无新增通道；整合时必须检查完整文件清单、迁移和路由变化。

## 本轮可复现证据

外部文件：

- `E:/Study/RoamSync-parallel-evidence-20261026/d/baseline_probe.py`
- `E:/Study/RoamSync-parallel-evidence-20261026/d/baseline_probe_result.json`

外部证据 SHA256：脚本 `5e8e8e1ae2abc8f05cd91b9909c11f1d186351d7750b698453db2cbd9c3104bd`；原始结果 `f3b9c804b00a8917d97413af324f41ddc1d7fbd19ccba7b2651d819b3a68222c`。外部文件不属于本次Git提交；主对话归档时需核对hash，不能因JSON被ignore而遗漏。review路径已检查不被gitignore忽略。

在 D 工作树显式 cwd 下运行：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& E:/Study/RoamSync/backend/.venv/Scripts/python.exe E:/Study/RoamSync-parallel-evidence-20261026/d/baseline_probe.py
```

脚本将 backend 绝对路径插入 sys.path，并输出真实 module.__file__，两模块均为 D 树。
计时0.008219599999961247秒是导入完成后的探针及hash过程，不是服务响应时间。
实际4项：预算服务费失败；景点数量分类失败；完整预算声明正例通过；五分服务费澄清反例通过。
原始JSON包含所有输入、receipt、期望/实际值、源码hash及导入路径；模型调用0、DB调用0。
无真实模型全文或工具轨迹，因未调用；无DB状态差异，因纯函数操作。不能把“未调用”记成真实模型成功或正式状态无写入测试通过。

源码 SHA256（真实文件字节，不用commit代替）：

| 文件（相对本树） | SHA256 |
| --- | --- |
| backend/app/read_calculations.py | 6dd48784deb634dbfbc94d83020d49e22b0f1e74b9c1fd34af9f8b7105207a89 |
| backend/app/saved_operation_bindings.py | 052fd39abfdaf412ff5d900b1bf72a8ba2a1674364d10488a6e1b798fe1bf399 |
| backend/app/read_references.py | b0249a68be36cf99b9750df96192c1cffe4d82d4cd99666329564e88a3f4c32c |
| backend/app/assistant_capabilities.py | 3a9635f82ec6136d87314cb9c9872be564cb73e786d2c9ffaea18101427e74b3 |
| backend/app/conversation_candidate/service.py | cc2eadd8b07dd86b9cba7d60a7905ecd7caac4114fbfad5b8caf1a144e776053 |
| backend/app/conversation_candidate/commands.py | 4d76591242479f668b4edf0e7f40373b89784c8358a45a36164b92a962366600 |
| backend/app/planning_goals.py | 5c0cbc501ff8b0fae95d7f947493bb6b9ab82ae2c07b2801fac1294685f3b685 |
| backend/app/assistant_operation.py | f74a9126830b3d660d2063e117995b0ab4c093ad3559b69b8c0146c93cccd059 |
| backend/app/place_content/images.py | d48375c57e642b174c1c584d8c6a33508e0e5bb4fb95b991f1b7479855f50e13 |
| web/src/components/PlacePhotos.tsx | 764324f9832385f02747c0f07e94a452fae102b21b294283e787b767234008d6 |

## 正式工作区验收清单：由主对话执行，当前全部未验收

1. **保全先于整合**：再次读取 E:/Study/RoamSync 的HEAD、分支、tracked diff、untracked清单（含可能影响运行的ignored配置/资产）。ea3ba83、6 tracked dirty 是交接观察而非当前证明。本轮D未读写正式树。建立外部可恢复快照和逐文件hash/大小/路径清单，核对备份可读及内容一致；密钥仅受保护保存，不输出。不能用reset/clean覆盖用户工作。
2. **提交可追踪**：逐个记录 A/B/C 产品提交和单独证据提交；检查合入差异、冲突解决及原正式dirty的归属。审查对象是整合后实际源码，不能仅拼各worker的通过数。D本报告不证明未收到的提交已通过。
3. **冻结内容完整**：正式目录记录HEAD、完整git status、tracked/untracked运行文件清单、源码/测试/配置/锁文件/迁移/静态照片/Web产物hash。运行前后复算；若源码变动，则记录新冻结，重跑受影响门槛；不得沿用旧成功链充当新版本通过。配置摘要不含密钥。
4. **启动来源一致**：绝对 WorkingDirectory=E:/Study/RoamSync（backend/web分别明确子目录）；记录启动脚本、解释器、参数、PID/父PID、启动时间、监听端口及Web代理目标。仅命令行包含路径不证明cwd或导入来源；在同一API/worker进程内捕获 os.getcwd、sys.executable、实际app模块__file__及文件hash，并与冻结清单比对。服务启动前hash不能证明内存已加载新版，必须确认旧进程不占目标端口、记录重启边界，并禁用不受控热重载。
5. **DB隔离可证明**：只使用127.0.0.1:15435和新建专属库；连接后记录 current_database/current_user/inet_server_addr/inet_server_port、迁移版本、API与worker/checkpointer的非敏感DSN标识。确认业务与checkpoint都落在指定库；拒绝15432、复用他人可变库或连接回退。Windows async psycopg使用SelectorEventLoopPolicy。D本轮没有创建库，因为没有DB测试。
6. **runner不误测旧树**：历史run_tests.py第4–8行固定旧root和共享库，必须复制到证据目录，改为正式源与独立库后归档副本hash。历史run_public_empty.py:184要求app-root，:188会拒绝正式目录，:191–:196限定新库并拒绝复用，:197设置sys.path；主对话须在适配副本中仅按新授权调整正式源限制，保留独立DB安全检查。核对有效root、导入路径、cwd、settings-source和两种DB URL；它的source_hash仅覆盖backend/app/*.py，不能代替完整冻结清单。D没有运行/修改这两个runner。
7. **工程验收一次归属同版**：主对话调度全后端、专用DB套件、Web、typecheck/build，避免worker并发全套。记录准确collected/pass/fail/skip和skip理由；fixture补齐字段不能降低真实snapshot契约。保留原失败；超时修复要证明等待条件/运行隔离，不能仅增加timeout后宣告无问题。
8. **连续真实链**：冻结后在正式目录启动的隔离服务，以空白独立DB、真实模型和高德运行成都及另两城；记录逐轮原始输入/输出、模型provider/model、所有repair和工具trace、成本/耗时/错误、session/trip/run/revision/hash/version，以及每步完整业务表diff。生成→局部修改→审阅→讨论→明确采用→回读→刷新必须是同一对象的连续链。克隆、手工补ID、重试或UI补救须显式标注，不得拼成自然链成功。
9. **安全和照片**：新对象覆盖未授权/否定/引用/未来采用、跨session/跨Trip、旧hash/版本、保护对象、混合未知操作；采用前业务表不变，采用后仅允许业务差异及明确解释的元数据刷新。照片展示/切换/归属/刷新与失败降级均需当前浏览器证据。来源信息不等于实际现场真值。
10. **独立封存最终评分**：仅在正式目录冻结和统一工程出口后，由指定独立评分流程对既有sealed5x4执行一次；D不读取、不新增第二套、不调题、不用旧题作独立分数。必须>=16/20、零未授权正式写、零critical无依据保证且其它门槛全部通过，否则NO-GO；不自动部署。任何未跑项逐项标“未验收”。

## 后续提交复核入口

主对话提供 A/B/C 的确切commit及整合冲突diff后，再对对应最小修复和负例复核。需同交：原失败、根因、产品/证据提交、准确测试结果、真实成功和失败的完整证据索引、源码hash、未完成项。此轮到基点复核/验收准备为止，不无限等待，不发起另一轮未见题。

当前剩余阻断：D-P1-01、D-P1-02；开放时间复合任务、A新地点真实生成、C fixture/Web、所有正式源整合与冻结后的运行门槛均未验收。**保持 HOLD / 产品 NO-GO。**
