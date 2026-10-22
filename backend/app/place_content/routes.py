"""Mount with create_router(service, trusted_owner_dependency).

The owner dependency MUST validate a server identity; never read owner_id from
query/body/header without authentication. Missing integration fails closed.
"""
from typing import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.map_transport import MapProviderError
from .contracts import Favorite, FavoriteState, GeoPoint, Place, RouteQuery, RouteResult, SearchQuery, SearchResponse
from .service import PlaceContentService, PlaceNotFoundError, project_freshness
from .images import ASSETS, MEDIA, reviewed_illustrations


def unavailable_owner() -> str:
    raise HTTPException(503, detail={"code": "owner_boundary_not_configured", "message": "收藏身份边界尚未配置"})


def create_router(service: PlaceContentService, owner_dependency: Callable = unavailable_owner) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["travel-content"])

    @router.get('/media/place-images')
    def destination_images(city: str = Query(min_length=1, max_length=100)):
        return {'items': reviewed_illustrations(city)}

    @router.get('/media/place-images/{filename}', include_in_schema=False)
    def place_image(filename: str):
        # Fixed reviewed asset allowlist, never an open URL proxy or path lookup.
        if filename not in ASSETS or not (MEDIA / filename).is_file():
            raise HTTPException(404, detail='Image unavailable')
        return FileResponse(MEDIA / filename, media_type='image/jpeg', headers={'Cache-Control':'public, max-age=3600', 'X-Content-Type-Options':'nosniff'})

    def verified_owner(owner=Depends(owner_dependency)) -> str:
        if not isinstance(owner, str) or not owner.strip() or len(owner) > 200:
            raise HTTPException(503, detail={"code": "owner_boundary_not_configured"})
        return owner

    async def call(awaitable):
        try:
            return await awaitable
        except PlaceNotFoundError:
            raise HTTPException(404, detail={"code": "place_not_found", "message": "未找到该地点身份"}) from None
        except MapProviderError as exc:
            # Never echo provider message/URL/key to clients.
            raise HTTPException(exc.status_code, detail={"code": exc.code, "message": "地点或路线服务暂不可用，请稍后重试", "provider": "amap", "provider_code": exc.provider_code}) from None

    @router.get("/places/search", response_model=SearchResponse)
    async def search(query: str = Query(default="", max_length=200), city: str | None = Query(default=None, max_length=100),
        category: str | None = None, longitude: float | None = None, latitude: float | None = None,
        coordinate_system: str = "GCJ02", radius_meters: int = Query(default=3000, ge=1, le=50000),
        page: int = Query(default=1, ge=1, le=100), page_size: int = Query(default=12, ge=1, le=25)):
        if (longitude is None) != (latitude is None):
            raise HTTPException(422, detail={"code": "invalid_search", "message": "经纬度必须成对提供"})
        try:
            point = GeoPoint(longitude=longitude, latitude=latitude, coordinate_system=coordinate_system) if longitude is not None else None
            if coordinate_system != "GCJ02":
                raise ValueError("unsupported coordinate system")
            request = SearchQuery(query=query, city=city, category=category, center=point, radius_meters=radius_meters, page=page, page_size=page_size)
        except (ValidationError, ValueError):
            raise HTTPException(422, detail={"code": "invalid_search", "message": "请提供有效区域或GCJ02经纬度及关键词/分类"}) from None
        return await call(service.search(request))

    @router.get("/places/{place_id}", response_model=Place)
    async def detail(place_id: UUID):
        return await call(service.get_place(place_id))

    @router.get("/me/favorites", response_model=list[Favorite])
    def favorites(owner: str = Depends(verified_owner), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        return [item.model_copy(update={"place": project_freshness(item.place)}) for item in service.repository.list_favorites(owner, limit, offset)]

    @router.get("/me/favorites/{place_id}", response_model=FavoriteState)
    def favorite_state(place_id: UUID, owner: str = Depends(verified_owner)):
        return FavoriteState(place_id=place_id, is_favorite=service.repository.is_favorite(owner, place_id))

    @router.put("/me/favorites/{place_id}", response_model=FavoriteState)
    def favorite(place_id: UUID, owner: str = Depends(verified_owner)):
        if service.repository.get(place_id) is None:
            raise HTTPException(404, detail={"code": "place_not_found", "message": "请先搜索并确认真实地点"})
        service.repository.favorite(owner, place_id)
        return FavoriteState(place_id=place_id, is_favorite=True)

    @router.delete("/me/favorites/{place_id}", status_code=204)
    def unfavorite(place_id: UUID, owner: str = Depends(verified_owner)):
        service.repository.unfavorite(owner, place_id)
        return Response(status_code=204)

    @router.post("/routes/query", response_model=RouteResult)
    async def route(query: RouteQuery):
        return await call(service.query_route(query))

    return router
