"""Deterministic resolution preserves disagreements, exclusions and sources."""
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import FactBundle, FactRequirement, FreshnessStatus, RejectedCandidate, ResolvedFact
from .policies import FactAuthorityPolicy, FactFreshnessPolicy, LEVEL_ORDER


def resolve_bundle(requirement: FactRequirement, bundle: FactBundle, freshness: FactFreshnessPolicy,
                   authority: FactAuthorityPolicy, *, now: datetime) -> ResolvedFact:
    evidence = {record.id:record for record in bundle.evidence}
    matching = [fact for fact in bundle.facts if fact.fact_type == requirement.fact_type and fact.subject == requirement.subject]
    refs = {ref for fact in matching for ref in fact.evidence_refs}
    preserved = tuple(evidence[ref] for ref in sorted(refs))
    base = dict(requirement=requirement, resolved_at=now, evidence=preserved)
    if requirement.fact_type not in freshness.rules:
        return ResolvedFact(**base, resolution_status="unsupported", reasons=("freshness_policy_not_configured",))
    eligible, stale, rejected = [], [], []
    for fact in matching:
        status = freshness.classify(fact, requirement, evidence, now=now)
        assessments = [authority.assess(fact.fact_type, evidence[ref]) for ref in fact.evidence_refs]
        assessment = max(assessments, key=lambda rule:(LEVEL_ORDER[rule.level], rule.rank))
        enough = assessment.rank > 0 and LEVEL_ORDER[assessment.level] >= LEVEL_ORDER[requirement.minimum_authority]
        priority = (assessment.rank, int(fact.specificity == "time_specific"))
        unknown = getattr(fact.value, "status", None) == "unknown" or getattr(fact.value, "unknown", False)
        local_date=getattr(fact.value,"local_date",None)
        date_mismatch=bool(local_date and (not requirement.time_scope or
            str(requirement.time_scope.start.astimezone(ZoneInfo(fact.value.timezone)).date())!=local_date))
        if date_mismatch: enough=False
        if enough and status == FreshnessStatus.FRESH and not unknown:
            eligible.append((fact, priority))
        else:
            rejected.append(RejectedCandidate(fact=fact, freshness_status=status,
                reason="opening_date_mismatch" if date_mismatch else "provider_status_unknown" if unknown else "insufficient_registered_authority" if not enough else status.value))
            if enough and not unknown and status == FreshnessStatus.STALE and freshness.stale_allowed(fact, requirement, evidence, now=now):
                stale.append((fact, priority))
    base["rejected_candidates"] = tuple(rejected)
    using_stale = not eligible
    pool = eligible or stale
    if not pool:
        return ResolvedFact(**base, resolution_status="stale" if any(r.freshness_status == FreshnessStatus.STALE for r in rejected) else "no_evidence",
            freshness_status=FreshnessStatus.STALE if any(r.freshness_status == FreshnessStatus.STALE for r in rejected)
                else rejected[0].freshness_status if rejected else FreshnessStatus.NO_EVIDENCE,
            reasons=("no_usable_evidence",))
    best_priority = max(priority for _,priority in pool)
    top = [fact for fact,priority in pool if priority == best_priority]
    if any(fact.value != top[0].value for fact in top):
        # Newer revision may supersede an older value ONLY within the exact
        # same provenance chain, not between independent conflicting sources.
        chains = {tuple((evidence[ref].provider, evidence[ref].source_type, evidence[ref].source_reference)
                        for ref in fact.evidence_refs) for fact in top}
        newest = max(f.observed_at for f in top)
        recent = [f for f in top if f.observed_at == newest]
        if len(chains) == 1 and all(f.value == recent[0].value for f in recent):
            top = recent
        else:
            return ResolvedFact(**base, resolution_status="conflicting", freshness_status=FreshnessStatus.STALE if using_stale else FreshnessStatus.FRESH,
                conflicting_facts=tuple(top), conflicting_evidence=tuple(evidence[ref] for ref in sorted({r for f in top for r in f.evidence_refs})),
                reasons=("equal_policy_priority_disagreement",))
    selected = sorted(top, key=lambda fact:(-fact.observed_at.timestamp(), fact.id))[0]
    supporting = {ref for fact,_ in pool if fact.value == selected.value for ref in fact.evidence_refs}
    conflicts = tuple(fact for fact in matching if fact.value != selected.value)
    conflict_refs = {ref for fact in conflicts for ref in fact.evidence_refs}
    corroborated = len({evidence[ref].provider for ref in supporting}) > 1
    simulation = any(evidence[ref].metadata.get("observation_source") == "simulation" for ref in selected.evidence_refs)
    return ResolvedFact(**base, resolution_status="stale" if using_stale else "resolved",
        freshness_status=FreshnessStatus.STALE if using_stale else FreshnessStatus.FRESH,
        value=selected.value, selected_fact=selected,
        selected_evidence=tuple(evidence[ref] for ref in sorted(supporting)),
        conflicting_facts=conflicts, conflicting_evidence=tuple(evidence[ref] for ref in sorted(conflict_refs)),
        confidence="limited" if using_stale or simulation else "corroborated" if corroborated else "policy_supported",
        usable_as_current=not using_stale and not simulation,
        reasons=("simulation_only_not_live_reality",) if simulation else ("stale_background_only",) if using_stale
            else ("selected_by_fact_specific_policy_conflicts_preserved",) if conflicts else ("policy_supported_evidence",))
