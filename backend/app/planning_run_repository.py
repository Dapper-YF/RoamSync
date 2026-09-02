import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import PlanningRun, PlanRevision
from app.repository import get_trip
from app.schemas import CandidatePlanSnapshot, PlanningRunCreate


class PlanningRunNotFoundError(Exception):
    pass


class PlanRevisionNotFoundError(Exception):
    pass


class InvalidPlanningRunStateError(Exception):
    pass


class StalePlanningRunError(Exception):
    pass


async def create_planning_run(
    session: AsyncSession, trip_id: uuid.UUID, payload: PlanningRunCreate
) -> PlanningRun:
    trip = await get_trip(session, trip_id)
    run = PlanningRun(
        trip_id=trip_id,
        run_type=payload.run_type,
        status="queued",
        user_request=payload.user_request,
        base_trip_version=trip.version,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_planning_run(session: AsyncSession, run_id: uuid.UUID) -> PlanningRun:
    run = await session.get(PlanningRun, run_id)
    if run is None:
        raise PlanningRunNotFoundError
    return run


async def get_latest_revision(
    session: AsyncSession, run_id: uuid.UUID
) -> PlanRevision:
    await get_planning_run(session, run_id)
    revision = await session.scalar(
        select(PlanRevision)
        .where(PlanRevision.planning_run_id == run_id)
        .order_by(PlanRevision.revision_number.desc())
        .limit(1)
    )
    if revision is None:
        raise PlanRevisionNotFoundError
    return revision


async def save_plan_revision(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    before_snapshot: dict,
    proposed_snapshot: CandidatePlanSnapshot,
    reason: str,
    difference_summary: dict,
    validation_result: dict,
    source_ids: list[uuid.UUID],
) -> PlanRevision:
    run = await get_planning_run(session, run_id)
    if run.status not in {"queued", "researching", "planning", "validating"}:
        raise InvalidPlanningRunStateError
    trip = await get_trip(session, run.trip_id)
    if trip.version != run.base_trip_version:
        raise StalePlanningRunError

    previous = await session.scalar(
        select(PlanRevision)
        .where(
            PlanRevision.planning_run_id == run_id,
            PlanRevision.status == "pending",
        )
        .order_by(PlanRevision.revision_number.desc())
        .limit(1)
    )
    if previous is not None:
        previous.status = "superseded"
    next_number = int(
        await session.scalar(
            select(func.coalesce(func.max(PlanRevision.revision_number), 0)).where(
                PlanRevision.planning_run_id == run_id
            )
        )
        or 0
    ) + 1
    revision = PlanRevision(
        planning_run_id=run_id,
        trip_id=run.trip_id,
        revision_number=next_number,
        reason=reason.strip(),
        before_snapshot=before_snapshot,
        proposed_snapshot=proposed_snapshot.model_dump(mode="json"),
        difference_summary=difference_summary,
        validation_result=validation_result,
        source_ids=[str(source_id) for source_id in source_ids],
        status="pending",
    )
    session.add(revision)
    run.status = "awaiting_confirmation"
    await session.commit()
    await session.refresh(revision)
    return revision


async def reject_revision(
    session: AsyncSession, revision_id: uuid.UUID
) -> PlanRevision:
    revision = await session.get(PlanRevision, revision_id)
    if revision is None:
        raise PlanRevisionNotFoundError
    if revision.status != "pending":
        raise InvalidPlanningRunStateError
    run = await get_planning_run(session, revision.planning_run_id)
    revision.status = "rejected"
    revision.decided_at = datetime.now(UTC)
    run.status = "rejected"
    run.completed_at = revision.decided_at
    await session.commit()
    await session.refresh(revision)
    return revision
