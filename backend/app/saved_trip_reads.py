"""Bounded detached saved-state reads. Selection is context, never authority."""
from copy import deepcopy
import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
import re
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Activity, DayPlan, PlaceCandidate, Trip, TripArrangementItem, SavedIntention, TripPreferences, PlanRevision, PlanningRun
from app.travel_language import chinese_number

READ_LIMIT = 100
READ_CONNECTION_LIMIT = 2
_read_gates = WeakKeyDictionary()


def _read_gate():
    # The application has one event loop per process. Loop-local gates also
    # support isolated test loops; never share asyncio locks between loops.
    loop = asyncio.get_running_loop()
    if loop not in _read_gates:
        _read_gates[loop] = asyncio.Semaphore(READ_CONNECTION_LIMIT)
    return _read_gates[loop]


class SavedTripReadStale(ValueError):
    """A known saved-state change requires a fresh explicit read."""


def requested_dates(message, days):
    """Literal saved-day references only; an invalid requested day stays empty."""
    clauses = re.split(r'[，,；;。!?！？\n]', message)
    focused = [c for c in clauses if re.search(r'(?:只|仅)(?:查看|查询|看看|看|读|查|列)', c)
        and re.search(r'第[一二三四五六七八九十两\d]+天|最后一天|20\d{2}-\d{1,2}-\d{1,2}|\d{1,2}月\d{1,2}[日号]', c)]
    if focused:
        message = '，'.join(focused)
    dates, explicit = set(), False
    by_position = {d['position'] + 1: d['date'] for d in days}
    for match in re.finditer(r'第\s*([一二三四五六七八九十两\d]+)\s*天', message):
        explicit = True
        value = by_position.get(chinese_number(match[1]))
        if value:
            dates.add(value)
    if '最后一天' in message and days:
        explicit = True
        dates.add(max(d['date'] for d in days))
    for match in re.finditer(r'(?<!\d)(20\d{2}-\d{1,2}-\d{1,2})(?!\d)', message):
        explicit = True
        try:
            dates.add(date(*(int(v) for v in match[1].split('-'))).isoformat())
        except ValueError:
            pass
    for match in re.finditer(r'(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})[日号]', message):
        explicit = True
        dates.update(d['date'] for d in days if
            (date.fromisoformat(d['date']).month, date.fromisoformat(d['date']).day) == (int(match[2]), int(match[3]))
            and (not match[1] or date.fromisoformat(d['date']).year == int(match[1])))
    return dates, explicit


