import asyncio
from copy import deepcopy
from uuid import uuid4

from app.database import PlanRevision, PlanningRun, AssistantSession, TripPreferences
from app.planning_context import build_planning_context
from app.planning_intent_service import resolve_planning_intent
from app.planning_goals import extract_planning_goals, check_goal_satisfaction
from app.schemas import CandidatePlanSnapshot, PlanningIntentParseRequest, SemanticIntentDraft, SemanticIntentOperation
from app.plan_revision_service import accept_plan_revision, InvalidPlanRevisionError
from test_formal_write_protection import sample, pending_revision, current
from sqlalchemy import select


async def prepared(sample, db):
    message='第一天第一项活动增加15分钟'
    draft=SemanticIntentDraft(primary_intent='replan_trip',operations=[SemanticIntentOperation(
        operation='replan_trip',raw_text=message,activity_mentions=['第一天第一项活动'])],confidence=1,parser='hybrid',parser_version='approved-operation-v2')
    resolution=await resolve_planning_intent(db,sample.trip_id,PlanningIntentParseRequest(message=message),prepared_draft=draft)
    assert resolution.policy_decision.route=='plan_preview'
    assert resolution.request.intent.requested_place_queries==[]
    context=(await build_planning_context(db,sample.trip_id)).model_dump(mode='json')
    return resolution, context


def test_existing_goal_checker_rejects_wrong_delta_peer_change_and_stale_baseline(sample):
    async def run():
        rid=await pending_revision(sample)
        async with sample.sessions() as db:
            resolution,context=await prepared(sample,db)
            revision=await db.get(PlanRevision,rid)
            data=deepcopy(revision.proposed_snapshot);data['activities'][0]['duration_minutes']=45
            goals=extract_planning_goals(user_request=resolution.request.user_request,intent_resolution=resolution.model_dump(mode='json'),context=context)
            def result(data,ctx=context):
                checks=check_goal_satisfaction(goals=goals,before_context=ctx,snapshot=CandidatePlanSnapshot.model_validate(data))
                return next(item for item in checks.results if item.goal=='saved_duration_changes')
            assert result(data).status=='satisfied'
            wrong=deepcopy(data);wrong['activities'][0]['duration_minutes']=15
            assert result(wrong).status=='unsatisfied'
            peer=deepcopy(data);peer['activities'][1]['duration_minutes']=45
            assert result(peer).status=='unsatisfied'
            route=deepcopy(data);route['route_legs'][0]['mode']='driving'
            assert result(route).status=='unsatisfied'
            # A duration edit on day one cannot alter another day's transport.
            cross_context=deepcopy(context)
            day_two=deepcopy(context['days'][0]);day_two['date']=sample.days[1].date.isoformat()
            ids={str(item['id']):str(uuid4()) for item in day_two['activities']}
            for item in day_two['activities']:
                item['id']=ids[str(item['id'])]
            day_two['route_mode']='walk';day_two['route_legs']=[]
            cross_context['days'].append(day_two)
            cross=deepcopy(data)
            for item in data['activities']:
                copied=deepcopy(item);copied['day_date']=day_two['date']
                copied['replaces_activity_id']=ids[str(item['replaces_activity_id'])]
                copied['candidate_id']='activity:'+copied['replaces_activity_id']
                copied['duration_minutes']=30;copied['transport_mode_to_here']='driving'
                cross['activities'].append(copied)
            leg=deepcopy(data['route_legs'][0]);leg['day_date']=day_two['date']
            leg['from_activity_ref']='activity:'+ids[leg['from_activity_ref'].removeprefix('activity:')]
            leg['to_activity_ref']='activity:'+ids[leg['to_activity_ref'].removeprefix('activity:')]
            leg['mode']='driving';cross['route_legs'].append(leg)
            assert result(cross,cross_context).status=='unsatisfied'
            cross['route_legs'][-1]['mode']='walk'
            for item in cross['activities'][2:]:
                item['transport_mode_to_here']='walk'
            assert result(cross,cross_context).status=='satisfied'
            stale=deepcopy(context);stale['days'][0]['activities'][0]['version']+=1
            assert result(data,stale).status=='unsatisfied'
    asyncio.run(run())


