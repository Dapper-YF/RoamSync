"""Small, explicitly authorized edits; reasoning stays in the existing Planner."""
import re

from sqlalchemy import select

from app.assistant_context import check_action_target
from app.database import PlanRevision
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


async def apply_arrangement_message(db, row, message, message_id, context):
    from app.assistant_service import AssistantToolError, confirm_action
    confirm = message.strip().rstrip("。！! ") in {"就按这份来", "就这样安排", "采用这份方案", "确认采用"}
    from app.conversation_candidate.commands import CandidateCommand, validate_command
    try:
        validate_command(CandidateCommand(action='adopt', source_quote=message.strip()), message)
        confirm = True
    except ValueError:
        pass
    enabled = context.prefer_flexible or context.action_target and context.action_target.operation in {"edit_arrangement", "accept_plan"}
    if not enabled:
        return None
    if row.trip_id is None and context.prefer_flexible and re.search(r"先讨论|先聊聊|暂不创建", message) and not re.search(r"[？?]|怎么|如何|什么|是否|帮我|请形成|请安排|请规划", message):
        return "我会把这些旅行想法用于接下来的讨论。目前还没有创建旅行或保存安排；未定时间与备选会保持未定。"
    # Natural-language schedule edits continue into the existing Planner and
    # PlanRevision preview. Only an explicit revision Accept may save them.
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
    if target.operation != 'edit_arrangement':
        return None
    trip = await lock_trip(db, row.trip_id, expected_version=target.expected_version)
    check_action_target(context, session_trip_id=row.trip_id, message_id=message_id, trip_version=trip.version, operation="edit_arrangement")
    if context.read_trip_id != trip.id or context.browsing_city and context.browsing_city.rstrip("市") != trip.destination.rstrip("市"):
        raise AssistantToolError("当前浏览背景与修改目标不同，请回到要修改的安排。")
    return '这类事项状态的聊天修改尚未形成可采用候选，正式安排未改变。可以继续讨论，或在事项表单明确编辑。'
