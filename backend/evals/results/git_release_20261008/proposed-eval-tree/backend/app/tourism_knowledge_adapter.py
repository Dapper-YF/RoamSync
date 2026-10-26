"""Only translates public Companion and Tourism Knowledge contracts."""
from datetime import UTC, datetime

from app.companion_contracts import (EvidenceAssertion, KnowledgeAdvisory, KnowledgeEvidence,
    KnowledgeToolRequest, KnowledgeToolResult)
from app.tourism_knowledge.interfaces import TourismKnowledgeRetriever
from app.tourism_knowledge.models import KnowledgeType, TourismKnowledgeRequest, TourismKnowledgeResult


class TourismKnowledgeToolAdapter:
    def __init__(self, retriever: TourismKnowledgeRetriever, *, supported_destinations: set[str] | None = None):
        self.retriever = retriever
        self.supported_destinations = supported_destinations

    async def retrieve(self, request: KnowledgeToolRequest) -> KnowledgeToolResult:
        if self.supported_destinations is not None and request.destination and request.destination not in self.supported_destinations:
            return KnowledgeToolResult(status="unavailable", outcome="unsupported_query")
        query = TourismKnowledgeRequest(query=request.query, destination=request.destination,
            knowledge_types=tuple(KnowledgeType(t) for t in request.knowledge_types), top_k=request.max_results,
            audience_tags=tuple(request.audience_tags), season_tags=tuple(request.season_tags),
            experience_tags=tuple(request.experience_tags), retrieval_mode="lexical", include_fixtures=False)
        try:
            result = TourismKnowledgeResult.model_validate(await self.retriever.retrieve_tourism_knowledge(query))
            if result.query != request.query:
                raise ValueError("retrieval query mismatch")
            evidence = []
            seen = set()
            now = datetime.now(UTC)
            for hit in result.hits[:request.max_results]:
                chunk = hit.chunk
                # Defensive public-contract validation, no ranking internals.
                if (chunk.source.source_type == "fixture" or (request.destination and chunk.destination != request.destination)
                    or (request.knowledge_types and chunk.knowledge_type.value not in request.knowledge_types)
                    or not set(request.audience_tags).issubset(chunk.audience_tags)
                    or not set(request.season_tags).issubset(chunk.season_tags)
                    or not set(request.experience_tags).issubset(chunk.experience_tags)
                    or chunk.language != "zh-CN" or (chunk.valid_until and chunk.valid_until <= now)):
                    raise ValueError("retrieval provenance/filter mismatch")
                ref = "knowledge_" + chunk.content_sha256[:16] + "_" + chunk.id[:32]
                if ref in seen:
                    continue
                seen.add(ref)
                applicability_value = chunk.metadata.get("applicability", "unspecified")
                scope_map = {
                    "hangzhou_or_westlake_stable_theme": ("place" if chunk.place_name else "destination", chunk.place_name or chunk.destination),
                    "west_lake_place": ("place", "西湖"),
                    "hangzhou_destination_theme": ("destination", "杭州"),
                    "general_senior_guidance_applied_as_discussion_not_local_facility_claim": ("audience", "senior"),
                    "seasonal_custom": ("season", "杭州·秋季"),
                }
                scope, target = scope_map.get(applicability_value, ("general_strategy" if chunk.audience_tags else "unspecified", None))
                evidence.append(KnowledgeEvidence(evidence_ref=ref, text=chunk.content[:2000],
                    source_reference=chunk.source.source_reference, knowledge_type=chunk.knowledge_type.value,
                    scope=chunk.knowledge_scope, document_id=chunk.document_id, chunk_id=chunk.id,
                    document_title=chunk.title, source_name=chunk.source.source_name, source_type=chunk.source.source_type,
                    source_authority=chunk.source.source_authority.value, reviewed_at=chunk.reviewed_at,
                    ingested_at=chunk.ingested_at, valid_until=chunk.valid_until,
                    external_place_ref=("tourism_corpus:" + chunk.place_id) if chunk.place_id else None,
                    place_name=chunk.place_name,
                    applicability=scope, applicability_target=target,
                    content_origin=chunk.metadata.get("content_origin", "source_paraphrase"),
                    source_page_title=chunk.metadata.get("source_page_title"), curator_title=chunk.title,
                    answerable_assertions=[EvidenceAssertion.model_validate(item)
                        for item in chunk.metadata.get("answerable_assertions", [])]))
            advisory = KnowledgeAdvisory.model_validate(result.advisory.model_dump())
            outcome = ("decision_context_required" if advisory.planning_decision_context_required else
                "live_verification_required" if advisory.live_fact_verification_required else
                "no_results" if not evidence else "knowledge_insufficient" if not advisory.knowledge_sufficient else "available")
            return KnowledgeToolResult(status="available" if evidence else "unavailable", evidence=evidence,
                outcome=outcome, advisory=advisory, retrieval_mode=result.effective_mode, retrieved_at=result.retrieved_at)
        except Exception:
            # Never include raw provider errors, source payloads or secrets.
            return KnowledgeToolResult(status="unavailable", outcome="retriever_unavailable")
