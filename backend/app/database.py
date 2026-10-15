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
    text,
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
        CheckConstraint(
            "(total_budget_fen IS NULL AND daily_budget_fen IS NULL) OR "
            "(total_budget_fen > 0 AND daily_budget_fen > 0 AND daily_budget_fen <= total_budget_fen)",
            name="ck_trips_budget_limits_consistent",
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
    # NULL means no budget constraint; a positive value is a hard cap.
    total_budget_fen: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    daily_budget_fen: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
            "status IN ('queued', 'researching', 'awaiting_clarification', 'planning', 'validating', "
            "'awaiting_confirmation', 'accepted', 'rejected', 'failed', 'cancelled', 'answered')",
            name="ck_planning_runs_status",
        ),
        CheckConstraint("base_trip_version > 0", name="ck_planning_runs_base_version"),
        CheckConstraint("token_usage >= 0", name="ck_planning_runs_token_usage"),
        Index("ix_planning_runs_trip_created", "trip_id", "created_at"),
        # A disruption may have many historical attempts, but only one run may
        # be capable of changing its still-unresolved itinerary at a time.
        Index("uq_planning_runs_active_recovery", "disruption_event_id", unique=True,
              postgresql_where=text("disruption_event_id IS NOT NULL AND status IN ('queued', 'researching', 'awaiting_clarification', 'planning', 'validating', 'awaiting_confirmation')")),
        Index("uq_planning_runs_active_trigger", "trip_id", "trigger_key", unique=True,
              postgresql_where=text("trigger_key IS NOT NULL AND status IN ('queued', 'researching', 'awaiting_clarification', 'planning', 'validating', 'awaiting_confirmation')")),
        Index("uq_planning_runs_active_automatic_version", "trip_id", "base_trip_version", unique=True,
              postgresql_where=text("trigger_type IN ('navigation_disruption', 'experience_impact') AND status IN ('queued', 'researching', 'awaiting_clarification', 'planning', 'validating', 'awaiting_confirmation')")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    disruption_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_disruption_events.id", ondelete="SET NULL"), nullable=True
    )
    trigger_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trigger_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    run_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    user_request: Mapped[str] = mapped_column(Text, nullable=False, default="")
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_point: Mapped[str] = mapped_column(String(24), nullable=False, default="trip_planner")
    selected_day_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("day_plans.id", ondelete="SET NULL"), nullable=True
    )
    selected_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    intent_resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    base_trip_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pending_interrupt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    worker_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    rejection_reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rejection_reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def planning_goals(self) -> dict | None:
        return (self.difference_summary or {}).get("planning_goals")

    @property
    def goal_satisfaction(self) -> dict | None:
        return (self.difference_summary or {}).get("goal_satisfaction")


