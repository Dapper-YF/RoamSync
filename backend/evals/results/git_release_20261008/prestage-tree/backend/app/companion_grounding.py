"""Claim assembly and deterministic boundaries; no NLP/LLM entailment verifier."""
import re

from app.companion_contracts import (ClaimSourceAttribution, CompanionAnswerDraft,
    CompanionContext, EvidenceApplicability, GroundedAnswerClaim, InformationNeed)
from app.companion_state import stable_identity


class GroundingContractError(ValueError):
    pass


_ATTRIBUTION = re.compile(
    r"资料(?:显示|指出|记载|认为|表明)|根据(?:检索|资料|来源|官方|UNESCO)|"
    r"(?:UNESCO|联合国教科文(?:组织)?|官方).{0,16}(?:推荐|认为|指出|表示|建议)|"
    r"来源.{0,6}(?:指出|表示|认为)|《[^》]{1,100}》.{0,8}(?:指出|认为|推荐|建议)", re.I)


def validate_provided_refs(draft, evidence):
    available = {e.evidence_ref for e in evidence}
    refs = set(getattr(draft, "evidence_refs", []))
    refs.update(ref for s in draft.suggestions for ref in s.evidence_refs)
    refs.update(ref for c in getattr(draft, "agent_claims", []) for ref in c.evidence_refs)
    refs.update(re.findall(r"knowledge_[A-Za-z0-9_]+", draft.model_dump_json()))
    if not refs <= available:
        raise GroundingContractError("Companion output references unknown evidence")


def applicability_compatible(scope: EvidenceApplicability, evidence) -> bool:
    """Source scope cannot be widened into a factual destination/current-trip claim."""
    if scope.scope == "current_trip":
        return False
    source_scope = {"general_strategy": "general", "destination_specific": "destination"}.get(
        evidence.applicability, evidence.applicability)
    if source_scope == "general":
        return scope.scope == "general"
    if source_scope == "unspecified":
        return False
    return scope.scope == source_scope and scope.target == evidence.applicability_target


def _source_attribution(evidence):
    return ClaimSourceAttribution(source_organization=evidence.source_name,
        source_page_title=evidence.source_page_title, source_url=evidence.source_reference,
        document_id=evidence.document_id)


def advice_issue(text: str, context: CompanionContext, need: InformationNeed) -> str | None:
    if _ATTRIBUTION.search(text):
        return "unvalidated_source_attribution"
    if any(e.curator_title and e.curator_title != e.source_page_title and e.curator_title in text
           for e in context.knowledge_context):
        return "curator_title_as_source_title"
    if ("senior_destination_suitability" in need.requested_fact_topics
        and re.search(r"(?:杭州|西湖|目的地|城市).{0,12}(?:最适合|很适合|适合|最佳).{0,8}(?:老人|长辈|父母)|"
            r"(?:老人|长辈|父母).{0,10}(?:最适合|很适合|适合|最佳).{0,8}(?:杭州|西湖|城市)", text)):
        return "general_guidance_scope_overreach"
    if ("photography_scope" in need.requested_fact_topics
        and re.search(r"(?:杭州全市|整个杭州|杭州所有|整个城市).{0,12}(?:适合|最佳|最适合).{0,8}(?:摄影|拍照)", text)):
        return "place_to_destination_scope_overreach"
    if ({"lake_formation_year", "lake_formation_history"}.intersection(need.requested_fact_topics)
        and re.search(r"形成于|诞生于|地质|水文|公元\d", text)):
        return "unsupported_factual_background"
    historical_topics = {"lake_formation_year", "lake_formation_history", "heritage_inscription_year",
        "west_lake_construction_period", "dynasty_history", "historical_figures", "fame_reasons",
        "cultural_significance", "history_general"}
    if (need.answer_mode == "mixed" and historical_topics.intersection(need.requested_fact_topics)
        and re.search(r"(?:公元)?\d{1,4}\s*年|[一二三四五六七八九十百]+世纪|"
            r"(?:唐|宋|元|明|清)(?:朝|代)|形成于|建于|开凿于|始建于|疏浚于", text)):
        return "unsupported_factual_background_in_advice"
    return None


