"""Exact expected JSON for narrowly identifiable representation errors.

Returns a repair specification, never executes or accepts its synthesized JSON.
The provider must explicitly return that exact representation once; all normal
schema/source/identity/business validation then runs again.
"""
from copy import deepcopy


def representation_repair(raw, errors, message, envelope, history=()):
    result=_representation_repair(raw,errors,message,envelope,history)
    if result:
        return result
    if not (isinstance(raw,dict) and raw.get('intent')=='create'
        and isinstance(raw.get('candidate_command'),dict) and raw['candidate_command'].get('action')=='generate'
        and not any(raw.get(k) for k in ('memory_updates','saved_intentions','planning_draft','creation'))
        and errors and all(e['type']=='extra_forbidden' and len(e['loc'])==2
            and e['loc'][0]=='candidate_command' and e['loc'][1] in {'start_time','end_time'} for e in errors)
        and {e['loc'][1] for e in errors}=={'start_time','end_time'}):
        return None
    # Known misplaced clocks must exactly duplicate literal daily bounds.
    # Other nonempty unknown fields and different values remain illegal.
    expected=deepcopy(raw)
    command=expected['candidate_command']
    try:
        from datetime import time
        from app.conversation_candidate.schedule_evidence import daily_window_source
        constraints=command['plan']['schedule_constraints']
        start,end=(time.fromisoformat(command[key]) for key in ('start_time','end_time'))
        if (start!=time.fromisoformat(constraints['daily_start_time']) or end!=time.fromisoformat(constraints['daily_end_time'])
            or not daily_window_source(message,start,end,history)):
            return None
        command.pop('start_time');command.pop('end_time')
        from app.assistant_capabilities import CapabilityDecision
        from pydantic import ValidationError
        try:
            CapabilityDecision.model_validate(expected)
        except ValidationError as error:
            details=error.errors(include_input=False,include_context=False,include_url=False)
            if any(tuple(e['loc'])!=('candidate_command','plan') or 'days must be consecutive' not in e.get('msg','') for e in details):
                return None
            subsequent=_representation_repair(expected,details,message,envelope,history)
            if not subsequent:
                return None
            expected=subsequent[0]
    except (KeyError,TypeError,ValueError):
        return None
    return expected,'redundant_candidate_clock_representation',(
        'Remove only candidate_command.start_time/end_time, which exactly duplicate the literal '
        'plan.schedule_constraints daily bounds. Copy required_representation exactly, including '
        'any independently verified empty duplicate day removal. Preserve every real constraint, '
        'quantity, item, source, identity and authority value.')


