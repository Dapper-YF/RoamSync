"""Companion-owned contracts. None is an Activity, Candidate or PlanRevision."""
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.assistant_places import PlaceView
from app.schemas import TravelGoalRouting
from app.travel_facts.models import FactRequirement, ResolvedFact
from app.companion_facts import ForecastPlan

CompanionGoal = Literal["travel_chat", "destination_exploration", "destination_discovery",
    "travel_advice", "comparison", "recommendation", "explanation"]
SuggestionStatus = Literal["suggested", "discussed", "user_liked", "user_confirmed", "must_do"]
KnowledgeType = Literal["destination_profile", "history_culture", "place_experience",
    "travel_strategy", "audience_strategy", "seasonal_experience", "local_lifestyle"]
AnswerMode = Literal["factual", "advisory", "mixed"]
ClaimType = Literal["retrieved_fact", "supported_summary", "curator_inference", "agent_inference", "recommendation"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EvidenceApplicability(Contract):
    scope: Literal["general", "destination", "place", "audience", "season", "current_trip"]
    target: str | None = Field(default=None, max_length=120)


class EvidenceAssertion(Contract):
    """Reviewed, server-owned assertion selectable as a sourced answer claim."""
    assertion_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,119}$")
    text: str = Field(min_length=1, max_length=1000)
    claim_type: Literal["retrieved_fact", "supported_summary", "curator_inference"]
    topics: list[str] = Field(default_factory=list, max_length=8)
    applicability: EvidenceApplicability


class EntityReference(Contract):
    kind: Literal["raw_mention", "suggestion", "external_place", "formal_activity"]
    value: str = Field(min_length=1, max_length=240)


class InformationNeed(Contract):
    knowledge_decision: Literal["general_knowledge", "context_required", "rag_candidate", "live_fact_required", "mixed"] = "general_knowledge"
    knowledge_strategy: Literal["selective", "general_only", "forced_rag"] = "selective"
    knowledge_reasons: list[str] = Field(default_factory=list, max_length=8)
    source_required: bool = False
    optional_rag: bool = False
    knowledge_required: bool = False
    general_knowledge_allowed: bool = False
    knowledge_types: list[KnowledgeType] = Field(default_factory=list, max_length=7)
    live_fact_required: bool = False
    forecast_required: bool = False
    opening_hours_required: bool = False
    fact_requirements: list[FactRequirement] = Field(default_factory=list, max_length=32)
    fact_types: list[str] = Field(default_factory=list, max_length=8)
    search_required: bool = False
    decision_history_required: bool = False
    trip_context_required: bool = False
    preferences_required: bool = False
    itinerary_required: bool = False
    audience_tags: list[str] = Field(default_factory=list, max_length=8)
    season_tags: list[str] = Field(default_factory=list, max_length=4)
    experience_tags: list[str] = Field(default_factory=list, max_length=8)
    filter_signals: list[str] = Field(default_factory=list, max_length=8)
    answer_mode: AnswerMode = "advisory"
    requested_fact_topics: list[str] = Field(default_factory=list, max_length=8)


class InformationGap(Contract):
    code: Literal["knowledge_unavailable", "live_fact_unavailable", "rationale_unavailable",
        "ambiguous_suggestion", "unknown_suggestion", "provider_unavailable", "knowledge_no_results",
        "knowledge_unsupported_query", "knowledge_insufficient"]
    message: str = Field(min_length=1, max_length=500)


class KnowledgeEvidence(Contract):
    evidence_ref: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=4000)
    source_reference: str = Field(min_length=1, max_length=2000)
    knowledge_type: KnowledgeType
    scope: Literal["stable", "semi_stable"] = "stable"
    document_id: str | None = Field(default=None, max_length=240)
    chunk_id: str | None = Field(default=None, max_length=240)
    document_title: str | None = Field(default=None, max_length=240)
    source_name: str | None = Field(default=None, max_length=240)
    source_type: str | None = None
    source_authority: str | None = None
    reviewed_at: datetime | None = None
    ingested_at: datetime | None = None
    valid_until: datetime | None = None
    external_place_ref: str | None = Field(default=None, max_length=300)
    place_name: str | None = Field(default=None, max_length=240)
    applicability: Literal["general", "destination", "place", "audience", "season", "current_trip",
        "destination_specific", "general_strategy", "unspecified"] = "unspecified"
    applicability_target: str | None = Field(default=None, max_length=120)
    content_origin: Literal["source_paraphrase", "curator_inference_mixed"] = "source_paraphrase"
    source_page_title: str | None = Field(default=None, max_length=300)
    curator_title: str | None = Field(default=None, max_length=300)
    answerable_assertions: list[EvidenceAssertion] = Field(default_factory=list, max_length=10)