def assemble_claims(context: CompanionContext, need: InformationNeed,
                    draft: CompanionAnswerDraft, session_id: str, turn_id: str):
    """Source text/type/scope/attribution comes from registered assertions, not draft."""
    validate_provided_refs(draft, context.knowledge_context)
    claims, issues, safe_suggestions = [], [], []
    supplied = {e.evidence_ref: e for e in context.knowledge_context}
    seen = set()

    def append_claim(**kwargs):
        claims.append(GroundedAnswerClaim(claim_id=stable_identity("claim", session_id, turn_id, len(claims)), **kwargs))

    for evidence in context.knowledge_context:
        for assertion in evidence.answerable_assertions:
            if assertion.assertion_id in seen:
                continue
            seen.add(assertion.assertion_id)
            if not applicability_compatible(assertion.applicability, evidence):
                issues.append("assertion_applicability_incompatible")
                continue
            if assertion.claim_type == "curator_inference":
                if need.answer_mode == "factual":
                    continue
                append_claim(text=assertion.text, claim_type="curator_inference",
                    evidence_refs=[evidence.evidence_ref], assertion_ids=[assertion.assertion_id],
                    applicability=assertion.applicability, support_status="partially_supported",
                    applicability_status="compatible", attribution_status="not_applicable",
                    source_attributions=[])
            else:
                append_claim(text=assertion.text, claim_type=assertion.claim_type,
                    evidence_refs=[evidence.evidence_ref], assertion_ids=[assertion.assertion_id],
                    applicability=assertion.applicability, support_status="supported",
                    applicability_status="compatible", attribution_status="accurate",
                    source_attributions=[_source_attribution(evidence)])
        if "source_page_title" in need.requested_fact_topics and evidence.source_page_title:
            marker = "page_title:" + evidence.source_reference
            if marker not in seen:
                seen.add(marker)
                append_claim(text="核实到的来源网页原始标题是《" + evidence.source_page_title + "》。",
                    claim_type="retrieved_fact", evidence_refs=[evidence.evidence_ref], assertion_ids=[],
                    applicability=EvidenceApplicability(scope="general"), support_status="supported",
                    applicability_status="compatible", attribution_status="accurate",
                    source_attributions=[_source_attribution(evidence)])

    if need.answer_mode != "factual":
        for claim in draft.agent_claims:
            issue = advice_issue(claim.text, context, need)
            if issue:
                issues.append(issue)
                continue
            status = "not_applicable" if not claim.evidence_refs else "compatible" if all(
                applicability_compatible(claim.applicability, supplied[ref]) for ref in claim.evidence_refs) else "overreach"
            # A broader recommendation remains advice; never promote it to
            # a source-backed factual claim or give it official attribution.
            append_claim(text=claim.text, claim_type=claim.claim_type, evidence_refs=claim.evidence_refs,
                assertion_ids=[], applicability=claim.applicability, support_status="not_applicable",
                applicability_status=status, attribution_status="not_applicable", source_attributions=[])
        for suggestion in draft.suggestions:
            issue = advice_issue(" ".join([suggestion.title, suggestion.summary, *suggestion.reasons]), context, need)
            if issue:
                issues.append(issue)
                continue
            safe_suggestions.append(suggestion)
            for text, kind in [(suggestion.summary, "recommendation"), *[(r, "agent_inference") for r in suggestion.reasons]]:
                append_claim(text=text, claim_type=kind, evidence_refs=suggestion.evidence_refs, assertion_ids=[],
                    applicability=EvidenceApplicability(scope="destination", target=context.current_destination),
                    support_status="not_applicable", applicability_status="not_applicable",
                    attribution_status="not_applicable", source_attributions=[])
        if draft.comparison:
            issue = advice_issue(draft.comparison.summary, context, need)
            if issue:
                issues.append(issue)
            else:
                append_claim(text=draft.comparison.summary, claim_type="agent_inference", evidence_refs=[], assertion_ids=[],
                    applicability=EvidenceApplicability(scope="general"), support_status="not_applicable",
                    applicability_status="not_applicable", attribution_status="not_applicable", source_attributions=[])
    return claims[:20], safe_suggestions, list(dict.fromkeys(issues))[:12]
