"""Isolated retrieval, provenance and boundary tests; no network or database."""
import asyncio
import math
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.tourism_knowledge.boundary import assess_suitability
from app.tourism_knowledge.ingestion import CuratedKnowledgeIngestor, chunk_document
from app.tourism_knowledge.interfaces import IndexedChunk
from app.tourism_knowledge.models import EmbeddingMetadata, KnowledgeDocument, TourismKnowledgeRequest, TourismKnowledgeResult
from app.tourism_knowledge.ranking import reciprocal_rank_fusion, tokenize
from app.tourism_knowledge.repository import InMemoryKnowledgeRepository
from app.tourism_knowledge.service import SemanticRetrievalUnavailable, TourismKnowledgeService
from evals.tourism_knowledge.fixtures import DeterministicFixtureEmbedding, NOW, fixture_repository, load_documents
from evals.tourism_knowledge.run import evaluate


def run(coro):
    return asyncio.run(coro)


def document(**updates):
    base = load_documents()[0].model_dump()
    base.update(updates)
    return KnowledgeDocument.model_validate(base)


def retrieve(query, *, mode="lexical", provider=None, **filters):
    async def scenario():
        repo = await fixture_repository(provider)
        service = TourismKnowledgeService(repo, provider, clock=lambda: NOW)
        return await service.retrieve_tourism_knowledge(TourismKnowledgeRequest(
            query=query, destination=filters.pop("destination", "杭州"), include_fixtures=True,
            retrieval_mode=mode, **filters))
    return run(scenario())


@pytest.mark.parametrize("query,expected,filters", [
    ("西湖有什么历史背景？", "fixture-history", {}),
    ("带父母去杭州怎么玩比较轻松？", "fixture-senior", {"knowledge_types":["audience_strategy"],"audience_tags":["senior"]}),
    ("秋天杭州有什么值得体验的？", "fixture-autumn", {"knowledge_types":["seasonal_experience"],"season_tags":["autumn"]}),
    ("杭州有什么比较当地生活化的体验？", "fixture-lifestyle", {}),
])
def test_required_retrieval_cases(query, expected, filters):
    result = retrieve(query, **filters)
    assert result.hits[0].chunk.document_id == expected
    assert result.advisory.knowledge_sufficient
    assert not result.advisory.live_fact_verification_required


@pytest.mark.parametrize("query", [
    "西湖今天几点关门？", "西湖今天开到几点？", "现在临时闭馆吗？", "杭州当前天气", "明天下雨吗？",
    "当前票价多少？", "门票库存还有吗？", "GPS定位", "ETA是多少？", "实时交通路况", "我已经玩了多久？",
    "灵隐寺开放时间", "How long have I spent here?", "opening hours", "ticket availability", "current weather",
    "实时日落", "How long to reach the museum?", "今天西湖历史介绍活动有哪些？", "公交班次", "西湖什么时候开放？",
])
def test_live_boundary(query):
    result = retrieve(query)
    assert result.advisory.live_fact_verification_required
    assert not result.advisory.knowledge_sufficient
    assert result.advisory.evidence_kind == "tourism_knowledge_not_live_verified"


@pytest.mark.parametrize("query", ["西湖的历史？", "杭州茶文化", "秋季体验通常有哪些", "父母旅行的一般节奏", "当地生活方式"])
def test_stable_boundary(query):
    assert not assess_suitability(query).live_fact_verification_required


@pytest.mark.parametrize("query", ["为什么你建议我18点去西湖？", "为什么安排１８：００游西湖？", "Why suggest West Lake at 6pm?"])
def test_timing_explanation_needs_decision_and_live_context(query):
    advisory = assess_suitability(query)
    assert advisory.planning_decision_context_required
    assert advisory.live_fact_verification_required
    assert not advisory.knowledge_sufficient


