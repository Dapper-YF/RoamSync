# Travel Companion Phase 2.5 — Final Acceptance

2026-09-30，Asia/Shanghai。**Phase 2.5 COMPLETE**：本轮限定的修复、评审、最终回归、正式重建与八项 smoke 已完成。不代表知识覆盖完整或普通模型事实已验证。

最终 backend 源码/测试/eval/migrations/依赖清单 SHA256：
`9c73bb878924d5f6d59e4e6f13f35e945cfe41ac3fcca1540dee3b0351849887`

机器验收：`backend/evals/results/companion_phase25/final_verification.json`；细项与原始输出：同目录 `final/`。HEAD `5572849209c943c5f5ad1579db4cef0ba2fb5b25`、branch `main`；验收对象为真实 dirty working tree，不是仅凭 HEAD 的提交快照。测量时间 UTC `2026-09-30T06:27:07.749413+00:00`，对应上海时间为 UTC+8。

## 1. Starting Reality

重新检查 git tracked/untracked、HEAD/branch、LATEST_HANDOFF、PROJECT_STATE、Phase 2/Conversation Policy、当前 tests/evals 与源码/容器。上一轮完成的短句探索 Router 修复仍在，未把历史失败直接认作当前失败；大量既有 dirty work 原样保留，无 commit/reset/index 改动。

当前真正缺口：明确“把第二个放进第二天下午”未命中动作；“800左右”“下午吧”“国庆第二天出发”“第二个”未续接已授权澄清。新真实长句链另复现“南京它是一个怎样的城市呢”被无主语代词规则阻断。上一轮 smoke 只有六项，本次需要八项；机器汇总与报告结构也须补齐。

正式环境起初因 PostgreSQL 停止而无法解析 postgres host；恢复时发现原宿主机55432落在 Windows 排除范围55415–55514。保留原数据卷，仅把本地 `.env` 的 POSTGRES_HOST_PORT 改为54329后恢复依赖；未改凭据/数据库内容/Compose业务逻辑。此次环境恢复与路由源码修复分别记录，见 `final/reality_recheck.json`。

## 2. Active Slice Scope

复用现有 Independent Companion Runtime、Suggestion stable identity、多轮引用、PlanningBrief、KnowledgeToolPort/adapter、Claim Model、applicability/attribution、Natural Renderer、general knowledge path、最小上下文、PlanningProgress、Ledger/Memory基础。Web普通loading仍“正在回复…”。

本次仅补Router字段/动作、现有引用解析bug及验收证据。上一轮prompt/renderer/need/provider最小修复保留且在新快照重新验收。未新增Agent、Phase、工具、语料、embedding、Travel Facts或Companion Weather；未重建任何已有能力、Planning Graph或正式审批边界。无Obsidian写入。

## 3. Router Root Cause

最初 `_NEW_TRIP` 将出游愿望、目的地、日期、时长误当创建授权；上一轮已移除这条宽规则。本次剩余是明确动作“放进”和受授权字段答复词形的召回缺口，不能靠完整句黑名单解决。

## 4. Router Fix

保留明确动作优先与信息/否定guards；新增“放进”动作，接受有界的无币种金额、时段、节日出发日期、无“就”的序号回答。目的地/时长本身仍不授予authority。字段答复仅在最新有效Planning上下文续接；未授权、单独pending action、cancelled/failed/rejected仍拒绝继承。

已有authorized clarification协议不改：runtime=planning、mutation_requested=false，authority来自先前明确请求；不是每次字段答复发起新变更。明确Planning/mutation请求仍mutation=true。Focused同时测试正例、无上下文、Companion历史与取消上下文。

## 5. Conversation Policy Alignment

普通与source prompt都先回答当前问题，探索为有效终点；明确Planning前不催日期/预算，不重复CTA，允许偏好/节奏问题。复用recent context，无CTA状态机。

最终真实长句链无多余planning-slot问题、重复CTA均0。模型仍会给示例三日玩法或强语气一般建议；这些不具有mutation authority，也不属于已验证source facts。

## 6. Grounded Response Fixes

现有renderer保留正文/claims/metadata分离：有支持背景时仍自然说明确切形成年份缺口；curator/agent inference及recommendation保留条件/建议语气，不冒充来源机构观点。内部topic key不进入正文，原metadata保留。无新renderer。

