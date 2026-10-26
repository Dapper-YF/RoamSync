"""Duration expressions and saved targets: source evidence, not write authority."""
import re
from decimal import Decimal

from app.saved_references import NUMBER, activity_reference, resolve_activity_position
from app.schemas import SavedDurationChange
from app.travel_language import chinese_number

_VERBS = r'增加|延长|多留|多待|再待|减少|缩短|少留|少待|改为|改成|调整为|设为|停留'
_DURATION = re.compile(r'('+_VERBS+r')\s*([一二三四五六七八九十两半\d.]+)\s*(?:个)?(分钟|小时)')
_PLACE_COUNT = re.compile(r'(?:增加|添加|再加|多加|加|多安排|减少|少安排)\s*[一二三四五六七八九十两\d.]+\s*(?:个)?(?:景点|景区)')


def _literal_name_matches(mention, alias):
    if mention == alias:
        return True
    if not alias or not mention.endswith(alias):
        return False
    prefix = mention[:-len(alias)]
    return bool(re.fullmatch(rf'(?:把|将)?(?:(?:第{NUMBER}天|首日|次日|今天|明天|20\d{{2}}-\d{{1,2}}-\d{{1,2}})(?:的)?)?(?:上午|下午|早上|晚上|中午)?的?',prefix))


def resolve_operation_targets(operation, entities, target_day, selected_activity_id, items=None):
    targets, unresolved = [], []
    for mention in operation.activity_mentions:
        ordinal = activity_reference(mention)
        if ordinal:
            scoped = [entity for entity in entities if target_day and entity.day_id == target_day.id]
            rows = [{'activity_id':str(entity.id), 'time':str(entity.scheduled_time),
                'position':getattr(entity,'position',0)} for entity in scoped]
            agenda = [item for item in (items or ()) if target_day and item['day_date'] == target_day.date.isoformat()]
            found, issue = resolve_activity_position(rows, agenda, ordinal, len(scoped))
            if not ordinal.explicit_activity and items is None:
                found, issue = [], 'agenda_not_captured'
            matches = [entity for entity in scoped if found and str(entity.id) == found[0]['activity_id']] if not issue else []
        elif mention in {'这个','这个活动','这个地方','它','该活动','那个景点','选中活动','选中的活动'}:
            matches = [entity for entity in entities if entity.id == selected_activity_id
                and (target_day is None or entity.day_id == target_day.id)]
        else:
            matches = [entity for entity in entities if any(_literal_name_matches(mention,alias) for alias in entity.aliases)
                and (target_day is None or entity.day_id == target_day.id)]
        if len(matches) != 1:
            unresolved.append(mention)
        elif matches[0].id not in {entity.id for entity in targets}:
            targets.append(matches[0])
    return targets, unresolved


def bind_duration_change(operation, index, targets, trip_version):
    matches = list(_DURATION.finditer(operation.raw_text))
    place_counts = list(_PLACE_COUNT.finditer(operation.raw_text))
    # A quantity of places is a planning count, not an incomplete minute edit.
    # A single operation mixing counts and durations still needs clarification.
    if matches and place_counts:
        return None, 'duration_expression_unsupported'
    if not matches:
        count_free_text = _PLACE_COUNT.sub('', operation.raw_text)
        if re.search(r'(?:'+_VERBS+r')\s*[一二三四五六七八九十两半\d.]|(?:'+_VERBS+r').*(?:分钟|小时|刻钟)', count_free_text):
            return None, 'duration_expression_unsupported'
        return None, None
    if len(matches) != 1 or len(targets) != 1:
        return None, 'duration_operation_not_atomic'
    entity, expression = targets[0], matches[0]
    quantities = list(re.finditer(r'[一二三四五六七八九十两半\d.]+\s*(?:个)?(?:分钟|小时)',operation.raw_text))
    if len(quantities) != 1 or re.match(r'[半一二三四五六七八九十两\d.]',operation.raw_text[expression.end():].lstrip()):
        return None, 'duration_expression_unsupported'
    separators = list(re.finditer(r'[，,。；;\n]|但是|但|而且',operation.raw_text))
    start = max((match.end() for match in separators if match.end() <= expression.start()),default=0)
    end = min((match.start() for match in separators if match.start() >= expression.end()),default=len(operation.raw_text))
    clause = operation.raw_text[start:end]
    from app.assistant_capabilities import affirmative_entity_source
    if not all(affirmative_entity_source(operation.raw_text, clause,
        re.escape(expression[1]), mention, action_offset=expression.start()-start) for mention in operation.activity_mentions):
        return None, 'duration_target_source_mismatch'
    before = getattr(entity,'duration_minutes',None)
    version = getattr(entity,'version',None)
    if before is None or version is None:
        return None, 'duration_baseline_missing'
    if entity.schedule_locked or getattr(entity,'status','planned') != 'planned':
        return None, 'duration_target_protected'
    operator = 'add' if expression[1] in {'增加','延长','多留','多待','再待'} else 'subtract' if expression[1] in {'减少','缩短','少留','少待'} else 'set'
    try:
        if not re.fullmatch(r'(?:半|\d+(?:\.\d+)?|[一二三四五六七八九两]|十[一二三四五六七八九]?|[一二三四五六七八九]十[一二三四五六七八九]?)',expression[2]):
            return None, 'duration_expression_unsupported'
        quantity = Decimal('0.5') if expression[2] == '半' else Decimal(expression[2]) if re.fullmatch(r'\d+(?:\.\d+)?',expression[2]) else Decimal(chinese_number(expression[2]))
        exact_minutes = quantity * (60 if expression[3] == '小时' else 1)
        if exact_minutes != exact_minutes.to_integral_value():
            return None, 'duration_expression_unsupported'
        minutes = int(exact_minutes)
    except (ValueError, ArithmeticError):
        return None, 'duration_expression_unsupported'
    after = before + minutes if operator == 'add' else before - minutes if operator == 'subtract' else minutes
    if not 1 <= minutes <= 1440 or not 1 <= after <= 1440:
        return None, 'duration_out_of_range'
    return SavedDurationChange(operation_index=index,source_quote=operation.raw_text,activity_id=entity.id,
        day_id=entity.day_id,activity_version=version,trip_version=trip_version,
        operator=operator,minutes=minutes,before_minutes=before,after_minutes=after), None