@dataclass(frozen=True)
class SavedTripReadSnapshot:
    trip: dict
    days: tuple[dict, ...]
    activities: tuple[dict, ...]
    items: tuple[dict, ...]
    counts_by_date: dict
    item_count: int
    captured_at: str
    preferences: dict | None = None
    selected_day_id: str | None = None
    selected_activity_id: str | None = None
    displayed_revision: dict | None = None

    def project(self, message):
        dates, explicit = requested_dates(message, self.days)
        rows = list(self.activities)
        items = list(self.items)
        total = sum(self.counts_by_date.values())
        kind, ambiguous = 'trip', False
        scope_issue = None
        all_days = bool(re.search(r'全程|整趟|所有天|全部天', message))
        ordinal = re.search(r'第([一二三四五六七八九十两\d]+)(?:项|站|个(?:活动|景点))', message)
        selected = bool(re.search(r'选中|这个(?:活动|馆|展馆|景点)|这(?:个|一)项|该(?:活动|馆)|它|\bselected\b', message))
        if explicit:
            kind = 'day'
            if not dates or not dates <= {d['date'] for d in self.days}:
                ambiguous, scope_issue = True, 'date_not_in_trip'
            rows = [r for r in rows if r['date'] in dates]
            items = [r for r in items if r['day_date'] in dates]
            total = sum(self.counts_by_date.get(d, 0) for d in dates)
        elif not all_days and re.search(r'这天|当天|当前这一天|选中日期', message) and self.selected_day_id:
            dates = {d['date'] for d in self.days if d['day_id'] == self.selected_day_id}
            kind = 'day'
            rows = [r for r in rows if r['date'] in dates]
            items = [r for r in items if r['day_date'] in dates]
            total = sum(self.counts_by_date.get(d, 0) for d in dates)
        if ordinal and len({r['date'] for r in rows}) <= 1 and (explicit or self.selected_day_id):
            ordered = sorted(rows, key=lambda r: (r.get('position', 0), r['time'], r['activity_id']))
            index = chinese_number(ordinal[1]) - 1
            day_total = total
            rows = ordered[index:index+1] if index >= 0 else []
            kind = 'activity'
            ambiguous = not rows or day_total != len(ordered)
            scope_issue = 'activity_order_incomplete' if ambiguous else None
            total = 1 if rows else 0
            items = []
        elif selected and not all_days and (not explicit or self.selected_activity_id or
                re.search(r'选中|这个(?:活动|馆|展馆|景点)|这(?:个|一)项|该(?:活动|馆)', message)):
            kind = 'activity'
            # No selection is different from an empty day. Never guess by list order.
            rows = [r for r in rows if r['activity_id'] == self.selected_activity_id] if self.selected_activity_id else []
            total = 1 if rows else 0
            ambiguous = not rows
            if ambiguous:
                scope_issue = 'selected_activity_unresolved'
            items = [r for r in items if r['activity_id'] == self.selected_activity_id] if rows else []
        elif not all_days:
            names = {r['name'] for r in rows if len(r['name']) >= 2 and r['name'] in message}
            if names:
                kind = 'named_activity'
                rows = [r for r in rows if r['name'] in names]
                # If the full saved scope was truncated, another same-name row
                # may be outside it. This is not a complete identity lookup.
                truncated = sum(self.counts_by_date.values()) > len(self.activities)
                total = None if truncated else len(rows)
                ambiguous = len(rows) > 1 or truncated
                if ambiguous:
                    scope_issue = 'name_not_unique_or_incomplete'
                items = [r for r in items if r['label'] in names]
        rows.sort(key=lambda r: (r['date'], r['time'], r['activity_id']))
        items.sort(key=lambda r: (r['day_date'] or '', r['start'] or '', r['id']))
        complete = total is not None and total == len(rows) and not ambiguous
        items_complete = self.item_count <= len(self.items)
        coverage = {'scope_kind': kind, 'requested_dates': sorted(dates),
            'selected_activity_id': self.selected_activity_id if selected else None,
            'matched_count': total, 'returned_count': len(rows), 'complete': complete,
            'arrangement_items_complete': items_complete, 'ambiguous': ambiguous,
            'scope_issue': scope_issue,
            'trip_version': self.trip['version'], 'preferences_version': self.trip.get('preferences_version'),
            'captured_at': self.captured_at}
        return {'activities': deepcopy(rows), 'arrangement_items': deepcopy(items), 'coverage': coverage,
                'trip_days': len(self.days)}

    def selection_summary(self, message):
        projected = self.project(message)
        return {**deepcopy(self.trip), 'activities': projected['activities'],
            'arrangement_items': projected['arrangement_items'], 'read_coverage': projected['coverage'], 'total_days': len(self.days),
            'displayed_revision':deepcopy(self.displayed_revision)}


async def load_saved_trip_read(db, trip_id, message='', *, selected_day_id=None, selected_activity_id=None, limit=READ_LIMIT, revision_ref=None):
    """Capture committed state in a short independent read-only MVCC unit.

    The caller's transaction is untouched. In particular execution status writes
    do not advance Trip.version, so two version checks alone cannot make a
    sequence of READ COMMITTED queries coherent. The extra connection closes
    here, before any selector/provider work; no ORM instances escape.
    """
    bind = db.bind.engine if isinstance(db.bind, AsyncConnection) else db.bind
    # A caller can already hold a business-pool connection and row locks. Never
    # borrow its second connection from that pool: saturated callers could all
    # wait for one another. This channel has at most two physical connections
    # per application loop, no idle pool, and closes/disposes on failure/cancel.
    gate = _read_gate()
    try:
        await asyncio.wait_for(gate.acquire(), timeout=5)
    except TimeoutError as exc:
        raise SavedTripReadStale('读取当前安排较忙，请稍后重新读取；没有修改安排。') from exc
    try:
        read_engine = create_async_engine(bind.url, poolclass=NullPool)
        try:
            async with read_engine.connect() as connection:
                connection = await connection.execution_options(isolation_level='REPEATABLE READ')
                async with connection.begin():
                    await connection.execute(text('SET TRANSACTION READ ONLY'))
                    async with AsyncSession(bind=connection, expire_on_commit=False) as reader:
                        snapshot = await _capture_saved_trip_read(reader, trip_id, message,
                            selected_day_id=selected_day_id, selected_activity_id=selected_activity_id, limit=limit,revision_ref=revision_ref)
        finally:
            await read_engine.dispose()
    finally:
        gate.release()
    # Reject known versioned changes committed during capture. These checks use
    # DB scalars, not the caller's identity map. They are a freshness fence, not
    # the consistency mechanism and not a promise that nothing changes later.
    current = (await db.execute(select(Trip.version).where(Trip.id == trip_id),
        execution_options={'autoflush': False})).scalar_one_or_none()
    preference = (await db.execute(select(TripPreferences.version).where(TripPreferences.trip_id == trip_id),
        execution_options={'autoflush': False})).scalar_one_or_none()
    if current != snapshot.trip['version'] or preference != snapshot.trip['preferences_version']:
        raise SavedTripReadStale('读取期间安排或偏好已更新，请重新读取当前版本。')
    return snapshot


