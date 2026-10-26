"""Stable identities and bounded subset snapshots. Never retain raw payloads."""
import hashlib
import json
from datetime import datetime

from .models import EvidenceRecord, FactBundle, TravelFact, scope_for
from .policies import FactFreshnessPolicy


def stable_id(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > 1_048_576:
        raise ValueError("provider payload exceeds normalization safety limit")
    return hashlib.sha256(encoded).hexdigest()


def evidence_record(*, provider: str, source_type: str, source_reference: str, retrieved_at: datetime,
                    normalized_snapshot: dict, raw_payload=None, provider_observed_at=None, metadata=None,
                    authority_level="specialist") -> EvidenceRecord:
    fields = dict(provider=provider, source_type=source_type, source_reference=source_reference,
        retrieved_at=retrieved_at, provider_observed_at=provider_observed_at, authority_level=authority_level,
        normalized_snapshot=normalized_snapshot, metadata=metadata or {},
        raw_snapshot_ref="sha256:" + stable_id(raw_payload) if raw_payload is not None else None)
    provisional = EvidenceRecord(id="provisional", **fields)
    return provisional.model_copy(update={"id":stable_id(provisional.model_dump(mode="json", exclude={"id"}))})


def fact_record(*, fact_type, subject, value, evidence: EvidenceRecord, freshness: FactFreshnessPolicy,
                nature: str, effective_from=None, effective_until=None, specificity="general") -> TravelFact:
    fields = dict(fact_type=fact_type, subject=subject, scope=scope_for(subject), value=value, nature=nature,
        observed_at=evidence.provider_observed_at or evidence.retrieved_at,
        effective_from=effective_from, effective_until=effective_until,
        fresh_until=freshness.fresh_until(fact_type, evidence.retrieved_at, provider_observed_at=evidence.provider_observed_at),
        evidence_refs=(evidence.id,), specificity=specificity)
    provisional = TravelFact(id="provisional", **fields)
    return provisional.model_copy(update={"id":stable_id(provisional.model_dump(mode="json", exclude={"id"}))})
