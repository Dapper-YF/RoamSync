"""Provider-independent async resolve_fact(s) facade and refresh lifecycle."""
import asyncio
import math
from pydantic import ValidationError
from datetime import UTC, datetime
from typing import Callable, Sequence

from .interfaces import FactProvider, FactRepository, ProviderUnavailable
from .models import FactBundle, FactRequirement, ResolvedFact
from .policies import FactAuthorityPolicy, FactFreshnessPolicy
from .resolution import resolve_bundle


def combine(*bundles: FactBundle) -> FactBundle:
    facts, evidence = {}, {}
    for bundle in bundles:
        for record in bundle.evidence:
            if record.id in evidence and evidence[record.id] != record:
                raise ValueError("evidence identity collision")
            evidence[record.id] = record
        for fact in bundle.facts:
            if fact.id in facts and facts[fact.id] != fact:
                raise ValueError("fact identity collision")
            facts[fact.id] = fact
    return FactBundle(facts=tuple(facts.values()), evidence=tuple(evidence.values()))


class TravelFactService:
    def __init__(self, repository: FactRepository, freshness: FactFreshnessPolicy,
                 authority: FactAuthorityPolicy, providers: Sequence[FactProvider] = (), *,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC), timeout_seconds: float = 15):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("provider timeout must be positive")
        self.repository, self.freshness, self.authority = repository, freshness, authority
        self.providers, self.clock, self.timeout_seconds = tuple(providers), clock, timeout_seconds

    async def resolve_fact(self, requirement: FactRequirement) -> ResolvedFact:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("resolver clock must be timezone-aware")
        canonical = requirement.fact_type.value.startswith(("execution.", "navigation."))
        cached = FactBundle() if canonical else await self.repository.get(requirement)
        initial = resolve_bundle(requirement, cached, self.freshness, self.authority, now=now)
        if requirement.fact_type not in self.freshness.rules:
            return initial
        providers = [p for p in self.providers if p.supports(requirement) and (not canonical or p.read_through)]
        if initial.usable_as_current and not any(p.read_through for p in providers):
            return initial.model_copy(update={"reasons":initial.reasons + ("fresh_cache_reused",)})
        bundles, failures = [cached], []
        for provider in providers:
            try:
                bundle = await asyncio.wait_for(provider.fetch(requirement, now=now), timeout=self.timeout_seconds)
                # Revalidate even a custom adapter's output and discard unrelated facts.
                bundle = FactBundle.model_validate(bundle.model_dump())
                matching = tuple(f for f in bundle.facts if f.fact_type == requirement.fact_type and f.subject == requirement.subject)
                refs = {r for f in matching for r in f.evidence_refs}
                bundle = FactBundle(facts=matching, evidence=tuple(e for e in bundle.evidence if e.id in refs))
                combine(*bundles, bundle)  # Detect cross-adapter collisions before cache mutation.
                if not canonical and not provider.read_through:
                    await self.repository.merge(bundle)
                bundles.append(bundle)
            except (TimeoutError, asyncio.TimeoutError):
                failures.append(provider.name + ":provider_timeout")
            except ProviderUnavailable as exc:
                failures.append(provider.name + ":" + exc.code)
            except (ValidationError, ValueError, TypeError, KeyError, AttributeError):
                # No raw provider exception text, URL, payload, or credential escapes.
                failures.append(provider.name + ":invalid_provider_data")
            except Exception:
                failures.append(provider.name + ":provider_unavailable")
        # Freshness is evaluated after network work, not at its start.
        result = resolve_bundle(requirement, combine(*bundles), self.freshness, self.authority, now=self.clock())
        status = result.resolution_status
        if status == "no_evidence" and failures:
            status = "unavailable"
        elif status == "no_evidence" and not providers and not cached.facts:
            status = "unsupported"
        return result.model_copy(update={"resolution_status":status, "provider_failures":tuple(failures)})

    async def resolve_facts(self, requirements: Sequence[FactRequirement]) -> tuple[ResolvedFact, ...]:
        # Sequential baseline avoids unbounded concurrency and provider QPS spikes.
        return tuple([await self.resolve_fact(requirement) for requirement in requirements])
