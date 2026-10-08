# Official Opening Schedule Collector Lifecycle — 2026-10-01

**CURRENT SLICE: PARTIAL. REGULAR + EXCEPTION READINESS: NOT READY.**

VERIFIED：增加离线官方列表collector、显式完整性门禁、文件审核生命周期；没有接入生产Fact查询路径。MEASURED：两站实际分页和二次稳定性复查完成，两条v1已审核公告重新发现。浙博历史空正文及未审核候选阻断完整例外判断。生产继续使用v1已验收实现，不能称生产collector生命周期已启用。

证据目录：`backend/evals/results/opening_collector/`。离线最终源码manifest：`d98284b9f4c6590c2c6acc16ddf30eef0d9104551fb03305b54a1bc38b1f67d1`；生产保留：`fc3a06ba3cf95aaa6317f95f3b3cc300d2dd582299ac24ac7b91dce995f3bdfb`。结果JSON/XML优先于本文摘要。

## 1. Starting Reality

VERIFIED：实际主仓库E:\Study\RoamSync，main/HEAD5572849209c943c5f5ad1579db4cef0ba2fb5b25；保留已有dirty work，没有commit/reset/clean/stash/merge。开始前读取handoff、PROJECT_STATE、前轮报告与现有源码。v1通过固定已审核notice ID和有限列表解析发布时间/适用日安排；没有全列表分页、collection completeness、hash重审或列表schema生命周期。常规周表未作为目标日verified，当前运营和临时闭馆不存在全渠道保障。Reality Audit在实现前已向用户报告。

## 2. Collector Architecture

VERIFIED：`app/travel_facts/official_collector.py`负责官方请求→列表分页→schema/内容归一化→范围分类→review匹配→独立accepted snapshots。`evals/opening_collector.py`负责实源采集和JSON审核工件。它们没有注册进composition、Companion或Agent；无DB/新表/Redis/Memory/新Agent/新Fact类型。仅复用原opening_hours纯解析函数，并提供accepted_payload桥接。新来源未通过门禁前不改变生产真源。

## 3. Existing Source Audit

|Source|Canonical venue|API / scope|现实风险|
|---|---|---|---|
|nanjing_museum|amap:B001907TGR/main|https://www.njmuseum.com/api/news/freshNotice；language=zh|包含非运营公告、重复条目、局部展厅公告|
|zhejiang_museum|amap:B0I15SU50Z/之江馆区|https://www.zjmuseum.com.cn/api/content/page；siteId22/categoryCodeNotice|多馆区、缺正文、历史公告；不能把孤山安排赋给之江|

只认可配置官方HTTPS域名/section。来源返回文本作为数据，不具备指令或工具权限。

## 4. Discovery Strategy

VERIFIED：入口只依赖官方域名、endpoint、栏目、pageNum/pageSize。发现请求不输入notice ID；抓到全列表后才与v1既有审核内容hash对照。ID只用于记录、去重、review匹配及旧reviewed parser兼容，没有用“已知ID请求详情”冒充发现。没有搜索摘要、模型挑公告或第三方替补真源。

## 5. Pagination Semantics

MEASURED：两站pageNum有效；page/pageNo/currentPage探针返回第一页，证据`pagination_parameter_probe.json`。真实两站均采用total模式，pageSize100。检查total不变、页元数据、每页预期长度、物理条目总数、重复页、同ID变更、max_pages上限；完整扫描后再次获取每一页并比对完整payload hash，检测顺序或内容漂移。空中间页/请求失败/total变化/顺序变化均collection_incomplete，accepted输出为空。通用cursor分支有fixture验证，**未宣称两站真实cursor支持**。

## 6. Completeness Definition

VERIFIED：pagination_complete仅表示配置列表所有物理页按CMS total耗尽且二次观察稳定；schema_status与此独立。collection_status可为complete、collection_incomplete、schema_changed。exception_scan_complete还要求schema有效、无待审核/不明确范围。complete并不等于所有候选accepted，更不等于官方所有渠道无例外。总数按列出的物理条目计，重复ID另去重，不强迫unique count等于CMS total。二次复查是观察稳定性，不是CMS事务快照。

## 7. Venue / Branch Scope

