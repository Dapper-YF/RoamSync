# Verified Opening Hours v1 — 2026-10-01

## 1. Starting Reality

VERIFIED：实际仓库 E:\Study\RoamSync；main/HEAD5572849不变，大量 dirty work 保留。前一正式源7e01c9c，部署前165运行文件全匹配；本轮最终源 `fc3a06ba3cf95aaa6317f95f3b3cc300d2dd582299ac24ac7b91dce995f3bdfb`。无commit/reset/clean/stash/merge。starting_status/head、baseline_runtime及前源验证留证。

## 2. Source Feasibility Audit

MEASURED：真实调用 AMap v3/v5 和三家官方页面；网络不是阻塞。v3已有biz_ext.open_time/opentime2，v5有opentime_today/opentime_week，但日期参数、更新时间、结构化节假日/临时闭馆均缺。已有AMap适配器只支持身份/位置/分类；maps_service投影丢弃时间字段。external_facts是传输封装；Tavily可发现官方链接，Knowledge和Planning research禁止充当营业时间真源。官网页面壳需要官方CMS响应；已取得南京/浙博公告，不采用搜索摘要。证据source_probe/official_api_probe/zhejiang_content_probe及只读审计脚本。

## 3. Source Authority Decision

PASS，见 [Opening Hours Source Decision](OPENING_HOURS_SOURCE_DECISION_20261001.md)。按opening_hours显式注册南京/浙博 official_notice authoritative/rank100；现有native source_type复用，无全局official标签授权。AMap营业时间没有注册verified authority、仅候选；不是默认80分营业事实。灵隐英文旧说明有效期/更新不明，排除。

## 4. Supported Scope

两个museum：南京博物院main venue amap:B001907TGR，2026-09-25至27及10-01至07；浙江省博物馆之江馆区 amap:B0I15SU50Z，2026-09-25至10-08。仅官方公告已经发布的目标日期安排，不代表所有展厅开放/入馆保证。

## 5. Unsupported Scope

公告覆盖外日期、其他场馆/馆区、全西湖统一时间、灵隐寺/飞来峰、现在是否实际开着、票务/预约/价格/人流/交通/路线/导航/Execution均不支持。年度国庆不隐式映射当前年份；无公告时诚实不能确认。

## 6. Fact Contract

复用 place.opening_hours、FactRequirement→TravelFactService→ResolvedFact。OpeningHoursValue最小扩展最多8段intervals、closed_all_day/unknown、local_date/timezone、schedule_semantics/last_admission；保留旧opens_at/closes_at兼容。未知不得resolve；日期不匹配由原生Resolver拒绝；旧Foundation87测试保留。

## 7. Place Identity

小时事实绑定精确AMap canonical ref、name和city，收集器逐项核对。不合并南京市博物馆与南京博物院，或之江与孤山。浙江省博物馆无馆区先澄清；模糊博物馆先问具体场馆。只有确定性generic followup可继承前明确实体，未知名场馆或opaque intervening turn结束继承；新增回归验证南京市博物馆/玄武湖不能借南京博物院身份。不采用助手推荐或最近POI第一项。

## 8. Schedule Semantics

区分regular_schedule/date_specific_schedule/special_exception/temporary_closure。本轮真实生产输出只有date_specific_schedule及公告闭馆special_exception。常规页/POI周表不推导verified目标日；多段native契约已测，真实两源只提供单段。

## 9. Target Date Applicability

FactRequirement当地午夜到次日午夜，Asia/Shanghai；解析今天/明天/后天、明确年月日、最近星期、国庆第二天。Fact有效期是要求的当地日，公告覆盖范围必须包含此日，检索不扩大有效期。公开的历史日期安排可以核实，非历史实际运营。

## 10. Weekday Handling

日期→当地weekday确定性计算；周一查询2026-10-05采用南京公告的国庆例外，不套用常规闭馆。浙博source内日期与星期逐项核验；生产closed-weekday用公告2026-09-28周一闭馆。

## 11. Holiday / Exception Handling

南京公告381205明示10-01至06延时到20:00、10-05不闭馆，10-07回17:00；浙博46554按之江段10-01至07延时20:00。2027国庆/未覆盖日期拒绝确认。exception_checked只指审阅公告，不是扫描全部公告后证明没有别的例外。

## 12. Temporary Closure

没有通用临时闭馆feed或生产temporary_closure truth provider。识别未审阅的更新开放/闭馆公告或selected notice中暂停/维修语义则fail closed；不宣称没有临时调整。原生冲突测试验证更高rank闭馆能覆盖日期安排；生产闭馆日期是已发布special_exception，不冒称维修等临时关闭。

