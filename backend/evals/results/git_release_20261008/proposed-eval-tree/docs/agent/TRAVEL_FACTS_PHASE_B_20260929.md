# Travel Fact & Evidence Foundation — Phase B

日期：2026-09-29。VERIFIED 指代码/测试证据，MEASURED 指实际执行结果；不宣称 live Provider 验收或正式 Agent 接入。

## 1. Repository Audit

真实应用仓库为 `E:/Study/RoamSync`，不是历史文档目录。开始时主工作区 HEAD `5572849`，包含未提交的 Router/Companion 等工作。用临时 Git index 捕获后端、已存在 migrations、依赖锁和 handoff；原工作区和原 index 未被 add/reset/stash。隔离快照为 `1679be4d874b300c3ad1b484032eea1cbbfe5ac0`。Phase A 的 `5023a28` 不在本轮实现依赖中。

| 已有代码/来源 | 真正的数据与 provenance | 时间/风险 |
| --- | --- | --- |
| `app/maps_service.py` AMap POI | `search_amap_location_pois` 已有 LocationPoiResponse，稳定 poi_id、名称、坐标、原生 type_name | 没有 Provider observation/retrieval 时间；`search_amap_places` 的 category、duration、cost 部分来自启发式，不能作为票价/停留时长事实 |
| 同文件 AMap Route | `_fetch_amap_route` 返回距离、向上取整的分钟数、Provider、estimate 标记、路径/备选 | duration 是路线预测，不是实测行驶时间；`resolve_route_result` 会写 RouteCache，允许配置时可回退 RoamSync Estimate |
| `app/external_facts.py` Open-Meteo | WeatherFact 有 provider、queried_at、经纬度、payload；请求 hourly temperature/probability/code | queried_at 是获取时间；未请求 current，未提供模型发行时间，hourly time 是预报有效时间 |
| 同文件 Tavily | SearchFact 有 provider、queried_at、query、原始 results | 搜索获取时间不是公告发布日期；标题/domain/snippet 都不足以建立事实权威 |
| `app/database.py` SourceRecord | trip 外键、title/url/provider/queried_at/confidence | 没有 typed assertion、有效区间、freshness、冲突/排除记录；不宜扩成共享 Evidence |
| NavigationObservation / NavigationSession | 已接受 sequence/fingerprint、observed_at、位置/精度、ETA、remaining、simulation/real_gps、itinerary/route revision | session.updated_at、route calculated_at 不能替代旧位置观测时间；初始 planned route 数值也不是当前观测 |
| TripExecution / ActivityExecution / TravelEvent | canonical 执行状态、actual start/end、已接受用户体验事件 | 执行进度里的 risk/slack/projected end/建议是派生结果；事件接受时间和实际事件时间不同 |

Planning 数据路径：`_collect_external_facts` → destination research（搜索来源索引/POI 匹配）→ planning context → candidate route enrichment → validator。`SourceRecord` 随 trip 保存；现有 external_facts 虽是独立 Python 文件，仍主要由 Planning 使用，尚无共享 resolver contract。导航观测进入 CAS/idempotent canonical ingestion，再进入 detector/disruption/recovery；读取业务 projection 的部分函数可能补写状态，因此本轮没有直接复用这些读取函数。

现有 freshness 是局部规则：RouteCache 的坐标五位精度+mode key、created_at/expires_at、配置默认 86400 秒；导航版本/sequence/观测时间校验。candidate route 的 calculated_at 可能在复用缓存后重新生成，不能据此让旧来源重新变新。不存在跨业务、按事实类型确定性的 source conflict resolver。external 与 execution 在数据模型上分开，但上层 context 已组合 canonical 数据与推导信息，不能把整块 context 都认证为 raw fact。最小侵入位置因此选择新增 `app/travel_facts/`。