VERIFIED：SourceProfile固化canonical venue、机构、branch、domain、endpoint、section、alias、schema_version及parser_profile。南京“南京市博物馆”标other_venue；局部展厅/非遗/停车场等标subvenue，不自动提升主馆truth。浙博正文明确之江才进入该branch；仅孤山及含糊范围待审，多馆区保留整篇并标multi_branch，旧parser另有section门禁。词法分类是候选提示，不替代人工审核，也不声称理解所有别名/分馆写法。

## 8. Candidate Filtering

VERIFIED：title+正文中开放/开馆时间、闭馆、停止入馆、维修等产生operational候选；只有国庆展览词不自动认定运营安排。空字符串正文明确review_required，null/字段缺失schema_changed，绝不当“没有例外”。保留原始notice、标准正文、机构/范围、发布日期/更新时间、date hints及hash。publication和年份提示不生成effective date，accepted review必须显式填写适用范围。

## 9. Schema Contract

VERIFIED：列表response成功标记、嵌套位置、rows list、integer total、page metadata严格检查。南京required：id/title/introduction/time；浙博：content_id/title/content/publish_date，时间格式严格；updated字段如有也检查。profile schema fingerprint与各notice HTML标签结构fingerprint分别记录。非法row保留notice ID错误并继续遍历其他页；schema整体无效，不输出accepted truth。

## 10. Schema Drift Detection

MEASURED：required字段删除/重命名、正文类型、时间格式、嵌套变化和已审核HTML包装结构变化有测试。字段drift显式schema_changed；HTML shape变化要求重审，并使schema无效。不会把异常吞成空公告列表。实源浙博第5页notice39496正文null被识别为notice_required_field_type；原因是实际历史坏数据，并非声称官网刚刚改版。

## 11. Content Hash / Source Change

VERIFIED：content_hash绑定ID/title/body/publication/updated；payload_hash保留完整row；semantic_hash用于相同展示内容去重。已审核同ID内容变更→source_changed；HTML结构变更→schema_changed。旧review不覆盖新内容，不“重新抓取即重新accepted”。accepted_payload再次校验raw_notice hash，防工件内容与审核hash不一致。工具的文件review信任显式审核输入；未实现签名、审批身份认证或多版本review冲突仲裁，暂不具备生产自动promote条件。

## 12. Review Lifecycle

VERIFIED：发现记录作为discovery工件保存，随后标review_required/rejected；审核明确accepted/rejected；hash或schema变化分别source_changed/schema_changed；仅有证据的显式修订才superseded。discovered是采集阶段，不是已批准状态。JSON review保存source/notice/hash/schema/venue/branch、reviewer、reviewed_at、reason、effective_ranges和supersedes。CLI例：

```sh
python -m evals.opening_collector
python -m evals.opening_collector --review-input evals/results/opening_collector/nanjing_museum_discovery.json --notice 381205 --review-action accepted --reviewer HUMAN --reason reviewed --dates 2026-10-01 2026-10-07 --review-output evals/results/opening_collector/review-v2.json
```

后一条仅写新版本review文件，拒绝覆盖已有路径；不是生产部署。本轮没有批量批准新公告。默认实源eval只继承v1已有两条确切审核hash；后续review registry组装仍需显式操作，未做后台审批UI或自动版本合并。

## 13. Accepted Snapshot

VERIFIED：candidate列表与accepted_snapshots分离；只有pagination_complete且schema valid才输出accepted列表。南京有1条；浙博review exact match有1条，但全来源schema门禁使accepted-for-use为false，accepted列表0条。不得将“review匹配”混写成“可用真源”。桥接用现有reviewed_schedule/nativeFact语义，无新Fact合同；现有parser仍只理解已审核v1公告格式，新增公告accepted也不代表自动新增parser能力。

## 14. Duplicate Handling

MEASURED：南京342物理条目，1个同ID重复，341候选。浙博562物理条目，1个null-body不能归一化，561候选；其中2个展示内容重复，标duplicate_content/rejected，不成为独立authority。重复页不等于完成；同ID同内容去重，同ID不同内容扫描失败。新notice发布时间较晚不自动supersede；只有显式review.supersedes、相同venue/branch/date范围、较晚publication且包含修订/更正/替代语义，才标旧记录superseded。

## 15. Source Availability

