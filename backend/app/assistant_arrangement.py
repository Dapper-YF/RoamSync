"""Small, explicitly authorized edits; reasoning stays in the existing Planner."""
import re

from sqlalchemy import select

from app.arrangement_service import ItemWrite, read_items, write_item
from app.assistant_context import check_action_target
from app.database import Activity, DayPlan, PlaceCandidate, PlanRevision, RouteLeg, TripPreferences
from app.formal_write import lock_trip


def choice_command(message):
    text = message.strip().rstrip("。！! ")
    for pattern, kind in [
        (r"(?:请)?(?:把)?(.+?)(?:改成|改为|设为|作为)备选", "optional"),
        (r"(.+?)(?:还是|仍是|仍为)备选(?:[，,](?:不要|别)(?:把它)?排进去)?", "optional"),
        (r"(?:请)?(?:保留|确定要去)(.+?)(?:[，,](?:其他|其余)(?:暂时)?不定)?", "selected"),
        (r"(?:今天)?(?:不想去|不去|取消)(.+?)(?:了)?", "cancelled"),
    ]:
        match = re.fullmatch(pattern, text)
        if match:
            return match.group(1).strip(), kind
    return None


async def simple_duration_edit(db, row, message, message_id, context):
    """Only one exact scalar edit, no downstream decision or invented route."""
    from app.assistant_service import AssistantToolError
    first = re.split(r"[，,。；;]", message)[0]
    rest = re.split(r"[，,。；;]", message)[1:]
    if any(clause.strip() and not re.search(r"不要动|保持不变|仍为备选|不安排|其他.*不变", clause) for clause in rest):
        return None  # Multiple changes require their own explicit coordination.
    match = re.fullmatch(r"(?:请)?(?:把)?(?:第([一二三123])天)?(.+?)(?:的)?(?:停留时长|停留时间|游览时长|时长)(?:改为|改成|调整为)(\d+)分钟", first)
    if not match or not row.trip_id:
        return None
    target = context.action_target
    if target is None or target.operation != "plan_trip":
        raise AssistantToolError("请从这份安排明确发起活动修改。")
    if context.read_trip_id != row.trip_id:
        raise AssistantToolError("当前读取的安排与修改目标不一致。")
    day_index, name, duration = match.groups()
    name = name.rstrip("的").strip()
    rows = (await db.execute(select(Activity, DayPlan).join(DayPlan).join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id).where(
        DayPlan.trip_id == row.trip_id, (PlaceCandidate.name == name) | (Activity.custom_name == name)))).all()
    if day_index:
        index = {"一": 0, "1": 0, "二": 1, "2": 1, "三": 2, "3": 2}[day_index]
        rows = [(a, d) for a, d in rows if d.position == index]
    if len(rows) != 1 or not 5 <= int(duration) <= 1440:
        return None
    activity, day = rows[0]
    if activity.schedule_locked or activity.status != "planned":
        return None
    duration = int(duration)
    minute = lambda t: t.hour*60+t.minute
    end = minute(activity.scheduled_time) + duration
    pref = await db.get(TripPreferences, row.trip_id)
    if end > 1440 or pref and end > minute(pref.daily_end_time):
        return None
    from app.arrangement_service import read_items
    if any(i.kind == "free_window" and i.day_date == day.date and minute(activity.scheduled_time) < minute(i.end_time) and end > minute(i.start_time)
           for i in await read_items(db, row.trip_id)):
        return None
    next_activity = await db.scalar(select(Activity).where(Activity.day_plan_id == day.id, Activity.position > activity.position).order_by(Activity.position).limit(1))
    if next_activity and duration > activity.duration_minutes:
        route = await db.scalar(select(RouteLeg).where(RouteLeg.from_activity_id == activity.id, RouteLeg.to_activity_id == next_activity.id))
        if route is None or end + route.duration_minutes > minute(next_activity.scheduled_time):
            return None
    trip = await lock_trip(db, row.trip_id, expected_version=target.expected_version)
    check_action_target(context, session_trip_id=row.trip_id, message_id=message_id, trip_version=trip.version, operation="plan_trip")
    from app.planner_repository import update_activity
    from app.schemas import ActivityUpdate
    await update_activity(db, activity.id, ActivityUpdate(version=activity.version, duration_minutes=duration),
        expected_trip_version=trip.version, commit=False)
    return f"已将{name}的停留时长改为{duration}分钟。已保存的路线与后续时间允许这次修改，其他活动和留白保持不变。"


