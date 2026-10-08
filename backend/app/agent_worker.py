import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.planning_graph_runtime import execute_planning_run


async def claim_next_run() -> uuid.UUID | None:
    now = datetime.now(UTC)
    lease_until = now + timedelta(seconds=get_settings().agent_lease_seconds)
    worker_id = os.getenv("HOSTNAME", "agent-worker")[:80]
    async with session_factory() as session:
        run = await session.scalar(
            select(PlanningRun)
            .where(
                or_(
                    PlanningRun.status == "queued",
                    (
                        PlanningRun.status.in_(("researching", "planning", "validating"))
                        & PlanningRun.worker_lease_expires_at.is_not(None)
                        & (PlanningRun.worker_lease_expires_at < now)
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
        await session.commit()
        return run.id


async def execute_claimed_run(run_id: uuid.UUID) -> None:
    try:
        await execute_planning_run(run_id)
    except Exception as exc:
        print(f"planning run {run_id} failed: {type(exc).__name__}")
    finally:
        try:
            async with session_factory() as session:
                run = await session.get(PlanningRun, run_id)
                if run is not None:
                    run.worker_lease_expires_at = None
                    run.worker_id = None
                    await session.commit()
        except Exception as exc:
            print(f"planning run {run_id} lease cleanup failed: {type(exc).__name__}")


async def main() -> None:
    settings = get_settings()
    delay = settings.agent_poll_seconds
    concurrency = settings.agent_worker_concurrency
    active: set[asyncio.Task] = set()
    while True:
        active = {task for task in active if not task.done()}
        if len(active) >= concurrency:
            await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
            continue
        run_id = await claim_next_run()
        if run_id is not None:
            active.add(asyncio.create_task(execute_claimed_run(run_id)))
        elif active:
            await asyncio.wait(active, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
        else:
            await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(main())