VERIFIED：请求timeout/异常记录fetch_unavailable类型，分页不完整，无accepted输出；不回退旧文件冒充本次可验证完整扫描。官方请求有限timeout/响应大小/page上限。真实结果是本次可用性观察，不承诺未来SLA。离线文件不自动成为生产缓存；保留原v1生产行为与限制，不把offline安全门禁描述为已部署。

## 16. Freshness vs Effective Date

VERIFIED：fetched_at、publication、updated、effective_ranges独立。fresh fetch只说明抓取时点，不能让历史安排变成明天truth；review日期不能代替公告适用日期。南京更新时间unknown，浙博源时间未证明时区，不虚构UTC更新语义。现有live v1仍每次fetch、无跨轮hours缓存。collector accepted review日期范围由人给定，不从发布时间推断。

## 17. Exception Completeness

MEASURED：南京exception_scan_complete=false（89条待审）；浙博=false（schema坏行以及167条待审记录/错误引用）。两站“没有发现针对某日例外”目前不能支持目标日常规时间verified。以后即使门禁通过，也只可表达“配置官方栏目已完成扫描，未发现符合审核范围的例外”，不能表达所有网站/微信/临时渠道没有闭馆通知。

## 18. Regular Schedule Readiness

**NOT READY。** 已实现发现、分页、范围、schema/hash/review工件，但未解决历史空正文、候选有效期/范围审核、review registry生产治理及accepted source接入；官方多渠道覆盖未知。未启用regular weekly + exception组合，没有新增目标日营业时间覆盖。南京列表schema有效也不代表exception complete。

## 19. Files Changed

VERIFIED：源码manifest相较fc3仅新增3文件：`backend/app/travel_facts/official_collector.py`、`backend/evals/opening_collector.py`、`backend/tests/test_official_collector.py`，旧manifest全部文件hash相同。新增本报告及`backend/evals/results/opening_collector/`版本化工件；更新`docs/handoff/LATEST_HANDOFF.md`和`PROJECT_STATE.md`。Router/Identity/Companion/Knowledge/Forecast/Planning/DB/migrations均未改；无新依赖。现有dirty变更不属于本轮改动清单。

## 20. Focused Tests

MEASURED：165/165，failures/errors/skipped均0，`focused.xml`。其中新collector29例，覆盖单/多页、晚页已审核公告、同ID/跨ID重复、重复页、失败/空页/total不一致、cursor终止/缺失/循环、schema删除/重命名/类型、content/HTML变化、accepted/rejected、范围歧义、展览非例外、二次扫描顺序变化、篡改snapshot、显式supersession与历史坏行。另覆盖opening_hours/Companion/native facts/resolver/eval。

## 21. Real Nanjing Source Discovery

MEASURED：四页100/100/100/42，CMS total342，全部二次复查稳定（8次真实page fetch）。无需手填ID重新发现381205，content hash与v1review相同，accepted1；旧parserOct2=09:00–20:00、19:00停止入馆。collection complete、schema valid、exception incomplete。89条候选等待review，没有自动提升。

## 22. Real Zhejiang Source Discovery

MEASURED：六页100/100/100/100/100/62，total562，全部二次复查稳定（12次真实page fetch）。无需手填ID重新发现46554，content hash与v1review相同；**accepted-for-use=false**。第5页39496《春节期间浙博开馆安排》，2016-02-05T14:48:48，content=null。分页完成，collection/schema_changed，accepted0、exception incomplete。历史发布时间不能证明该缺正文的适用范围，未擅自忽略它以通过门禁。

## 23. Pagination Evidence

MEASURED：`pagination_parameter_probe.json`、`page_two_probe.json`、两站`*_proof.json`与`*_discovery.json`、`rediscovery.json`保存实际CMS totals、页大小、逐页payload hash、fetch时点、二次复查标记、去重/错误/停止原因。第二页真实请求不是mock；两站实际全部页扫描成功。cursor和故障注入的测试证据与真实total模式证据分开。实源扫描绑定最终d982源码manifest。

## 24. Schema Change Drill

MEASURED：`schema_change_drill.json`为显式受控演练，将南京required introduction重命名为content。pagination可以耗尽，但schema_changed、错误notice:381205:notice_contract_changed、accepted0、exception false、no_truth=true。另HTML结构drift由fixture验证。演练没有改官网、生产source或原fixture，没有把controlled结果当实源故障。

