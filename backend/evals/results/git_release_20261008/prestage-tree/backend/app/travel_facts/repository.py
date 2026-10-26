"""Bounded ephemeral evidence cache; canonical execution is never copied here."""
import json
from collections import OrderedDict

from .models import FactBundle, FactRequirement


def identity_key(fact_type, subject) -> str:
    return fact_type.value + ":" + json.dumps(subject.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class InMemoryFactRepository:
    def __init__(self, *, max_subjects: int = 128, history_per_subject: int = 8):
        if max_subjects < 1 or history_per_subject < 1:
            raise ValueError("cache limits must be positive")
        self.max_subjects, self.history_per_subject = max_subjects, history_per_subject
        self._bundles: OrderedDict[str, FactBundle] = OrderedDict()

    async def get(self, requirement: FactRequirement) -> FactBundle:
        return self._bundles.get(identity_key(requirement.fact_type, requirement.subject), FactBundle()).model_copy(deep=True)

    async def merge(self, bundle: FactBundle) -> None:
        if any(f.fact_type.value.startswith(("execution.", "navigation.")) for f in bundle.facts):
            raise ValueError("canonical execution facts must use read-through, not cache persistence")
        all_evidence = {e.id:e for b in self._bundles.values() for e in b.evidence}
        all_facts = {f.id:f for b in self._bundles.values() for f in b.facts}
        for record in bundle.evidence:
            if record.id in all_evidence and all_evidence[record.id] != record:
                raise ValueError("evidence identity collision")
        for fact in bundle.facts:
            if fact.id in all_facts and all_facts[fact.id] != fact:
                raise ValueError("fact identity collision")
        evidence = {**all_evidence, **{e.id:e for e in bundle.evidence}}
        updated = self._bundles.copy()
        grouped = {}
        for fact in bundle.facts:
            grouped.setdefault(identity_key(fact.fact_type, fact.subject), []).append(fact)
        for key, incoming in grouped.items():
            prior = updated.get(key, FactBundle())
            facts = {f.id:f for f in (*prior.facts, *incoming)}
            ordered = sorted(facts.values(), key=lambda f:(f.observed_at, f.id))[-self.history_per_subject:]
            refs = {ref for fact in ordered for ref in fact.evidence_refs}
            updated[key] = FactBundle(facts=tuple(ordered), evidence=tuple(evidence[ref] for ref in sorted(refs))).model_copy(deep=True)
            updated.move_to_end(key)
        while len(updated) > self.max_subjects:
            updated.popitem(last=False)
        self._bundles = updated  # Atomic after all validation succeeds.