## 13. Last Admission

只解析来源明确的停止入馆标签，独立于闭馆。南京国庆19:00停止入馆、20:00闭馆；之江19:30与20:00。native校验入馆截止属于开放段；不保证还有名额、不从闭馆时间猜截止。任意钟点入馆问题只提供时段/截止，不保证能进去。

## 14. Freshness

每轮重新取官方CMS，没有跨轮小时缓存。native30秒为同次操作边界（15秒fetch预算+resolve/render），不是schedule更新周期或30秒实际运营保证。南京公告日期2026-09-17、last_updated未知；浙博create Sep17、publish_date Sep21 08:00、update_time Sep21 14:39:08，保留原字段、source timezone未提供，不伪造UTC时间或用它当实测。

## 15. Conflict Resolution

原生Resolver按事实类型注册的authority/specificity仲裁；候选POI不达到最低authority。相同优先级不同值保持conflicting、服务端拒绝单一时间，不由模型选择。真实AMap南京17:00与官方国庆20:00差异留在源审计；真实Companion冲突case明确为同权威注入，未声称官方真的互相冲突。

## 16. Companion Integration

InformationNeed拥有opening_hours_required/native requirements；FactToolPort准备/resolve，图只消费typed结果。复用CompanionFactAdapter和现有图节点，独立opening_hours_plan只为查询/回答元数据；不是平行事实contract。native需求总上限32容纳24小时天气+1场馆。小时自然回答服务端生成，模型不提取HTML或补时间，Router未改。

## 17. Knowledge / Weather Mixed Handling

真实混合测试通过：opening+weather都成功，hours源失败但weather成功，weather失败但hours成功，Knowledge失败但hours成功；stable来源内容独立，weather-only无hours fetch、hours-only无weather fetch。保留Knowledge既有限制，不用它给营业时间背书。

## 18. Planning Safety

20真实图场景中所有事实请求Companion/mutation=false/no handoff；明确南京三天控制仍Planning。生产1–9无Run，10正常Brief及日期澄清，不跳审批。Router/Identity/PlanningBrief/Agent执行权限未改。

## 19. Formal State Safety

MEASURED：PostgreSQL/API测试对Trip/DayPlan/Activity/PlanningRun/PlanRevision/TripExecution/NavigationSession完整行逐项前后比较；生产部署前后、smoke前后七表counts+全行hash及Trip versions均相等。只创建独立synthetic Assistant session/messages，无生产reset、无批准、无正式状态写入。

## 20. Files Changed

运行源增/改：companion_contracts/facts/graph/information，travel_facts/models/resolution，新增travel_facts/opening_hours。测试test_opening_hours及两份真实源fixture，扩展test_companion_fact_safety；新增evals/opening_hours_v1。scripts三个审计/生产脚本+本报告生成器；报告、Source Decision、LATEST_HANDOFF及证据。完整changed_source_files记录在verification.json；原dirty内容保留。

## 21. Focused Tests

MEASURED：218 passed，focused.xml。涵盖Foundation、forecast、Companion Phase2.5/Knowledge/conversation/Router、date/closed/multiple intervals/unknown/schema drift/同级冲突/高权威闭馆/日期不匹配/更新未知/entity/freshness/调用隔离/正式状态。早期两个路径选择错误与初次契约问题已修正；最终测试结果绑定当前源。

## 22. Real Source Validation

2/2：南京/浙博官方CMS，source_fetch timestamp、canonical place、API/公告URL、notice id、source payload hash、native Requirement/ResolvedFact、时段/截止/authority/freshness均保存在real_source_validation.json。2026-10-02南京09–20/19截止，之江09–20/19:30截止；无模型猜测。

## 23. Real Companion Evaluation

20/20，real_companion.json；真实来源/真实图，非模型质量评估，无DB mutation port。自然失败/注入失效/冲突显式区分。source_found=11；regular_schedule_resolved=0；date_applicable=8；published-notice exception_checked=8；final_verified=8。这些是请求结果数，含重复场馆；不是二十家场馆、全面例外覆盖或真实运营准确率。早期real_companion_network_failure.json保留外部天气失败，最终真实重跑通过。

## 24. Full Regression