async def _capture_saved_trip_read(db, trip_id, message='', *, selected_day_id=None, selected_activity_id=None, limit=READ_LIMIT,revision_ref=None):
    async def rows(query):
        return (await db.execute(query, execution_options={'autoflush': False})).all()
    captured_at = datetime.now(UTC).isoformat()
    trip_rows = await rows(select(Trip.id, Trip.title, Trip.destination, Trip.version).where(Trip.id == trip_id))
    if not trip_rows:
        raise ValueError('读取的旅行不存在。')
    t = trip_rows[0]
    preference_rows = await rows(select(TripPreferences.version, TripPreferences.pace,
        TripPreferences.interest_categories, TripPreferences.avoid_categories, TripPreferences.free_text_requirements)
        .where(TripPreferences.trip_id == trip_id))
    preference_version = preference_rows[0].version if preference_rows else None
    preferences = {k: deepcopy(v) for k, v in preference_rows[0]._mapping.items() if k != 'version'} if preference_rows else None
    days = tuple({'day_id': str(r.id), 'date': r.date.isoformat(), 'position': r.position}
        for r in await rows(select(DayPlan.id, DayPlan.date, DayPlan.position).where(DayPlan.trip_id == trip_id).order_by(DayPlan.position)))
    if selected_day_id and str(selected_day_id) not in {d['day_id'] for d in days}:
        raise ValueError('选中的日期不属于读取的旅行。')
    if selected_activity_id:
        selected_rows = await rows(select(Activity.id, Activity.day_plan_id).join(DayPlan).where(
            DayPlan.trip_id == trip_id, Activity.id == selected_activity_id))
        if not selected_rows or selected_day_id and selected_rows[0].day_plan_id != selected_day_id:
            raise ValueError('选中的活动不属于读取的旅行或日期。')
    counts = {r.date.isoformat(): r.count for r in await rows(select(DayPlan.date, func.count(Activity.id).label('count'))
        .join(Activity, Activity.day_plan_id == DayPlan.id).where(DayPlan.trip_id == trip_id).group_by(DayPlan.date))}
    dates, _ = requested_dates(message, days)
    priority = []
    if selected_activity_id:
        priority.append((Activity.id == selected_activity_id, 0))
    if selected_day_id:
        priority.append((DayPlan.id == selected_day_id, 1))
    if dates:
        priority.append((DayPlan.date.in_([date.fromisoformat(d) for d in dates]), 1))
    query = select(Activity.id, Activity.day_plan_id, Activity.custom_name, PlaceCandidate.name, DayPlan.date, Activity.position,
        Activity.scheduled_time, Activity.duration_minutes, Activity.version, Activity.schedule_locked,
        Activity.status, PlaceCandidate.longitude, PlaceCandidate.latitude).join(DayPlan, Activity.day_plan_id == DayPlan.id)
    query = query.join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id).where(DayPlan.trip_id == trip_id)
    order = [case(*priority, else_=2)] if priority else []
    activities = tuple({'activity_id': str(r.id), 'day_id': str(r.day_plan_id), 'date': r.date.isoformat(),
        'name': r.custom_name or r.name, 'time': str(r.scheduled_time)[:5], 'start_time': str(r.scheduled_time)[:5],
        'duration_minutes': r.duration_minutes, 'version': r.version, 'schedule_locked': r.schedule_locked, 'position': r.position,
        'status': r.status, 'longitude': float(r.longitude), 'latitude': float(r.latitude),
        'subject_ref': {'kind': 'formal_activity', 'value': str(r.id)}}
        for r in await rows(query.order_by(*order, DayPlan.date, Activity.scheduled_time, Activity.id).limit(limit)))
    item_count = (await rows(select(func.count()).select_from(TripArrangementItem).where(TripArrangementItem.trip_id == trip_id)))[0][0]
    item_query = select(TripArrangementItem).where(TripArrangementItem.trip_id == trip_id)
    if dates:
        item_query = item_query.order_by(case((TripArrangementItem.day_date.in_([date.fromisoformat(d) for d in dates]), 0), else_=1))
    items = tuple({'id': str(r.id), 'trip_id': str(r.trip_id), 'kind': r.kind, 'label': r.label,
        'source_ref': r.source_ref, 'decision_ref': r.decision_ref, 'place_id': str(r.place_id) if r.place_id else None,
        'day_date': r.day_date.isoformat() if r.day_date else None, 'start': str(r.start_time)[:5] if r.start_time else None,
        'end': str(r.end_time)[:5] if r.end_time else None, 'activity_id': str(r.activity_id) if r.activity_id else None}
        for (r,) in await rows(item_query.order_by(TripArrangementItem.id).limit(limit)))
    if items:
        periods = {str(r.linked_arrangement_item_id): r.time_period for r in await rows(select(
            SavedIntention.linked_arrangement_item_id, SavedIntention.time_period).where(
                SavedIntention.linked_arrangement_item_id.in_([UUID(i['id']) for i in items])))}
        items = tuple({**i, 'time_period': periods.get(i['id'])} for i in items)
    displayed=None
    if revision_ref:
        revision=await db.scalar(select(PlanRevision).where(PlanRevision.id==revision_ref['id'],
            PlanRevision.trip_id==trip_id,PlanRevision.planning_run_id==revision_ref['run_id']),execution_options={'autoflush':False})
        run=await db.get(PlanningRun,revision_ref['run_id'])
        from app.revision_presentation import revision_presentation_hash,revision_review
        if (revision and run and revision.status=='pending' and run.base_trip_version==t.version
            and revision_presentation_hash(revision)==revision_ref['hash']):
            review=revision_review(revision)
            if review['complete']:
                displayed={'id':str(revision.id),'presentation_hash':revision_ref['hash'],
                    'trip_version':t.version,'review':review,'captured_at':captured_at}
    return SavedTripReadSnapshot(trip={'id': str(t.id), 'title': t.title, 'destination': t.destination,
        'version': t.version, 'preferences_version': preference_version},
        days=days, activities=activities, items=items, counts_by_date=counts, item_count=item_count,
        captured_at=captured_at, preferences=preferences,
        selected_day_id=str(selected_day_id) if selected_day_id else None,
        selected_activity_id=str(selected_activity_id) if selected_activity_id else None,displayed_revision=displayed)


