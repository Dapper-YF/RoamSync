import asyncio
from datetime import time
from sqlalchemy import select
from app.database import TripPreferences
from app.plan_revision_service import validate_candidate_plan, accept_plan_revision, InvalidPlanRevisionError
from app.schemas import CandidateActivity, CandidatePlanSnapshot, IntentConstraints, PlanningIntentResolution
from test_formal_write_protection import sample, pending_revision, current
import pytest


def test_final_validator_rejects_walk_limit_from_current_intent(sample):
    async def scenario():
        async with sample.sessions() as db:
            rid=await pending_revision(sample)
            from app.database import PlanRevision
            revision=await db.get(PlanRevision,rid)
            snapshot=CandidatePlanSnapshot.model_validate(revision.proposed_snapshot)
            resolution=PlanningIntentResolution.model_validate({'request':{'trip_id':str(sample.trip_id),'user_request':'步行最多5分钟','intent':{'intent_type':'replan_trip','source_text':'步行最多5分钟'}},'requires_clarification':False,'grounded_intent':{'trip_id':str(sample.trip_id),'primary_intent':'replan_trip','operation_types':['replan_trip'],'target_day_ids':[str(sample.days[0].id)],'constraints':{'max_walking_minutes':5}}})
            result=await validate_candidate_plan(db,sample.trip_id,snapshot,intent_resolution=resolution)
            assert any(e.code=='walking_limit_exceeded' for e in result.errors)
    asyncio.run(scenario())


@pytest.mark.parametrize('limit,accepted',[(5,False),(15,True)])
def test_accept_revalidates_grounded_walking_limit_and_rolls_back(sample,limit,accepted):
    async def scenario():
        from app.database import PlanRevision, PlanningRun
        rid=await pending_revision(sample)
        before=await current(sample)
        async with sample.sessions() as db:
            revision=await db.get(PlanRevision,rid)
            run=await db.get(PlanningRun,revision.planning_run_id)
            run.intent_resolution={'request':{'trip_id':str(sample.trip_id),'user_request':f'步行最多{limit}分钟','intent':{'intent_type':'replan_trip','source_text':f'步行最多{limit}分钟'}},'requires_clarification':False,'grounded_intent':{'trip_id':str(sample.trip_id),'primary_intent':'replan_trip','operation_types':['replan_trip'],'target_day_ids':[str(sample.days[0].id)],'constraints':{'max_walking_minutes':limit}}}
            await db.commit()
        async with sample.sessions() as db:
            if accepted:
                result=await accept_plan_revision(db,rid)
                assert result.status=='accepted'
                again=await accept_plan_revision(db,rid)
                assert again.id==rid
            else:
                with pytest.raises(InvalidPlanRevisionError) as error:
                    await accept_plan_revision(db,rid)
                assert any(e.code=='walking_limit_exceeded' for e in error.value.result.errors)
                await db.rollback()
        after=await current(sample)
        if not accepted: assert after==before
    asyncio.run(scenario())


def test_missing_or_estimated_routes_are_unknown_not_zero():
    from test_planning_goals import _snapshot,_context
    from app.planning_goals import check_goal_satisfaction
    from app.schemas import PlanningGoals
    context=_context()
    goals=PlanningGoals.model_validate({'target_days':['2026-10-20'],'hard_goals':{'max_walking_minutes':20}})
    snapshot=_snapshot(end=time(17),walking_minutes=10)
    for legs in ([],[snapshot.route_legs[0].model_copy(update={'is_estimated':True})],
                 [snapshot.route_legs[0].model_copy(update={'mode':'transit'})]):
        result=check_goal_satisfaction(goals=goals,before_context=context,snapshot=snapshot.model_copy(update={'route_legs':legs}))
        assert result.results[0].status=='not_evaluable'
        assert result.results[0].evidence['walking_scope']=='inter_activity_travel_only'


def test_validated_semantic_edit_reuses_existing_preview_when_legacy_verb_unknown(sample):
    from uuid import uuid4
    from app.assistant_service import send_message, ToolDecision
    from app.assistant_capabilities import CapabilityDecision
    from app.database import AssistantSession, Trip, PlanningRun
    async def run():
        before = await current(sample)
        async with sample.sessions() as db:
            trip = await db.get(Trip, sample.trip_id)
            row = AssistantSession(trip_id=trip.id, messages=[], applied_actions={})
            db.add(row); await db.commit()
            mid = uuid4()
            async def selector(*args):
                return CapabilityDecision(intent="modify", authorization_quote="请协调第一天的安排", reason_code="explicit_write")
            class Router:
                async def decide(self, context):
                    return ToolDecision(tool="plan_trip", reply="准备候选", planning_request="请调整整个旅行")
            text = "请协调第一天的安排：测试地点0需要12:30以后才能开始，其他日期保持不变。先给候选，等我确认再保存。"
            result = await send_message(db, row.id, text, mid, router=Router(), capability_selector=selector,
                context={"topic_id":"quality-edit", "surface":"trip", "read_trip_id":str(trip.id), "prefer_flexible":True,
                    "action_target":{"trip_id":str(trip.id), "expected_version":trip.version, "operation":"plan_trip", "authorization_message_id":str(mid)}})
            assert result.latest_run_id
            preview = await db.get(PlanningRun, result.latest_run_id)
            assert preview.user_request == text  # never the model's expanded scope
            assert preview.intent_resolution["policy_decision"]["route"] == "plan_preview"
            assert preview.intent_resolution["semantic_draft"]["parser_version"] == "current-turn-v1"
            from app.planning_intent_service import restore_current_turn_modification, resolve_planning_intent
            from app.schemas import PlanningIntentParseRequest
            hint = restore_current_turn_modification(preview, trip.id, text, trip.version)
            assert hint is not None
            repeated = await resolve_planning_intent(db, trip.id, PlanningIntentParseRequest(message=text), semantic_provider=hint)
            assert repeated.policy_decision.route == "plan_preview"
            assert restore_current_turn_modification(preview, trip.id, text, trip.version+1) is None
            assert restore_current_turn_modification(preview, trip.id, "假如"+text, trip.version) is None
            assert restore_current_turn_modification(preview, uuid4(), text, trip.version) is None
        assert await current(sample) == before
    asyncio.run(run())