class CandidateRouteLeg(Base):
    __tablename__ = "candidate_route_legs"
    __table_args__ = (
        UniqueConstraint(
            "plan_revision_id", "day_date", "position",
            name="uq_candidate_route_legs_revision_day_position",
        ),
        CheckConstraint("position >= 0", name="ck_candidate_route_legs_position_nonnegative"),
        CheckConstraint(
            "distance_meters >= 0", name="ck_candidate_route_legs_distance_nonnegative"
        ),
        CheckConstraint(
            "duration_minutes >= 0", name="ck_candidate_route_legs_duration_nonnegative"
        ),
        CheckConstraint(
            "mode IN ('walk', 'transit', 'driving')",
            name="ck_candidate_route_legs_mode_allowed",
        ),
        Index(
            "ix_candidate_route_legs_revision_day",
            "plan_revision_id", "day_date", "position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_activity_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    to_activity_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    is_estimated: Mapped[bool] = mapped_column(nullable=False, default=False)
    path: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    alternatives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
            "importance IN ('low', 'normal', 'high', 'must_do')",
            name="ck_activities_importance_allowed",
        ),
        CheckConstraint("importance != 'must_do' OR can_skip = false", name="ck_activities_must_do_not_skippable"),
        CheckConstraint("minimum_duration_minutes IS NULL OR (minimum_duration_minutes > 0 AND minimum_duration_minutes <= duration_minutes)", name="ck_activities_minimum_duration"),
        CheckConstraint("importance_source IN ('user_explicit', 'user_confirmed', 'system_default', 'unknown')", name="ck_activities_importance_source"),
        CheckConstraint("can_skip_source IN ('user_explicit', 'user_confirmed', 'system_default', 'unknown')", name="ck_activities_can_skip_source"),
        CheckConstraint("minimum_duration_source IN ('user_explicit', 'user_confirmed', 'system_default', 'unknown')", name="ck_activities_minimum_duration_source"),
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
    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    can_skip: Mapped[bool] = mapped_column(nullable=False, default=True)
    minimum_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    importance_source: Mapped[str] = mapped_column(String(20), nullable=False, default="system_default")
    can_skip_source: Mapped[str] = mapped_column(String(20), nullable=False, default="system_default")
    minimum_duration_source: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
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


class TripExecution(Base):
    __tablename__ = "trip_executions"
    __table_args__ = (
        UniqueConstraint("trip_id", name="uq_trip_executions_trip"),
        CheckConstraint(
            "status IN ('in_progress', 'paused', 'completed')",
            name="ck_trip_executions_status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_progress")
    itinerary_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_day_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("day_plans.id", ondelete="SET NULL"), nullable=True
    )
    current_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    actual_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class NavigationSession(Base):
    """A runtime projection of one formal itinerary leg.

    Activity and RouteLeg UUIDs intentionally have no foreign keys here.  A
    revision can delete and recreate those rows, while this historical runtime
    record must retain the identity it was created from and become superseded.
    """

    __tablename__ = "navigation_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'active', 'rerouting', 'arrived', 'completed', "
            "'failed', 'cancelled', 'superseded')",
            name="ck_navigation_sessions_status_allowed",
        ),
        CheckConstraint("itinerary_version > 0", name="ck_navigation_sessions_itinerary_version_positive"),
        CheckConstraint("route_revision >= 0", name="ck_navigation_sessions_route_revision_nonnegative"),
        CheckConstraint("state_version > 0", name="ck_navigation_sessions_state_version_positive"),
        CheckConstraint("last_location_sequence >= 0", name="ck_navigation_sessions_location_sequence_nonnegative"),
        CheckConstraint(
            "progress_ratio IS NULL OR (progress_ratio >= 0 AND progress_ratio <= 1)",
            name="ck_navigation_sessions_progress_ratio_range",
        ),
        CheckConstraint(
            "last_location_accuracy_meters IS NULL OR last_location_accuracy_meters >= 0",
            name="ck_navigation_sessions_accuracy_nonnegative",
        ),
        CheckConstraint(
            "remaining_duration_seconds IS NULL OR remaining_duration_seconds >= 0",
            name="ck_navigation_sessions_remaining_duration_nonnegative",
        ),
        CheckConstraint(
            "navigation_status IS NULL OR navigation_status IN ('navigating', 'rerouting', 'paused', 'arrived')",
            name="ck_navigation_sessions_navigation_status",
        ),
        CheckConstraint(
            "observation_source IS NULL OR observation_source IN ('simulation', 'real_gps')",
            name="ck_navigation_sessions_observation_source",
        ),
        Index(
            "uq_navigation_sessions_execution_live",
            "trip_execution_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'rerouting')"),
        ),
        Index("ix_navigation_sessions_trip_created", "trip_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    trip_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False
    )
    # Stable leg identity: trip_id + itinerary_version + this pair.  The route
    # id is only source evidence because RouteLeg rows are replaceable.
    from_activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    formal_route_leg_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    itinerary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    travel_mode: Mapped[str] = mapped_column(String(12), nullable=False)
    coordinate_system: Mapped[str] = mapped_column(String(16), nullable=False, default="gcj02")
    origin_longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    origin_latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    destination_longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    destination_latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    planned_departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_arrival_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remaining_distance_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    route_path: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    route_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_location_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_location_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_location_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_location_accuracy_meters: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    last_location_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remaining_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    navigation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    observation_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_observation_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class NavigationDetectionState(Base):
    """Durable debounce state derived from accepted navigation observations."""

    __tablename__ = "navigation_detection_states"
    __table_args__ = (
        CheckConstraint("itinerary_version > 0", name="ck_navigation_detection_version_positive"),
        CheckConstraint("last_processed_observation_sequence >= 0", name="ck_navigation_detection_sequence_nonnegative"),
        CheckConstraint("consecutive_risk_count >= 0", name="ck_navigation_detection_count_nonnegative"),
        CheckConstraint(
            "current_risk_state IN ('normal', 'warning', 'critical', 'infeasible')",
            name="ck_navigation_detection_risk_state",
        ),
    )

    navigation_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("navigation_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    itinerary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    last_processed_observation_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_risk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_risk_state: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    minimum_downstream_slack_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_impacted_activity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_risk_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_escalation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TripDisruptionEvent(Base):
    __tablename__ = "trip_disruption_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('missed_time_window', 'itinerary_infeasible')", name="ck_trip_disruptions_type"),
        CheckConstraint("status IN ('active', 'resolved', 'dismissed')", name="ck_trip_disruptions_status"),
        Index("uq_trip_disruptions_active_dedup", "dedup_key", unique=True, postgresql_where=text("status = 'active'")),
        Index("ix_trip_disruptions_trip_detected", "trip_id", "detected_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    trip_execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False)
    navigation_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("navigation_sessions.id", ondelete="CASCADE"), nullable=False)
    itinerary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    impacted_identity: Mapped[str] = mapped_column(String(120), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    impact_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    resolution_plan_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_revisions.id", ondelete="SET NULL"), nullable=True
    )
    resolution_planning_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ActivityExecution(Base):
    __tablename__ = "activity_executions"
    __table_args__ = (
        UniqueConstraint("trip_execution_id", "activity_id", name="uq_activity_executions_trip_activity"),
        CheckConstraint(
            "status IN ('pending', 'arrived', 'in_progress', 'completed', 'skipped')",
            name="ck_activity_executions_status_allowed",
        ),
        CheckConstraint("delay_minutes >= 0", name="ck_activity_executions_delay_nonnegative"),
        Index("ix_activity_executions_trip_status", "trip_execution_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    actual_arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TravelEvent(Base):
    __tablename__ = "travel_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('trip_started', 'arrived', 'activity_started', 'completed', 'skipped', "
            "'paused', 'resumed', 'trip_finished', 'delay', 'temporary_closure', "
            "'weather_change', 'fatigue', 'budget_change', 'user_change', "
            "'user_extend_stay', 'user_leave_early')",
            name="ck_travel_events_type_allowed",
        ),
        Index("ix_travel_events_execution_occurred", "trip_execution_id", "occurred_at"),
        Index("ix_travel_events_activity_type", "activity_execution_id", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False
    )
    activity_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_executions.id", ondelete="SET NULL"), nullable=True
    )
    client_action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


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
    path: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    alternatives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
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
    path: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    alternatives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=True, index=True)
    messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pending_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    applied_actions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    latest_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
