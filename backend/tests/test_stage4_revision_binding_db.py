import asyncio

import pytest

from app.database import PlanRevision
from app.plan_revision_service import accept_plan_revision
from app.revision_presentation import revision_presentation_hash
from test_formal_write_protection import sample, pending_revision, current


def test_locked_accept_rejects_changed_content_and_does_not_write(sample):
    async def run():
        rid=await pending_revision(sample)
        before=await current(sample)
        async with sample.sessions() as db:
            revision=await db.get(PlanRevision,rid)
            shown=revision_presentation_hash(revision)
            revision.reason='显示后发生变化'
            await db.commit()
            with pytest.raises(ValueError,match='内容已经变化'):
                await accept_plan_revision(db,rid,expected_presentation_hash=shown)
            await db.rollback()
        assert await current(sample)==before
    asyncio.run(run())


def test_api_and_locked_revision_hash_are_identical(sample):
    async def run():
        from app.schemas import PlanRevisionResponse
        rid=await pending_revision(sample)
        async with sample.sessions() as db:
            revision=await db.get(PlanRevision,rid)
            view=PlanRevisionResponse.model_validate(revision)
            assert view.presentation_hash==revision_presentation_hash(revision)
            await accept_plan_revision(db,rid,expected_presentation_hash=view.presentation_hash)
            assert (await db.get(PlanRevision,rid)).status=='accepted'
    asyncio.run(run())


def test_displayed_revision_read_uses_same_snapshot_and_refuses_a_wrong_hash(sample):
    async def run():
        from app.planning_context import build_planning_context
        from app.saved_trip_reads import load_saved_trip_read,render_displayed_revision
        rid=await pending_revision(sample)
        async with sample.sessions() as db:
            revision=await db.get(PlanRevision,rid)
            revision.before_snapshot=(await build_planning_context(db,sample.trip_id)).model_dump(mode='json')
            snapshot=dict(revision.proposed_snapshot);snapshot['activities']=[dict(a) for a in snapshot['activities']]
            snapshot['activities'][0]['duration_minutes']=20
            revision.proposed_snapshot=snapshot
            await db.commit()
            ref={'id':rid,'run_id':revision.planning_run_id,'hash':revision_presentation_hash(revision)}
            before=await current(sample)
            read=await load_saved_trip_read(db,sample.trip_id,revision_ref=ref)
            assert read.displayed_revision and '30分钟 →' in render_displayed_revision(read)
            assert '20分钟' in render_displayed_revision(read)
            assert not (await load_saved_trip_read(db,sample.trip_id,revision_ref={**ref,'hash':'0'*64})).displayed_revision
            assert not (await load_saved_trip_read(db,sample.trip_id)).displayed_revision
            assert await current(sample)==before
    asyncio.run(run())


def test_content_changed_while_accept_waits_for_revision_lock_is_rejected(sample):
    from sqlalchemy import select
    from test_formal_write_protection import wait_for_blocked
    async def run():
        rid=await pending_revision(sample);before=await current(sample)
        async with sample.sessions() as guard:
            revision=await guard.scalar(select(PlanRevision).where(PlanRevision.id==rid).with_for_update())
            shown=revision_presentation_hash(revision)
            async def adopt():
                async with sample.sessions() as db:
                    with pytest.raises(ValueError,match='内容已经变化'):
                        await accept_plan_revision(db,rid,expected_presentation_hash=shown)
                    await db.rollback()
            task=asyncio.create_task(adopt())
            await wait_for_blocked(sample)
            revision.reason='锁等待期间修改了候选内容'
            await guard.commit()
            await asyncio.wait_for(task,8)
        assert await current(sample)==before
    asyncio.run(run())
