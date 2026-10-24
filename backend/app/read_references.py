"""Short-lived server-owned Place references, never planning authorization.

Only persisted cards in the current topic/city participate. Search result rank
does not establish conversation order; use the user's list or presented cards.
"""
import re
from uuid import UUID

from app.travel_language import chinese_number

REFERENCE = re.compile(r"第\s*([一二三四五六七八九十两\d]+)\s*(?:个|处)(?:地方|地点|景点)?|前一个|后一个|前者|后者|这两个(?:地方|地点|景点)?|两个(?:地方|地点|景点)|它|那里")


def place_catalog(history, envelope):
    city = (envelope.browsing_city or '').removesuffix('市')
    latest = []
    for turn in reversed(history):
        cards = turn.get('place_cards') or []
        places = []
        for card in cards:
            p = card.get('place') or {}
            try:
                UUID(str(p.get('place_id')))
            except (ValueError, TypeError):
                continue
            if not p.get('name') or not p.get('city') or city and p['city'].removesuffix('市') != city:
                continue
            if str(p['place_id']) not in {str(item['place_id']) for item in places}:
                places.append(p)
        if places:
            # A comparison's requested order takes precedence over retrieval
            # ordering. Provider aliases are accepted only from server cards.
            source = turn.get('user', '')
            def position(p):
                names = [p['name'], *p.get('aliases', [])]
                positions = [source.index(n) for n in names if n and n in source]
                return min(positions) if positions else len(source) + places.index(p)
            ordered = sorted(places, key=position)[:8]
            if not latest:
                latest = ordered
            # A read focused on one member does not renumber the comparison.
            # A genuinely new identity starts a different reference scope.
            if len(ordered) > 1 and {str(p['place_id']) for p in latest} <= {str(p['place_id']) for p in ordered}:
                return ordered
            if any(str(p['place_id']) not in {str(q['place_id']) for q in ordered} for p in latest):
                break
    return latest


def resolve_read_text(text, places):
    if not places or re.search(r"第.{0,8}(?:条建议|个建议|个方案)|suggestion_", text):
        return text
    def replace(match):
        word = match[0]
        if match[1]:
            index = chinese_number(match[1]) - 1
        elif word in {'前一个', '前者'}:
            index = 0 if len(places) == 2 else -1
        elif word in {'后一个', '后者'}:
            index = 1 if len(places) == 2 else -1
        elif word.startswith(('这两个', '两个')):
            return '和'.join(p['name'] for p in places) if len(places) == 2 else word
        else:
            index = 0 if len(places) == 1 else -1
        return places[index]['name'] if 0 <= index < len(places) else word
    return REFERENCE.sub(replace, text)


def argument_in_read_scope(value, source, places):
    if not value:
        return True
    resolved = resolve_read_text(source, places)
    if value in resolved:
        return True
    # Canonical and provider/reviewed aliases refer to one exact ID. An
    # explicitly named peer cannot donate its identity to another task.
    matches = [p for p in places if value in [p['name'], *p.get('aliases', [])]]
    return len(matches) == 1 and any(n and n in resolved for n in
        [matches[0]['name'], *matches[0].get('aliases', [])])
