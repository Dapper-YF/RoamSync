from typing import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.drafts.repository import DraftError
from app.drafts.routes import unavailable_owner
from .contracts import ConfirmRequest, Operation, PreparedPlan, PreviewRequest, PromotionError


def create_router(service, owner_dependency: Callable = unavailable_owner):
    router = APIRouter(prefix="/api/v1", tags=["draft-promotion"])

    def owner(value=Depends(owner_dependency)):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise HTTPException(503, detail={"code": "owner_boundary_not_configured"})
        return value

    async def call(fn, *args):
        try:
            return await fn(*args)
        except PromotionError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from None
        except DraftError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": "草稿已变化，请刷新。"}) from None

    @router.post("/drafts/{draft_id}/promotion-preview", response_model=PreparedPlan)
    async def preview(draft_id: UUID, data: PreviewRequest, user: str = Depends(owner)):
        return await call(service.preview, user, draft_id, data)

    @router.get("/drafts/{draft_id}/promotions", response_model=list[Operation])
    async def listing(draft_id: UUID, user: str = Depends(owner)):
        return await call(service.list, user, draft_id)

    @router.post("/draft-promotions", response_model=Operation, status_code=201)
    async def confirm(data: ConfirmRequest, user: str = Depends(owner)):
        return await call(service.confirm, user, data)

    @router.get("/draft-promotions/{operation_id}", response_model=Operation)
    async def detail(operation_id: UUID, user: str = Depends(owner)):
        return await call(service.get, user, operation_id)

    @router.post("/draft-promotions/{operation_id}/resume", response_model=Operation)
    async def resume(operation_id: UUID, user: str = Depends(owner)):
        return await call(service.resume, user, operation_id)

    @router.post("/draft-promotions/{operation_id}/cancel", response_model=Operation)
    async def cancel(operation_id: UUID, user: str = Depends(owner)):
        return await call(service.cancel, user, operation_id)

    @router.post("/draft-promotions/{operation_id}/review", response_model=Operation)
    async def review(operation_id: UUID, data: ConfirmRequest, user: str = Depends(owner)):
        return await call(service.review, user, operation_id, data)

    return router
