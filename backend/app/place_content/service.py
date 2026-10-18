import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.map_transport import MapProviderError
from .contracts import Place, RouteQuery, RouteResult, SearchQuery, SearchResponse
from .provider import AMapContentProvider
from .repository import ContentRepository
from .images import project_images


class PlaceNotFoundError(Exception):
    pass


def project_freshness(place: Place) -> Place:
    place = project_images(place)
    return place.model_copy(update={"source": place.source.model_copy(update={
        "freshness": "stale" if place.source.freshness == "stale" or place.identity_status != "provider_identity" or place.source.expires_at <= datetime.now(UTC) else "fresh"
    })})


class PlaceContentService:
    def __init__(self, provider: AMapContentProvider, repository: ContentRepository):
        self.provider = provider
        self.repository = repository

    async def search(self, query: SearchQuery) -> SearchResponse:
        result = await self.provider.search(query)
        for place in result.items:
            await asyncio.to_thread(self.repository.save, place)
        return result

    async def get_place(self, place_id: UUID, *, allow_stale: bool = True) -> Place:
        cached = await asyncio.to_thread(self.repository.get, place_id)
        if cached is None:
            raise PlaceNotFoundError(str(place_id))
        try:
            current = await self.provider.detail(cached.ref)
        except MapProviderError as exc:
            state = "uncertain" if exc.code == "place_identity_uncertain" else "provider_unavailable"
            degraded = cached.model_copy(update={"identity_status": state, "source": cached.source.model_copy(update={"freshness": "stale"})})
            await asyncio.to_thread(self.repository.save, degraded)
            if not allow_stale:
                raise
            return project_images(degraded)
        if current is None:
            degraded = cached.model_copy(update={"identity_status": "provider_id_invalid", "source": cached.source.model_copy(update={"freshness": "stale"})})
            await asyncio.to_thread(self.repository.save, degraded)
            if not allow_stale:
                raise MapProviderError("高德地点身份已失效", code="place_provider_id_invalid", status_code=410)
            return project_images(degraded)
        await asyncio.to_thread(self.repository.save, current)
        return current

    async def query_route(self, query: RouteQuery) -> RouteResult:
        return await self.provider.route(query)