class KnowledgeAdvisory(Contract):
    knowledge_sufficient: bool = False
    live_fact_verification_required: bool = False
    planning_decision_context_required: bool = False
    reasons: list[str] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)
    evidence_kind: Literal["tourism_knowledge_not_live_verified"] = "tourism_knowledge_not_live_verified"


class KnowledgeToolRequest(Contract):
    query: str = Field(min_length=1, max_length=4000)
    destination: str | None = None
    knowledge_types: list[KnowledgeType] = Field(default_factory=list)
    max_results: int = Field(default=5, ge=1, le=10)
    audience_tags: list[str] = Field(default_factory=list, max_length=8)
    season_tags: list[str] = Field(default_factory=list, max_length=4)
    experience_tags: list[str] = Field(default_factory=list, max_length=8)


class KnowledgeToolResult(Contract):
    status: Literal["available", "unavailable"]
    evidence: list[KnowledgeEvidence] = Field(default_factory=list, max_length=10)
    outcome: Literal["available", "no_results", "retriever_unavailable", "unsupported_query",
        "knowledge_insufficient", "live_verification_required", "decision_context_required"] | None = None
    advisory: KnowledgeAdvisory | None = None
    retrieval_mode: Literal["lexical", "semantic", "hybrid"] | None = None
    retrieved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_availability(self):
        if (self.status == "available") != bool(self.evidence):
            raise ValueError("available knowledge requires evidence")
        if len({e.evidence_ref for e in self.evidence}) != len(self.evidence):
            raise ValueError("knowledge evidence references must be unique")
        if self.outcome == "available" and self.status != "available":
            raise ValueError("available outcome requires available evidence")
        if self.outcome in {"no_results", "retriever_unavailable", "unsupported_query"} and self.status != "unavailable":
            raise ValueError("empty/error outcomes cannot supply available evidence")
        if self.outcome == "live_verification_required" and (not self.advisory or not self.advisory.live_fact_verification_required):
            raise ValueError("live outcome requires matching advisory")
        if self.outcome == "decision_context_required" and (not self.advisory or not self.advisory.planning_decision_context_required):
            raise ValueError("decision outcome requires matching advisory")
        if self.outcome == "available" and self.advisory and (not self.advisory.knowledge_sufficient
            or self.advisory.live_fact_verification_required or self.advisory.planning_decision_context_required):
            raise ValueError("available answer outcome cannot override restrictive advisory")
        return self


class KnowledgeToolPort(Protocol):
    async def retrieve(self, request: KnowledgeToolRequest) -> KnowledgeToolResult: ...


class KnowledgeRetrievalSummary(Contract):
    quality_rejections: list[str] = Field(default_factory=list, max_length=10)
    accepted_evidence_count: int = Field(default=0, ge=0, le=10)
    status: Literal["available", "unavailable"]
    outcome: str | None = None
    advisory: KnowledgeAdvisory | None = None
    retrieval_mode: str | None = None
    retrieved_at: datetime | None = None
    retrieved_document_refs: list[str] = Field(default_factory=list, max_length=10)
    retrieved_chunk_refs: list[str] = Field(default_factory=list, max_length=10)


