"""Server-owned saved-object references; parsing never grants write authority."""
from dataclasses import dataclass
import re

from app.travel_language import chinese_number

NUMBER = r'[一二三四五六七八九十两\d]+'
ACTIVITY_ORDINAL = re.compile(rf'第\s*({NUMBER})\s*(项(?:活动|景点)?|站|个(?:活动|景点))')


@dataclass(frozen=True)
class SavedActivityReference:
    source_quote: str
    ordinal: int
    explicit_activity: bool


def activity_reference(source):
    matches = list(ACTIVITY_ORDINAL.finditer(source))
    if len(matches) != 1:
        return None
    match = matches[0]
    return SavedActivityReference(match[0], chinese_number(match[1]), match[2] != '项')


def ordered_activities(rows):
    # Handbook sorts chronologically, with stable saved position for ties.
    return sorted(rows, key=lambda r: (r['time'], r.get('position', 0)))


def resolve_activity_position(rows, items, reference, expected_count):
    ordered = ordered_activities(rows)
    if expected_count != len(ordered):
        return [], 'activity_order_incomplete'
    if not reference.explicit_activity and any(item['kind'] != 'cancelled' and not item.get('activity_id') for item in items):
        return [], 'mixed_agenda_ordinal'
    if len({(r['time'], r.get('position', 0)) for r in ordered}) != len(ordered):
        return [], 'activity_order_ambiguous'
    index = reference.ordinal - 1
    if index < 0 or index >= len(ordered):
        return [], 'activity_ordinal_out_of_range'
    return [ordered[index]], None
