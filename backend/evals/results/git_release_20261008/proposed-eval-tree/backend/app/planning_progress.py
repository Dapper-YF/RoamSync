"""Persist observed milestones, without pretending model thinking is observable."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, update
from app.config import get_settings
from app.database import PlanningRun, session_factory

active_run = ContextVar("progress_run", default=None)
WORKING = ("queued", "researching", "planning", "validating")
logger = logging.getLogger(__name__)


async def report_progress(stage: str, message: str):
    run_id = active_run.get()
    if run_id is None:
        return
    now = datetime.now(UTC)
    async with session_factory() as db:
        run = await db.scalar(select(PlanningRun).where(PlanningRun.id == run_id, PlanningRun.status.in_(WORKING)).with_for_update())
        if run is not None:
            run.progress = {**(run.progress or {}), "stage": stage, "message": message, "updated_at": now.isoformat()}
            run.heartbeat_at = now
        await db.commit()


async def pulse(run_id):
    now = datetime.now(UTC)
    async with session_factory() as db:
        await db.execute(update(PlanningRun).where(PlanningRun.id == run_id, PlanningRun.status.in_(WORKING)).values(heartbeat_at=now))
        # Only claimed jobs own a lease. Keep long provider calls from being reclaimed.
        await db.execute(update(PlanningRun).where(PlanningRun.id == run_id, PlanningRun.status.in_(WORKING), PlanningRun.worker_id.is_not(None)).values(
            worker_lease_expires_at=now + timedelta(seconds=get_settings().agent_lease_seconds)))
        await db.commit()


@asynccontextmanager
async def track_progress(run_id):
    token = active_run.set(run_id)
    async def heartbeat():
        while True:
            try:
                await pulse(run_id)
            except Exception:
                logger.warning("Planning heartbeat write failed", exc_info=False)
            await asyncio.sleep(15)
    task = asyncio.create_task(heartbeat())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        active_run.reset(token)