class CompanionSuggestion(Contract):
    place_ref: PlaceView | None = None
    suggestion_id: str = Field(pattern=r"^suggestion_[0-9a-f]{32}$")
    suggestion_type: Literal["place", "destination", "experience", "strategy"]
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1000)
    entity_refs: list[EntityReference] = Field(default_factory=list, max_length=10)
    destination: str | None = None
    reasons: list[str] = Field(default_factory=list, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    grounding: Literal["unverified_proposal", "knowledge_supported"]
    created_at: datetime
    conversation_turn_id: str
    status: SuggestionStatus = "suggested"


class SuggestionInteraction(Contract):
    suggestion_id: str
    status: SuggestionStatus
    source_turn_id: str


class CompanionExplanation(Contract):
    subject_ref: EntityReference | None = None
    explanation_type: Literal["original_saved_suggestion", "original_validated_decision",
        "current_reconstruction", "rationale_unavailable", "saved_plan_notes"]
    reasons: list[str] = Field(default_factory=list, max_length=10)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    based_on_prior_decision: bool = False
    source_turn_ref: str | None = None
    source_decision_ref: str | None = None
    fact_freshness_warning: str | None = None
    missing_evidence: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def original_requires_provenance(self):
        original = self.explanation_type.startswith("original_")
        if self.based_on_prior_decision != original:
            raise ValueError("original and reconstructed rationale must be distinguished")
        if original and (not self.subject_ref or not (self.source_turn_ref or self.source_decision_ref) or not self.reasons):
            raise ValueError("original rationale requires persisted identity, reasons and source")
        if self.explanation_type == "original_saved_suggestion" and (self.subject_ref.kind != "suggestion" or not self.source_turn_ref):
            raise ValueError("saved suggestion rationale requires a suggestion and originating turn")
        if self.explanation_type == "original_validated_decision" and (self.subject_ref.kind != "formal_activity" or not self.source_decision_ref):
            raise ValueError("validated decision rationale requires a formal activity and source decision")
        if self.explanation_type == "saved_plan_notes" and (not self.source_decision_ref or not self.reasons or not self.fact_freshness_warning):
            raise ValueError("saved plan notes require provenance and an explicit verification limitation")
        return self


class CompanionComparison(Contract):
    options: list[str] = Field(min_length=2, max_length=5)
    dimensions: list[str] = Field(default_factory=list, max_length=8)
    summary: str = Field(min_length=1, max_length=1500)


class PreferenceStatement(Contract):
    text: str = Field(min_length=1, max_length=1000)
    source_turn_id: str
    scope: Literal["conversation"] = "conversation"


class BriefInterest(Contract):
    suggestion_ref: str
    display_name: str
    entity_refs: list[EntityReference] = Field(default_factory=list)
    status: SuggestionStatus
    source_turn_ref: str


class PlanningBrief(Contract):
    brief_id: str = Field(pattern=r"^brief_[0-9a-f]{32}$")
    status: Literal["prepared", "needs_clarification"]
    authorization_turn_id: str
    user_request: str = Field(min_length=1, max_length=4000)
    destination: str | None = None
    date_request: str | None = None
    duration_days: int | None = Field(default=None, ge=1, le=31)
    party_statement: str | None = None
    budget_statement: str | None = None
    confirmed_preferences: list[PreferenceStatement] = Field(default_factory=list, max_length=30)
    avoidances: list[PreferenceStatement] = Field(default_factory=list, max_length=30)
    candidate_interests: list[BriefInterest] = Field(default_factory=list, max_length=10)
    must_do: list[str] = Field(default_factory=list, max_length=10)
    user_decisions: list[PreferenceStatement] = Field(default_factory=list, max_length=30)
    open_questions: list[str] = Field(default_factory=list, max_length=10)
    source_turn_refs: list[str] = Field(default_factory=list, max_length=60)
    suggestion_refs: list[str] = Field(default_factory=list, max_length=10)
    effective_requirements: list[dict] = Field(default_factory=list, max_length=200)


class CompanionContext(Contract):
    read_tool_context: dict = Field(default_factory=dict)
    assistant_context: dict | None = None
    place_context: list[dict] = Field(default_factory=list, max_length=10)
    current_message: str
    travel_goal: TravelGoalRouting
    conversation_summary: str | None = None
    recent_turns: list[dict] = Field(default_factory=list, max_length=12)
    resolved_entities: list[EntityReference] = Field(default_factory=list, max_length=10)
    current_destination: str | None = None
    trip_summary: dict | None = None
    displayed_revision: dict | None = None
    formal_itinerary_summary: list[dict] = Field(default_factory=list, max_length=100)
    itinerary_read_coverage: dict = Field(default_factory=dict)
    arrangement_items: list[dict] = Field(default_factory=list)
    relevant_user_preferences: list[PreferenceStatement] = Field(default_factory=list, max_length=30)
    saved_trip_preferences: dict | None = None
    relevant_prior_suggestions: list[CompanionSuggestion] = Field(default_factory=list, max_length=10)
    referenced_decision: CompanionExplanation | None = None
    saved_plan_notes: dict | None = None
    knowledge_context: list[KnowledgeEvidence] = Field(default_factory=list, max_length=10)
    knowledge_retrieval: KnowledgeRetrievalSummary | None = None
    pending_planning_handoff: PlanningBrief | None = None
    forecast_plan: ForecastPlan | None = None
    opening_hours_plan: ForecastPlan | None = None
    resolved_facts: list[ResolvedFact] = Field(default_factory=list, max_length=32)


class VisualSubject(Contract):
    subject: str = Field(min_length=2, max_length=80)
    kind: Literal["attraction", "food", "architecture"]


class CompanionResult(Contract):
    visual_subjects: list[VisualSubject] = Field(default_factory=list, max_length=3)
    analysis_summary: str = Field(default="", max_length=600)
    response_text: str = Field(min_length=1, max_length=5000)
    goal_type: CompanionGoal
    status: Literal["completed", "needs_information", "needs_clarification"] = "completed"
    suggestions: list[CompanionSuggestion] = Field(default_factory=list, max_length=10)
    resolved_suggestion_refs: list[str] = Field(default_factory=list, max_length=10)
    interactions: list[SuggestionInteraction] = Field(default_factory=list, max_length=10)
    comparison: CompanionComparison | None = None
    explanation: CompanionExplanation | None = None
    information_need: InformationNeed
    information_gaps: list[InformationGap] = Field(default_factory=list, max_length=10)
    planning_handoff: PlanningBrief | None = None
    conversation_destination: str | None = None
    runtime_trace: list[str] = Field(default_factory=list, max_length=20)
    knowledge_evidence: list[KnowledgeEvidence] = Field(default_factory=list, max_length=10)
    answer_evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    knowledge_retrieval: KnowledgeRetrievalSummary | None = None
    grounding_status: Literal["not_applicable", "unverified_proposal", "citations_validated",
        "insufficient_evidence", "live_verification_required", "verified_forecast", "verified_opening_schedule", "verified_mixed_facts", "decision_context_required"] = "not_applicable"
    grounding_limitations: list[str] = Field(default_factory=list, max_length=8)
    claims: list["GroundedAnswerClaim"] = Field(default_factory=list, max_length=20)
    claim_validation_issues: list[str] = Field(default_factory=list, max_length=12)
    forecast_plan: ForecastPlan | None = None
    opening_hours_plan: ForecastPlan | None = None
    resolved_facts: list[ResolvedFact] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def companion_cannot_authorize_handoff(self):
        if self.planning_handoff is not None:
            raise ValueError("a Companion result cannot authorize Planning; explicit Planning turn owns handoff")
        return self


class SuggestionDraft(Contract):
    suggestion_type: Literal["place", "destination", "experience", "strategy"] = "place"
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1000)
    reasons: list[str] = Field(default_factory=list, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)