最终clean Linux/Python3.11.16/PostgreSQL17，空tmpfs test DB，alembic upgrade head到0034，最终full pytest：795 passed，2既有Starlette警告。backend_final.log/XML。验收复查发现未知具体实体可能继承旧场馆，故前一794全量成为中间证据、保存backend_before_identity_fix；修正后按新源重新做focused/real/frozen/full及部署smoke，并未隐藏多跑的原因。Foundation基准28/28；Knowledge冻结60，need34/60、assertions35/44、mixed7/10与前正式slice相同，旧标签/输出SHA全未改。

## 25. Production Deployment

全部Gate后build/recreate API+agent-worker；两者各167运行源hash匹配final source。build/deploy/binding evidence留存。API live/ready和Web200、PostgreSQL healthy、worker进程运行（没有Docker healthcheck），迁移0034 head。Web未重建，无DB迁移新增。Knowledge+forecast+hours一起保留。

## 26. Production Smoke

10/10，production_smoke.json：hello/南京探索/有来源西湖历史/杭州天气/南京hours/周一闭馆/2027国庆不确定/now unsupported/hours+weather/南京三天Planning。1–9无Run或mutation；10准备Brief/澄清日期，run delta0。七表+versions全不变。首轮9/10的天气失败保存在production_smoke_network_failure.json，最终真实重跑通过；不等于网络永远稳定。

## 27. Known Limitations

日期/场馆极窄，reviewed notices固定2026且无全部公告/渠道扫描；改格式/新公告失败保守拒答。无跨馆/全年/regular advisory truth、通用临时closure、当前运营/入馆保证，source更新字段不是实时观测。只验证来源和链路，无独立运营现场核验。外部天气瞬时失败仍存在。既有Knowledge缺口、Ledger2.2 OPEN、Demo rehearsal NOT READY保留。

## 28. Deferred Issues

新场馆、全年weekly+exception扫描、人工审核更新workflow、独立collector语法版本测试；票务/预约/人流/交通/Memory/新Agent/DB/Knowledge expansion/vector/DecisionLedger均未做。不要为未知日期重放固定公告当事实。

## 29. Recommended Next Slice

Official Opening Schedule Collector Lifecycle：仅扩展已有collector的公告发现/分页完整性、馆区范围和格式变更审核，再评估全年regular+exception支持；复用Foundation，不重做Forecast/Knowledge/Router/Planning边界。

# CHATGPT HANDOFF SUMMARY

CURRENT SLICE: Verified Opening Hours v1 COMPLETE — strictly bounded published-date schedules.
SOURCE AUTHORITY: 两家venue official_notice，type-specific authoritative/rank100；POI/search仅候选。
SUPPORTED PLACES / TYPES: 南京博物院main、浙博之江；two museums，2026公告限定日期。
SUPPORTED SEMANTICS: date_specific_schedule/special_exception；native multiple intervals/closed/unknown。
REGULAR SCHEDULE: 不作目标日verified推导，regular resolved=0。
SPECIAL DATE / HOLIDAY: 2026中秋/国庆官方明确日期；其他日期unavailable。
TEMPORARY CLOSURE: 无通用verified feed；未知新闭馆公告fail closed，不证明absence。
LAST ADMISSION: 来源明确截止，南京19:00/之江19:30与20:00关馆独立。
FRESHNESS: 每轮重新fetch，无hours跨轮cache；30秒同操作guard；日期有效期独立；CMS timestamps保留。
CONFLICT: Native同优先级conflicting拒答，高权威测试裁决，不交模型。
REAL SOURCES: 2/2，native evidence及trace留证。
REAL COMPANION: 20/20，四类mixed/故障隔离和冲突注入标明。
WEATHER REGRESSION: focused+real+production通过，瞬时网络失败记录保留。
KNOWLEDGE REGRESSION: 冻结60，34/60、35/44、7/10不变；旧outputs/labels不改。
PLANNING SAFETY: 生产1–9 Companion/mutation=false/no Run；10 PlanningBrief+日期澄清。
FORMAL STATE: 七表完整行hash/count及Trip versions部署/烟测前后不变。
BACKEND: focused218/full795/Foundation28/28，Python3.11+PG17，2既有warn。
PRODUCTION: API+worker已部署，each167 runtime hashes match；smoke10/10；Web未重建。
KNOWN LIMITATIONS: two venues/explicit2026 dates，不代表当前运营、全年时间或完整例外覆盖；旧Knowledge/Ledger/Demo限制保留。
DO NOT REDO: Foundation、Knowledge、forecast、Router、Identity、Brief、Planning审批；保留dirty main。
NEXT RECOMMENDED SLICE: Official collector discovery/pagination/schema review lifecycle，扩scope先验源。
