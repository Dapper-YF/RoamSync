"""Short-lived server-owned Place references, never planning authorization.

Only persisted cards in the current topic/city participate. Search result rank
does not establish conversation order; use the user's list or presented cards.
"""
import re
from uuid import UUID

from app.travel_language import chinese_number

REFERENCE = re.compile(r"第\s*([一二三四五六七八九十两\d]+)\s*(?:个|处)(?:地方|地点|景点)?|前一个|后一个|前者|后者|这两个(?:地方|地点|景点)?|两个(?:地方|地点|景点)|它们|它|那里")


def place_catalog(history, envelope):
    city = (envelope.browsing_city or '').removesuffix('市')
    active = []
    for turn in history:
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
            ids = {str(p['place_id']) for p in ordered}
            explicit = sum(any(n and n in source for n in [p['name'], *p.get('aliases', [])]) for p in ordered)
            # A new named list establishes order; a route returning B,A does not.
            new_order = explicit > 1 and bool(re.search(r'比较|按.{0,12}顺序|重新排序', source))
            if not active or new_order or not ids <= {str(p['place_id']) for p in active}:
                active = ordered
    return active


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
        elif word == '它们':
            return '和'.join(p['name'] for p in places) if len(places) > 1 else word
        elif word.startswith(('这两个', '两个')):
            return '和'.join(p['name'] for p in places) if len(places) == 2 else word
        else:
            index = 0 if len(places) == 1 else -1
        return places[index]['name'] if 0 <= index < len(places) else word
    return REFERENCE.sub(replace, text)


def read_reference_context(message, places, names=()):
    """Read-only server scope. Literal search subjects never become IDs."""
    resolved = resolve_read_text(message, places)
    bound = [p for p in places if any(n and n in resolved for n in [p['name'], *p.get('aliases', [])])]
    explicit = [n for n in names if n and n in message]
    unresolved = [m[0] for m in REFERENCE.finditer(message) if resolve_read_text(m[0], places) == m[0]]
    return {'version': 1, 'kind': 'place', 'source_text': message, 'resolved_text': resolved,
        'ordered_refs': [str(p['place_id']) for p in places if p.get('place_id')],
        'bound_refs': [str(p['place_id']) for p in bound if p.get('place_id')], 'explicit_names': explicit,
        'unresolved': unresolved,
        'owns_reference': bool(bound or explicit) and not unresolved and not bool(re.search(r'建议|suggestion_', message))}


def argument_in_read_scope(value, source, places):
    if not value:
        return True
    resolved = resolve_read_text(source, places)
    if literal_search_subject(value, resolved):
        return True
    # Canonical and provider/reviewed aliases refer to one exact ID. An
    # explicitly named peer cannot donate its identity to another task.
    matches = [p for p in places if value in [p['name'], *p.get('aliases', [])]]
    return len(matches) == 1 and any(n and n in resolved for n in
        [matches[0]['name'], *matches[0].get('aliases', [])])


def literal_search_subject(value, source):
    if value in source:
        return True
    decorated = re.fullmatch(r'(.+?)[（(]([^（）()]+)[）)]', value)
    return bool(decorated and all(part in source for part in decorated.groups()))


def task_referents(message, decision, historical):
    """Bind same-turn ellipsis to literal named subjects, not sibling results.

    Raw subjects can authorize a name search only. They have no place ID and
    must still be resolved through the real provider before routing/planning.
    """
    names = list(dict.fromkeys([*decision.names, *(n for t in decision.read_tasks for n in t.names)]))
    names = [n for n in names if n and n in message]
    names.sort(key=message.index)
    if len(names) < 2:
        return historical
    return [next((p for p in historical if n in [p['name'], *p.get('aliases', [])]),
        {'name': n, 'aliases': [], 'place_id': None, 'kind': 'raw_mention'}) for n in names]
