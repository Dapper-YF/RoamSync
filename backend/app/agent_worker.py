import asyncio
import uuid

from sqlalchemy import select

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.planning_graph_runtime import execute_planning_run


async def claim_next_run() -> uuid.UUID | None:
    async with session_factory() as session:
        run = await session.scalar(
            select(PlanningRun)
            .where(PlanningRun.status == "queued")
            .order_by(PlanningRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if run is None:
            return None
        run.status = "researching"
        await session.commit()
        return run.id


async def main() -> None:
    delay = get_settings().agent_poll_seconds
    while True:
        run_id = await claim_next_run()
        if run_id is None:
            await asyncio.sleep(delay)
            continue
        try:
            await execute_planning_run(run_id)
        except Exception as exc:
            print(f"planning run {run_id} failed: {type(exc).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
