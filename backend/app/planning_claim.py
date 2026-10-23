"""Lease identity for one execution attempt, checked only in short write units."""
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import PlanningRun, Trip


class LostPlanningClaim(RuntimeError):
    pass


@dataclass(frozen=True)
class PlanningClaim:
    run_id: uuid.UUID
    trip_id: uuid.UUID
    token: str


active_claim: ContextVar[PlanningClaim | None] = ContextVar("planning_claim", default=None)
CHECKPOINT_THREAD = "worker_checkpoint_thread"


def checkpoint_thread(run: PlanningRun) -> str:
    return (run.trigger_snapshot or {}).get(CHECKPOINT_THREAD) or str(run.id)


async def assert_planning_claim(session, run_id=None, trip_id=None):
    claim = active_claim.get()
    if claim is None:
        return
    if (run_id is not None and claim.run_id != run_id) or (trip_id is not None and claim.trip_id != trip_id):
        raise LostPlanningClaim("execution claim does not match this operation")
    # All leased business writers take Trip first, then Run. Never call this
    # before external work: these locks last until this write unit completes.
    await session.scalar(select(Trip.id).where(Trip.id == claim.trip_id).with_for_update())
    row = (await session.execute(select(
        PlanningRun.worker_id, PlanningRun.worker_lease_expires_at, PlanningRun.status,
    ).where(PlanningRun.id == claim.run_id).with_for_update())).one_or_none()
    if (row is None or row.worker_id != claim.token or row.worker_lease_expires_at is None
        or row.worker_lease_expires_at <= datetime.now(UTC)
        or row.status not in {"queued", "researching", "planning", "validating", "awaiting_confirmation", "awaiting_clarification", "answered"}):
        raise LostPlanningClaim("execution lease expired, ended or changed owner")
