"""Short-lived server-owned Place references, never planning authorization.

Only persisted cards in the current topic/city participate. Search result rank
does not establish conversation order; use the user's list or presented cards.
"""
import re
from uuid import UUID

from app.travel_language import chinese_number

REFERENCE = re.compile(r"第\s*([一二三四五六七八九十两\d]+)\s*(?:个|处)(?:地方|地点|景点)?|前一个|后一个|前者|后者|这两个(?:地方|地点|景点)?|两个(?:地方|地点|景点)|它们|它|那里")
ADDRESS_LINK = r'\s*(?:[（(]|(?:的)?(?:地址|位置)?(?:在|是|位于|按|选|：|:)\s*|(?:的)?地址\s*)'


def subject_matches_place(name, place):
    """Only server names/aliases and a provider-confirmed literal address bind IDs."""
    known = [place['name'], *place.get('aliases', [])]
    if name in known:
        return True
    decorated = re.fullmatch(r'(.+?)[（(]([^（）()]+)[）)]', name)
    if not decorated or decorated[1] not in known:
        return False
    address = place.get('address') or ''
    for match in re.finditer(re.escape(decorated[2]), address):
        # An administrative prefix may be omitted; a different street prefix
        # (东路 versus 新东路) cannot donate its identity by substring.
        before, after = address[:match.start()], address[match.end():]
        if (not before or before[-1] in '省市区县镇乡 ，,（(') and (
            not after or after[0] in '附楼栋室院 ，,（）()'):
            return True
    return False


def literal_subjects_cover(required, existing, source):
    """Deduplicate read obligations, without supplying a place identity.

    A bare name and its sole literal address decoration in this same source
    describe one search subject. Two explicit addresses stay separate.
    """
    def equivalent(left, right):
        if left == right:
            return True
        a = re.fullmatch(r'(.+?)[（(]([^（）()]+)[）)]', left)
        b = re.fullmatch(r'(.+?)[（(]([^（）()]+)[）)]', right)
        if bool(a) == bool(b):
            return False
        decorated, bare = (a, right) if a else (b, left)
        if decorated[1] != bare or decorated[0] not in source:
            return False
        addresses = set(re.findall(re.escape(bare) + r'[（(]([^（）()]+)[）)]', source))
        return addresses == {decorated[2]}
    return all(any(equivalent(name, other) for other in existing) for name in required)


def explanation_requested(text):
    """Explicit stable subgoals; naming a place alone is not an explanation."""
    for clause in re.split(r'[，,。；;!?！？\n]',text):
        for match in re.finditer(r'看点|看什么|值得看(?:什么|的东西|哪)?|怎么玩|玩法|各自特色',clause):
            if re.search(r'(?:不(?:用|要|必|想)?|别)(?:再)?(?:介绍|解释|了解|知道|说|讲|查|看)[^，,。；;]*$',clause[:match.start()]):
                continue
            if re.match(r'(?:先|暂时)?(?:不用|不要|不必|别)(?:再)?(?:介绍|解释|了解|知道|说|讲|查|看)',clause[match.end():]):
                continue
            return True
    return False


def place_catalog(history, envelope):
    city = (envelope.browsing_city or '').removesuffix('市')
    active = []
    focus = None
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
            if not any(subject_matches_place(name, p) for p in places):
                places.append({'name':name, 'aliases':[], 'city':city, 'place_id':None,
                    'kind':'raw_mention'})
        subjects = list(dict.fromkeys(requested))
        if len(subjects) > 1:
            slots = []
            for name in sorted(subjects,key=source.index):
                candidates = [p for p in places if p.get('place_id') and subject_matches_place(name, p)]
                slot = candidates[0] if len(candidates) == 1 else {
                    'name':name,'aliases':[],'city':city,'place_id':None,'kind':'raw_mention'}
                if slot.get('place_id') and any(p.get('place_id') == slot['place_id'] for p in slots):
                    continue
                slots.append(slot)
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
                subject_matches_place(old['name'],p)] for i,old in enumerate(active)}
            upgrades = {i:ps[0] for i,ps in matches.items() if not active[i].get('place_id') and len(ps) == 1 and
                sum(any(p['place_id'] == ps[0]['place_id'] for p in candidates)
                    for candidates in matches.values()) == 1}
            if active and any(matches.values()) and not new_order and all(
                any(subject_matches_place(old['name'], p) or
                    subject_matches_place(p['name'], old) for old in active) for p in ordered):
                active = [upgrades.get(i,p) for i,p in enumerate(active)]
            elif not active or new_order or not ids <= {key(p) for p in active}:
                active = ordered
                focus = None
        # Conversational attention is separate from the comparison's order.
        # Retain it only when this user turn identifies one member, never by
        # the order of independent tools or by mutating persisted cards.
        scoped = [{**p, '_reference_focus': _reference_key(p) == focus} for p in active]
        for clause in re.split(r'[，,。；;!?！？\n]', source):
            if read_clause_denied(clause):
                continue
            scoped = [{**p, '_reference_focus': _reference_key(p) == focus} for p in active]
            resolved = resolve_read_text(clause, scoped)
            targets = [p for p in active if any(n and n in resolved for n in [p['name'], *p.get('aliases', [])])
                and argument_in_read_scope(p['name'], clause, scoped, capabilities=['poi'])]
            unresolved = any(resolve_read_text(m[0], scoped) == m[0] for m in REFERENCE.finditer(clause))
            if len(targets) == 1 and not unresolved:
                focus = _reference_key(targets[0])
            elif len(targets) > 1 or unresolved:
                focus = None
    return [{**p, '_reference_focus': _reference_key(p) == focus} for p in active]