上一轮已修source refs与assertion IDs混用、enum/extra-field说明、一次有界schema/完整JSON修复（最多两代，第二次错误仍失败）。raw string newline可规范化，尾随文本/多对象/越权字段不以prefix salvage接受。当前provider真实批次format repair=0，不保证未来可用性。

本次引用解析只让有明确命名主语的“南京它是…”不被当成无指向saved suggestion；不推断place ID，不创建新identity。真正无主语“它是怎样的地方”仍澄清，既有序号/名称/代词测试通过。

## 7. Eval Protocol Versioning

v2协议见 `docs/agent/COMPANION_PHASE25_EVAL_PROTOCOL_20260930.md`。七类mode：general_conversation、source_grounded_knowledge、recommendation、exploration_non_planning、live_fact_required、decision_explanation、explicit_planning。

每case标记protocol_version并记录expected goal/runtime/mutation/knowledge/planning allowed/answer mode/evidence；manual review补充reviewer-assigned目标。原holdout无独立goal taxonomy，明确标为not independently labelled，不能拿当前router输出当独立goal正确率。普通稳定问答允许 `model_general_knowledge_unverified`，明确来源请求才要求RAG；live/original-rationale边界优先。

## 8. Holdout Method

原50条 `holdout_v1.json` 字节/expected labels不变，hash `07505a83aa6921639f70f82af4670a1a6624b038000cf5a849757e718ddeec22`。旧pending字段归档不改；50条当前评审保存在新结果中。

旧协议默认knowledge→RAG；保留原wording的controlled routing/need诊断，仅对原knowledge-required case附加明确来源请求重放。变换逐题记录，解封后用于修bug，**非盲回归**，非新blind holdout。未改expected断言IDs来追分；不同ID的等价表达不自动算exact通过。上一轮final及报告在 `prior_closeout/` 留存，与本次快照分开。

## 9. Holdout Results

50 reviewed/pending0/errors0；13次实际model generations，事实/live分支确定性执行，不能说50次模型生成。Runtime与planning authority50/50；旧need标签39/50（78%），原exact assertion coverage34/50（68%）；检索related43/44。

`hist_04`把人工堤岛时期误作地质形成，漏用已有断言；`profile_02`误取老人guidance后未答地理问题。每题记录need/relevance/sufficiency/claim/scope/attribution/recommendation/usefulness。未标注原fixture的goal准确率不虚构。

## 10. Claim-level Review

单Codex reviewer；检查实际断言文字/type/scope与source metadata，不仅citation存在。没有新的独立官网核验或通用entailment保证。General回答不纳入verified-source分母。

|批次|supported source facts|partially supported|unsupported structured source facts|not applicable inference|recommendation not fact|
|---|---:|---:|---:|---:|---:|
|Real|14|0|0|7|4|
|Holdout|57|0|0|32|26|

另记holdout `rec_02`建议中的“苏堤或白堤”命名线路细节：提供的断言未支持，**1条unsupported embedded detail**，不能归入supported来源知识。“unsupported structured source facts=0”不意味着所有输出无unsupported内容。上一轮可选日期邀请/修辞引文是历史批次问题，本次未再出现，不混入当前分数。建议的安静程度、晨昏光线、经典构图等隐含判断仍未验证。

## 11. Real Model Evaluation

16 scenarios/errors0，实际provider generations8，fake0、format repairs0。确切使用新要求的长句链：你好→过几天国庆/独行无聊→目前三四天→你觉得南京怎么样→南京它是怎样的城市→南京老街巷→听起来不错帮我规划南京三天。最后Brief prepared、南京、3天；没有Suggestion自动变Activity。

另覆盖supported fact/summary、unsupported精确detail、attribution/applicability traps、source建议、general问答、live关门时间、缺原始18点rationale。六轮连续性经输出评审：当前担忧/时长/南京/文化承接存在，明确命名主语不再过度澄清。General仍可能主动提国庆拥挤、预约/秋叶等未经实时核验判断，不能当当前facts的准确性测量。

原始before_named_subject_fix结果保留。修复后重新snapshot/live/holdout/focused，未使用前一候选数字冒充最终结果。

## 12. Planning Authorization Metrics

Real goal15/16（93.75%，source文化摄影recommendation被分为explanation）；runtime16/16（100%）；提前Planning authority0/6（0%）。Holdout authority50/50。SQL集成证明六轮探索PlanningRun增量0，随后明确Planning增量1且Trip.version未变。

