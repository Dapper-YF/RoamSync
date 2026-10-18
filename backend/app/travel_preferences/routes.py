from typing import Callable
from fastapi import APIRouter, Depends, HTTPException
from app.map_transport import MapProviderError
from app.place_content.routes import unavailable_owner
from .contracts import DiscoveryQuery, DiscoveryResponse, TravelPreferences
from .service import PreferenceService

def create_router(service: PreferenceService, owner_dependency: Callable = unavailable_owner) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["travel-preferences"])
    def owner(value=Depends(owner_dependency)):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise HTTPException(503, detail={"code": "owner_boundary_not_configured"})
        return value

    @router.get("/me/travel-preferences", response_model=TravelPreferences)
    def get_preferences(value: str = Depends(owner)):
        return service.get(value)

    @router.put("/me/travel-preferences", response_model=TravelPreferences)
    def put_preferences(body: TravelPreferences, value: str = Depends(owner)):
        return service.save(value, body)

    @router.post("/places/discover", response_model=DiscoveryResponse)
    async def discover(body: DiscoveryQuery, value: str = Depends(owner)):
        try:
            return await service.discover(value, body)
        except MapProviderError as exc:
            raise HTTPException(exc.status_code, detail={"code": exc.code, "message": "地点发现服务暂不可用，请重试"}) from None
    return router
