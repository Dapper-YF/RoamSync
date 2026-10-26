import asyncio
import json
from sqlalchemy import select, cast, String, text
from app.database import PlanningRun, session_factory
from app.companion_context import CompanionContextReader
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal

class ForbiddenProvider:
    async def generate(self, *args):
        raise AssertionError('No model call authorized for read-only verification')

async def main():
    async with session_factory() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        rows = (await db.execute(select(PlanningRun.id, PlanningRun.trip_id, PlanningRun.status)
            .where(cast(PlanningRun.id, String).like('88df1262%')).limit(2))).all()
        if len(rows) != 1:
            print(json.dumps({'screenshot_run_matches': len(rows), 'verification': 'not_resolved', 'writes': 0}))
            return
        row = rows[0]
        message = '为什么会这样安排行程？'
        result = await CompanionRuntime(CompanionContextReader(db, row.trip_id), ForbiddenProvider()).run(
            session_id='read-only-release-check', turn_id='read-only-release-check', message=message,
            goal=route_travel_goal(message), messages=[])
        print(json.dumps({'screenshot_run_matches': 1, 'run_id': str(row.id), 'run_status': row.status,
            'explanation_type': result.explanation.explanation_type if result.explanation else None,
            'source_revision': result.explanation.source_decision_ref if result.explanation else None,
            'saved_reason_count': len(result.explanation.reasons) if result.explanation else 0,
            'writes': 0, 'model_calls': 0}))

asyncio.run(main())
