import asyncio
import json
import sys
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.database import Activity, CandidateRouteLeg, DayPlan, PlanningRun, PlanRevision, session_factory
from app.demo_seed import DEMO_TRIP_ID, seed_demo_data
from app.planning_graph_runtime import execute_planning_run
from app.planning_run_repository import create_planning_run
from app.schemas import PlanningRunCreate, PlanningRunDecision


async def _formal_fingerprint() -> dict[str, Any]:
    async with session_factory() as session:
        activities = list(
            (
                await session.scalars(
                    select(Activity)
                    .join(DayPlan)
                    .where(DayPlan.trip_id == DEMO_TRIP_ID)
                    .order_by(DayPlan.position, Activity.position)
                )
            ).all()
        )
        return {
            "activity_ids": [str(item.id) for item in activities],
            "activity_versions": [item.version for item in activities],
        }


async def run() -> dict[str, Any]:
    async with session_factory() as session:
        await seed_demo_data(session, reset=False)
    before = await _formal_fingerprint()
    async with session_factory() as session:
        run_row = await create_planning_run(
            session,
            DEMO_TRIP_ID,
            PlanningRunCreate(
                run_type="replan",
                user_request="调整第二天下午，轻松一点并优化路线",
                entry_point="trip_planner",
            ),
        )
        run_id = run_row.id

    await execute_planning_run(run_id)
    async with session_factory() as session:
        run_row = await session.get(PlanningRun, run_id)
        revision = await session.scalar(
            select(PlanRevision)
            .where(PlanRevision.planning_run_id == run_id)
            .order_by(PlanRevision.revision_number.desc())
            .limit(1)
        )
        route_providers: Counter[str] = Counter()
        if revision is not None:
            route_providers.update(
                (
                    await session.scalars(
                        select(CandidateRouteLeg.provider).where(
                            CandidateRouteLeg.plan_revision_id == revision.id
                        )
                    )
                ).all()
            )
        report: dict[str, Any] = {
            "run_id": str(run_id),
            "status_before_decision": run_row.status if run_row else "missing",
            "error_code": run_row.error_code if run_row else "run_missing",
            "model_provider": run_row.model_provider if run_row else None,
            "model_name": run_row.model_name if run_row else None,
            "token_usage": run_row.token_usage if run_row else 0,
            "pending_interrupt_kind": (
                run_row.pending_interrupt.get("kind")
                if run_row and run_row.pending_interrupt
                else None
            ),
            "revision_created": revision is not None,
            "revision_id": str(revision.id) if revision else None,
            "validation_valid": (
                bool(revision.validation_result.get("valid")) if revision else False
            ),
            "route_providers": dict(route_providers),
        }

    if report["pending_interrupt_kind"] == "approval":
        await execute_planning_run(
            run_id, decision=PlanningRunDecision(decision="reject")
        )
    else:
        async with session_factory() as session:
            unfinished = await session.get(PlanningRun, run_id)
            if unfinished is not None and unfinished.status not in {
                "accepted", "rejected", "failed", "cancelled"
            }:
                unfinished.status = "cancelled"
                await session.commit()
    async with session_factory() as session:
        final_run = await session.get(PlanningRun, run_id)
        report["final_run_status"] = final_run.status if final_run else "missing"
    report["formal_state_unchanged"] = before == await _formal_fingerprint()
    report["ok"] = bool(
        report["status_before_decision"] == "awaiting_confirmation"
        and report["pending_interrupt_kind"] == "approval"
        and report["revision_created"]
        and report["validation_valid"]
        and report["route_providers"]
        and report["final_run_status"] == "rejected"
        and report["formal_state_unchanged"]
    )
    return report


def main() -> None:
    if sys.platform == "win32":
        report = asyncio.run(run(), loop_factory=asyncio.SelectorEventLoop)
    else:
        report = asyncio.run(run())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
