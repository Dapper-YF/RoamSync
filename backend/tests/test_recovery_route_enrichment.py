import asyncio
import uuid
from sqlalchemy import update

from fastapi.testclient import TestClient

from app.main import app
from app.database import session_factory, Activity
from app.demo_seed import DEMO_TRIP_ID, demo_uuid
from app.candidate_route_service import enrich_candidate_routes
from app.plan_revision_service import validate_candidate_plan
from app.schemas import CandidatePlanSnapshot
from app.planning_context import build_planning_context
from app.planning_explanation import candidate_cost_totals


def test_recovery_routes_include_implicitly_retained_navigation_target():
    with TestClient(app) as client:
        assert client.post('/api/v1/demo/reset').status_code == 200
        execution = client.post(f'/api/v1/trips/{DEMO_TRIP_ID}/execution/start',json={'day_plan_id':str(demo_uuid('day','day-1'))}).json()
        leg = client.get(f'/api/v1/trips/{DEMO_TRIP_ID}/days').json()[0]['route_legs'][0]
        response = client.post(f'/api/v1/trips/{DEMO_TRIP_ID}/navigation-sessions',json={'trip_execution_id':execution['id'],'from_activity_id':leg['from_activity_id'],'to_activity_id':leg['to_activity_id']})
        assert response.status_code == 201

        async def scenario():
            async with session_factory() as session:
                await session.execute(update(Activity).where(Activity.id.in_([uuid.UUID(leg['from_activity_id']),uuid.UUID(leg['to_activity_id'])])).values(schedule_locked=False))
                await session.commit()
                # Ordinary user Planning must retain runtime-protected pending
                # activities too; protection cannot depend on a recovery flag.
                snapshot = await enrich_candidate_routes(session,DEMO_TRIP_ID,CandidatePlanSnapshot(activities=[]))
                refs={ref for route in snapshot.route_legs for ref in (route.from_activity_ref,route.to_activity_ref)}
                assert f"activity:{leg['to_activity_id']}" in refs
                result=await validate_candidate_plan(session,DEMO_TRIP_ID,snapshot)
                assert 'candidate_route_set_mismatch' not in [error.code for error in result.errors]
                missing=await validate_candidate_plan(session,DEMO_TRIP_ID,CandidatePlanSnapshot(activities=[]))
                assert 'candidate_route_set_mismatch' in [error.code for error in missing.errors]
                context=(await build_planning_context(session,DEMO_TRIP_ID)).model_dump(mode='json')
                protected_cost=sum(a['estimated_cost_fen'] for a in context['days'][0]['activities'][:2])
                assert candidate_cost_totals(context,snapshot)[0]==protected_cost
        asyncio.run(scenario())