## 25. Opening Hours Regression

MEASURED：实际CMS验证2/2；real Companion graph20/20，`companion_regression/real_source_validation.json`及`real_companion.json`。包含两馆开/闭、多日期、周一holiday、范围外/未知场馆/景区/当前运营/不支持事实/馆区、显式source failure、same-authority conflict。常规regular resolved仍0；只验证已发布公告覆盖日。失败与conflict标记注入，未称官网真实冲突。collector fail-closed不取代v1 production query path。

## 26. Weather / Knowledge Regression

MEASURED：同一20场景含真实forecast、hours+weather、hours+Knowledge、三种独立失败组合。服务器渲染路径无动态模型猜测真值。Knowledge冻结60例、errors0、runtime/authority60/60，need34/60、type48/60、assertions35/44、mixed7/10、85条来源claim supported，与v1 summary完全相同；不是全部Knowledge问题已修好。旧opening_hours_v1与knowledge_coverage共60证据文件hash完全保留，`protected_artifact_verification.json`。没有改冻结标签或历史outputs。

## 27. Planning / Formal State Safety

MEASURED：real graphPlanning控制正确走Planning Brief；完整后端测试包含原Planning权限/状态测试。collector无DB端口、无Agent执行、无审批操作。生产扫描前后`formal_before.json`与`formal_after.json`精确相同：Trip178、Day349、Activity841、PlanningRun105、Revision35、Execution8、Navigation9，各表完整行hash及所有Trip versions不变，Run delta0。本轮未发送新生产Planning请求；不要把前轮生产10/10 smoke声称为本轮新smoke。

## 28. Full Regression

MEASURED：完成最终一次干净验收：只重建tmpfs postgres-test，生产PG未动；Linux、Python3.11.16、PostgreSQL17，空库alembic一路至20260924_0034 head。最终full pytest **824 passed，2既有StarletteDeprecationWarning**，0 failed/error/skipped，`backend_final.xml`。Foundation28/28，`foundation_benchmark.json`。本轮最终full后无源码变更；`acceptance_summary.json`验证最终manifest、实源/实时/冻结结果绑定及旧源码hash不变。辅助证据脚本首次缺PYTHONPATH导入失败，补足运行环境后成功；不属于pytest失败，也未修改产品源码绕过测试。

## 29. Production Decision

VERIFIED：**NO DEPLOYMENT**，理由是本轮仅新增offline tools，没有runtime query path变更，且源完整性门禁尚不成立。API/worker各167 runtime files仍精确匹配fc3生产manifest（`*-runtime.json`）；API live/ready与Web均200，保留已有生产实现。未重建Web/API/worker或替换任何生产accepted来源。production truth维持v1已审核源，不能因为新collector发现候选就扩覆盖；生产仍有v1的人工ID/有限列表限制。

## 30. Known Limitations

PARTIAL的直接原因：浙博null正文、两站大量未审候选；不能证明exception completeness。范围识别和关键词过滤有限，可能漏识别非标准措辞；人工effective scope仍必需。CMS二次观察不提供原子快照或永不漏页保证。只覆盖两个官方列表，不包括微信/其他栏目。review CLI是工件工具，无认证/签名/多版本冲突仲裁/生产source promotion。现有parser只支持既有已审格式；生产尚未接入collector门禁。全站历史schema失败采取保守阻断，后续只能在取得有效期证据后改策略，不能用发布日期跳过坏行。

## 31. Deferred Issues

未做常规周表+目标日例外、第三场馆、新Fact类型、新Agent/后台审核UI/Knowledge扩展/Execution治理。Ledger2.2 OPEN、Demo rehearsal NOT READY以及既有Knowledge覆盖缺口保留。未修改Router/Identity/Brief/审批，不重跑或改写旧里程碑以冒充本轮能力。SOURCE_CHANGED/SCHEMA_CHANGED需要实际人审恢复，不自动accept。

## 32. Recommended Next Slice

建议“Official Collector Source Repair & Reviewed Promotion Gate”：针对39496补充官方详情原文或可证明失效日期的来源，决定null-body来源schema的可审策略；对运营候选做venue+effective-range审核，治理review registry版本/冲突，保留拒绝原因；先得到完整例外扫描证据，再单独评估把accepted source接入既有Fact provider，运行最终全量及对应production部署验收。仍未达到时保持PARTIAL/NOT READY；不要重做Foundation/Forecast/Router/Identity/Planning。

