# Tourism Knowledge RAG — Phase A

日期：2026-09-29。状态：独立 Contract / Retrieval Foundation 已实现；生产语料、持久化与真实 embedding integration 尚未实现。本报告只依据隔离源码快照、实际 SQL 探测和本轮执行结果，不把历史 README 当验收证据。

## 1. Repository Audit

当前用户工作目录是仅含历史交付片段的文档仓库；真实应用位于 `E:/Study/RoamSync`，分支 main，HEAD `5572849`。审计和实施基于其当前未提交后端源码，隔离快照为 `0fab28819abb48a177fbff3d3da5d2e806a487f1`。

| 项目 | VERIFIED 现状 | 证据 |
|---|---|---|
| embedding / vector / RAG | 无 embedding provider、向量库、pgvector 或通用 Document/Chunk/Retriever | backend/app、migrations、pyproject.toml 全文检查 |
| PostgreSQL | SQLAlchemy async + psycopg；开发、测试均为 postgres:17-alpine | database.py、compose.yaml、compose.test.yaml |
| FTS / BM25 | 无应用 FTS/BM25；数据库有内建 FTS 能力 | 源码检查、实际 SQL |
| extension | 测试容器 pg_available_extensions 可见 pg_trgm，未列出 vector；本轮没有启用任何扩展 | 只读 `SELECT name FROM pg_available_extensions WHERE name IN ('vector','pg_trgm')` |
| 中文 FTS | `to_tsvector('simple', '西湖历史杭州茶文化')` 返回一个完整词 | 实际 PostgreSQL 17 探测 |
| research | SearchFact(provider, queried_at, query, payload)，原始 Tavily results 保留在 payload | external_facts.py: SearchFact / search_tavily |
| source | SourceRecord 含 title/url/provider/queried_at/confidence，但必需 trip_id，生命周期随旅行 | database.py: SourceRecord；schemas.py: SourceRecordResponse |
| 模型抽象 | build_model_client / create_model_response 是生成模型抽象，无 embedding 方法 | model_client.py；destination_research.py |
| 测试 / eval | pytest；独立 PostgreSQL tmpfs Compose；Alembic；离线 cases + runner + JSON artifacts | backend/pyproject.toml、Dockerfile、evals/run_travel_goal_eval.py |

现有 destination research 调用链：planning_graph.resolve → `_collect_external_facts`（宽泛/指定地点 Tavily 检索，可独立收集天气）→ `research_destination` → schema-bounded ResearchOutput → 来源下标与名称支持检查 → AMap 唯一地点匹配 → trip-owned POI snapshot → research.places / external_facts 写入图上下文 → Planner。网页提炼只保留 title/url/content，最多 8 条；包含请求地点、别名、推荐理由与 prominence，并非共享旅游知识索引。源码比冻结旧架构文档更新，不能依据后者断言 Search 尚未接入。

## 2. Architecture Decision

选择：provider/repository abstraction + 小语料内存参考适配器 + 中文 BM25 + 可注入 semantic + RRF hybrid；不增加数据库、迁移或依赖。

原假设“已有 PostgreSQL 就可直接上 FTS/pgvector”：真实部署缺 vector 扩展，默认 FTS 无中文分词，现有模型 SDK 接入仅用于生成。调整为先提供可测契约和真实可执行的 lexical 路径，保留未来替换存储和 embedding 的边界。支持库具备 embedding API 并不证明项目已有 embedding provider。

