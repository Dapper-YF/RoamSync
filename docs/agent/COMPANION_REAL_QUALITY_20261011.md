# Companion 真实模型评估与质量门禁 — 2026-10-11

结论：真实 Provider 已恢复，原固定 18 题的 54 组执行完成，53 组有有效回答、1 组被 Provider 过滤。新增南京/苏州 7 题的 21 组全部有回答；三组四轮真实对话完成。68 个固定集/留出集答案完成六维匿名评审和有限独立事实核查。C 在覆盖充分的明确来源题有收益，普通问题与 A 大体持平，不能宣称整体最优或成本最低。专业 RAG 明显增益尚未得到证明，质量验收仍为 PARTIAL / OPEN。

建议保留现有 C 默认策略及其严格来源边界，继续处理下列已记录问题；这不构成生产发布批准。本轮没有部署、改生产配置或运行正式 Planning/数据库评测；所有真实输入和历史均为评估夹具。

## 1. 基线、诊断与可复现证据

仓库 HEAD 确认为 `0b5010fe5a7b06dcec1ab7b159b5b337244247ae`。既有 Companion、Planning 评估、Android 及文档工作树保留，未 reset、未提交覆盖。历史 `companion_knowledge_strategy_20261011/real.json` 保留原样。

本轮证据根目录：`backend/evals/results/companion_real_quality_20261011/`。

| 对照 | 同一生产客户端、同一最小请求 | 结果 |
|---|---|---|
| 原本机配置 | GLM `glm-5.3-flash`，`host.docker.internal:7897` | 7.385s，`planner_unavailable`；`APIConnectionError → RemoteProtocolError → RemoteProtocolError` |
| 仅评估进程覆盖代理 | `127.0.0.1:7897`；模型、Key、SDK、API 路径不变 | 1.815s，`completed/stop`，`{"ok":true}`，139 Token |
| 无凭据 HTTP CONNECT | 原代理 TCP 可接通但关闭 CONNECT；本机回环代理 | 后者返回 `HTTP/1.1 200 Connection established` |

VERIFIED：失败发生于本机评估的代理路径，未到有效模型输出/结构化解析阶段；不是根据错误类猜测 Key 或模型不可用。原主机名解析为 `10.241.211.159`，TCP 通并不代表 HTTPS 代理握手正常。更深层关闭原因仍 UNKNOWN；不能把该结论迁移为 Docker/Worker 的网络诊断。

配置确实读取根 `.env`：API 为 `https://open.bigmodel.cn/api/paas/v4`，OpenAI SDK 2.54.0、httpx 0.28.1、timeout 90s、Provider 重试 0。生产 `build_model_client` / `create_model_response` 被 smoke 和 `ModelCompanionProvider` 直接复用，没有另造 Eval Provider。成功的真实调用证明当前模型名、认证、流式 Chat Completions 与 SDK 转换链可工作，不代表所有参数/模型组合已验证。

安全日志仅保存异常类型链、允许格式的 Provider 错误码、HTTP 状态、去凭据端点、用量与时长，不保存 Key、上游错误消息/错误响应体或思维过程。`provider_smoke_01.json`、`provider_smoke_loopback.json`、`proxy_probe.json`、`proxy_connect.json` 构成诊断证据。

新发现两次独旅请求 `finish_reason=sensitive`，状态 `incomplete`、usage 缺失：固定集 A 一次，独立有界补跑 C 一次。过滤的更深原因未查明；不改写为 JSON 解析问题，不自动格式重试，不把缺失 Token 填成 0。原 A 记录保留当时粗分类 `planner_invalid_output`；最小修复使后续未完成输出明确带现有 `planner_incomplete_output` 码，补跑验证了该分类。

## 2. 实际执行范围与比较规则