async def apply_arrangement_message(db, row, message, message_id, context):
    from app.assistant_service import AssistantToolError, confirm_action
    confirm = message.strip().rstrip("。！! ") in {"就按这份来", "就这样安排", "采用这份方案", "确认采用"}
    enabled = context.prefer_flexible or context.action_target and context.action_target.operation in {"edit_arrangement", "accept_plan"}
    if not enabled:
        return None
    if row.trip_id is None and context.prefer_flexible and re.search(r"先讨论|先聊聊|暂不创建", message) and not re.search(r"[？?]|怎么|如何|什么|是否|帮我|请形成|请安排|请规划", message):
        return "我会把这些旅行想法用于接下来的讨论。目前还没有创建旅行或保存安排；未定时间与备选会保持未定。"
    simple = await simple_duration_edit(db, row, message, message_id, context)
    if simple is not None:
        return simple
    if confirm:
        if context.preview_action_id:
            key = str(context.preview_action_id)
            if key in row.applied_actions:
                return "这份安排已经保存，没有重复创建。"
            if not row.pending_action or row.pending_action["id"] != key:
                raise AssistantToolError("这份建议已经变化，请查看当前建议后再采用。")
            if row.pending_action.get("topic_id") not in {None, context.topic_id}:
                raise AssistantToolError("这份建议不属于当前对话，请重新打开对应建议。")
            await confirm_action(db, row.id, key, True)
            return "已采用并保存这份安排；未定的部分保持未定。"
        target = context.action_target
        if target and target.operation == "accept_plan" and target.revision_id and row.trip_id:
            trip = await lock_trip(db, row.trip_id, expected_version=target.expected_version)
            check_action_target(context, session_trip_id=row.trip_id, message_id=message_id, trip_version=trip.version, operation="accept_plan")
            revision = await db.scalar(select(PlanRevision).where(PlanRevision.id == target.revision_id, PlanRevision.trip_id == trip.id))
            if revision is None:
                raise AssistantToolError("没有匹配到当前显示的候选，请重新打开方案。")
            from app.plan_revision_service import accept_plan_revision
            await accept_plan_revision(db, revision.id, commit=False)
            return "已采用当前明确选择的方案，其他决定以保存后的安排为准。"
        return "请先打开要采用的那份建议，或点击它的采用按钮；我不会把一段聊天文字当作已确认的安排。"
    command = choice_command(message)
    if command is None or not row.trip_id:
        return None
    target = context.action_target
    if target is None:
        raise AssistantToolError("请从这份安排发起修改并刷新内容；只读背景不能授权写入。")
    trip = await lock_trip(db, row.trip_id, expected_version=target.expected_version)
    check_action_target(context, session_trip_id=row.trip_id, message_id=message_id, trip_version=trip.version, operation="edit_arrangement")
    if context.read_trip_id != trip.id or context.browsing_city and context.browsing_city.rstrip("市") != trip.destination.rstrip("市"):
        raise AssistantToolError("当前浏览背景与修改目标不同，请回到要修改的安排。")
    name, kind = command
    matches = [i for i in await read_items(db, trip.id) if i.kind != "free_window" and (i.label == name or name in i.label)]
    if len(matches) != 1:
        return "没有唯一匹配到这个事项，请使用安排里显示的完整名称。尚未修改安排。"
    item = matches[0]
    try:
        await write_item(db, trip.id, ItemWrite(expected_version=trip.version, kind=kind, label=item.label,
            source_ref=f"message:{message_id}", place_id=item.place_id, day_date=item.day_date), item_id=item.id, commit=False)
    except ValueError as exc:
        raise AssistantToolError(str(exc)) from exc
    return {"optional": f"已把{item.label}改为备选。", "selected": f"已保留{item.label}，时间可以继续未定。",
            "cancelled": f"已取消{item.label}；保留了决定来源。"}[kind] + "其他安排没有重规划。"
