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
        source = turn.get('user', '')
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
        # Preserve the positions of explicitly requested but unresolved peers.
        # Validated task arguments are server-produced; raw mentions authorize
        # only another search, never a route coordinate or a planning identity.
        requested = []
        for task in (turn.get('read_tools') or {}).get('tasks', []):
            args = task.get('validated_arguments') or {}
            if city and args.get('city') and args['city'].removesuffix('市') != city:
                continue
            requested.extend(n for n in args.get('names', []) if n and n in source)
        for name in dict.fromkeys(requested):
            if not any(name in [p['name'], *p.get('aliases', [])] for p in places):
                places.append({'name':name, 'aliases':[], 'city':city, 'place_id':None,
                    'kind':'raw_mention'})
        subjects = list(dict.fromkeys(requested))
        if len(subjects) > 1:
            slots = []
            for name in sorted(subjects,key=source.index):
                candidates = [p for p in places if p.get('place_id') and name in [p['name'],*p.get('aliases',[])]]
                slots.append(candidates[0] if len(candidates) == 1 else
                    {'name':name,'aliases':[],'city':city,'place_id':None,'kind':'raw_mention'})
            places = slots
        if places:
            # A comparison's requested order takes precedence over retrieval
            # ordering. Provider aliases are accepted only from server cards.
            def position(p):
                names = [p['name'], *p.get('aliases', [])]
                positions = [source.index(n) for n in names if n and n in source]
                return min(positions) if positions else len(source) + places.index(p)
            ordered = sorted(places, key=position)[:8]
            def key(p):
                return str(p['place_id']) if p.get('place_id') else 'raw:'+p['name']
            ids = {key(p) for p in ordered}
            explicit = sum(any(n and n in source for n in [p['name'], *p.get('aliases', [])]) for p in ordered)
            # A new named list establishes order; a route returning B,A does not.
            new_order = explicit > 1 and bool(re.search(r'比较|顺序|重新排序|各自|分别|都想了解', source))
            # Resolution of one member upgrades its binding in place, without
            # collapsing or renumbering the original requested comparison.
            matches = {i:[p for p in ordered if p.get('place_id') and
                old['name'] in [p['name'],*p.get('aliases',[])]] for i,old in enumerate(active)}
            upgrades = {i:ps[0] for i,ps in matches.items() if not active[i].get('place_id') and len(ps) == 1 and
                sum(any(p['place_id'] == ps[0]['place_id'] for p in candidates)
                    for candidates in matches.values()) == 1}
            if active and any(matches.values()) and not new_order and all(
                any(p['name'] in [old['name'],*old.get('aliases',[])] or
                    old['name'] in [p['name'],*p.get('aliases',[])] for old in active) for p in ordered):
                active = [upgrades.get(i,p) for i,p in enumerate(active)]
            elif not active or new_order or not ids <= {key(p) for p in active}:
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


def argument_in_read_scope(value, source, places, *, capabilities=()):
    if not value:
        return True
    resolved = resolve_read_text(source, places)
    def affirmative_name(name):
        for clause in re.split(r'[，,。；;!?！？\n]', resolved):
            if name not in clause:
                continue
            before, after = clause.split(name,1)
            if re.search(r'(?:不(?:用|要|必)?|别)(?:再)?(?:查询|搜索|查|搜|看)[^，,。；;]*$',before):
                continue
            if re.match(r'(?:的)?(?:地址|位置|路线|开放时间)?(?:先|暂时)?(?:不用|不要|别|不)(?:再)?(?:查|搜|看)',after):
                continue
            return True
        return False
    base = re.split(r'[（(]',value)[0]
    if set(capabilities) and set(capabilities) <= {'poi','web'}:
        # A later denial of this object's address lookup is not revoked by
        # an earlier positive introduction. Direct explanatory tasks retain it.
        for clause in re.split(r'[，,。；;!?！？\n]', resolved):
            if base in clause:
                before,after=clause.split(base,1)
                if re.search(r'(?:不(?:用|要|必)?|别)(?:再)?(?:查询|搜索|查|搜|看)[^，,。；;]*$',before) or re.match(
                    r'(?:的)?(?:地址|位置|路线|开放时间)?(?:先|暂时)?(?:不用|不要|别|不)(?:再)?(?:查|搜|看)',after):
                    return False
    if literal_search_subject(value, resolved) and affirmative_name(base):
        return True
    # Canonical and provider/reviewed aliases refer to one exact ID. An
    # explicitly named peer cannot donate its identity to another task.
    matches = [p for p in places if value in [p['name'], *p.get('aliases', [])]]
    return len(matches) == 1 and any(n and n in resolved and affirmative_name(n) for n in
        [matches[0]['name'], *matches[0].get('aliases', [])])


def literal_search_subject(value, source):
    if value in source:
        return True
    decorated = re.fullmatch(r'(.+?)[（(]([^（）()]+)[）)]', value)
    # A name and an address appearing in different clauses are not a binding.
    # Literal decorated names remain allowed; real provider resolution still
    # must confirm the actual address before an identity is used.
    return bool(decorated and re.search(re.escape(decorated[1])
        + r'\s*(?:[（(]|(?:的)?(?:地址|位置)?(?:在|是|位于|按|选|：|:)\s*|(?:的)?地址\s*)'
        + re.escape(decorated[2]), source))


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
