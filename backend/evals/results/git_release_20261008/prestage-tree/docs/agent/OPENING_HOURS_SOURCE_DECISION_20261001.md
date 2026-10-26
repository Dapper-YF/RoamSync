# Opening Hours Source Decision

Decision: PASS for a bounded official published-date schedule capability. This is
not a current operational status capability or a general venue-hours collector.

MEASURED source probes: `backend/evals/results/opening_hours_v1/`. Official CMS
responses were fetched from the running API's network environment on 2026-10-01.

| Provider / source | Authority class | Data semantics / applicable entities | Effective dates | Update and freshness evidence | Holidays / closures | Conflict / limitations |
| --- | --- | --- | --- | --- | --- | --- |
| 南京博物院 `/api/news/freshNotice`, notice 381205 | Venue official published notice | Main museum visitor schedule; not every gallery, parking or nonheritage hall | Explicit 2026 Sep25–27 and Oct1–7 | Notice date Sep17; modification time not supplied; fetch every answer | Explicit holiday extension and Monday exception; separate nonheritage-hall closure must not be applied to main museum | Date notice outranks regular source; same-rank disagreement remains conflicting. Coverage does not establish absence of other closures |
| 浙江省博物馆 `/api/content/page`, Notice, site22, content46554 | Venue official published notice | Split named campus sections; enable ONLY 之江馆区, exact AMap identity B0I15SU50Z | Explicit 2026 Sep25–Oct8, including closed Sep28 and Oct8 | create_time Sep17, publish_date Sep21 08:00, update_time Sep21 14:39:08; source timezone not supplied, these CMS fields do not assert live operation; fetch every answer | Explicit holiday extension, closed dates, postponed closing day | Section guard prevents 孤山 schedule leaking into 之江. Unrecognized changed notice fails closed |
| 南京博物院 `/api/home/info` nbOpenTime | Venue official regular page | Weekly main museum schedule and last admission | No explicit effective period / last update | Fresh retrieval proves publication, not date applicability | Holiday qualifications, no complete exception coverage | Advisory only outside parsed date notice |
| AMap v3 biz_ext.open_time/opentime2; v5 business.opentime_today/opentime_week | Specialist POI assertion, candidate | Exact venue identity plus free-text weekly/today descriptions | Today field has no target date parameter; weekly text is not a future date promise | Real responses supply no modification/publication time | Generic holiday words, no structured temporary-closure feed | No verified opening-hours authority registered. Actual 南京 response says 17:00 while official Oct1–6 notice says 20:00 |
| Lingyin English maps page | Official publisher, insufficient currency | Regular English description, temple / scenic-entry distinction unresolved | None | No publication / effective date; old footer alone is not a freshness proof | None verified | Candidate only; exclude |
| Tavily, Knowledge, Planning research | Discovery / background | May identify official URLs, never truth for opening hours | None verified | Search retrieval is not source publication | None verified | No opening-hours authority |

Implementation policy: explicit per-type registration for reviewed venue date
notices; general regular schedule remains advisory. Target date is Asia/Shanghai
local midnight–midnight. Native resolver arbitrates facts; model does not parse
HTML or select sources. A bounded deterministic parser checks source schema,
notice identity/year, named sections, exact date ranges and last-entry labels.
Changes outside the reviewed grammar fail closed. No inferred closure absence.

Freshness: no cross-turn hours cache. Fetch each operation; the 30-second native
max-age bound is a same-operation guard (15-second fetch budget plus resolution
and rendering), not a claim that a schedule stays true for 30 seconds. Preserve
source publication/update time as metadata; absent last_updated stays unknown.
Notice coverage defines effective dates; retrieval does not extend that coverage.

Supported types: two museums only. Unspecified 浙江省博物馆 requires campus
clarification. 灵隐寺 / 飞来峰 / 西湖景观 are not supported venue identities.
Current status, admission guarantee, reservation and all ticket facts excluded.

Gate is conditional on collector/schema/date tests and two native real-source
validations before deployment. Source availability alone is not slice completion.