对时间语义的外部核对来自 [Open-Meteo 官方文档](https://open-meteo.com/en/docs) 和 [AMap 路径规划文档](https://developer.amap.com/api/webservice/guide/api/newroute)。实际适配能力以本仓库代码为准。

## 2. Architecture Decision

新增独立模块，依赖方向为：上层 → FactResolver protocol / TravelFactService → repository、per-type policy、Provider adapters → 原 Provider 网络函数或 canonical SQL。没有 LLM、Agent runtime、新 HTTP endpoint 或新业务写入。

Fact 是带来源的 typed assertion；Evidence 是来源快照；Inference 不属于该契约。`nature` 强制区分 provider_assertion / provider_prediction / canonical_record / canonical_prediction，不能填 inference。不导入 Tourism Knowledge 的 SourceAuthority/contracts：知识权威不等于现场事实时效，复用会掩盖 `tourism_knowledge_not_live_verified` 边界。

## 3. Fact Taxonomy

| 类别 | 本轮真实 adapter 能产出 | 仅 contract/fixture，可显式 unsupported |
| --- | --- | --- |
| Place | identity、location、category（AMap 原生分类） | opening_hours、operational_status、ticket_availability |
| Weather | forecast（小时预报温度、降水概率、天气 code） | current |
| Route | distance、duration；subject 内包含 mode 和端点坐标系 | eta |
| Execution | activity_status、actual_start、actual_end | 未实现 remaining_duration 或 TravelEvent 聚合 |
| Navigation | position、eta、remaining_distance，读取已接受 canonical 观测 | 未实现 traffic/status/new routing |

官方临时闭馆/开放时间冲突只用明确标记的合成 fixture 验证 policy，**没有官方采集器**。AMap duration 不加当前时间伪造 route.eta；current weather 也不从 forecast 改名而来。不一次实现 reservation、price、alert 等未来 taxonomy。

## 4. Contracts

- `TravelFact`：typed subject/scope/value、aware timestamps、有效区间、fresh_until、evidence_refs、specificity、nature。value 使用 discriminated union，量值显式 meters/minutes，GCJ-02/WGS84 显式保留；scope 与 subject 校验。禁止任意 JSON value、无来源事实、naive 时间、非有限数字、错单位/状态、inference。
- `EvidenceRecord`：provider/source_type/reference、retrieved_at、可选 provider_observed_at、authority hint、subset snapshot、metadata、可选 SHA-256 payload fingerprint。snapshot ≤8 KiB、metadata ≤4 KiB，hash 输入 ≤1 MiB；hash 不是可恢复的 blob 地址。`payload_trust=untrusted_data_no_tool_authority` 固定。
- `FactRequirement`：版本 travel-facts-v1、类型/subject、TimeScope(start,end 可选且右开)、可选 freshness 秒阈值、minimum_authority、required、≤240 字符 reason、allow_stale。reason 是短用途说明；required/optional 都不允许补猜。
- `ResolvedFact`：版本、原 requirement、typed value、selected_fact/evidence、conflicts、rejected_candidates、全部 matching evidence、freshness/status、symbolic confidence、usable_as_current、固定失败码。校验结果引用完整、主体匹配；gap/conflict 不允许带决策值。

`usable_as_current` 表示该声明在解析时足够新、可用于**请求的时间范围**。未来 forecast 可以为 true，但 nature/有效时间仍明确标为预报；它并不宣称未来天气已经被实测。confidence 是 policy_supported/corroborated/limited/none，不是概率或权威等级。

## 5. Freshness Policy

`FactFreshnessPolicy` 必须由 composition root 显式传入逐类型规则。生产环境没有隐藏统一 TTL，也没有按提示词填入 SLA。未配置类型 → unsupported。测试里的 10/60/300/3600 等秒数只用于跨边界测试，绝不能直接搬成生产保证。

deadline = min(fact.fresh_until, 最早 fact/source 时间 + min(类型 max_age, 请求阈值))。Provider 有 observation 时间时使用它，重读/重新获取不得刷新旧观测。`now < deadline` 才 fresh，等于截止时 stale。先判断 request 有效区间：future_effective / expired；完整区间必须被同一声明覆盖，不拼凑多个小时预报。当前 live 状态没有 bounded validity 时不承诺未来状态。最终时间在网络调用之后重取。

stale 默认没有 value。仅显式 allow_stale、该类型配置 grace 且仍在 grace 内时，允许背景值，status 永远 stale、usable_as_current 永远 false；navigation/route ETA、current weather、票量、activity status 不允许 stale fallback。unknown 也返回证据缺口。

## 6. Authority / Conflict Policy

按 `(fact_type, provider, source_type)` 注册权威和 rank；现有 AMap 只在 POI/route、Open-Meteo 在 weather、RoamSync 在 canonical execution/nav 注册规则。自称 authoritative 的 metadata、官方域名/标题和 Tavily 候选不自动取得 rank。未来官方 collector 需要应用明确注册受信来源；rank 是配置，不是外部文本决定。

先过滤 exact subject/type、有效时间、freshness、minimum authority，再比较该类型的 rank 和 bounded time_specific。旧高权威不可压过 eligible 新低权威；旧证据作为 rejected/conflicting evidence 保留。同优先级独立来源不同值 → conflicting，无 value。只有同 provider/type/reference 的来源链明确较新版本可替代旧版本，旧分歧仍保留；两个独立来源不会因时间较新就强行选择。不同来源同值可标 corroborated；本轮不要求 quorum，也没有概率融合或 LLM 仲裁。

## 7. Provider Adapters

AMapPoiAdapter 精确匹配调用者给出的 `amap:<poi_id>`，还需要 name/destination 作为已有搜索 API 参数；零/多匹配均 gap，不猜实体。复用 `search_amap_location_pois`；保留原生类别，不使用停留时间/费用启发式。

AMapRouteAdapter 复用网络-only 私有 `_fetch_amap_route`，避开写缓存和 Estimate fallback。GCJ-02 端点，transit 需要 city，拒绝未来 departure；只输出 distance/duration，原始 geometry 不上送，hash 留痕。分钟向上取整/预测语义保留。与该 private seam 的兼容是已知维护风险，有真实模块 monkeypatch 测试。

WeatherForecastAdapter 复用 `fetch_open_meteo`，WGS84 + UTC query；验证 Provider、请求坐标、时区、小时序列、数组长度、units/value，取一个覆盖请求的小时窗口。获取时间不能充当模型发行时间；元数据明确模型发行时间未知。外部额外文本不进入 normalized snapshot。

Tavily 只提供纯函数 `normalize_search_evidence`，最多 5 条候选、短标题/摘录、HTTP(S) URL（拒绝 credentials，去 query/fragment），不产出 TravelFact，不主动再接搜索 API。没有新第三方 dependency/API。

## 8. Execution Boundary

ExecutionFactAdapter 每次 read-through，自建 session，关闭 autoflush，第一条 SQL 为 `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`；只查询，退出 rollback。检查 trip 所属 execution、trip/execution itinerary_version、navigation 所属关系和 route_revision。调用者仍应先在业务入口认证/授权；本层版本校验不是用户权限系统。

导航须 live session/in_progress execution + accepted fingerprint/sequence/last_location_at + 可用 navigation_status。默认只允许 real_gps；simulation 显式 opt-in 后仍标 limited 且不可作为现场现实。重读不续期 observation。actual start/end 的值是历史时间，当前 DB read 确认该记录，而不是用历史事件时间计算缓存年龄。

不调用业务 projection/read-model 函数，不写 TravelFact 表、不缓存 canonical fact、不复制 events、无双写路径。现有 Execution Context 继续直接读取 Core；Fact adapter 是未来跨 Agent 标准化的可选只读界面，不强制迁移现在的 UI。

## 9. Persistence / Cache

无 migration、新表或配置文件修改。`InMemoryFactRepository` 是有限 ephemeral 外部缓存：默认 128 个 (type,完整subject) key、每 key 8 个声明历史，有限 subset evidence、deep-copy 防止别名变更、相同 id/content exact retry 去重、同 id 不同内容 collision 拒绝。重新获取的新 timestamp 是新 evidence，而不是 exact retry。

fresh cache reuse → stale/gap/conflict 时询问支持的 providers → normalize/revalidate → merge → deterministic resolve。cache key 保留坐标系/mode/版本；time_scope 在 resolution 时检查。fresh cache 不主动探测新公告，subject 上限/history eviction 也不是持久审计档案。共享跨进程存储、强制 refresh/通知、官方 notice ingestion、永久 evidence 生命周期均推迟。

旧 RouteCache 缺原始 retrieval/provenance，且可能保存推估，不能无损复用，所以本层单独有界缓存。日后可在不改上层契约下替换 repository。live navigation 不值得复制到长期 Fact 表。

## 10. Files Changed

全部为新增路径，无任何既有核心文件修改：

- `backend/app/travel_facts/`：`__init__.py`、`models.py`、`interfaces.py`、`policies.py`、`resolution.py`、`repository.py`、`normalization.py`、`service.py`、`adapters.py`、`execution.py`、`search_evidence.py`。
- `backend/evals/travel_facts/`：fixtures、cases、runner、baseline/results/verification 证据。
- `backend/tests/test_travel_facts.py`、`test_travel_facts_execution.py`、`test_travel_facts_eval.py`。
- 本报告、`docs/handoff/TRAVEL_FACTS_PHASE_B_HANDOFF.md`。

## 11. Tests

新增离线契约/解析/Provider 边界、真实 PostgreSQL 和 benchmark 测试。覆盖类型/scope/time/units/bounds、证据完整、fresh/stale/future/expired、authority/freshness 冲突、同级冲突、同源修订、最低权威、精确重试、缓存边界/深复制/collision、刷新/失败/真实 timeout/调用后时效、POI exact ID、route Estimate 隔离、天气单位/数据损坏、payload safety、canonical age/版本/模拟来源。

PostgreSQL 测试比较适配器读取前后**全部 public 表的完整行快照**，并捕获 SQL 验证 SELECT/SET-only 和每次新只读事务；验证 canonical owner 的更新能立即被下次读取看见，无 repository 副本。此处 real_gps 标签是测试用 synthetic canonical 行，不是真实设备/定位链路验收。

本机 Python 曾因缺后端依赖导致 gateway seam 导入失败；在 frozen Docker 依赖下通过，未改弱该测试。最终次数/耗时/源码哈希以 `backend/evals/travel_facts/verification.json` 为准。

## 12. Eval

`python -m evals.travel_facts.run --output PATH`，28 个固定离线场景。案例有 fresh/stale/background、过期/未来 notice、独立冲突、官方临时闭馆、旧官方/新地图、unknown、error/timeout/empty/unsupported、route ETA unsupported、route duration prediction、Estimate 排除、3 类 POI、未来/旧 weather、current unsupported、canonical ETA/状态/stale/simulation、exact retry、未来现场状态 gap。

指标来自 expected vs actual typed result：freshness correctness、provenance preservation、resolution correctness、conflict preservation、unavailable honesty。JSON 保留场景实际状态/值、evidence IDs、检查布尔值、分子分母与 fixture SHA-256。MEASURED 28/28 场景通过，前四个指标均 28/28，unavailable honesty 16/16。官方 notice 为合成数据、timeout benchmark 是固定错误码（真实 wait_for 超时在 unit tests），结果不是 Provider 准确率、Agent 回答质量或盲测。

## 13. Regression

MEASURED 修改前同快照/隔离 PostgreSQL/frozen lock：405 passed，0 failed，2 warnings，46.07s。最终全套后端：492 passed，0 failed，2 warnings，51.42s；新增 87 项通过。本轮新增失败 0，合并前基线失败 0。2 个既有 warnings 为 Starlette HTTP_422_UNPROCESSABLE_ENTITY 弃用警告，来自旧 planner 测试。机器证据见 verification.json。

Planning/Router/Execution/Companion 旧测试包含于该快照的完整 suite；这不代表之后另一个会话继续编辑的代码已验收。未改 Web/Android，未运行它们；未启动/重置真实 Demo，未部署，也未跑 live Provider。

## 14. Parallel Merge Safety

branch `codex/travel-facts-phase-b`；worktree `E:/Study/RoamSync-travel-facts`；Compose project `roamsync-travel-facts-test`。implementation commit 是该分支最终 HEAD，见独立 handoff 和交付消息。

**只 cherry-pick implementation commit；不要 merge 整个分支，也不要 cherry-pick `1679be4...` snapshot。** snapshot 捕获另一会话原有未提交 backend/Router 状态，用于正确测试，但并非本轮开发内容。最终实现提交只新增 Phase B 文件；不修改 assistant_service、router、planning graph、schemas、companion、execution core、database/migrations、依赖锁或共享 handoff。

项目 AGENTS 默认要求更新共享 PROJECT_STATE/LATEST_HANDOFF；本轮用户明确要求并行隔离且避免抢 handoff，所以交付专门 handoff，不覆盖共享文件。后续整合时由主工作区维护者更新全局状态。没有 Obsidian 写入。

## 15. Risks

未验证 live AMap/Open-Meteo；测试验证 normalized boundary 与真实 seam，不能保证未来响应格式/Provider 时间准确。Open-Meteo 模型发行时间未知、网格代表性/跨小时组合未实现；AMap 缺 observed timestamp、duration 分钟精度且依赖私有 seam。Product 需明确 freshness 配置、来源注册、调用额度、缓存 refresh 和缺证据 UX。Provider failure 时不生成伪事实。

缓存有界且进程内，source history 会被淘汰，hash 无法恢复 raw payload；不适合永久审计/跨 worker consistency。未知 Entity 无自动解释、官方 collector 未建、TravelEvent aggregation 未建、route ETA/current weather 未建。本轮没有通用多来源合并/概率 quorum 或实时监控保证。

既有 Provider 使用 asyncio.to_thread 的 blocking 网络函数；wait_for 限制 resolver 等待，但超时不会强制停止底层线程，该线程仍受原 Provider 网络 timeout 限制。本轮没有修改已有 transport。

## 16. Recommended Next Step

先 cherry-pick 独立实现提交，在 Companion 完成后的真实合并树重跑 backend。随后为一个小范围只读 InformationNeed 增加显式 freshness composition、身份/版本已校验的 requirement 构造、缺证据/冲突展示；不赋予 Fact Resolver 业务写权限。官方临时公告先设计受信 collector 和发布时间/有效时间契约，再做真实源接入。Planning 的 raw Provider 迁移分阶段推进，保留现有 validator，不把 Knowledge 回答升级成 live fact。
