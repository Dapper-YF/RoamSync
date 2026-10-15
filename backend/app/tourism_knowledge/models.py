"""Versioned public contracts. Source authority describes provenance, not truth."""
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class KnowledgeType(str, Enum):
    DESTINATION_PROFILE = "destination_profile"
    HISTORY_CULTURE = "history_culture"
    PLACE_EXPERIENCE = "place_experience"
    TRAVEL_STRATEGY = "travel_strategy"
    AUDIENCE_STRATEGY = "audience_strategy"
    SEASONAL_EXPERIENCE = "seasonal_experience"
    LOCAL_LIFESTYLE = "local_lifestyle"


class SourceAuthority(str, Enum):
    OFFICIAL_GOVERNMENT = "official_government"
    OFFICIAL_DESTINATION = "official_destination"
    OFFICIAL_MUSEUM = "official_museum"
    OFFICIAL_ATTRACTION = "official_attraction"
    INSTITUTIONAL = "institutional"
    HIGH_QUALITY_EDITORIAL = "high_quality_editorial"
    COMMERCIAL_TRAVEL = "commercial_travel"
    UGC = "ugc"
    INTERNAL_CURATED = "internal_curated"


class KnowledgeSource(Contract):
    source_type: Literal["web", "publication", "internal", "fixture"]
    source_name: str = Field(min_length=1, max_length=240)
    source_reference: str = Field(min_length=1, max_length=2000)
    source_authority: SourceAuthority
    published_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None


class KnowledgeMetadata(Contract):
    destination: str = Field(min_length=1, max_length=120)
    # Corpus identity, optionally namespaced (amap:...); never a trip-owned POI FK.
    place_id: str | None = Field(default=None, min_length=1, max_length=240)
    place_name: str | None = Field(default=None, min_length=1, max_length=240)
    knowledge_type: KnowledgeType
    audience_tags: tuple[str, ...] = ()
    season_tags: tuple[str, ...] = ()
    experience_tags: tuple[str, ...] = ()
    source: KnowledgeSource
    ingested_at: AwareDatetime
    reviewed_at: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    knowledge_scope: Literal["stable", "semi_stable"] = "stable"
    language: str = Field(default="zh-CN", min_length=2, max_length=35)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_review_window(self):
        if self.valid_until is not None:
            start = self.reviewed_at or self.ingested_at
            if self.valid_until <= start:
                raise ValueError("valid_until must follow reviewed_at/ingested_at")
        if self.knowledge_scope == "semi_stable" and self.valid_until is None:
            raise ValueError("semi_stable knowledge requires an explicit review expiry")
        return self


class KnowledgeDocument(KnowledgeMetadata):
    id: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200000)


class EmbeddingMetadata(Contract):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    dimensions: int = Field(ge=1)
    version: str = Field(min_length=1)


class KnowledgeChunk(KnowledgeMetadata):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    approximate_size: int = Field(ge=1, description="Unicode characters, not model tokens")
    heading_path: tuple[str, ...] = ()
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    embedding: EmbeddingMetadata | None = None


class TourismKnowledgeRequest(Contract):
    contract_version: Literal["tourism-knowledge-v1"] = "tourism-knowledge-v1"
    query: str = Field(min_length=1, max_length=4000)
    destination: str | None = Field(default=None, min_length=1, max_length=120)
    place_id: str | None = Field(default=None, min_length=1, max_length=240)
    knowledge_types: tuple[KnowledgeType, ...] = ()
    audience_tags: tuple[str, ...] = ()
    season_tags: tuple[str, ...] = ()
    experience_tags: tuple[str, ...] = ()
    language: str = Field(default="zh-CN", min_length=2, max_length=35)
    top_k: int = Field(default=5, ge=1, le=50)
    retrieval_mode: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    include_fixtures: bool = False


class RetrievalAdvisory(Contract):
    knowledge_sufficient: bool = Field(default=False, description="Scope advisory: relevant knowledge exists and no live/decision signal was detected; not a factual correctness guarantee")
    live_fact_verification_required: bool = False
    planning_decision_context_required: bool = False
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    # Never upgraded by a high similarity score, source authority or recent ingestion.
    evidence_kind: Literal["tourism_knowledge_not_live_verified"] = "tourism_knowledge_not_live_verified"


class KnowledgeHit(Contract):
    chunk: KnowledgeChunk
    score: float = Field(ge=0)
    retrieval_method: Literal["lexical", "semantic", "hybrid"]
    lexical_score: float | None = None
    semantic_score: float | None = None


class TourismKnowledgeResult(Contract):
    contract_version: Literal["tourism-knowledge-v1"] = "tourism-knowledge-v1"
    query: str
    retrieved_at: AwareDatetime
    hits: tuple[KnowledgeHit, ...] = ()
    advisory: RetrievalAdvisory
    effective_mode: Literal["lexical", "semantic", "hybrid"]
    score_kind: Literal["bm25", "cosine", "reciprocal_rank_fusion"]