# CHATGPT HANDOFF SUMMARY

CURRENT SLICE:
Official Opening Schedule Collector Lifecycle PARTIAL

DISCOVERY:
两站官方栏目实源分页发现已实现；不是生产runtime接入。

MANUAL NOTICE IDS:
发现入口无人工notice IDs；既有IDs仅用于hash审核匹配与旧parser兼容。

PAGINATION:
南京4页+4次稳定性复查；浙博6页+6次复查。真实total模式；cursor只有fixture证明。

COLLECTION COMPLETENESS:
两站pagination_complete=true；南京collection complete，浙博schema_changed；两者exception_scan_complete=false。

VENUE / BRANCH SCOPE:
canonical main/之江profile；其他机构、分馆、局部展厅或含糊范围不可自动提升。

SCHEMA DRIFT:
required fields/list metadata/HTML profile检查；实源39496 null正文阻断；controlled rename drill no truth。

CONTENT CHANGE:
hash变化必须source_changed或schema_changed重新审核，无静默复用。

REVIEW LIFECYCLE:
discovery工件→review_required/accepted/rejected；source_changed/schema_changed；显式同范围修订才superseded。无自动promote。

ACCEPTED SNAPSHOT:
候选与accepted分离。南京1；浙博既有review匹配1，但accepted-for-use0。

REAL NANJING:
342物理条目/341候选/1重复；381205重新发现并hash匹配；89待审。

REAL ZHEJIANG:
562条/561可归一化/2内容重复；46554重新发现hash匹配；39496 null正文；167待审/错误引用。

OPENING HOURS REGRESSION:
实源2/2；real Companion20/20；regular resolved0；既有公告日期覆盖保持。

WEATHER:
真实forecast与混合/独立失败边界通过；无新weather能力。

KNOWLEDGE:
frozen60，need34/60、assertions35/44、mixed7/10与前版相同；旧60证据文件hash未变。

PLANNING SAFETY:
正常Planning Brief控制、原权限回归通过；collector无DB/Agent执行。

FORMAL STATE:
7表完整行hash/count、Trip versions前后相同；production Run delta0。

BACKEND:
focused165；final clean Linux/Python3.11.16/PG17/alembic0034 full824，2旧warnings；Foundation28/28。

PRODUCTION:
本轮未部署。API/worker各167文件匹配fc3a06ba…；API live/ready/Web200；v1 production truth保留。

REGULAR + EXCEPTION READINESS:
NOT READY

KNOWN LIMITATIONS:
- 实源schema阻断、待审核候选、有限词法scope/关键词、多渠道未知。
- 无review认证/多版本仲裁/生产promotion；旧parser格式有限；生产未接入新collector。

DO NOT REDO:
- 不重做Foundation/forecast/Router/Identity/Brief/Planning审批。
- 不覆盖冻结标签/旧证据，不启用regular fallback，不用第一页无公告证明无例外。

NEXT RECOMMENDED SLICE:
Official Collector Source Repair & Reviewed Promotion Gate；修复/证明历史空正文范围、候选人工审核、review版本治理，完整性成立后再评估runtime接入。


## Request recheck — 2026-10-08

VERIFIED: The repeated Collector request was checked against current code and recorded artifacts. All 19 selected Travel Facts/collector/review source and test files still match the Source Repair manifest. No product code, production state, Git history or accepted source was changed in this recheck.

MEASURED: Current Windows focused regression passed 181 tests (collector, review gate, opening hours, Companion facts, native facts and fact eval). Historical clean Linux/Python3.11/PostgreSQL17 full824 remains evidence for its original Collector snapshot, not a new full-regression claim for the later dirty worktree. Official listing counts and source limitations above are historical observations; no new live scan was performed in this recheck. Evidence: backend/evals/results/opening_collector/request_recheck_20261008.json.

RESULT: PARTIAL retained; regular+exception NOT READY. Discovery/pagination/scope/schema/hash/review engineering is present. Missing source body and unreviewed candidate scopes prevent exception completeness and promotion. No deployment is needed for the offline-only Collector. Subsequent Demo/Planning work visible in the working tree belongs to a separate scope and was preserved.