@pytest.mark.parametrize("filters,expected", [
    ({"place_id":"fixture:lingyin"}, {"fixture-place"}),
    ({"audience_tags":["family"]}, {"fixture-family"}),
    ({"season_tags":["autumn"], "experience_tags":["photography","walking"]}, {"fixture-lifestyle"}),
    ({"destination":"其他城市"}, {"fixture-other-city"}),
    ({"language":"en"}, {"fixture-english"}),
    ({"knowledge_types":["destination_profile","place_experience"]}, {"fixture-profile","fixture-place"}),
    ({"audience_tags":["senior","family"]}, set()),
    ({"destination":"不存在"}, set()),
    ({"season_tags":["winter"]}, set()),
    ({"place_id":"unknown"}, set()),
])
def test_hard_filters(filters, expected):
    query = "West Lake history" if filters.get("language") == "en" else "西湖杭州历史城市空间灵隐景区体验亲子家庭当地生活化摄影"
    result = retrieve(query, top_k=50, **filters)
    assert {hit.chunk.document_id for hit in result.hits} == expected


def test_fixtures_excluded_by_default_and_no_match_is_insufficient():
    async def scenario():
        service = TourismKnowledgeService(await fixture_repository(), clock=lambda: NOW)
        result = await service.retrieve_tourism_knowledge(TourismKnowledgeRequest(query="西湖历史"))
        assert not result.hits
        assert not result.advisory.knowledge_sufficient
        assert "no_matching_knowledge" in result.advisory.reasons
    run(scenario())
    assert not retrieve("qzxv987654").hits


def test_expiry_is_hard_filter_at_exact_boundary():
    async def scenario():
        repo = InMemoryKnowledgeRepository()
        doc = document(knowledge_scope="semi_stable", valid_until=NOW)
        await CuratedKnowledgeIngestor(repo).ingest(doc)
        request = TourismKnowledgeRequest(query="历史", include_fixtures=True)
        assert await repo.candidates(request, now=NOW - timedelta(seconds=1))
        assert not await repo.candidates(request, now=NOW)
    run(scenario())
    assert all(hit.chunk.document_id != "fixture-expired" for hit in retrieve("秋天杭州", top_k=50).hits)


@pytest.mark.parametrize("updates", [
    {"knowledge_scope":"live_fact"}, {"knowledge_scope":"semi_stable"},
    {"valid_until":"2025-01-01T00:00:00Z"}, {"ingested_at":"2026-01-01T00:00:00"},
    {"knowledge_type":"weather"}, {"language":""}, {"content":"  "}, {"id":""},
])
def test_invalid_documents(updates):
    with pytest.raises(ValidationError):
        document(**updates)


@pytest.mark.parametrize("updates", [{"query":" "}, {"top_k":0}, {"top_k":51}, {"unexpected":True},
                                           {"retrieval_mode":"vector_sql"}, {"knowledge_types":["live_weather"]}])
def test_invalid_requests(updates):
    with pytest.raises(ValidationError):
        TourismKnowledgeRequest.model_validate({"query":"历史", **updates})


def test_chunking_provenance_heading_size_content_and_stable_identity():
    doc = document(content="# 主标题\n" + "历史背景" * 45 + "\n## 子标题\n茶文化测试", audience_tags=["senior"], season_tags=["autumn"])
    chunks = chunk_document(doc, max_characters=64)
    assert len(chunks) > 2
    assert chunks == chunk_document(doc, max_characters=64)
    assert len({chunk.id for chunk in chunks}) == len(chunks)
    assert "历史背景" * 45 in "".join(chunk.content for chunk in chunks)
    assert chunks[-1].heading_path == ("主标题", "子标题")
    for index, chunk in enumerate(chunks):
        assert chunk.chunk_index == index
        assert chunk.approximate_size == len(chunk.content) <= 64
        assert chunk.source == doc.source
        assert chunk.document_id == doc.id
        assert chunk.audience_tags == doc.audience_tags
        assert chunk.season_tags == doc.season_tags
        assert chunk.metadata == doc.metadata
    with pytest.raises(ValueError):
        chunk_document(doc, max_characters=1)