Standalone live eval无DB/mutation port，不能冒充DB证明。正式预旅行smoke最后进入Brief/Planning日期澄清，未确认创建trip或执行完整规划；正常确认边界保留。

## 13. Grounding Metrics

14+57条结构化source facts在当前提供registry文字/scope内支持，unsupported structured rate0/71；部分支持0不表示题目级证据完整。额外建议内unsupported detail单列，未纳入这71分母，不能宣称全输出事实错误率0。

Bounded applicability/attribution复核未发现结构化source事实扩大scope或错误publisher观点（14/14、57/57）。一般老人规范不能证明杭州一定适合父母；没有精确形成年份/UNESCO官方摄影推荐则自然显示缺口；当前营业时间及缺原rationale诚实降级。知识证据不补写历史Planning rationale。

## 14. Answer Coverage

Real16/16有回应或Brief，但实质内容10/16（62.5%），部分/诚实限制5/16，planning转换1/16。多余slot0/16，重复CTA0/16；不是以拒答换完整覆盖。

Holdout28/50实质有用（56%）、14/50部分/有限、6/50安全live限制、2/50遗漏/不相关。48/50有一定帮助不等于96%完整回答。过度保守/unused已有source见hist_04及若干partial case；mixed live安全降级会漏稳定子题，记录成本。

## 15. Tool Selection

Real TP6/FP0/FN0，precision/recall1.0；source holdout TP44/FP0/FN0，precision/recall1.0，仅适用显式协议集合。Unnecessary calls0。工具调用正确率不能替代43/44相关性、34/50断言覆盖或答案准确性；普通general不强制RAG。

## 16. Files Changed

本次实际修改 `backend/app/travel_goal_router.py`、`companion_state.py`、`backend/tests/test_phase25_final.py`、`backend/evals/phase25_final.py`。另更新review/smoke/binding/report脚本、protocol/report/handoff/artifacts、本地端口字段。

上一轮本Slice改动保留：companion_provider/graph/information、assistant_tools/conversation_regressions测试、diagnostic与验收工具；都在当前final manifest验收。整份git dirty清单不是本轮归因。核心service/graph/adapter/contracts等受保护哈希见audit_binding；Web/Android本轮无改动。

## 17. Focused Tests

最终 **164 passed/0 failed/0 skipped**，JUnit `final_focused.xml`。涵盖探索反例、明确动作、授权字段、未授权/取消、命名主语vs代词、partial gap、qualified advice、schema repair及SQL边界，并回归现有Companion/assistant/routing/conversation。

开发阶段复用 `roamsync-test-postgres-test-1` 与现有test image挂载app/tests；未每次fix重建baseline/database。第一次本次focused163，命名主语修复后164，最终当前artifact为164。

## 18. Full Regression

Linux/Python3.11/PostgreSQL17、alembic upgrade head、完整pytest：**650 passed / 0 failed / 0 skipped / 2 existing Starlette warnings，55.97s**；`final/backend_final.xml/log`。本次最终test image构建一次，代码冻结且real/holdout完成后full执行一次。

历史542/568失败/587/上一轮632不能替代650当前证据。上一轮第一次full预算fixture失败保留于prior_closeout（631+1）；旧隐式创建输入纠正为明确规划，预算/原子性/审批断言保留。机器汇总包含HEAD/dirty身份、逐文件hash、JUnit失败数、holdout协议/results、真实输出artifact、Web、images与measured_at。

## 19. Web / Android Validation

Web源码hash与已验收artifact一致：123 tests/20 files、typecheck/build PASS；本次未改Web，复用相同Web源码的已有检查，明确非本次重新测量。Web容器未重建，页面HTTP200、healthy。

Android contract未变，本次不机械开发或重跑；不以历史Android数字冒充当前新验收。Demo rehearsal NOT READY、Ledger Stage2.2 OPEN保持。

## 20. Production Container Rebuild

全部gate通过后 `docker compose build api agent-worker`，再 `up -d --no-deps --wait api agent-worker`。正式production target独立构建，非test容器晋升。日志在final production_build/startup。

