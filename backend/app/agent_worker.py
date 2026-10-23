import asyncio
import os
import uuid
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update, func
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.planning_graph_runtime import execute_planning_run
from app.planning_claim import PlanningClaim, active_claim, LostPlanningClaim, CHECKPOINT_THREAD

logger = logging.getLogger(__name__)


async def claim_next_run() -> PlanningClaim | None:
    now = datetime.now(UTC)
    lease_until = now + timedelta(seconds=get_settings().agent_lease_seconds)
    worker_id = f"{os.getenv('HOSTNAME', 'agent-worker')[:47]}:{uuid.uuid4().hex}"
    async with session_factory() as session:
        run = await session.scalar(
            select(PlanningRun)
            .where(
                or_(
                    PlanningRun.status == "queued",
                    (
                        PlanningRun.status.in_(("researching", "planning", "validating"))
                        & or_(PlanningRun.worker_lease_expires_at < now,
                            PlanningRun.worker_lease_expires_at.is_(None) &
                            (func.coalesce(PlanningRun.heartbeat_at, PlanningRun.started_at, PlanningRun.created_at)
                                < now - timedelta(seconds=get_settings().agent_lease_seconds)))
                    ),
                )
            )
            .order_by(PlanningRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if run is None:
            return None
        run.status = "researching"
        run.worker_id = worker_id
        run.worker_lease_expires_at = lease_until
        run.started_at = run.started_at or now
        # An expired attempt may still finish a provider call. Its checkpoint
        # writes cannot corrupt the new attempt or the user's later resume.
        run.trigger_snapshot = {**(run.trigger_snapshot or {}),
            CHECKPOINT_THREAD: f"{run.id}:{uuid.uuid4().hex}"}
        await session.commit()
        return PlanningClaim(run.id, run.trip_id, worker_id)


async def execute_claimed_run(claim: PlanningClaim) -> None:
    token = active_claim.set(claim)
    try:
        await execute_planning_run(claim.run_id)
    except LostPlanningClaim:
        logger.info("Planning run %s stopped after ownership changed", claim.run_id)
    except Exception as exc:
        logger.warning("Planning run %s failed: %s", claim.run_id, type(exc).__name__)
    finally:
        active_claim.reset(token)
        try:
            async with session_factory() as session:
                # A shutdown or unexpected exit makes unfinished work eligible
                # for immediate recovery. Never clear a replacement's lease.
                owned = (PlanningRun.id == claim.run_id, PlanningRun.worker_id == claim.token)
                await session.execute(update(PlanningRun).where(*owned,
                    PlanningRun.status.in_(("queued", "researching", "planning", "validating")))
                    .values(worker_lease_expires_at=datetime.now(UTC)))
                await session.execute(update(PlanningRun).where(*owned,
                    PlanningRun.status.not_in(("queued", "researching", "planning", "validating")))
                    .values(worker_id=None, worker_lease_expires_at=None))
                await session.commit()
        except Exception as exc:
            logger.warning("Planning run %s lease cleanup failed: %s", claim.run_id, type(exc).__name__)


async def main() -> None:
    settings = get_settings()
    delay = settings.agent_poll_seconds
    concurrency = settings.agent_worker_concurrency
    active: set[asyncio.Task] = set()
    failures = 0
    try:
        while True:
            for task in list(active):
                if task.done():
                    active.remove(task)
                    if not task.cancelled():
                        try:
                            task.result()
                        except Exception as exc:
                            logger.warning("Worker task failed: %s", type(exc).__name__)
            if len(active) >= concurrency:
                await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                claim = await claim_next_run()
                failures = 0
            except (SQLAlchemyError, OSError) as exc:
                failures += 1
                retry_delay = min(30, max(delay, .1) * 2 ** min(failures - 1, 8))
                logger.warning("Worker claim failed (%s); retrying in %.1fs", type(exc).__name__, retry_delay)
                await asyncio.sleep(retry_delay)
                continue
            if claim is not None:
                active.add(asyncio.create_task(execute_claimed_run(claim)))
            elif active:
                await asyncio.wait(active, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
            else:
                await asyncio.sleep(delay)
    finally:
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