def test_ingestion_replacement_removes_old_chunks_and_results_are_detached():
    async def scenario():
        repo = InMemoryKnowledgeRepository()
        ingest = CuratedKnowledgeIngestor(repo, max_characters=64)
        doc = document(content="历史背景" * 100)
        old = await ingest.ingest(doc)
        doc.metadata["caller_mutation"] = True
        request = TourismKnowledgeRequest(query="历史", include_fixtures=True)
        stored = await repo.candidates(request, now=NOW)
        assert "caller_mutation" not in stored[0].chunk.metadata
        stored[0].chunk.metadata["reader_mutation"] = True
        assert "reader_mutation" not in (await repo.candidates(request, now=NOW))[0].chunk.metadata
        updated = document(content="新的文化内容")
        new = await ingest.ingest(updated)
        assert len(new) == 1
        assert not {chunk.id for chunk in old} & {chunk.id for chunk in new}
        assert len(await repo.candidates(request, now=NOW)) == 1
        await ingest.ingest(updated)
        assert len(await repo.candidates(request, now=NOW)) == 1
    run(scenario())


def test_repository_rejects_provenance_mismatch():
    async def scenario():
        repo = InMemoryKnowledgeRepository()
        doc = document()
        chunk = chunk_document(doc)[0].model_copy(update={"destination":"不同城市"})
        with pytest.raises(ValueError, match="provenance"):
            await repo.replace_document(doc, [IndexedChunk(chunk)])
        assert not await repo.candidates(TourismKnowledgeRequest(query="历史", include_fixtures=True), now=NOW)
    run(scenario())


def test_result_round_trip_preserves_all_sources_without_vectors():
    result = retrieve("西湖历史背景", top_k=2)
    parsed = TourismKnowledgeResult.model_validate_json(result.model_dump_json())
    assert parsed == result
    source = load_documents()[0].source
    assert parsed.hits[0].chunk.source == source
    assert parsed.hits[0].chunk.source.updated_at == source.updated_at
    assert "vector" not in result.model_dump_json()


def test_lexical_default_hybrid_fallback_is_explicit():
    result = retrieve("西湖历史", mode="hybrid")
    assert result.effective_mode == "lexical"
    assert result.score_kind == "bm25"
    assert "semantic_provider_not_configured_using_lexical" in result.advisory.warnings
    with pytest.raises(SemanticRetrievalUnavailable):
        retrieve("西湖历史", mode="semantic")


@pytest.mark.parametrize("mode", ["semantic", "hybrid"])
def test_semantic_paraphrase_without_lexical_overlap(mode):
    assert not retrieve("长辈省体力").hits
    result = retrieve("长辈省体力", mode=mode, provider=DeterministicFixtureEmbedding())
    assert result.hits[0].chunk.document_id == "fixture-senior"
    assert result.hits[0].semantic_score > 0
    assert result.hits[0].lexical_score is None
    assert result.effective_mode == mode


def test_embedding_model_version_mismatch_cannot_be_compared():
    async def scenario():
        provider = DeterministicFixtureEmbedding()
        repo = await fixture_repository(provider)
        provider.descriptor = provider.descriptor.model_copy(update={"version":"v2"})
        service = TourismKnowledgeService(repo, provider, clock=lambda: NOW)
        request = TourismKnowledgeRequest(query="西湖历史", include_fixtures=True)
        result = await service.retrieve_tourism_knowledge(request)
        assert result.effective_mode == "lexical"
        assert "semantic_index_unavailable_using_lexical" in result.advisory.warnings
        with pytest.raises(SemanticRetrievalUnavailable):
            await service.retrieve_tourism_knowledge(request.model_copy(update={"retrieval_mode":"semantic"}))
    run(scenario())


@pytest.mark.parametrize("vectors", [[], [[1]], [[0]*9], [[math.nan]*9], [[math.inf]*9], [[1]*9,[1]*9]])
def test_invalid_embedding_does_not_replace_document(vectors):
    class Broken(DeterministicFixtureEmbedding):
        async def embed(self, texts):
            return vectors
    async def scenario():
        repo = InMemoryKnowledgeRepository()
        await CuratedKnowledgeIngestor(repo).ingest(document())
        request = TourismKnowledgeRequest(query="历史", include_fixtures=True)
        before = await repo.candidates(request, now=NOW)
        with pytest.raises(ValueError):
            await CuratedKnowledgeIngestor(repo, Broken()).ingest(document(content="新版内容"))
        assert await repo.candidates(request, now=NOW) == before
    run(scenario())


