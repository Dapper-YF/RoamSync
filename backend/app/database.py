import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("total_budget_fen > 0", name="ck_trips_total_budget_positive"),
        CheckConstraint("daily_budget_fen > 0", name="ck_trips_daily_budget_positive"),
        CheckConstraint(
            "daily_budget_fen <= total_budget_fen",
            name="ck_trips_daily_not_above_total",
        ),
        CheckConstraint("end_date >= start_date", name="ck_trips_dates_ordered"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    destination: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    destination_adcode: Mapped[str] = mapped_column(String(12), nullable=False, default="")
    destination_citycode: Mapped[str] = mapped_column(String(12), nullable=False, default="")
    center_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    center_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    accommodation: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    accommodation_poi_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    accommodation_address: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    accommodation_district: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    accommodation_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    accommodation_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_budget_fen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_budget_fen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @property
    def status(self) -> str:
        if self.archived_at is not None:
            return "archived"
        today = datetime.now(UTC).date()
        if today < self.start_date:
            return "upcoming"
        if today <= self.end_date:
            return "active"
        return "completed"


class TripPreferences(Base):
    __tablename__ = "trip_preferences"
    __table_args__ = (
        CheckConstraint(
            "pace IN ('relaxed', 'balanced', 'intensive')",
            name="ck_trip_preferences_pace_allowed",
        ),
        CheckConstraint(
            "daily_end_time > daily_start_time",
            name="ck_trip_preferences_daily_window",
        ),
        CheckConstraint(
            "max_walking_minutes > 0 AND max_walking_minutes <= 480",
            name="ck_trip_preferences_max_walking_minutes",
        ),
        CheckConstraint("version > 0", name="ck_trip_preferences_version_positive"),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pace: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")
    interest_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    transport_modes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["walk", "transit"]
    )
    daily_start_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(9, 0)
    )
    daily_end_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(21, 0)
    )
    meal_preferences: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    avoid_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    max_walking_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    free_text_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PlanningRun(Base):
    __tablename__ = "planning_runs"
    __table_args__ = (
        CheckConstraint("run_type IN ('initial_plan', 'replan')", name="ck_planning_runs_type"),
        CheckConstraint(
            "status IN ('queued', 'researching', 'planning', 'validating', "
            "'awaiting_confirmation', 'accepted', 'rejected', 'failed', 'cancelled')",
            name="ck_planning_runs_status",
        ),
        CheckConstraint("base_trip_version > 0", name="ck_planning_runs_base_version"),
        CheckConstraint("token_usage >= 0", name="ck_planning_runs_token_usage"),
        Index("ix_planning_runs_trip_created", "trip_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    run_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    user_request: Mapped[str] = mapped_column(Text, nullable=False, default="")
    base_trip_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlanRevision(Base):
    __tablename__ = "plan_revisions"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "revision_number", name="uq_plan_revisions_run_number"),
        CheckConstraint("revision_number > 0", name="ck_plan_revisions_number"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'superseded')",
            name="ck_plan_revisions_status",
        ),
        Index("ix_plan_revisions_trip_created", "trip_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    planning_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planning_runs.id", ondelete="CASCADE"), nullable=False
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    before_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    proposed_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    difference_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint(
            "trip_id", "idempotency_key", name="uq_expenses_trip_idempotency"
        ),
        CheckConstraint("amount_fen > 0", name="ck_expenses_amount_positive"),
        CheckConstraint(
            "category IN ('food', 'transport', 'ticket', 'lodging', 'shopping', 'other')",
            name="ck_expenses_category_allowed",
        ),
        Index("ix_expenses_trip_spent_at", "trip_id", "spent_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount_fen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    spent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DayPlan(Base):
    __tablename__ = "day_plans"
    __table_args__ = (
        UniqueConstraint("trip_id", "date", name="uq_day_plans_trip_date"),
        UniqueConstraint("trip_id", "position", name="uq_day_plans_trip_position"),
        CheckConstraint("position >= 0", name="ck_day_plans_position_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    theme: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    route_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="walk")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_source_records_confidence_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)


class PlaceCandidate(Base):
    __tablename__ = "place_candidates"
    __table_args__ = (
        UniqueConstraint("trip_id", "slug", name="uq_place_candidates_trip_slug"),
        CheckConstraint(
            "category IN ('sight', 'food', 'culture', 'nature', 'shopping')",
            name="ck_place_candidates_category_allowed",
        ),
        CheckConstraint(
            "suggested_duration_minutes > 0",
            name="ck_place_candidates_duration_positive",
        ),
        CheckConstraint(
            "estimated_cost_fen >= 0",
            name="ck_place_candidates_cost_nonnegative",
        ),
        CheckConstraint("rating >= 0 AND rating <= 5", name="ck_place_candidates_rating"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    suggested_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_fen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("day_plan_id", "position", name="uq_activities_day_position"),
        UniqueConstraint("day_plan_id", "place_candidate_id", name="uq_activities_day_place"),
        CheckConstraint("position >= 0", name="ck_activities_position_nonnegative"),
        CheckConstraint("duration_minutes > 0", name="ck_activities_duration_positive"),
        CheckConstraint("estimated_cost_fen >= 0", name="ck_activities_cost_nonnegative"),
        CheckConstraint("version > 0", name="ck_activities_version_positive"),
        CheckConstraint(
            "status IN ('planned', 'active', 'completed', 'skipped')",
            name="ck_activities_status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    day_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("day_plans.id", ondelete="CASCADE"), nullable=False
    )
    place_candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("place_candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scheduled_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_fen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    custom_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    schedule_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RouteLeg(Base):
    __tablename__ = "route_legs"
    __table_args__ = (
        UniqueConstraint("day_plan_id", "position", name="uq_route_legs_day_position"),
        CheckConstraint("position >= 0", name="ck_route_legs_position_nonnegative"),
        CheckConstraint("distance_meters >= 0", name="ck_route_legs_distance_nonnegative"),
        CheckConstraint("duration_minutes >= 0", name="ck_route_legs_duration_nonnegative"),
        CheckConstraint(
            "mode IN ('walk', 'transit', 'driving')",
            name="ck_route_legs_mode_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    day_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("day_plans.id", ondelete="CASCADE"), nullable=False
    )
    from_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    to_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    is_estimated: Mapped[bool] = mapped_column(nullable=False, default=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RouteCache(Base):
    __tablename__ = "route_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    is_estimated: Mapped[bool] = mapped_column(nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
