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
