import asyncio
import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import session_factory
from app.candidate_edit import bind_initial_candidate, load_initial_candidate
from app.initial_places_service import prepare_initial_candidates
from app.planner_repository import get_candidates, get_day_plans
from app.planning_context import build_planning_context
from app.planning_run_repository import create_planning_run, save_plan_revision
from app.plan_revision_service import validate_candidate_plan
from app.plan_revision_service import accept_plan_revision
from app.openai_planner import build_planner_input, preserve_out_of_scope_activities
from app.schemas import CandidateActivity, CandidatePlanSnapshot, PlanningIntentResolution, PlanningRunCreate, PlaceSearchResultResponse


def test_initial_candidate_edit_preserves_unaccepted_other_dates_and_fails_closed():
    with TestClient(app) as client:
        trip = client.post('/api/v1/trips', json={'title':'Candidate edit regression','destination':'杭州市','start_date':'2026-11-01','end_date':'2026-11-02'}).json()

        async def scenario():
            async with session_factory() as session:
                tid = uuid.UUID(trip['id'])
                places = [PlaceSearchResultResponse(provider_place_id=f'edit-{i}', name=f'测试公园{i}', category='nature', longitude=120.1+i*.001, latitude=30.2, suggested_duration_minutes=90, estimated_cost_fen=0, source_url=f'https://www.amap.com/search?id=edit-{i}') for i in range(2)]
                await prepare_initial_candidates(session, tid, search=AsyncMock(return_value=places))
                candidates = await get_candidates(session, tid)
                days = await get_day_plans(session, tid)
                base = CandidatePlanSnapshot(activities=[CandidateActivity(candidate_id=f'original-{i}',day_date=day.date,place_candidate_id=candidates[i].id,planned_start_time='09:00',duration_minutes=90,estimated_cost_fen=0,transport_mode_to_here='walk',source_ids=[candidates[i].source.id]) for i,day in enumerate(days)])
                source = await create_planning_run(session,tid,PlanningRunCreate(run_type='initial_plan',user_request='帮我规划行程，历史、美食，步行适量'))
                revision = await save_plan_revision(session,source.id,before_snapshot={},proposed_snapshot=base,reason='test',difference_summary={},validation_result={'valid':True,'errors':[],'warnings':[]},source_ids=[],enrich_routes=False)
                source.status='awaiting_confirmation';await session.commit()
                run = await create_planning_run(session,tid,PlanningRunCreate(run_type='initial_plan',user_request='请调整第二天的行程，节奏轻松一点'))
                await bind_initial_candidate(session,source.id,run);await session.commit()
                loaded = await load_initial_candidate(session,run)
                assert loaded == base
                context=(await build_planning_context(session,tid)).model_dump(mode='json')
                assert all(not d['activities'] for d in context['days'])
                context['candidate_edit_base']=loaded.model_dump(mode='json')
                state={'planning_context':context,'intent_resolution':run.intent_resolution,'run_type':'initial_plan','user_request':run.user_request}
                prompt,allowed,dates=build_planner_input(state,max_candidates=30)
                assert dates == {date(2026,11,2)}
                assert base.activities[0].place_candidate_id not in allowed
                assert prompt['unaccepted_candidate_context']['status']=='draft_only_not_formal'
                changed = base.activities[1].model_copy(update={'duration_minutes':60})
                revised = preserve_out_of_scope_activities(CandidatePlanSnapshot(activities=[changed]),state)
                assert base.activities[0] in revised.activities
                resolution=PlanningIntentResolution.model_validate(run.intent_resolution)
                result=await validate_candidate_plan(session,tid,revised,intent_resolution=resolution,candidate_edit_base=loaded)
                assert result.valid, result
                omitted=await validate_candidate_plan(session,tid,CandidatePlanSnapshot(activities=[changed]),intent_resolution=resolution,candidate_edit_base=loaded)
                assert 'candidate_edit_scope_changed' in [e.code for e in omitted.errors]
                altered=base.activities[0].model_copy(update={'duration_minutes':30})
                bad=await validate_candidate_plan(session,tid,CandidatePlanSnapshot(activities=[changed,altered]),intent_resolution=resolution,candidate_edit_base=loaded)
                assert not bad.valid
                assert 'intent_scope_new_activity_outside_target' in [e.code for e in bad.errors]
                source.status='rejected';await session.commit()
                with pytest.raises(ValueError,match='candidate_edit_base_unavailable'):
                    await load_initial_candidate(session,run)
                assert all(not d.activities for d in await get_day_plans(session,tid))
                source.status='awaiting_confirmation';await session.commit()
                revision.proposed_snapshot={**revision.proposed_snapshot,'activities':[]};await session.commit()
                with pytest.raises(ValueError,match='candidate_edit_base_unavailable'):
                    await load_initial_candidate(session,run)
                revision.proposed_snapshot=base.model_dump(mode='json');await session.commit()
                final=await save_plan_revision(session,run.id,before_snapshot=context,proposed_snapshot=revised,reason='edit',difference_summary={},validation_result={'valid':True,'errors':[],'warnings':[]},source_ids=[],enrich_routes=False)
                run.status='awaiting_confirmation';await session.commit()
                assert all(not d.activities for d in await get_day_plans(session,tid))
                await accept_plan_revision(session,final.id)
                formal=await get_day_plans(session,tid)
                assert [len(d.activities) for d in formal]==[1,1]
        asyncio.run(scenario())