def test_query_embedding_invalid_is_not_silently_used():
    class Broken(DeterministicFixtureEmbedding):
        async def embed(self, texts):
            return [[1]]
    async def scenario():
        repo = await fixture_repository(DeterministicFixtureEmbedding())
        service = TourismKnowledgeService(repo, Broken(), clock=lambda: NOW)
        with pytest.raises(ValueError):
            await service.retrieve_tourism_knowledge(TourismKnowledgeRequest(query="历史", include_fixtures=True))
    run(scenario())


def test_recent_official_source_does_not_turn_knowledge_into_live_fact():
    async def scenario():
        doc = document(source={"source_type":"internal", "source_name":"Curated test", "source_reference":"internal:test",
                              "source_authority":"official_attraction", "updated_at":NOW}, ingested_at=NOW)
        repo = InMemoryKnowledgeRepository()
        await CuratedKnowledgeIngestor(repo).ingest(doc)
        result = await TourismKnowledgeService(repo, clock=lambda: NOW).retrieve_tourism_knowledge(
            TourismKnowledgeRequest(query="西湖历史与今天关门时间"))
        assert result.hits
        assert result.advisory.live_fact_verification_required
        assert not result.advisory.knowledge_sufficient
    run(scenario())


def test_provider_failure_preserves_prior_ingestion():
    class Failing(DeterministicFixtureEmbedding):
        async def embed(self, texts):
            raise RuntimeError("fixture_provider_unavailable")
    async def scenario():
        repo = InMemoryKnowledgeRepository()
        await CuratedKnowledgeIngestor(repo).ingest(document())
        request = TourismKnowledgeRequest(query="历史", include_fixtures=True)
        before = await repo.candidates(request, now=NOW)
        with pytest.raises(RuntimeError, match="fixture_provider_unavailable"):
            await CuratedKnowledgeIngestor(repo, Failing()).ingest(document(content="replacement"))
        assert await repo.candidates(request, now=NOW) == before
    run(scenario())


def test_partial_embedding_index_is_visible_and_hard_filters_apply_to_semantics():
    async def scenario():
        provider = DeterministicFixtureEmbedding()
        repo = await fixture_repository(provider)
        await CuratedKnowledgeIngestor(repo).ingest(load_documents()[0])
        service = TourismKnowledgeService(repo, provider, clock=lambda: NOW)
        result = await service.retrieve_tourism_knowledge(TourismKnowledgeRequest(query="西湖历史", destination="杭州", include_fixtures=True))
        assert "some_chunks_missing_matching_embedding_index" in result.advisory.warnings
        result = await service.retrieve_tourism_knowledge(TourismKnowledgeRequest(query="长辈省体力", destination="杭州",
            audience_tags=["family"], include_fixtures=True, retrieval_mode="semantic"))
        assert not result.hits
    run(scenario())


def test_defensive_filters_even_if_repository_adapter_ignores_contract():
    class Unfiltered:
        async def candidates(self, request, *, now):
            return [IndexedChunk(chunk_document(doc)[0]) for doc in load_documents()]
    service = TourismKnowledgeService(Unfiltered(), clock=lambda: NOW)
    result = run(service.retrieve_tourism_knowledge(TourismKnowledgeRequest(query="西湖历史")))
    assert not result.hits


def test_rrf_is_rank_based_and_deterministic():
    result = reciprocal_rank_fusion({"a":1000,"b":3}, {"b":0.9,"c":0.8})
    assert max(result, key=result.get) == "b"
    assert result["a"] == pytest.approx(1/61)
    assert result["b"] == pytest.approx(1/62 + 1/61)
    assert tokenize("ＷＥＳＴ 西湖") == tokenize("west 西湖")


@pytest.mark.parametrize("mode", ["lexical","semantic","hybrid"])
def test_offline_benchmark(mode):
    report = run(evaluate(mode))
    for key in ("recall_at_3", "category_match_at_1", "metadata_filter_accuracy_per_hit", "source_preservation_per_hit",
                "live_fact_boundary_accuracy", "empty_result_accuracy"):
        assert report[key]["rate"] == 1, (key, report[key])
    assert report["provider_calls"] == 0