def test_original_accept_chain_refuses_wrong_delta_without_formal_mutation(sample):
    async def run():
        rid=await pending_revision(sample)
        async with sample.sessions() as db:
            resolution,context=await prepared(sample,db)
            revision=await db.get(PlanRevision,rid)
            run=await db.get(PlanningRun,revision.planning_run_id)
            run.intent_resolution=resolution.model_dump(mode='json');run.user_request=resolution.request.user_request
            revision.before_snapshot=context
            data=deepcopy(revision.proposed_snapshot);data['activities'][0]['duration_minutes']=15
            revision.proposed_snapshot=data
            await db.commit()
        before=await current(sample)
        async with sample.sessions() as db:
            try:
                await accept_plan_revision(db,rid)
            except InvalidPlanRevisionError as error:
                assert 'saved_duration_change_mismatch' in str(error.result)
            else:
                raise AssertionError('Wrong delta was adopted')
            await db.rollback()
        assert await current(sample)==before
    asyncio.run(run())


def test_original_accept_applies_only_the_approved_duration_and_duplicate_is_idempotent(sample):
    async def run():
        rid=await pending_revision(sample)
        async with sample.sessions() as db:
            resolution,context=await prepared(sample,db)
            revision=await db.get(PlanRevision,rid)
            run=await db.get(PlanningRun,revision.planning_run_id)
            run.intent_resolution=resolution.model_dump(mode='json');run.user_request=resolution.request.user_request
            revision.before_snapshot=context
            data=deepcopy(revision.proposed_snapshot);data['activities'][0]['duration_minutes']=45
            revision.proposed_snapshot=data
            await db.commit()
        before=await current(sample)
        async with sample.sessions() as db:
            await accept_plan_revision(db,rid)
        after=await current(sample)
        changed=[(a,b) for a,b in zip(before['activities'],after['activities']) if a!=b]
        assert len(changed)==1 and changed[0][1]['id']==str(sample.activities[0].id)
        assert changed[0][0]['duration']==30 and changed[0][1]['duration']==45
        async with sample.sessions() as db:
            await accept_plan_revision(db,rid)
        assert await current(sample)==after
    asyncio.run(run())


def test_read_only_chat_does_not_clean_up_historical_requirement_records(sample):
    from app.assistant_service import send_message
    from app.assistant_capabilities import CapabilityDecision
    from app.requirements import EffectiveRequirement
    async def run():
        async with sample.sessions() as db:
            record=EffectiveRequirement(id='historical-preservation',text='其他活动、个人偏好保持原样',scope={'kind':'trip','trip_id':str(sample.trip_id)},
                source={'kind':'user_explicit','ref':'historical-record'},strength='soft').model_dump(mode='json')
            pref=await db.scalar(select(TripPreferences).where(TripPreferences.trip_id==sample.trip_id))
            pref.requirement_records=[record]
            conversation=AssistantSession(trip_id=sample.trip_id,messages=[],applied_actions={})
            db.add(conversation);await db.commit()
            await db.refresh(pref)
            sid=conversation.id
            before=pref.version,deepcopy(pref.requirement_records),pref.updated_at
        async def selector(*args):
            return CapabilityDecision(intent='itinerary',capabilities=['itinerary'],itinerary_purpose='saved_values',reason_code='current_information')
        async with sample.sessions() as db:
            await send_message(db,sid,'第一天保存的活动是什么？',uuid4(),context={'surface':'trip','read_trip_id':str(sample.trip_id)},capability_selector=selector)
        async with sample.sessions() as db:
            pref=await db.scalar(select(TripPreferences).where(TripPreferences.trip_id==sample.trip_id))
            assert (pref.version,pref.requirement_records,pref.updated_at)==before
    asyncio.run(run())
