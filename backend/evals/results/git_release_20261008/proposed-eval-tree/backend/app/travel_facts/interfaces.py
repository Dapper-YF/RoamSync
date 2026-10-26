"""Ports do not give callers access to provider URLs or canonical writes."""
from datetime import datetime
from typing import Protocol, Sequence

from .models import FactBundle, FactRequirement, ResolvedFact


class FactProvider(Protocol):
    name: str
    read_through: bool
    def supports(self, requirement: FactRequirement) -> bool: ...
    async def fetch(self, requirement: FactRequirement, *, now: datetime) -> FactBundle: ...


class FactRepository(Protocol):
    async def get(self, requirement: FactRequirement) -> FactBundle: ...
    async def merge(self, bundle: FactBundle) -> None: ...


class FactResolver(Protocol):
    async def resolve_fact(self, requirement: FactRequirement) -> ResolvedFact: ...
    async def resolve_facts(self, requirements: Sequence[FactRequirement]) -> Sequence[ResolvedFact]: ...


class ProviderUnavailable(RuntimeError):
    """Only a fixed sanitized code escapes provider adapters."""
    def __init__(self, code: str = "provider_unavailable"):
        if code not in {"provider_unavailable", "provider_timeout", "invalid_provider_data", "canonical_version_mismatch"}:
            raise ValueError("unknown provider failure code")
        self.code = code
        super().__init__(code)
