"""Persist observed milestones, without pretending model thinking is observable."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, update
from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.planning_claim import active_claim, assert_planning_claim, LostPlanningClaim

active_run = ContextVar("progress_run", default=None)
WORKING = ("queued", "researching", "planning", "validating")
logger = logging.getLogger(__name__)


async def report_progress(stage: str, message: str):
    run_id = active_run.get()
    if run_id is None:
        return
    now = datetime.now(UTC)
    async with session_factory() as db:
        await assert_planning_claim(db, run_id)
        run = await db.scalar(select(PlanningRun).where(PlanningRun.id == run_id, PlanningRun.status.in_(WORKING)).with_for_update())
        if run is not None and active_claim.get() is None and run.worker_id is not None:
            return
        if run is not None:
            run.progress = {**(run.progress or {}), "stage": stage, "message": message, "updated_at": now.isoformat()}
            run.heartbeat_at = now
        await db.commit()


async def pulse(run_id):
    now = datetime.now(UTC)
    claim = active_claim.get()
    if claim is not None and claim.run_id != run_id:
        raise LostPlanningClaim("heartbeat does not match execution")
    async with session_factory() as db:
        conditions = [PlanningRun.id == run_id, PlanningRun.status.in_(WORKING)]
        values = {"heartbeat_at": now}
        if claim is not None:
            conditions.extend([PlanningRun.worker_id == claim.token, PlanningRun.worker_lease_expires_at > now])
            values["worker_lease_expires_at"] = now + timedelta(seconds=get_settings().agent_lease_seconds)
        else:
            conditions.append(PlanningRun.worker_id.is_(None))
        result = await db.execute(update(PlanningRun).where(*conditions).values(**values))
        if claim is not None and result.rowcount != 1:
            row = await db.get(PlanningRun, run_id)
            if (row is not None and row.worker_id == claim.token
                and row.worker_lease_expires_at is not None and row.worker_lease_expires_at > datetime.now(UTC)
                and row.status in {"awaiting_confirmation", "awaiting_clarification", "answered"}):
                return False  # Normal interrupt/completion, not ownership loss.
            raise LostPlanningClaim("heartbeat lease expired or changed owner")
        await db.commit()
        return result.rowcount == 1


@asynccontextmanager
async def track_progress(run_id):
    token = active_run.set(run_id)
    parent = asyncio.current_task()
    ownership_lost = False
    async def heartbeat():
        nonlocal ownership_lost
        while True:
            try:
                if await pulse(run_id) is False:
                    return
            except LostPlanningClaim:
                ownership_lost = True
                parent.cancel()
                return
            except Exception:
                logger.warning("Planning heartbeat write failed", exc_info=False)
            await asyncio.sleep(15)
    task = asyncio.create_task(heartbeat())
    try:
        yield
    except asyncio.CancelledError:
        if ownership_lost:
            raise LostPlanningClaim("heartbeat detected a replacement execution") from None
        raise
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        active_run.reset(token)