def _representation_repair(raw, errors, message, envelope, history=()):
    if not isinstance(raw,dict) or not errors:
        return None
    if (raw.get('intent') in {'direct','lookup','facts','route','itinerary'}
        and not any(raw.get(k) for k in ('candidate_command','planning_draft','creation','saved_intentions','authorization_quote'))
        and all(e['type']=='string_type' and len(e['loc'])==3 and e['loc'][0]=='memory_updates'
            and e['loc'][2]=='value' for e in errors)):
        expected=deepcopy(raw)
        for e in errors:
            update=expected['memory_updates'][e['loc'][1]]
            value=update.get('value')
            if type(value) is not int or update.get('field') not in {'party_size','duration_days'}:
                return None
            update['value']=str(value)
        return expected,'memory_scalar_representation',(
            'Only stringify the integer memory_updates value at each validation error. '
            'Preserve its exact number, subject, operation, source, scope and all other fields. '
            'The server will independently validate the literal quantity before applying anything.')
    if (raw.get('intent')=='read_tasks' and raw.get('read_tasks')
        and not any(raw.get(k) for k in ('candidate_command','planning_draft','creation','saved_intentions','authorization_quote'))
        and all(e['type']=='literal_error' and tuple(e['loc'])==('intent',) for e in errors)):
        expected=deepcopy(raw)
        expected['intent']='lookup'
        return expected,'read_container_namespace',(
            'Only change intent from the field name read_tasks to lookup, the read-only container. '
            'Preserve every read task, source, argument and all other JSON values exactly.')
    if (raw.get('intent') in {'direct','itinerary'}
        and raw.get('itinerary_purpose') in {'conditions_only','conditions_recall'}
        and raw.get('response_purpose')==raw.get('itinerary_purpose')
        and not any(raw.get(k) for k in ('candidate_command','planning_draft','creation',
            'saved_intentions','authorization_quote','read_tasks'))
        and all(e['type']=='literal_error' and tuple(e['loc'])==('itinerary_purpose',) for e in errors)):
        expected=deepcopy(raw)
        expected['itinerary_purpose']='other'
        return expected,'condition_purpose_namespace',(
            'Only change itinerary_purpose to other. conditions_recall/conditions_only belongs '
            'to the already supplied response_purpose. Preserve all other JSON values exactly.')
    if (raw.get('intent')!='create' or not isinstance(raw.get('candidate_command'),dict)
        or raw['candidate_command'].get('action')!='generate'
        or any(raw.get(k) for k in ('memory_updates','saved_intentions','planning_draft','creation'))
        or any(e['type']!='value_error' or tuple(e['loc'][:2])!=('candidate_command','plan') for e in errors)):
        return None
    expected=deepcopy(raw)
    plan=expected['candidate_command'].get('plan')
    if not isinstance(plan,dict) or not isinstance(plan.get('days'),list):
        return None
    allowed_messages=('item interval must be positive and agree with duration_minutes',
        'days must be consecutive relative day_index values starting at 1')
    if any(not any(msg in e.get('msg','') for msg in allowed_messages) for e in errors):
        return None
    corrected=[]
    from app.drafts.timing import explicit_interval
    from app.conversation_candidate.sources import named_user_clauses
    from app.conversation_candidate.commands import literal_minutes
    from app.drafts.timing import quoted_clocks
    for e in errors:
        loc=e['loc']
        if len(loc)==6 and loc[2]=='days' and loc[4]=='items':
            try:
                item=plan['days'][loc[3]]['items'][loc[5]]
                quote=item.get('source_quote','')
                start,end=item.get('start_time'),item.get('end_time')
                from datetime import time
                start=time.fromisoformat(start) if isinstance(start,str) else start
                end=time.fromisoformat(end) if isinstance(end,str) else end
                target_clauses=named_user_clauses(item.get('name',''),history,message)
                if (item.get('kind','visit')!='visit' or item.get('duration_source')!='planning_allocation'
                    or not start or not end or not isinstance(item.get('duration_minutes'),int)
                    or explicit_interval(quote,start,end) or explicit_interval(message,start,end)
                    or any(quoted_clocks(clause) or literal_minutes(clause) or '预约' in clause for clause in target_clauses)):
                    return None
                # Only redundant, unsupported model visit clocks are removed;
                # duration, requested windows and every other field stay exact.
                item.pop('start_time',None)
                item.pop('end_time',None)
                corrected.append(list(loc))
            except (ValueError,TypeError,KeyError,IndexError):
                return None
        elif tuple(loc)!=('candidate_command','plan'):
            return None
    from app.assistant_selection_contract import known_day_count
    count=known_day_count(message,envelope,history)
    days=[]
    seen=set()
    for day in plan['days']:
        if day.get('day_index') in seen:
            if day.get('items') or day.get('start_time') or day.get('end_time'):
                return None
            corrected.append(['empty_duplicate_day',day.get('day_index')])
        else:
            seen.add(day.get('day_index'))
            days.append(day)
    if len(days)!=len(plan['days']):
        if count!=len(days):
            return None
        plan['days']=days
    if not corrected or len(corrected)>4:
        return None
    try:
        from app.assistant_capabilities import CapabilityDecision
        CapabilityDecision.model_validate(expected)
    except ValueError:
        return None
    return expected,'candidate_representation',(
        'Remove only the inconsistent planning_allocation visit start_time/end_time identified '
        'in validation_errors; preserve its duration and literal source. Remove only empty '
        'duplicate day_index placeholders; the actual unique day count must match the user. '
        'Preserve every other field exactly, including authority, windows, items, quantities, '
        'source references, names, dates, budgets and transport. No new operation or permission.')