class CompanionDraft(Contract):
    """Model boundary excludes identity, authority, status, original rationale and handoff."""
    analysis_summary: str = Field(default="", max_length=600)
    response_text: str = Field(min_length=1, max_length=3000)
    suggestions: list[SuggestionDraft] = Field(default_factory=list, max_length=10)
    comparison: CompanionComparison | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    visual_subjects: list[VisualSubject] = Field(default_factory=list, max_length=3)


class AgentAnswerText(Contract):
    """Unsourced prose is explicitly advice/inference, never source attribution."""
    text: str = Field(min_length=1, max_length=700)
    claim_type: Literal["agent_inference", "recommendation"]
    applicability: EvidenceApplicability
    evidence_refs: list[str] = Field(default_factory=list, max_length=5)


class CompanionAnswerDraft(Contract):
    """Knowledge wire contract: source facts are selected and rendered by server."""
    analysis_summary: str = Field(default="", max_length=600)
    agent_claims: list[AgentAnswerText] = Field(default_factory=list, max_length=8)
    suggestions: list[SuggestionDraft] = Field(default_factory=list, max_length=10)
    comparison: CompanionComparison | None = None
    visual_subjects: list[VisualSubject] = Field(default_factory=list, max_length=3)


class GroundedAnswerClaim(Contract):
    claim_id: str = Field(pattern=r"^claim_[0-9a-f]{32}$")
    text: str = Field(min_length=1, max_length=1000)
    claim_type: ClaimType
    evidence_refs: list[str] = Field(default_factory=list, max_length=5)
    assertion_ids: list[str] = Field(default_factory=list, max_length=5)
    applicability: EvidenceApplicability
    support_status: Literal["supported", "partially_supported", "unsupported", "not_applicable"]
    applicability_status: Literal["compatible", "overreach", "unknown", "not_applicable"]
    attribution_status: Literal["accurate", "misattributed", "unattributed", "not_applicable"]
    source_attributions: list["ClaimSourceAttribution"] = Field(default_factory=list, max_length=5)


class ClaimSourceAttribution(Contract):
    source_organization: str | None = Field(default=None, max_length=240)
    source_page_title: str | None = Field(default=None, max_length=300)
    source_url: str = Field(min_length=1, max_length=2000)
    document_id: str | None = Field(default=None, max_length=240)


class CompanionProvider(Protocol):
    async def generate(self, context: CompanionContext, need: InformationNeed) -> CompanionDraft | CompanionAnswerDraft: ...


class ContextReaderPort(Protocol):
    async def load(self, context: CompanionContext, need: InformationNeed) -> CompanionContext: ...