def render_displayed_revision(snapshot):
    value=snapshot.displayed_revision
    if not value:
        return '没有匹配到当前已展示、仍有效的修改候选。请重新打开候选后再查看差异；正式安排没有修改。'
    lines=['这份修改候选尚未采用，正式安排仍是修改前的保存状态：']
    def describe(item):
        return f"{item['name']} {item['date']} {item['time']} / {item['duration_minutes']}分钟"
    for change in value['review']['changes']:
        prior,after=change['before'],change['after']
        lines.append(('删除：'+describe(prior)) if not after else ('新增：'+describe(after)) if not prior else
            '修改：'+describe(prior)+' → '+describe(after))
    if not value['review']['changes']:
        lines.append('没有活动内容变化。')
    lines.extend('需留意：'+warning['message'] for warning in value['review']['warnings'])
    lines.append('只有明确采用当前这份候选，才会按已展示变化保存。')
    return '\n'.join(lines)


def render_saved_request(snapshot, message):
    """Project independent saved-value goals from one immutable read snapshot."""
    count = bool(re.search(r'几天|多少天|总天数|一共.*天|共.*天', message))
    first = list(re.finditer(r'第[一二三四五六七八九十两\d]+天第[一二三四五六七八九十两\d]+(?:项|站|个活动)', message))
    last = '最后一天' in message
    meals = [word for word in ('早餐', '午餐', '晚餐') if word in message]
    if sum((count, len(first), last, message.count('餐'))) < 2:
        return render_saved_read(snapshot.project(message), message)
    parts = []
    if count:
        parts.append(f'这份已保存行程共{len(snapshot.days)}天。')
    for match in first:
        parts.append(render_saved_read(snapshot.project(match[0]), match[0]))
    if meals:
        matching = []
        for meal in meals:
            clauses = [p for p in re.split(r'[，,。；;、]|和|及', message) if meal in p]
            for clause in clauses:
                dates, explicit = requested_dates(clause[:clause.index(meal)+len(meal)], snapshot.days)
                matching.extend(r for r in snapshot.items if meal in r['label'] and (not explicit or r['day_date'] in dates)
                    and r not in matching)
        parts.extend(f"{r['day_date'] or '日期未定'} {r['start'] or '时间未定'}—{r['end'] or '时间未定'} · {r['label']}。" for r in matching)
        if not matching:
            parts.append('本次读取范围没有对应餐饮窗口记录。' if snapshot.item_count <= len(snapshot.items)
                else '餐饮窗口读取范围不完整，不能确定是否另有记录。')
    if last:
        parts.append(render_saved_read(snapshot.project('最后一天'), '最后一天'))
    residual = message
    for match in first:
        residual = residual.replace(match[0], '')
    for meal in meals:
        residual = re.sub(r'第[一二三四五六七八九十两\d]+天[^，,。；;、]*' + meal, '', residual)
    remaining_dates, _ = requested_dates(residual.replace('最后一天', ''), snapshot.days)
    for day in sorted(remaining_dates):
        parts.append(render_saved_read(snapshot.project(day), day))
    return '\n\n'.join(parts)


