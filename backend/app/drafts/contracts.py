from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from app.requirements import EffectiveRequirement


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class DraftCreate(DTO):
    city: str = Field(min_length=1, max_length=100)
    title: str = Field(default="未定日期的旅行", min_length=1, max_length=200)
    day_count: int = Field(default=3, ge=1, le=14)
    requirements: str = Field(default="", max_length=3000)


class DraftItem(DTO):
    name: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=1000)
    place_id: UUID | None = None
    identity_status: Literal["provider_confirmed", "unknown"] = "unknown"


class DraftDay(DTO):
    day_index: int = Field(ge=1, le=14)
    title: str = Field(min_length=1, max_length=200)
    items: list[DraftItem] = Field(max_length=12)


class DraftPlan(DTO):
    days: list[DraftDay] = Field(min_length=1, max_length=14)

    @model_validator(mode="after")
    def consecutive_days(self):
        if [day.day_index for day in self.days] != list(range(1, len(self.days) + 1)):
            raise ValueError("days must be consecutive relative day_index values starting at 1")
        return self


class VersionRequest(DTO):
    expected_version: int = Field(ge=1, strict=True)


class DraftEdit(VersionRequest):
    title: str = Field(min_length=1, max_length=200)
    requirements: str = Field(max_length=3000)
    plan: DraftPlan | None


class RunRequest(VersionRequest):
    request_id: UUID
    requirements: str = Field(default="", max_length=3000)
    target_day_indices: list[StrictInt] = Field(default_factory=list, max_length=14)

    @model_validator(mode="after")
    def valid_scope(self):
        if any(day < 1 or day > 14 for day in self.target_day_indices):
            raise ValueError("target days must be between 1 and 14")
        if len(set(self.target_day_indices)) != len(self.target_day_indices):
            raise ValueError("target days must be unique")
        self.target_day_indices = sorted(self.target_day_indices)
        return self


class DraftRun(DTO):
    id: UUID
    request_id: UUID
    status: Literal["running", "completed", "failed", "cancelled", "interrupted"]
    requirements: str
    target_day_indices: list[int] = Field(default_factory=list)
    source: Literal["model", "fixture"]
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    lease_expires_at: datetime | None = None


class Draft(DTO):
    id: UUID
    title: str
    city: str
    day_count: int
    requirements: str
    requirement_records: list[dict] = Field(default_factory=list, max_length=200)
    version: int
    status: Literal["active", "cancelled"]
    saved: bool
    plan: DraftPlan | None
    runs: list[DraftRun]
    updated_at: datetime
