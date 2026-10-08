"""Stable async tool contract; no database/embedding details exposed to Agents."""
from datetime import UTC, datetime
from typing import Callable

from .boundary import assess_suitability
from .interfaces import EmbeddingProvider, KnowledgeRepository
from .models import KnowledgeHit, TourismKnowledgeRequest, TourismKnowledgeResult
from .ranking import lexical_rank, reciprocal_rank_fusion, semantic_rank, validate_vectors
from .repository import matches_filters


class SemanticRetrievalUnavailable(RuntimeError):
    pass


class TourismKnowledgeService:
    def __init__(self, repository: KnowledgeRepository, embedding_provider: EmbeddingProvider | None = None,
                 *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.clock = clock

    async def retrieve_tourism_knowledge(self, request: TourismKnowledgeRequest) -> TourismKnowledgeResult:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("retrieval clock must be timezone-aware")
        advisory = assess_suitability(request.query)
        # Defensive validation protects the tool contract from a future faulty adapter.
        candidates = [item for item in await self.repository.candidates(request, now=now)
                      if matches_filters(item, request, now=now)]
        lexical = lexical_rank(request.query, candidates) if request.retrieval_mode != "semantic" else {}
        semantic = {}
        warnings = []
        mode = request.retrieval_mode
        if mode != "lexical":
            if self.embedding_provider is None:
                if mode == "semantic":
                    raise SemanticRetrievalUnavailable("semantic retrieval requires an embedding provider")
                mode = "lexical"
                warnings.append("semantic_provider_not_configured_using_lexical")
            else:
                descriptor = self.embedding_provider.descriptor
                eligible = [item for item in candidates if item.vector is not None and item.chunk.embedding == descriptor]
                if len(eligible) != len(candidates):
                    warnings.append("some_chunks_missing_matching_embedding_index")
                if candidates and not eligible:
                    if mode == "semantic":
                        raise SemanticRetrievalUnavailable("corpus must be indexed with the configured embedding descriptor")
                    mode = "lexical"
                    warnings.append("semantic_index_unavailable_using_lexical")
                elif eligible:
                    query_vector = validate_vectors(await self.embedding_provider.embed([request.query]),
                                                    count=1, dimensions=descriptor.dimensions)[0]
                    semantic = semantic_rank(query_vector, eligible)
        if mode == "hybrid":
            scores = reciprocal_rank_fusion(lexical, semantic, limit=max(100, request.top_k * 4))
            kind = "reciprocal_rank_fusion"
        elif mode == "semantic":
            scores, kind = semantic, "cosine"
        else:
            scores, kind = lexical, "bm25"
        by_id = {item.chunk.id: item.chunk for item in candidates}
        ordered = sorted(scores, key=lambda key: (-scores[key], key))[:request.top_k]
        hits = tuple(KnowledgeHit(chunk=by_id[key], score=scores[key], retrieval_method=mode,
                                 lexical_score=lexical.get(key), semantic_score=semantic.get(key)) for key in ordered)
        sufficient = bool(hits) and not advisory.live_fact_verification_required and not advisory.planning_decision_context_required
        reasons = advisory.reasons + (("no_matching_knowledge",) if not hits else ())
        advisory = advisory.model_copy(update={"knowledge_sufficient": sufficient, "reasons": reasons,
                                                "warnings": tuple(warnings)})
        return TourismKnowledgeResult(query=request.query, retrieved_at=now, hits=hits, advisory=advisory,
                                      effective_mode=mode, score_kind=kind)
