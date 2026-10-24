from app.assistant_capabilities import CapabilityDecision
from app.assistant_operation import approved_draft
from test_formal_write_protection import sample


def test_supported_duration_edit_reuses_existing_rules_after_model_unsupported():
    text = '请把第一天人民公园的停留改为60分钟，其他活动与午餐保持不变。先给修改候选，等我明确采用再保存。'
    decision = CapabilityDecision(intent='modify', reason_code='explicit_write', authorization_quote=text,
        planning_draft={'primary_intent':'unsupported', 'operations':[{'operation':'unsupported','raw_text':text}],
            'confidence':.5, 'parser':'model', 'parser_version':'v1'})
    draft = approved_draft(decision, text)
    assert draft.primary_intent == 'replan_trip'
    assert draft.operations[0].activity_mentions
    assert not draft.operations[0].place_mentions


def test_redundant_malformed_saved_wrapper_is_repairable_only_without_new_semantics():
    from app.assistant_capabilities import _repairable_saved_wrapper
    text = '把人民公园改为60分钟，午餐不变'
    raw = dict(intent='modify', reason_code='explicit_write', authorization_quote=text,
        planning_draft={'primary_intent':'replan_trip','operations':[{'operation':'replan_trip',
            'raw_text':text,'activity_mentions':['人民公园']}],'confidence':.9,'parser':'model','parser_version':'v1'},
        candidate_command={'action':'modify','patches':[{'item_ref':'人民公园',
            'duration_minutes':60,'source_quote':'把人民公园改为60分钟'}],'source_refs':[]})
    assert not _repairable_saved_wrapper(raw, {'id':'saved'})
    empty = {**raw, 'candidate_command':{'action':'modify','plan':None,'patches':[],'source_refs':[]}}
    assert _repairable_saved_wrapper(empty, {'id':'saved'})
    raw['candidate_command']['patches'][0]['duration_minutes'] = 90
    assert not _repairable_saved_wrapper(raw, {'id':'saved'})


def test_wrapper_cannot_drop_contradictory_quote_or_borrow_peer_operation():
    from app.assistant_capabilities import _repairable_saved_wrapper
    raw = dict(intent='modify', reason_code='explicit_write', planning_draft={
        'primary_intent':'replan_trip','operations':[{'operation':'replan_trip',
        'raw_text':'甲园60分钟','activity_mentions':['甲园']}, {'operation':'replan_trip',
        'raw_text':'乙馆90分钟','activity_mentions':['乙馆']}], 'confidence':.9,'parser':'model','parser_version':'v1'},
        candidate_command={'action':'modify','source_quote':'不要修改'})
    assert not _repairable_saved_wrapper(raw, {'id':'saved'})
    raw['candidate_command'] = {'action':'modify','patches':[{'item_ref':'甲园','source_quote':'乙馆90分钟','duration_minutes':90}]}
    assert not _repairable_saved_wrapper(raw, {'id':'saved'})
    raw['candidate_command']['patches'] = None
    assert not _repairable_saved_wrapper(raw, {'id':'saved'})


def test_accept_only_target_changes_unchanged_peer_row_is_identical(sample):
    import asyncio
    from sqlalchemy import select
    from app.database import Activity, PlanRevision
    from app.plan_revision_service import accept_plan_revision
    from test_formal_write_protection import pending_revision
    async def run():
        rid = await pending_revision(sample)
        async with sample.sessions() as db:
            before = [dict(row) for row in (await db.execute(select(Activity.__table__).where(
                Activity.id.in_([a.id for a in sample.activities])).order_by(Activity.position))).mappings()]
            revision = await db.get(PlanRevision, rid)
            snapshot = dict(revision.proposed_snapshot)
            snapshot['activities'] = [dict(a) for a in snapshot['activities']]
            snapshot['activities'][0]['duration_minutes'] = 20
            revision.proposed_snapshot = snapshot
            await db.commit()
            await accept_plan_revision(db, rid)
            after = [dict(row) for row in (await db.execute(select(Activity.__table__).where(
                Activity.id.in_([a.id for a in sample.activities])).order_by(Activity.position))).mappings()]
            assert after[1] == before[1]
            assert after[0]['duration_minutes'] == 20 and after[0]['version'] == before[0]['version'] + 1
    asyncio.run(run())