先执行 `history/followup/source_valid/forecast/planning` 五例三组，15 组完成，确认逐行持久化、引用、观测与 usage。随后执行原始固定集，未修改问题、上下文或规则；另行冻结 7 道留出题。所有 A/B/C 均使用同一模型配置：reasoning low、max output 8000、temperature 1.0、top_p 0.95、Provider 重试 0、最多一次 JSON/schema 格式修复。

| 记录 | 执行完成 | 有效输出与边界 |
|---|---:|---|
| `representative.json` | 15/15 | 12 Companion 答案 + 3 纯 Planning 路由 |
| `fixed18_real.json` | 54/54 已尝试 | 47 Companion 答案、1 过滤失败、6 纯 Planning/重规划路由；不是 54 次 LLM 成功 |
| `holdout_real.json` | 21/21 | 21 Companion 答案，涵盖明城墙、借景、昆曲/云锦、偏好、虎丘文献、预约、否定出处需求 |
| `dialogue_real.json` | 12/12 | 9 Companion 答案 + 3 PlanningBrief；原目的地检查失败，见修复 |
| `solo_repeat.json` | 3/3 已尝试 | A/B 有输出，C 被过滤；独立记录，不替换原批次、不拼接全成功样本 |

固定集和留出集各题三组输入与历史完全一致。长对话使用各组实际上一轮回答继续，因此后续上下文不同，属于纵向产品验证，不能混入固定上下文的匹配质量均值。

A 为 general_only；仍遵守明确来源、动态事实与原规划理由合同，不绕过合同强迫模型回答。B 为 forced_rag 压力对照，不代表历史生产所有请求的实际行为。B 常直接渲染来源/缺口而不调用模型，故这是三种运行策略比较，不是 54 份纯 LLM 生成的消融实验。C 为 selective + gate。当前 Companion 真实检索为 lexical/BM25；Vector/Embedding/RRF 未在此次运行调用，也未改动。

实时 FactTool 故意缺席，三组一致：测的是不可验证时降级，而非 AMap/Weather/Search 实际线上查询正确性。Reader 是只读夹具，不读取正式 Trip/用户记忆。正式 itinerary 解释本轮只覆盖原理由缺失的边界；有效 accepted Revision 解释仍依赖既有回归，未做生产数据真实回放。

固定顺序串行 A→B→C，单次采样，Provider 存在缓存与性能波动；没有随机化调用顺序、重复采样置信区间或固定生成 seed。不要把小差异归因于检索或宣称统计显著。

## 3. 六维评审与事实核查

量表在读取完整答案前冻结于 `rubric.json`；1 严重错误、2 明显缺陷、3 基本可用、4 良好、5 充分满足。准确性、相关完整性、自然程度、个性化、来源支持、不确定性分别评分，各自有理由。诚实拒答可以准确且安全，但不能因此获得完整性高分；普通知识未要求资料时不因没有引用扣分；要求出处却无法给出，来源支持为 3。

`blind/blind_packet.json` 为随机匿名顺序和用户可见来源；组别/决策/debug 隐藏。`blind/blind_key.json` 分离映射。`blind/ratings.json` 先落盘，再生成 `review_unblinded.json` 和 `comparison_summary.json`。每题完整回答、六项分数、六项理由、核查状态/来源均可追踪。

限制：单一 Codex 评审，措辞可揭示策略；修正来源导出时查看过一个已知 C 来源题实例。不是独立人类双盲，不把评审模型偏好当事实证据。涉及专业细节、精确数字、当前人流/价格或活动而无法完整核查，准确性标 null/PENDING，不给“看起来正确”的分数。

