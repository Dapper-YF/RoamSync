"""Conservative reviewed-assertion gate; ranking scores are not confidence."""
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.companion_contracts import CompanionContext, InformationNeed, KnowledgeToolResult
from app.companion_information import SPECIALIST_PATTERN
from app.tourism_knowledge.ranking import tokenize

TRUSTED_AUTHORITIES = {"official_government", "official_destination", "official_museum",
    "official_attraction", "institutional", "high_quality_editorial"}


def gate_evidence(result: KnowledgeToolResult, context: CompanionContext,
                  need: InformationNeed, *, now: datetime | None = None):
    now = now or datetime.now(UTC)
    accepted, rejected = [], []
    conflicts = set()
    assertions = {}
    dated_assertions = {}
    for evidence in result.evidence:
        for assertion in evidence.answerable_assertions:
            previous = assertions.setdefault(assertion.assertion_id, assertion.text)
            if previous != assertion.text:
                conflicts.add(assertion.assertion_id)
            if "heritage_inscription_year" in assertion.topics:
                years = tuple(re.findall(r"\d{4}年", assertion.text))
                key = (assertion.applicability.scope, assertion.applicability.target)
                if years:
                    dated_assertions.setdefault(key, []).append((assertion.assertion_id, years))
    for values in dated_assertions.values():
        if len({years for _, years in values}) > 1:
            conflicts.update(ref for ref, _ in values)
    for evidence in result.evidence:
        reasons = []
        url = urlparse(evidence.source_reference)
        if evidence.source_authority not in TRUSTED_AUTHORITIES or evidence.source_type not in {"web", "publication"}:
            reasons.append("untrusted_provenance")
        if evidence.source_type == "web" and (url.scheme not in {"https", "http"} or not url.hostname):
            reasons.append("invalid_source_reference")
        if not evidence.reviewed_at or evidence.reviewed_at.tzinfo is None or evidence.reviewed_at > now:
            reasons.append("review_missing_or_invalid")
        if (evidence.valid_until and (evidence.valid_until.tzinfo is None or evidence.valid_until <= now)) or (evidence.scope == "semi_stable" and not evidence.valid_until):
            reasons.append("expired_or_missing_validity")
        if (context.current_destination and evidence.applicability in {"place", "destination", "destination_specific"}
            and evidence.applicability_target not in {context.current_destination, evidence.place_name}
            and not (context.current_destination == "杭州" and evidence.applicability_target == "西湖")):
            reasons.append("subject_mismatch")
        if evidence.applicability == "place" and evidence.place_name and evidence.place_name not in context.current_message:
            # A city's profile may include one place; an explicitly different
            # place cannot inherit that place's historical assertions.
            other_places = re.findall(r"[\u3400-\u9fff]{2,8}(?:寺|塔|博物馆|遗址|古镇)", context.current_message)
            if other_places and not any(evidence.place_name in name for name in other_places):
                reasons.append("subject_mismatch")
        usable = [a for a in evidence.answerable_assertions if not need.requested_fact_topics
                  or set(a.topics).intersection(need.requested_fact_topics)]
        # Broad history_general alone must not authorize an unrelated niche fact.
        specialist_terms = re.findall(SPECIALIST_PATTERN, context.current_message)
        if specialist_terms:
            usable = [a for a in usable if any(term in a.text for term in specialist_terms)]
        if not need.requested_fact_topics:
            ignored = {"杭州", "南京", "西湖", "来源", "出处", "资料", "请给", "给出", "推荐", "建议", "什么", "哪些", "适合", "旅游", "旅行"}
            terms = {t for t in tokenize(context.current_message) if len(t) > 1} - ignored
            usable = [a for a in usable if terms.intersection(tokenize(a.text))]
        if not usable and not ("source_page_title" in need.requested_fact_topics and evidence.source_page_title):
            reasons.append("no_direct_assertion_support")
        if any(a.assertion_id in conflicts for a in usable):
            reasons.append("conflicting_assertion_identity")
        if reasons:
            rejected.extend(reasons)
        else:
            accepted.append(evidence.model_copy(update={"answerable_assertions": usable}))
    return accepted, list(dict.fromkeys(rejected))[:10]
