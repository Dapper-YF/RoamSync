"""Stable business-facing routing contracts.

Provider adapters translate their native API, coordinate system and failure
format into these types.  No database model or Planning Graph type crosses this
boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RoutingCoordinate:
    longitude: float
    latitude: float


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    origin: RoutingCoordinate
    destination: RoutingCoordinate
    travel_mode: str
    departure_at: datetime
    coordinate_system: str


@dataclass(frozen=True, slots=True)
class RoutingResult:
    distance_meters: int
    duration_minutes: int
    eta: datetime
    provider: str
    provider_metadata: dict[str, str | int | float | bool] = field(default_factory=dict)
    path: tuple[RoutingCoordinate, ...] = ()


class RoutingProviderError(Exception):
    """A provider failure expressed without leaking a provider-specific DTO."""

    def __init__(self, message: str, *, code: str = "routing_provider_unavailable") -> None:
        super().__init__(message)
        self.code = code


class RoutingProvider(Protocol):
    async def route(self, request: RoutingRequest) -> RoutingResult: ...


class UnavailableRoutingProvider:
    """Production placeholder until an explicitly selected adapter is wired."""

    async def route(self, request: RoutingRequest) -> RoutingResult:
        raise RoutingProviderError("实时路线 Provider 尚未配置", code="routing_not_configured")