独立依据包括 [UNESCO 西湖](https://whc.unesco.org/en/list/1334/)、[苏州园林](https://whc.unesco.org/en/list/813/)、[官方园林借景说明](https://lhsr.sh.gov.cn/jnylwh/20200824/7cc5e5102094470b94a8f771808c1f53.html)、[南京历史沿革](https://tb.nanjing.gov.cn/njjj/lsyg/)、[南京城墙资料](https://www.nanjing.gov.cn/xxgkn/jytabljggk/2023njytabl/shirddbjy/202312/t20231205_4115215.html)、[秦淮灯会国家非遗档案](https://www.ihchina.cn/art/detail/id/15014.html)、[UNESCO 昆曲](https://ich.unesco.org/en/RL/kun-qu-opera-00004)。这些资料用于评审，不回填成模型当时检索证据。

以下仅逐维匹配平均，不计算总质量排名：固定集除 solo 后 15 个完整 Companion 三组；准确性仅 9 个三组均可判定的题。规划路由不评对话质量。

| 固定集，1–5 | A | B | C | 匹配题数 |
|---|---:|---:|---:|---:|
| 准确性 | 4.67 | 5.00 | 4.56 | 9 |
| 相关性/完整性 | 3.07 | 2.07 | 3.27 | 15 |
| 自然程度 | 3.20 | 2.53 | 3.27 | 15 |
| 个性化/上下文边界 | 5.00 | 4.80 | 5.00 | 15 |
| 来源支持 | 4.53 | 4.73 | 4.67 | 15 |
| 不确定性/安全 | 3.80 | 4.60 | 4.00 | 15 |

| 留出集，1–5 | A | B | C | 匹配题数 |
|---|---:|---:|---:|---:|
| 准确性 | 4.75 | 5.00 | 4.50 | 4 |
| 相关性/完整性 | 3.86 | 1.43 | 3.86 | 7 |
| 自然程度 | 3.43 | 2.00 | 3.29 | 7 |
| 个性化/上下文边界 | 5.00 | 4.57 | 5.00 | 7 |
| 来源支持 | 4.71 | 4.71 | 4.71 | 7 |
| 不确定性/安全 | 4.14 | 4.29 | 3.86 | 7 |

B 多数拒答，因此“准确性 5”主要意味着没有提出错误事实，不意味着回答最好。大量题目无个性化需求，相关维度的 5 表示不虚构上下文；真正偏好题 A/C 均利用明确偏好，B 多数忽略。待核验事实被排除，以上准确性均值不能代表全题事实准确率。

## 4. 成本与真实延迟

| 固定 18 题 | A | B | C |
|---|---:|---:|---:|
| Companion 题 | 16 | 16 | 16 |
| RAG 调用 / 比率 | 0 / 0% | 12 / 75% | 5 / 31.25% |
| 模型实际调用 | 9 | 1 | 10 |
| 已报告输入 Token | 9,674 | 2,214 | 12,851 |
| 已报告输出 Token | 3,310 | 211 | 3,803 |
| 已报告总 Token | ≥12,984 | 2,425 | 16,654 |
| usage 缺失调用 | 1 | 0 | 0 |
| 平均整轮延迟（含降级/失败） | 5.250s | 0.426s | 5.671s |
| 中位整轮延迟 | 4.443s | 0.093s | 7.359s |
| 成功模型生成轮平均延迟 | 10.149s | 5.194s | 10.013s |
| 累计本地检索时间 | 0 | 12.963ms | 4.384ms |

C 的 followup 出现一次生产格式修复，两次调用均计入 3,409 Token 和 10.678s。第一次非法结构文本未单独保存，仅最终有效答案及两次 Provider usage/status/时长保留，无法事后还原具体 schema 违例。不把修复调用隐藏。

排除缺失 solo，完全匹配的 15 题总 Token A/B/C = 12,984 / 2,425 / 15,116；C 比 A **增加 16.4%**，平均整轮 5.456s / 0.432s / 5.439s，A/C 几乎相同。这比使用包含缺失 usage 的全批次总数做比例更可信。

| 留出 7 题 | A | B | C |
|---|---:|---:|---:|
| RAG 调用 | 0 | 6 | 1 |
| 模型调用 | 5 | 0 | 6 |
| 总 Token（全部已知） | 8,934 | 0 | 10,346 |
| 平均整轮延迟 | 9.280s | 0.172s | 8.496s |
| 本地检索累计 | 0 | 0.094ms | 0.016ms |

留出 C Token 比 A 增加 15.8%，平均延迟低 8.5%；C 出现额外格式修复调用。检索耗时非常小，因为 unsupported_query 提前退出；不能拿它估算大知识库/Embedding 开销。B 快且低 Token 的主要原因是未生成有用回答，不能视为性能优化胜出。

真实多轮 A/B/C 模型调用 3/0/3，总 Token 7,861/0/7,853，前 3 轮平均 14.977/0.198/14.670s；不同历史长度影响 Token，不混入匹配实验。所有原始逐轮时间和 usage 都已保存。未测生产并发、首 Token 延迟或财务成本。

## 5. 成功、失败与验收判断

- 有效来源：西湖入遗年份 C/B 正确答 2011 并关联真实 UNESCO 断言，A 因合同缺来源降级。RAG 的收益是来源真实性及完成特定可支持问题，不是靠模型续写填补史料。
- 普通问题：苏州借景 A/C 都给出通俗定义与北寺塔例子，B 因覆盖不足拒答；独立园林资料支持核心例子。南京/苏州通用介绍不必因缺本地语料拒绝，C 与 A 相近。
- 专业检索不足：西湖碑刻训诂 C 丢弃无直接支持的资料，回退一般模型，但具体学术概括仍待核验。B 给出大段西湖景观背景，偏离问题。此次没有证明专业 RAG 提供了直接学术增益；必须用具体碑刻/拓本及专家核查再评。
- 来源缺口：南京文献、虎丘版本三组仍无法提供资料，诚实但模板化。不能以拒答安全掩盖覆盖不足或用户体验问题。
- 动态问题：天气、开门、今年灯会、明天预约三组均没有模型生成猜测；但回答统一列天气/开放/票价/交通，对“预约名额”及“灯会日期”不够贴切，查证指引不具体。
- 隐含动态断言：C 的苏州偏好回答 Q021 写“几元一杯茶的茶位费”，followup Q035 写“行人少”；A Q044 写“几乎不用排队”。真实多轮 A/C 又出现固定人流高峰与保证安静的表述。输入知识决策安全不等于输出不会夹带状态事实；这项安全门禁仍 OPEN。
- 通用事实错误：C Q062 的鸡鸣寺/同泰寺时代与关系混淆，独立[南京地方志](https://dfz.nanjing.gov.cn/gzdt/202603/t20260304_5799793.html)说明两寺关系不可如此简化；A Q063 把白堤描述为白居易留下的堤，独立[白堤史鉴](https://www.ccdi.gov.cn/lswhn/shijian/201902/t20190227_29393.html)明确今白堤与白公堤不同。六朝 360 年的说法可能指 229–589 年跨度，不能简单判为累计建都 360 年错误；报告将年代与遗址关联分别标明，避免误判。
- formal 边界：自然对话 9 轮全部 Companion、无 Handoff/PlanningRun；最终明确规划均转 Planning、无额外 Companion 模型。原三份 Brief 的目的地错误已真实复现，下面的最小修复后回放均正确。未创建 itinerary、Revision 或正式规划候选。

优先级：P1 为建议输出中的未验证价格/排队/人流断言，以及 benign solo 请求的 Provider 过滤不稳定；P2 为专业回退细节核查、降级模板的具体查证路径、来源请求缺口、过长/不必要的摄影建议。目的地 Handoff 缺陷已修复。此轮不通过扩库、画像或泛化正则替换来掩盖这些问题；提示词已经禁止动态事实，仍需基于上述坏例建立输出层最小可验证方案。

是否 C 比 A 好：覆盖充分的明确来源题更好；普通题大体持平，且有事实错误，不能全面肯定。是否 C 比 B 好：完整性和自然程度在本集明显较好，但 B 的拒答安全更高。RAG 哪些无收益：B 的未覆盖城市查询、碑刻问题的背景命中；C 的小众查询虽安全丢弃，却未取得专业直接证据。是否继续改专业检索：应先形成直接支持的专业留出材料与人工核查，现有证据不支持大规模改检索算法。

## 6. 本轮最小修改与回归

生产 app 仅两处增量：

1. `companion_provider.py`：未完成/过滤输出带现有 incomplete 错误码；不增加过滤重试、不伪造成功。
2. `companion_state.py`：只有经 Router 明确授权的 `build_planning_brief` 可以绕过文化知识文本的目的地过滤，当前明确“南京三天”优先于历史比较目的地。知识问答及否定规划仍不授权。

评估增量：`companion_provider_smoke.py`、`companion_quality_dialogue.py`、`companion_blind_review.py`、`companion_quality_report.py`、`companion_source_manifest.py`；原 runner 增加指定夹具/用例、安全失败分类、选择性继续、配置/历史/usage 记录；新增七题 holdout 和五项有意义的回归测试（两城市授权优先级、过滤错误不重试、安全日志、匿名导出）。没有重新设计 Router/Agent、检索算法、Validator 或正式 itinerary 写入边界。

`handoff_replay_after_fix.json` 直接使用原多轮真实历史，A/B/C 三份 Brief 均为南京/三天、prepared、偏好来源和授权轮保持，0 新模型调用；不是新一轮生成，也不是 Mock 冒充真实对话。

回归与源文件绑定以 `verification.json` 为准。完整后端通过隔离 Linux/Python3.11/新空 PG17 tmpfs、独立 Compose 项目测试；909 个用例包括工作树既有 Planning 评估测试与本轮五项新测试。Web 125 项、typecheck、build 均通过。`backend_test_image_manifest.json` 记录被测 app/tests/锁定依赖哈希；当前 app/tests 与镜像一致。后续只新增评估报告/分析工具时单独记录，不迁移未被镜像覆盖的通过声明。

保留失败过程：首次本地快速回归误选含 DB 用例文件并已中断；隔离不可连接端点复现 Windows Psycopg 在连接前拒绝 ProactorEventLoop，该本地 DB 回归不算通过。匿名导出测试初始使用不符合合同的字符串 evidence，修为合法字典 fixture 后通过。一次 Compose 回归虽输出 909 passed，但同时启动的镜像诊断容器继承 Compose 标签，触发 abort，使包装进程非零/测试容器137；原日志保留，不算 clean exit，之后以隔离 `compose run` 重新迁移和完整回归，取得正常退出。全部数据库测试最终只在临时 PG 执行，未改生产数据库。

## 7. 复现

在仓库根 PowerShell，只给当前进程设置本机可用代理，不保存 `.env`：

```powershell
$env:PYTHONPATH='backend'
$env:PLANNER_PROXY_URL='http://127.0.0.1:7897'
backend/.venv/Scripts/python.exe -m evals.companion_provider_smoke --output <新目录>/smoke.json
backend/.venv/Scripts/python.exe -m evals.companion_knowledge_strategy --real --continue-on-error --output <新目录>/fixed.json
backend/.venv/Scripts/python.exe -m evals.companion_knowledge_strategy --real --continue-on-error --fixture backend/evals/fixtures/companion_quality_holdout_v1.json --output <新目录>/holdout.json
backend/.venv/Scripts/python.exe -m evals.companion_quality_dialogue --output <新目录>/dialogue.json
```

选择新输出目录，不覆盖本次原始证据。认证/连接/超时/限额类错误停止；有界 schema/incomplete 错误只有显式 `--continue-on-error` 才继续。没有回答的题不评分或插补。`run()` 返回 complete 仅表示遍历结束，不表示全成功。

未完成：独立人类复评、专业材料完整核验、成功实时 Provider 查询比较、真实 accepted Revision 解释、生产全链/E2E、重复采样统计、过滤根因。保持 C 默认的工程建议与上述质量门禁状态分别记录。
