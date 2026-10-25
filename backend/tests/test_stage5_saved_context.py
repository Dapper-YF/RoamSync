"""Observed pending-review context loss, independent of selector labels."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4
import pytest

from app.companion_context import CompanionContextReader
from app.companion_contracts import CompanionContext, InformationNeed
from app.database import PlanRevision
from app.schemas import TravelGoalRouting
from app.saved_trip_reads import load_saved_trip_read
from app.revision_presentation import revision_presentation_hash
from test_formal_write_protection import sample, pending_revision, current


def test_general_consultation_sees_only_the_exact_valid_displayed_revision(sample):
    async def run():
        from app.planning_context import build_planning_context
        rid=await pending_revision(sample)
        async with sample.sessions() as db:
            revision=await db.get(PlanRevision,rid)
            revision.before_snapshot=(await build_planning_context(db,sample.trip_id)).model_dump(mode='json')
            proposal=dict(revision.proposed_snapshot)
            proposal['activities']=[dict(item) for item in proposal['activities']]
            proposal['activities'][0]['duration_minutes']=20
            revision.proposed_snapshot=proposal
            await db.commit()
            ref={'id':rid,'run_id':revision.planning_run_id,'hash':revision_presentation_hash(revision)}
            before=await current(sample)
            question='当前修改候选具体改了哪项、原来多久、建议多久？先不采用。'
            context=CompanionContext(current_message=question,displayed_revision={'id':'unverified'},travel_goal=TravelGoalRouting(
                goal_type='travel_chat',target_runtime='companion',mutation_requested=False,
                knowledge_required=False,trip_context_required=False,live_fact_likely_required=False,confidence=.9))
            need=InformationNeed(general_knowledge_allowed=True)
            snapshot=await load_saved_trip_read(db,sample.trip_id,question,revision_ref=ref)
            value=await CompanionContextReader(db,sample.trip_id,read_snapshot=snapshot).load(context,need)
            assert value.displayed_revision['id']==str(rid)
            assert value.displayed_revision['presentation_hash']==ref['hash']
            changes=value.displayed_revision['review']['changes']
            assert changes[0]['before']['duration_minutes']==30 and changes[0]['after']['duration_minutes']==20
            assert not value.formal_itinerary_summary  # no unrelated whole itinerary
            value.displayed_revision['review']['changes'].clear()
            assert snapshot.displayed_revision['review']['changes']  # detached projection
            for invalid in [None,{**ref,'hash':'0'*64}]:
                snapshot=await load_saved_trip_read(db,sample.trip_id,question,revision_ref=invalid)
                result=await CompanionContextReader(db,sample.trip_id,read_snapshot=snapshot).load(context,need)
                assert result.displayed_revision is None
            assert await current(sample)==before
    asyncio.run(run())


@pytest.mark.parametrize('delivered',[False,True])
def test_revision_receipt_distinguishes_capture_from_delivery(monkeypatch,delivered):
    from app.assistant_capabilities import CapabilityDecision, _answer_leaf
    from app.assistant_context import ContextEnvelope
    from app.companion_contracts import CompanionResult
    from app.config import Settings
    snapshot=SimpleNamespace(displayed_revision={'id':str(uuid4()),'presentation_hash':'a'*64,'trip_version':2})
    async def load(_reader,context,need):
        return context.model_copy(update={'displayed_revision':snapshot.displayed_revision})
    monkeypatch.setattr(CompanionContextReader,'load',load)
    class Runtime:
        def __init__(self,reader,**kwargs):self.reader=reader
        async def run(self,**kwargs):
            if delivered:
                await self.reader.load(CompanionContext(current_message=kwargs['message'],travel_goal=kwargs['goal']),InformationNeed())
            return CompanionResult(response_text='本轮仅讨论，不采用。',goal_type='travel_chat',information_need=InformationNeed())
    monkeypatch.setattr('app.companion_runtime.CompanionRuntime',Runtime)
    class DB:
        async def commit(self):pass
    goal=TravelGoalRouting(goal_type='travel_chat',target_runtime='companion',mutation_requested=False,
        knowledge_required=False,trip_context_required=False,live_fact_likely_required=False,confidence=.9)
    bundle,_=asyncio.run(_answer_leaf(Settings(_env_file=None),CapabilityDecision(intent='direct',reason_code='stable_knowledge'),
        '先讨论，不采用',[],ContextEnvelope(),None,DB(),uuid4(),uuid4(),uuid4(),goal,read_snapshot=snapshot,referents=[]))
    receipt=bundle['read_tools']['revision_read']
    assert receipt['status']=='context_available'
    assert receipt['delivered_to_answer_context'] is delivered
    assert receipt['semantics']=='captured_context_not_answer_completion_or_adoption'
