"""Explicit per-type policies. No universal TTL or LLM source ranking."""
from datetime import datetime, timedelta
from typing import Mapping

from pydantic import Field

from .models import AuthorityLevel, Contract, EvidenceRecord, FactRequirement, FactType, FreshnessStatus, TravelFact

LEVEL_ORDER = {AuthorityLevel.UNVERIFIED:0, AuthorityLevel.SECONDARY:1,
               AuthorityLevel.SPECIALIST:2, AuthorityLevel.AUTHORITATIVE:3}
LIVE_NO_STALE = {FactType.NAV_ETA, FactType.NAV_POSITION, FactType.NAV_REMAINING_DISTANCE,
                 FactType.ROUTE_ETA, FactType.WEATHER_CURRENT, FactType.TICKET_AVAILABILITY,
                 FactType.ACTIVITY_STATUS}


class FreshnessRule(Contract):
    max_age_seconds: int = Field(gt=0)
    stale_grace_seconds: int = Field(default=0, ge=0)


class FactFreshnessPolicy:
    def __init__(self, rules: Mapping[FactType, FreshnessRule]):
        # No built-in production TTL: the composition root must choose policies.
        self.rules = dict(rules)

    def fresh_until(self, fact_type: FactType, retrieved_at: datetime, *, provider_observed_at: datetime | None = None) -> datetime:
        rule = self.rules[fact_type]
        return min(retrieved_at, provider_observed_at or retrieved_at) + timedelta(seconds=rule.max_age_seconds)

    def deadline(self, fact: TravelFact, requirement: FactRequirement, evidence: Mapping[str, EvidenceRecord]) -> datetime:
        anchor = min([fact.observed_at] + [min(evidence[ref].retrieved_at,
                     evidence[ref].provider_observed_at or evidence[ref].retrieved_at) for ref in fact.evidence_refs])
        maximum = self.rules[fact.fact_type].max_age_seconds
        if requirement.required_freshness_seconds is not None:
            maximum = min(maximum, requirement.required_freshness_seconds)
        return min(fact.fresh_until, anchor + timedelta(seconds=maximum))

    def classify(self, fact: TravelFact, requirement: FactRequirement, evidence: Mapping[str, EvidenceRecord], *, now: datetime) -> FreshnessStatus:
        if any(ref not in evidence for ref in fact.evidence_refs):
            return FreshnessStatus.NO_EVIDENCE
        if fact.observed_at > now or any(evidence[ref].retrieved_at > now for ref in fact.evidence_refs):
            return FreshnessStatus.FUTURE_EFFECTIVE
        target = requirement.time_scope.start if requirement.time_scope else now
        end = requirement.time_scope.end if requirement.time_scope else None
        if (target > now and fact.effective_until is None
            and (fact.fact_type in LIVE_NO_STALE or fact.fact_type == FactType.OPERATIONAL_STATUS)):
            return FreshnessStatus.FUTURE_EFFECTIVE  # Current records don't promise future state.
        if fact.effective_from is not None and fact.effective_from > target:
            return FreshnessStatus.FUTURE_EFFECTIVE
        if fact.effective_until is not None and (fact.effective_until <= target or (end is not None and fact.effective_until < end)):
            return FreshnessStatus.EXPIRED
        return FreshnessStatus.FRESH if now < self.deadline(fact, requirement, evidence) else FreshnessStatus.STALE

    def stale_allowed(self, fact: TravelFact, requirement: FactRequirement, evidence: Mapping[str, EvidenceRecord], *, now: datetime) -> bool:
        rule = self.rules[fact.fact_type]
        return (requirement.allow_stale and fact.fact_type not in LIVE_NO_STALE and rule.stale_grace_seconds > 0
                and now < self.deadline(fact, requirement, evidence) + timedelta(seconds=rule.stale_grace_seconds))


class AuthorityRule(Contract):
    level: AuthorityLevel
    rank: int = Field(ge=0, le=100)


class FactAuthorityPolicy:
    def __init__(self, rules: Mapping[tuple[FactType, str, str], AuthorityRule] | None = None):
        self.rules = dict(rules or {})

    @classmethod
    def existing_providers(cls):
        rules = {}
        for kind in (FactType.PLACE_IDENTITY, FactType.PLACE_LOCATION, FactType.PLACE_CATEGORY,
                     FactType.ROUTE_DISTANCE, FactType.ROUTE_DURATION):
            rules[kind, "amap", "structured_api"] = AuthorityRule(level="specialist", rank=80)
        for kind in (FactType.WEATHER_FORECAST, FactType.WEATHER_CURRENT):
            rules[kind, "open_meteo", "structured_api"] = AuthorityRule(level="specialist", rank=80)
        for kind in (FactType.ACTIVITY_STATUS, FactType.ACTUAL_START, FactType.ACTUAL_END,
                     FactType.NAV_POSITION, FactType.NAV_ETA, FactType.NAV_REMAINING_DISTANCE):
            rules[kind, "roamsync", "canonical_execution"] = AuthorityRule(level="authoritative", rank=100)
        # Tavily/search_candidate never gets fact authority. Official publishers
        # require explicit trusted collector registration, not a claimed label.
        return cls(rules)

    def assess(self, fact_type: FactType, evidence: EvidenceRecord) -> AuthorityRule:
        return self.rules.get((fact_type, evidence.provider, evidence.source_type), AuthorityRule(level="unverified", rank=0))
