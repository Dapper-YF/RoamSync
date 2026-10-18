from typing import Callable, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .contracts import Draft, DraftCreate, DraftEdit, RunRequest, VersionRequest
from .repository import DraftError
from .service import draft_records
from app.requirements import project_requirements


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    requirement_id: str
    day_index: int | None = Field(default=None, ge=1, le=14)


def unavailable_owner():
    raise HTTPException(503, detail={"code": "owner_boundary_not_configured"})


def create_router(service, owner_dependency: Callable = unavailable_owner):
    router = APIRouter(prefix="/api/v1/drafts", tags=["drafts"])

    def owner(value=Depends(owner_dependency)):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise HTTPException(503, detail={"code": "owner_boundary_not_configured"})
        return value

    def call(fn, *args):
        try:
            return fn(*args)
        except DraftError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": "草稿已更新或当前操作不可用，请刷新后重试。"}) from None

    @router.get("", response_model=list[Draft])
    def listing(user: str = Depends(owner)):
        service.repository.recover_interrupted(owner=user)
        return service.repository.list(user)

    @router.post("", response_model=Draft, status_code=201)
    def create(data: DraftCreate, user: str = Depends(owner)):
        return service.repository.create(user, data)

    @router.get("/{draft_id}", response_model=Draft)
    def detail(draft_id: UUID, user: str = Depends(owner)):
        service.repository.recover_interrupted(owner=user, draft_id=draft_id)
        return call(service.repository.get, user, draft_id)

    @router.post("/{draft_id}/runs", response_model=Draft)
    async def generate(draft_id: UUID, data: RunRequest, user: str = Depends(owner)):
        try:
            return await service.run(user, draft_id, data)
        except DraftError as exc:
            raise HTTPException(exc.status, detail={"code": exc.code, "message": "草稿已更新，请刷新后重试。"}) from None

    @router.post("/{draft_id}/edit", response_model=Draft)
    async def edit(draft_id: UUID, data: DraftEdit, user: str = Depends(owner)):
        try:
            return await service.edit_resolved(user, draft_id, data)
        except DraftError as exc:
            message = "所选地点暂时无法核实，请重新搜索选择；原草稿仍保留。" if exc.code == "draft_selected_place_unavailable" else "草稿已更新或当前操作不可用，请刷新后重试。"
            raise HTTPException(exc.status, detail={"code": exc.code, "message": message}) from None

    @router.post("/{draft_id}/{action}", response_model=Draft)
    def action(draft_id: UUID, action: Literal["save", "cancel", "restore", "cancel-run"], data: VersionRequest, user: str = Depends(owner)):
        return call(service.action, user, draft_id, data.expected_version, action)

    @router.get("/{draft_id}/requirements")
    def requirements(draft_id: UUID, user: str = Depends(owner)):
        draft = call(service.repository.get, user, draft_id)
        records = draft_records(draft)
        return {"version": draft.version, "records": records,
            "effective_by_day": {str(n): project_requirements(records, draft_id=str(draft.id), city=draft.city,
                day_index=n) for n in range(1, draft.day_count + 1)}}

    @router.post("/{draft_id}/requirements/revoke", response_model=Draft)
    def revoke(draft_id: UUID, data: RevokeRequest, user: str = Depends(owner)):
        return call(service.revoke_requirement, user, draft_id, data.expected_version, data.requirement_id, data.day_index)

    return router