|容器|Image ID|状态|
|---|---|---|
| roamsync-api | `sha256:2928e791cfa76a6bc8557cda4dcc050c9ebbf17727e3c3b68a1629a4b6626a8d` | healthy |
| roamsync-agent-worker-1 | `sha256:e7f9689c756e3cbebc5aedd201942e4c13f3a5bde2ea730e6a6a25b0d9b44ceb` | running |
| roamsync-web | `sha256:9794c7029f6ca25800174e7072d701065df2b6bbff6110dd168f4c6b614f99b8` | healthy |
| roamsync-postgres | `sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73` | healthy |

API/worker各144运行文件逐项匹配最终manifest。API live/ready与Web/trips HTTP200。Worker进程记录 `production_worker_process.log`；Docker未配置worker healthcheck，running不冒充完成远程规划。生产alembic current=`20260924_0034 (head)`，`production_migrations.log`；环境恢复前DNS错误与恢复后启动分别披露，不把旧错误当当前源码失败。

## 21. Production Smoke

正式真实HTTP八轮：你好→独行顾虑→玩三四天→南京怎么样→普通南京城市知识→可靠资料西湖历史/形成年份→今天景区关门→明确南京三天规划。

**8/8通过**：前七轮Companion/mutation=false；普通知识保留unverified且无retrieval；source有支持背景并显示具体年份缺口；live标记live_verification_required不猜；最后prepared Brief/Planning日期澄清。详见 `final/production_smoke.json`。

独立synthetic session；无Demo reset、候选/旅行确认；前后Trip/Run数量与全部Trip.version一致，formal_state_unchanged=true。现有真实数据与会话不删除；保留smoke会话。源码hash、smoke、health、images与结果统一绑定在final_verification。

## 22. Remaining Limitations

非盲holdout；need39/50、exact coverage34/50、goal15/16；source建议一条未由断言支持的命名路线细节；general与建议隐含事实/实时假设未验证；单reviewer与bounded registry评审不能证明通用entailment或来源网页当前状态。

Router/subject判断为有限规则。模型未来超时/无效JSON/服务不可用仍可失败；最终errors0不是SLA。没有Travel Facts：当前facts安全限制，mixed子题覆盖受损。明确Planning仍需日期/确认，不宣称smoke完成规划。

## 23. Deferred Issues

已有来源topic recall（地理/茶地点/持续时长/UNESCO title）、人工堤岛与地质形成区分、mixed子题覆盖、建议隐含事实核验、general输出未经实时核验的拥挤/预约/秋叶判断、独立未解封评估。除阻塞此次退出的命名主语/路由bug外未扩开发。

未cherry-pick5f9f5e5，未接Travel Facts/Open-Meteo到Companion、Weather Agent、FactResolver、embedding、长期Memory、Experience扩展、Stage2.2或复杂Citation UI；无新Phase/Agent/Runtime/Renderer/Identity/Brief。

## 24. Recommended Next Slice

仅在用户选择后：现有来源回答覆盖与独立冻结评估，先冻结新fixture/标签，再检查检索遗漏、mixed答案、建议内隐含事实。复用已完成组件与审批边界。本轮结束，不自动启动新Phase。

# CHATGPT HANDOFF SUMMARY

CURRENT SLICE: Phase 2.5 COMPLETE。
ROUTER: 探索不授权；新增动作/字段续接与明确主语bug修复。
NATURAL CONVERSATION: 长句六轮无提前Planning/slot追问/重复CTA；最后明确Brief转换。
KNOWLEDGE RELIABILITY: source gap/attribution/applicability保留；general unverified；建议内未支持detail单列。
HOLDOUT: 50 reviewed、原fixture未改、非盲；runtime/authority50/50、need39/50、exact34/50。
REAL MODEL: 16 scenarios/errors0、8实际generations、runtime16/16、goal15/16。
BACKEND: focused164、full650/2 existing warnings；最终源码绑定。
WEB: 同Web源码123/typecheck/build证据复用，HTTP200。
ANDROID: 契约未变，无本次重跑。
PRODUCTION: API/worker重建、hash匹配、migration head、八轮smoke通过且正式状态未变。

KNOWN LIMITATIONS:
- 有限检索覆盖、单reviewer、general/建议事实未验证；非盲评估。
- Demo NOT READY / Ledger Stage2.2 OPEN。

DO NOT REDO:
- Runtime/Renderer/Identity/Brief/Adapter；不新增Phase/Agent/Travel Facts。

NEXT RECOMMENDED SLICE: 经用户选择后的已有来源覆盖与独立冻结评估。