def render_saved_read(projection, message=''):
    """Only saved values, no live facts, recommendations, routes or writes."""
    rows, items, c = projection['activities'], projection['arrangement_items'], projection['coverage']
    if c['ambiguous']:
        if c['scope_issue'] == 'date_not_in_trip':
            return '没有匹配到这次旅行中的日期，请确认要读第几天或具体日期；已保存安排没有修改。'
        return '没有唯一确定本次要读的活动。请选中具体活动或说明是哪一天；已保存安排没有修改。'
    text = []
    if re.search(r'几天|多少天|总天数|一共.*天|共.*天', message):
        text.append(f"这份已保存行程共{projection.get('trip_days', '未知')}天。")
        if not re.search(r'活动|安排|景点|留白|备选|第.+(?:天|项)|最后一天', message):
            rows, items = [], []
    statuses = {'planned': '已安排', 'active': '进行中', 'completed': '已完成', 'skipped': '已跳过'}
    for r in rows:
        text.append(f"{r['date']} {r['time']} · {r['name']}，保存的停留时长{r['duration_minutes']}分钟"
                    + ('，时间已锁定' if r['schedule_locked'] else '')
                    + ('，'+statuses[r['status']] if r['status'] != 'planned' else '') + '。')
    for r in items:
        if r['activity_id'] and any(a['activity_id'] == r['activity_id'] for a in rows):
            continue
        label = {'optional': '备选，未排入活动', 'selected': '已选，尚未排程', 'cancelled': '已取消', 'free_window': '留白'}.get(r['kind'], r['kind'])
        clock = f" {r['start']}—{r['end']}" if r['start'] and r['end'] else ''
        text.append(f"{r['day_date'] or '日期未定'}{clock} · {r['label']}：{label}。")
    if not text:
        text = ['这个读取范围内没有保存的活动或事项。']
    if not c['complete'] or not c['arrangement_items_complete']:
        text.append(f"本次仅读取了{c['returned_count']}项活动，读取范围尚不完整，不能据此排除其他安排。")
    return '已保存的安排：\n'+'\n'.join(text) + '\n本次只读取了保存状态，没有修改安排。'
