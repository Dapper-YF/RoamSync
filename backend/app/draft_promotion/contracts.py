from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.drafts.contracts import DTO
from app.place_content.contracts import Place, RouteResult


class PreviewRequest(DTO):
    expected_version: int = Field(ge=1)
    start_date: date
    total_budget_fen: int | None = Field(default=None, gt=0)
    daily_budget_fen: int | None = Field(default=None, gt=0)
    transport_mode: Literal["walk", "driving"] = "walk"
    duration_minutes: int = Field(default=90, ge=15, le=480)
    unknown_cost_estimate_fen: int = Field(default=10000, gt=0)
    daily_start_time: time = time(9)
    daily_end_time: time = time(21)
    max_walking_minutes: int = Field(default=60, gt=0, le=480)
    operation_id: UUID | None = None

    @model_validator(mode="after")
    def constraints(self):
        if (self.total_budget_fen is None) != (self.daily_budget_fen is None):
            raise ValueError("总预算和每日预算必须同时填写或同时留空")
        if self.daily_budget_fen and self.daily_budget_fen > self.total_budget_fen:
            raise ValueError("每日预算不能超过总预算")
        if self.daily_end_time <= self.daily_start_time:
            raise ValueError("每日结束时间必须晚于开始时间")
        if self.daily_start_time.second or self.daily_start_time.microsecond or self.daily_end_time.second or self.daily_end_time.microsecond:
            raise ValueError("时间精度必须为分钟")
        return self


class PreparedActivity(DTO):
    ref: str
    day_date: date
    position: int
    name: str
    place_id: UUID | None
    place: Place | None
    planned_start_time: time
    duration_minutes: int
    transport_mode: Literal["walk", "driving"]
    estimated_cost_fen: int
    cost_nature: Literal["provider_reference", "planning_estimate"]
    note: str


class PreparedRoute(DTO):
    day_date: date
    position: int
    from_ref: str
    to_ref: str
    route: RouteResult


class Coverage(DTO):
    checked: list[str]
    missing: list[str]
    blockers: list[str]


class PreparedPlan(DTO):
    id: UUID
    draft_id: UUID
    draft_version: int
    operation_id: UUID | None = None
    city: str
    title: str
    requirements: str
    requirement_records: list[dict] = Field(default_factory=list)
    constraints: PreviewRequest
    end_date: date
    activities: list[PreparedActivity]
    routes: list[PreparedRoute]
    coverage: Coverage
    content_hash: str
    evidence_hash: str
    prepared_hash: str
    created_at: datetime
    expires_at: datetime


class ConfirmRequest(DTO):
    request_id: UUID
    prepared_id: UUID
    prepared_hash: str = Field(min_length=64, max_length=64)
    action: Literal["create_only", "create_and_adopt"]
    confirmation: Literal["创建旅行", "创建并采用当前方案"]

    @model_validator(mode="after")
    def explicit_action(self):
        expected = "创建旅行" if self.action == "create_only" else "创建并采用当前方案"
        if self.confirmation != expected:
            raise ValueError("确认文字必须对应明确的操作")
        return self


class Operation(DTO):
    id: UUID
    draft_id: UUID
    draft_version: int
    prepared_id: UUID
    prepared_hash: str
    content_hash: str
    evidence_hash: str
    allowed_action: Literal["create_only", "create_and_adopt"]
    status: Literal["requested", "trip_created", "awaiting_apply", "needs_review", "applied", "created", "failed", "cancelled"]
    stage: str
    target_trip_id: UUID | None = None
    target_run_id: UUID | None = None
    target_revision_id: UUID | None = None
    authorized_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
    error: str | None = None
    validation: dict | None = None
    equivalence_check: dict | None = None
    updated_at: datetime


class PromotionError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(code)