def _reference_key(place):
    return str(place['place_id']) if place.get('place_id') else 'raw:' + place['name']


def read_clause_denied(clause):
    return bool(re.match(r'\s*(?:请)?(?:先)?(?:不看|不读|不要(?:查看|读取|列出|看|读)|不用(?:查看|读取|看|读)|别(?:看|读))', clause))


def bind_read_task_reference(task, places):
    """Interpret only a source-bound read, never a planning/adoption operation.

    A model's paraphrased name cannot override the server's unique deictic
    binding. Literal names retain precedence; unresolved references stay gaps.
    """
    source = task.source_quote
    changes = {}
    matches = list(REFERENCE.finditer(source))
    # This recovery is limited to the existing opening-hours property. Require
    # a complete single-subject read expression: unknown words may be another
    # place or relation and must not disappear behind a known pronoun.
    remainder = REFERENCE.sub('', source)
    atoms = ('什么时候', '开放时间', '营业时间', '有依据', '有没有', '是否', '能否',
        '今天', '明天', '当天', '现在', '开放', '营业', '闭馆', '开门', '关门',
        '时间', '几点', '查询', '帮我', '看看', '请', '再', '查', '看', '的', '到', '吗', '呢')
    for atom in sorted(atoms, key=len, reverse=True):
        remainder = remainder.replace(atom, '')
    single_property = (task.fact_kind == 'opening_hours' and len(matches) == 1
        and bool(re.search(r'开放时间|营业时间|开放到几点|几点(?:开放|关门|闭馆|开门)|今天开放|明天开放',source))
        and not remainder.strip(' ?？!！。\t\n')
        and task.capabilities in ([], ['poi'], ['facts']))
    if single_property and not task.origin and not task.destination and not any(name in source for name in task.names):
        if all(resolve_read_text(match[0], places) != match[0] for match in matches):
            resolved = resolve_read_text(source, places)
            targets = [p for p in places if any(name and name in resolved for name in [p['name'], *p.get('aliases', [])])]
            if len(targets) == 1 and argument_in_read_scope(targets[0]['name'], source, places):
                changes.update(names=[targets[0]['name']], query='')
    if (changes.get('names') and task.capabilities in ([], ['poi'], ['facts'])
        and not read_clause_denied(source)):
        changes['capabilities'] = ['facts']
    return task.model_copy(update=changes) if changes else task


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
            focused = [i for i,p in enumerate(places) if p.get('_reference_focus')]
            index = 0 if len(places) == 1 else focused[0] if len(focused) == 1 else -1
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
    addresses = set(re.findall(re.escape(base)+r'[（(]([^（）()]+)[）)]',resolved))
    decorated = re.fullmatch(r'(.+?)[（(]([^（）()]+)[）)]',value)
    if decorated and addresses and addresses!={decorated[2]}:
        return False
    if 'route' in capabilities and not decorated and addresses:
        # A bare route endpoint cannot drop the user's current qualifier and
        # borrow a historical identity at another address.
        qualified = [p for p in places if value in [p['name'],*p.get('aliases',[])]
            and all(subject_matches_place(value+'（'+address+'）',p) for address in addresses)]
        if len(qualified)!=1:
            return False
    elif 'route' in capabilities and not decorated and re.search(re.escape(value)+ADDRESS_LINK,resolved):
        qualified = [p for p in places if value in [p['name'],*p.get('aliases',[])] and p.get('address')
            and literal_search_subject(value+'（'+p['address']+'）',resolved)]
        if len(qualified)!=1:
            return False
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
    matches=[]
    for place in places:
        if not subject_matches_place(value,place):
            continue
        names=[place['name'],*place.get('aliases',[])]
        if decorated and any(name and name in source for name in names):
            continue
        if 'route' in capabilities and any(re.search(re.escape(name)+ADDRESS_LINK,resolved)
            and not (place.get('address') and literal_search_subject(name+'（'+place['address']+'）',resolved))
            for name in names if name):
            continue
        matches.append(place)
    return len(matches) == 1 and any(n and n in resolved and affirmative_name(n) for n in
        [matches[0]['name'], *matches[0].get('aliases', [])])


def literal_search_subject(value, source):
    if value in source:
        return True
    decorated = re.fullmatch(r'(.+?)[（(]([^（）()]+)[）)]', value)
    # A name and an address appearing in different clauses are not a binding.
    # Literal decorated names remain allowed; real provider resolution still
    # must confirm the actual address before an identity is used.
    return bool(decorated and re.search(re.escape(decorated[1])+ADDRESS_LINK+re.escape(decorated[2]),source))


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