INFERRED：生产持久化值得继续复用 PostgreSQL，知识可独立表存储，不绑定 Trip；先根据中文检索质量与规模决定预分词 FTS/pg_trgm 候选，之后如需向量检索再启用 pgvector。pgvector 要先安装扩展文件并在目标数据库启用；须同时处理开发/测试镜像、版本、migration、索引与回滚，目前部署不是即插即用。[pgvector 官方安装说明](https://github.com/pgvector/pgvector)。FTS 的 parser/dictionary 决定分词行为，不能把内建功能等同于中文质量已经验证。[PostgreSQL 文本检索配置](https://www.postgresql.org/docs/18/sql-createtsconfig.html)。

本轮内存扫描的 CPU/内存开销随候选数量增长，不作为大规模 production adapter。Semantic 为 cosine 扫描，可实际注入 provider，但没有配置真实供应商；fake 仅位于 evals，不进入 app。未宣称 pgvector 或真实语义检索已上线。

## 3. Knowledge Boundary

- Knowledge：稳定/半稳定的目的地轮廓、历史文化、地点体验、旅行/人群策略、季节体验、当地生活；七种类别与本轮 taxonomy 一致。
- Search：当前网上可找到的材料；不是自动验证过的事实。Tavily 可用于现有实时 research，也可能作为未来候选 corpus discovery，必须经过权利/内容审核、稳定性分类、来源与版本记录后才 ingest；不自动把搜索结果灌入 corpus。
- Travel Fact/Evidence：今天营业、临时闭馆、库存、价格、天气、交通、ETA、GPS、用户实际停留；本模块不调用任何实时 API。
- Planner：具体排程、正式活动身份、前后约束、版本与候选接受；本轮不改其流程。

SourceAuthority 属于来源 provenance，在 Knowledge 中保留是必要的；未来 Evidence 可共享这些值，但不复用 trip-bound SourceRecord 或把 authority 当事实正确率/新鲜度。未因“官方”自动提高 relevance 分数，也未把 official label 当真实性认证。

## 4. New Contracts

所有公共模型使用 Pydantic、extra=forbid，contract version 为 tourism-knowledge-v1。

- KnowledgeDocument：id/title/content，destination，可选 corpus-scoped place_id/place_name，knowledge_type，audience/season/experience tags，language，source，ingested_at/reviewed_at/valid_until，stable/semi_stable scope，扩展 JSON metadata。
- KnowledgeSource：source_type/name/reference/authority，published_at/updated_at；authority 有九种既定层级；fixture 是独立 source_type，不伪装成生产来源。
- KnowledgeChunk：继承完整 KnowledgeMetadata/source，document_id/title/index，content，字符近似长度，heading_path，content_sha256，embedding descriptor。Vector 只在 IndexedChunk 存储内部，结果不暴露。
- EmbeddingMetadata：provider/model/dimensions/version；模型或版本不同不能混比。
- TourismKnowledgeRequest：query、destination/place/type/tag/language filters、top_k 1..50，lexical/semantic/hybrid；fixture 默认为排除。Destination/place/language 精确匹配，类别列表 OR，同类 tags 为全部满足，不同过滤维度 AND；空列表表示该维度不限制。不隐式推断地点、人群、季节或放宽过滤。
- KnowledgeHit/Result：完整 chunk（含标题、目的地、地点和所有时间/source），score/method，lexical/semantic components，retrieved_at、effective_mode、score_kind、advisory。BM25、cosine、RRF 分数不可跨方法直接比较，均非可信度概率。
- KnowledgeRepository：原子 replace_document + 过滤后的 candidates；KnowledgeIngestor：显式 ingest；EmbeddingProvider：descriptor + async batch embed；TourismKnowledgeRetriever：async retrieve_tourism_knowledge(request)。

扩展 metadata 和模型内部字典不是深度不可变；内存适配器在读写边界深拷贝，防止调用者修改已存 provenance。

## 5. Retrieval Flow

```text
审核者提供 KnowledgeDocument
 → CuratedKnowledgeIngestor
 → deterministic heading-aware chunk_document
 → optional batch EmbeddingProvider + shape/finite/nonzero validation
 → KnowledgeRepository.replace_document（同文档整版替换）

未来 Companion Tool adapter
 → TourismKnowledgeService.retrieve_tourism_knowledge(request)
 → boundary.assess_suitability
 → repository.candidates（hard filters / expiry / fixture exclusion）
 → service defensive filter check
 → Chinese-aware BM25 / optional same-descriptor cosine
 → hybrid reciprocal-rank fusion
 → deterministic top_k + provenance + advisory
```

BM25 使用 Unicode normalization、英文词、中文字符与双字索引；多字中文查询抑制单字噪声，单字查询仍支持。无同义词词典或自动 query rewrite，不声称等同于成熟中文分词器。RRF 使用 rank_constant=60，每路最多 max(100,4*top_k) 候选；并列按 chunk_id 确定顺序。

默认 hybrid 没有 provider 时显式返回 lexical 和 warning；显式 semantic 缺 provider/index 时抛 SemanticRetrievalUnavailable。缺少同模型索引的 chunk 会被说明；不同 descriptor 不比较。配置 provider 的调用/向量校验失败不会伪装成 semantic success，也不会破坏已 ingest 的旧版本。

未来最小使用方式（由调用方做依赖注入，无全局自动加载 corpus）：

```python
from app.tourism_knowledge import TourismKnowledgeRequest, TourismKnowledgeService
from app.tourism_knowledge.repository import InMemoryKnowledgeRepository
from app.tourism_knowledge.ingestion import CuratedKnowledgeIngestor

repository = InMemoryKnowledgeRepository()
ingestor = CuratedKnowledgeIngestor(repository)
# await ingestor.ingest(reviewed_document)  # 真实审核文档，不是 fixture
service = TourismKnowledgeService(repository)
result = await service.retrieve_tourism_knowledge(TourismKnowledgeRequest(
    query="西湖的历史？", destination="杭州", top_k=3,
))
```

## 6. Live Fact Guard

Result 永远带 evidence_kind=tourism_knowledge_not_live_verified。规则对营业/票价/库存/天气/交通/ETA/GPS/已玩多久以及今天/现在等信号设置 live_fact_verification_required；即使来源官方、刚入库、相似度高，也不变成 live fact。

“西湖历史”：有相关命中且没有 live/decision signal 时，knowledge_sufficient=true，表示检索范围可用，不是事实正确性保证；无命中为 false。“今天几点关门”：可返回背景，但 sufficient=false，live verification=true。“为什么建议18点去西湖”：额外 planning_decision_context_required=true，须由 Companion 合并一般体验、当天条件和实际决策依据；本层不推导今天18点最佳。

半稳定知识必须有明确 valid_until；到期包括等于检索时间均排除。入库时间不能替代来源更新时间。fixture 默认不参与检索，fixture URL/metadata 明确其人工构造性质。

HYPOTHESIS/限制：规则不覆盖任意语言、隐喻或省略表达，可能保守误报；它是 tool-local advisory 而非新 Router。未来 InformationNeed 应提供结构化时效需求，并由上层对所有 operational assertions 强制 live evidence 校验。Ingest 是受审核输入边界，不自动识别所有被误标为 stable 的实时句子。Source 内容是待分析数据，未来 Companion 必须防止其中的指令影响工具权限。

## 7. Files Changed

只新增以下独立文件，未修改任何 baseline 文件：

| 文件 | 职责 |
|---|---|
| backend/app/tourism_knowledge/__init__.py | public service/request/result/document exports |
| backend/app/tourism_knowledge/models.py | versioned contracts、taxonomy、source、review expiry |
| backend/app/tourism_knowledge/interfaces.py | repository/ingestor/embedding/retriever ports |
| backend/app/tourism_knowledge/boundary.py | live/decision advisory |
| backend/app/tourism_knowledge/repository.py | 原子替换、hard filters、detached provenance |
| backend/app/tourism_knowledge/ingestion.py | deterministic chunking、可选 embedding ingest |
| backend/app/tourism_knowledge/ranking.py | 中文 BM25、cosine、RRF、vector validation |
| backend/app/tourism_knowledge/service.py | async tool facade、模式与索引状态 |
| backend/tests/test_tourism_knowledge.py | isolated contract/retrieval/filter/boundary/error tests |
| backend/evals/tourism_knowledge/__init__.py | benchmark package |
| backend/evals/tourism_knowledge/corpus.json | 12 个明确人工构造的 fixture documents，含其他城市、英文、过期 decoys |
| backend/evals/tourism_knowledge/cases.json | 28 个评测案例，逐模式适用标记 |
| backend/evals/tourism_knowledge/fixtures.py | fixture loader、deterministic fake provider |
| backend/evals/tourism_knowledge/run.py | 独立离线 runner，复用既有 cases/artifact 模式 |
| backend/evals/tourism_knowledge/results.json | 真实执行的逐案例测量 artifact |
| backend/evals/tourism_knowledge/verification.json | 模块/回归与基线的紧凑验证证据 |
| docs/agent/TOURISM_KNOWLEDGE_PHASE_A_20260929.md | 本轮 Audit / ADR / evidence / merge report |
| docs/handoff/TOURISM_KNOWLEDGE_PHASE_A_20260929.md | 独立分支交接，避免覆盖并行全局 handoff |

## 8. Tests

VERIFIED：最终 Linux/Python 3.11、冻结依赖环境，模块 **82 passed in 0.75s**。覆盖四个必需 retrieval 场景、全部 taxonomy、destination/place/category/language/tag 过滤、tag AND 语义、来源继承与 JSON round-trip、heading/chunk identity、fixture 默认排除、expiry 精确边界、幂等文档替换、深拷贝、向量 batch/dimension/finite/nonzero 校验、provider 失败原子性、descriptor/version mismatch、缺索引降级、无 lexical overlap 的 semantic paraphrase、live traps、官方来源不会升级为 live fact、18点规划解释边界。

MEASURED：28 个独立案例；按模式排除不适用的单路案例，每种模式执行 27 条。固定小 corpus 上结果如下，全部是 fixture 测量，不是生产泛化率：

| 指标 | lexical | semantic fake | hybrid fake |
|---|---|---|---|
| Recall@3（有标注 relevant 文档的 query） | 12/12 | 13/13 | 13/13 |
| Category match@1 | 12/12 | 13/13 | 13/13 |
| Metadata filter accuracy（每个返回 hit） | 35/35 | 17/17 | 37/37 |
| Source preservation（每个返回 hit） | 35/35 | 17/17 | 37/37 |
| Live/decision boundary accuracy（含 stable negatives） | 27/27 | 27/27 | 27/27 |
| Expected-empty accuracy | 2/2 | 1/1 | 1/1 |

没有 relevant 标签的 live trap 不计入 Recall/category 分母；零命中不靠“全部过滤正确”的 vacuous truth 算成 hit-level 成功，另有 expected-empty 指标。伪语义概念是人工编写，Corpus 也为人工文本，本轮不测真实旅游事实正确率、真实 provider 质量或 held-out 泛化。无网络 corpus 抓取或 live provider 请求。fixture_clock 用于固定 expiry；measured_at 为实际 Linux 执行时间。

基线复跑（不收集新增模块测试）：**402 passed / 2 failed / 2 warnings，49.76s**。复现同两个原有失败：

1. test_assistant_tools.py::test_shrinking_populated_days_requires_resolution_and_cancel_is_read_only：`row.pending_action` 为 None，测试索引时 TypeError。
2. test_destination_research.py::test_rejection_clears_approval_and_next_request_uses_empty_formal_plan：`router.contexts` 为空，测试索引时 IndexError。

两者位于并行 Router/Assistant 工作边界；核心源码与快照相同，且现有 app 模块没有任何新模块引用。本轮不改这些测试或放宽断言。最终完整回归：**484 passed / 2 failed / 2 warnings，49.59s**；与基线相比增加 82 个 passing tests，无新增失败。紧凑 evidence 见 verification.json，其中最终计数由已完成容器日志解析，并保留被测源码 SHA256；非零退出不能宣称全项目 regression 全绿。两次既有 warnings 均为 Starlette HTTP_422_UNPROCESSABLE_ENTITY 弃用提醒。

复现命令（worktree 根目录；完整回归时不要在同项目并发创建 one-off Compose 容器）：

```powershell
docker compose -p roamsync-tourism-knowledge-test -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from api-test
# 完整回归退出后再执行以下独立验证
docker compose -p roamsync-tourism-knowledge-test -f compose.test.yaml run --rm --no-deps api-test uv run --no-sync pytest tests/test_tourism_knowledge.py -ra
docker compose -p roamsync-tourism-knowledge-test -f compose.test.yaml run --rm --no-deps api-test uv run --no-sync python -m evals.tourism_knowledge.run --output /tmp/tourism-knowledge-results.json
# 最后只清理本任务自己的 Compose 项目
docker compose -p roamsync-tourism-knowledge-test -f compose.test.yaml down -v
```

使用独立 project name、网络、tmpfs PostgreSQL；不复用/重启默认 roamsync-test 或开发数据库。未运行 Web/Android 回归：本轮完全独立 Python 模块且没有 API 注册、客户端、共享模型、配置、dependency 或 migration 变化。

## 9. Dependencies

零新增 dependency；复用 Pydantic + pytest，其他算法均 Python standard library。pyproject.toml、uv.lock、Compose、共享 config、数据库模型与 migrations 均未修改。

## 10. Merge Safety

独立分支：codex/tourism-knowledge-phase-a；worktree：E:/Study/RoamSync-tourism-knowledge。用临时 GIT_INDEX_FILE 和 commit-tree 创建当前后端快照，不触碰原仓库 index/working files；快照 parent 是原 HEAD，包含原先未提交源码，绝不可把整个快照分支直接 merge 到原 main。

仅 cherry-pick 本轮实现提交（其 parent 为 0fab288），或将该提交相对 parent 的新增文件 diff 应用到 Router 集成后的干净分支。可以在完成 Router 集成的干净分支执行 `git cherry-pick codex/tourism-knowledge-phase-a`（只应用 branch tip 的本轮实现）。Router、assistant routes/service、planning intent/graph/runtime、PlanningRun/Revision、研究链路以及它们的 tests 均零改动、零文件重叠。不要 cherry-pick snapshot commit，不清理/覆盖其他会话未提交修改。

本轮遵循用户“独立、低冲突”的要求，专门新增分支 handoff，未覆盖 AGENTS.md 默认要求的全局 PROJECT_STATE/LATEST_HANDOFF；建议集成人在合并后汇总这份交接。

## 11. Open Questions

真实知识来源/使用权与人工 review 标准；目的地行政编码与 corpus place_id canonicalization；真实 embedding provider、成本/维度/版本及重建策略；中文检索 held-out 数据；生产 PostgreSQL adapter 的 schema/index/分页策略；半稳定类别的有效期 policy；Companion 消费 unknown scope、空命中、provider error 和 source conflict 的行为；来源权威 taxonomy 在未来 Evidence 的共享方式。

## 12. Recommended Next Step

Router Phase 0 合并后，为 Companion 新增 tourism_knowledge_retrieval 工具 adapter，输入 InformationNeed 的显式 metadata filters，输出本契约并执行 knowledge/live/decision 约束。先用少量经审核的真实来源验证引用与回答边界，再决定持久化、中文索引和真实 embedding；不把 fake benchmark 的 100% 当生产质量证据，不提前实现 Weather/AMap Fact Resolver 或 Knowledge Agent。
