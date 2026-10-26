"""Tavily is candidate evidence only. This module never emits TravelFact."""
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from .normalization import evidence_record


def normalize_search_evidence(search_fact):
    if search_fact.provider != "tavily":
        raise ValueError("search evidence provider mismatch")
    retrieved = datetime.fromisoformat(search_fact.queried_at)
    records = []
    for item in search_fact.payload.get("results", [])[:5]:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        reference = urlsplit(item["url"])
        if reference.scheme not in {"http", "https"} or not reference.hostname or reference.username or reference.password:
            continue
        # Strip query/fragment, which may contain tokens. No publisher authority
        # is inferred from a title, domain or search ranking.
        safe_reference = urlunsplit((reference.scheme, reference.netloc, reference.path, "", ""))
        record = evidence_record(provider="tavily", source_type="search_candidate", source_reference=safe_reference,
            retrieved_at=retrieved, authority_level="unverified",
            normalized_snapshot={"title":str(item.get("title", ""))[:240], "excerpt":str(item.get("content", ""))[:500]},
            metadata={"candidate_only":True, "source_query_removed":bool(reference.query)})
        if record.id not in {prior.id for prior in records}:
            records.append(record)
    return tuple(records)
