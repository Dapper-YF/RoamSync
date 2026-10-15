"""Controllable routing provider for deterministic integration tests."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from app.navigation.providers import RoutingProviderError, RoutingRequest, RoutingResult


@dataclass(frozen=True, slots=True)
class FakeRouteResponse:
    result: RoutingResult | None = None
    error: RoutingProviderError | None = None
    delay_seconds: float = 0


class FakeRoutingProvider:
    """Returns queued responses in call order while allowing completion reordering.

    ``delay_seconds`` is intentionally applied after a response is claimed. Two
    concurrent calls can therefore start as revisions 5 and 6 while revision 6
    returns first.  Tests can also inject an exact ETA/distance or a failure.
    """

    def __init__(self, responses: list[FakeRouteResponse]) -> None:
        self._responses = deque(responses)
        self._lock = asyncio.Lock()
        self.requests: list[RoutingRequest] = []

    async def route(self, request: RoutingRequest) -> RoutingResult:
        async with self._lock:
            self.requests.append(request)
            if not self._responses:
                raise RoutingProviderError("fake routing response queue exhausted", code="fake_exhausted")
            response = self._responses.popleft()
        if response.delay_seconds:
            await asyncio.sleep(response.delay_seconds)
        if response.error is not None:
            raise response.error
        if response.result is None:
            raise RoutingProviderError("fake response has no result", code="fake_invalid_response")
        return response.result
