"""Content binding for an existing Revision; neither authority nor a new writer."""
import hashlib
import json


def revision_presentation_hash(revision):
    from app.schemas import CandidatePlanSnapshot
    snapshot = CandidatePlanSnapshot.model_validate(revision.proposed_snapshot).model_dump(mode='json')
    validation = revision.validation_result or {}
    value = {'version':'revision-presentation-v1', 'id':str(revision.id),
        'planning_run_id':str(revision.planning_run_id), 'trip_id':str(revision.trip_id),
        'reason':revision.reason, 'before_snapshot':revision.before_snapshot,
        'proposed_snapshot':snapshot, 'difference_summary':revision.difference_summary,
        'validation':{key:validation.get(key) for key in ('valid','errors','warnings')}}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),default=str).encode()).hexdigest()


def bound_adoption_context(context, message):
    """A passive displayed reference becomes an action only on this command."""
    target=context.action_target
    if not target or not target.revision_id or not target.revision_hash:
        return context
    if not explicit_revision_adoption(message):
        return context
    return context.model_copy(update={'action_target':target.model_copy(update={'operation':'accept_plan'})})


def explicit_revision_adoption(message):
    from app.conversation_candidate.commands import CandidateCommand,validate_command
    if message.strip().rstrip('。！! ') in {'就按这份来','就这样安排','采用这份方案','确认采用'}:
        return True
    try:
        validate_command(CandidateCommand(action='adopt',source_quote=message.strip()),message)
        return True
    except ValueError:
        return False


def revision_review(revision):
    """All activity additions/removals/changes from the bound before snapshot."""
    from app.schemas import CandidatePlanSnapshot
    before=revision.before_snapshot or {}
    proposed=CandidatePlanSnapshot.model_validate(revision.proposed_snapshot).model_dump(mode='json')
    from app.revision_delta import protected_activity_ids
    execution=before.get('execution_recovery') or {}
    source_items=[item for day in before.get('days',[]) for item in day.get('activities',[])]
    protected=protected_activity_ids(source_items,execution.get('frozen_activity_ids',[]),execution.get('protected_activity_ids',[]))
    old={}
    for day in before.get('days',[]):
        for item in day.get('activities',[]):
            old[str(item['id'])]={'activity_id':str(item['id']), 'place_id':str(item['place_id']),
                'name':item.get('display_name') or item.get('name'),'date':day['date'],
                'time':str(item['scheduled_time'])[:5], 'duration_minutes':item['duration_minutes'],
                'estimated_cost_fen':item.get('estimated_cost_fen'),'locked':item.get('schedule_locked',False)}
    places={str(p['id']):p for p in before.get('candidates',[])}
    complete=(isinstance(before.get('trip'),dict) and isinstance(before.get('days'),list)
        and isinstance(execution.get('frozen_activity_ids'),list) and isinstance(execution.get('protected_activity_ids'),list)
        and all('status' in item and 'schedule_locked' in item for item in source_items))
    changes=[];retained=set()
    for item in proposed['activities']:
        key=str(item.get('replaces_activity_id') or '')
        prior=old.get(key)
        if prior:
            retained.add(key)
        place=places.get(str(item['place_candidate_id']),{})
        name=place.get('name') or (prior['name'] if prior and prior['place_id']==str(item['place_candidate_id']) else None)
        if not name:
            complete=False
        after={'activity_id':key or None,'place_id':str(item['place_candidate_id']), 'name':name,
            'date':item['day_date'],'time':str(item['planned_start_time'])[:5],
            'duration_minutes':item['duration_minutes'],'estimated_cost_fen':item['estimated_cost_fen'],'locked':item['locked']}
        if prior and key in protected:
            after=dict(prior)
        if prior is None or any(prior[k]!=after[k] for k in ('place_id','date','time','duration_minutes','estimated_cost_fen','locked')):
            changes.append({'kind':'add' if prior is None else 'change','before':prior,'after':after})
    changes.extend({'kind':'remove','before':value,'after':None} for key,value in old.items() if key not in retained and key not in protected)
    return {'complete':complete,'base_trip_version':before.get('trip',{}).get('version'),
        'changes':changes,'routes':proposed['route_legs'],
        'preserved':[value for key,value in old.items() if key in protected and key not in retained],
        'warnings':(revision.validation_result or {}).get('warnings',[])}
