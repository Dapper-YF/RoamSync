from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from app.requirements import EffectiveRequirement


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)

    @field_validator("schema_version", "protocol_version", mode="before", check_fields=False)
    @classmethod
    def explicit_version(cls, value):
        if type(value) is not int or value not in {1, 2}:
            raise ValueError("version must be the explicit integer 1 or 2")
        return value


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
    item_ref: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_:-]+$")
    kind: Literal["visit", "meal", "rest", "free_window", "optional", "blank_day"] = "visit"
    provider_place_id: str | None = Field(default=None, min_length=1, max_length=200)
    duration_minutes: int | None = Field(default=None, strict=True, ge=1, le=1440)
    duration_source: Literal["user_explicit", "planning_allocation"] = "planning_allocation"
    start_time: time | None = None
    end_time: time | None = None
    source_quote: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def valid_interval(self):
        for value in (self.start_time, self.end_time):
            if value and (value.second or value.microsecond or value.tzinfo):
                raise ValueError("schedule times must be local minute precision")
        if self.end_time is not None and self.start_time is None:
            raise ValueError("end_time requires start_time")
        if self.start_time is not None and self.end_time is not None:
            minutes = (self.end_time.hour * 60 + self.end_time.minute) - (self.start_time.hour * 60 + self.start_time.minute)
            if minutes <= 0 or (self.duration_minutes is not None and self.duration_minutes != minutes):
                raise ValueError("item interval must be positive and agree with duration_minutes")
        if self.duration_source == "user_explicit" and not self.source_quote:
            raise ValueError("user_explicit duration requires source_quote")
        if self.kind in {"meal", "rest", "free_window", "blank_day"} and (
                self.place_id is not None or self.provider_place_id is not None or self.identity_status != "unknown"):
            raise ValueError("windows cannot masquerade as real POIs; use visit for a confirmed restaurant")
        return self


class DraftScheduleConstraints(DTO):
    start_date: date
    daily_start_time: time
    daily_end_time: time
    transport_mode: str = Field(min_length=1, max_length=40)
    max_walking_minutes: int | None = Field(default=None, strict=True, gt=0, le=1440)
    walking_scope: Literal["inter_activity", "all_day", "continuous"] = "inter_activity"
    total_budget_fen: int | None = Field(default=None, strict=True, gt=0)
    daily_budget_fen: int | None = Field(default=None, strict=True, gt=0)

    @model_validator(mode="after")
    def valid_bounds(self):
        if any(t.second or t.microsecond or t.tzinfo for t in (self.daily_start_time, self.daily_end_time)):
            raise ValueError("schedule times must be local minute precision")
        if self.daily_end_time <= self.daily_start_time:
            raise ValueError("daily_end_time must follow daily_start_time")
        if self.total_budget_fen and self.daily_budget_fen and self.daily_budget_fen > self.total_budget_fen:
            raise ValueError("daily budget exceeds total budget")
        return self


class DraftDay(DTO):
    day_index: int = Field(ge=1, le=14)
    title: str = Field(min_length=1, max_length=200)
    items: list[DraftItem] = Field(max_length=12)
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def valid_bounds(self):
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("day start and end must be provided together")
        if self.start_time is not None:
            if any(t.second or t.microsecond or t.tzinfo for t in (self.start_time, self.end_time)):
                raise ValueError("schedule times must be local minute precision")
            if self.end_time <= self.start_time:
                raise ValueError("invalid day interval")
        return self


class DraftPlan(DTO):
    schema_version: Literal[1, 2] = 1
    schedule_constraints: DraftScheduleConstraints | None = None
    days: list[DraftDay] = Field(min_length=1, max_length=14)

    @model_validator(mode="after")
    def consecutive_days(self):
        if [day.day_index for day in self.days] != list(range(1, len(self.days) + 1)):
            raise ValueError("days must be consecutive relative day_index values starting at 1")
        if self.schema_version == 1:
            if self.schedule_constraints is not None or any(day.start_time is not None for day in self.days):
                raise ValueError("v1 cannot contain v2 schedule constraints")
            for day in self.days:
                for item in day.items:
                    legacy = DraftItem(name=item.name, note=item.note, place_id=item.place_id, identity_status=item.identity_status)
                    if item != legacy:
                        raise ValueError("v1 cannot contain v2 item fields")
        else:
            if self.schedule_constraints is None:
                raise ValueError("v2 requires explicit schedule_constraints")
            refs = [item.item_ref for day in self.days for item in day.items]
            if any(ref is None for ref in refs) or len(set(refs)) != len(refs):
                raise ValueError("v2 item_ref must be present and globally unique")
            if sum(item.kind == "visit" for day in self.days for item in day.items) > 100:
                raise ValueError("v2 supports at most 100 scheduled visits")
            for day in self.days:
                if any(item.kind == "blank_day" for item in day.items) and (
                        len(day.items) != 1 or day.items[0].start_time is not None or day.items[0].duration_minutes is not None):
                    raise ValueError("blank_day must be the sole item and use the full day bounds")
                for item in day.items:
                    if item.kind not in {"optional", "blank_day"} and item.duration_minutes is None and item.end_time is None:
                        raise ValueError("scheduled v2 items require a duration or explicit interval")
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
    schema_version: Literal[1, 2] = 1
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

    @model_validator(mode="after")
    def compatible_schema(self):
        if self.plan is not None and self.plan.schema_version != self.schema_version:
            raise ValueError("draft and plan schema_version must agree")
        if self.schema_version == 2:
            for record in self.requirement_records:
                EffectiveRequirement.model_validate(record)
        return self
