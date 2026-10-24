"""One model decision proposes content; literal sources and stored refs bound it."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.drafts.contracts import DraftPlan, DraftScheduleConstraints
from app.drafts.timing import quoted_clocks, explicit_interval

CHANGE_VERBS = r"调整|修改|改|创建|生成|添加|加入|增加|删除|删掉|取消|替换|换|延后|提前|多留|多待|少逛|少留|延长|缩短|减少|移到|挪到"
ACTION_VERBS = {"generate": r"创建|生成|安排|规划|制定|给我看|展示|出(?:一份|一版)?(?:候选|方案)",
    "modify": r"改|调整|延长|多待|少待|停留|留|逛", "adopt": r"保存|采用",
    "discard": r"放弃|撤回|丢弃|取消"}


class CandidateSchedule(DraftScheduleConstraints):
    # A new operation proposes one supported semantic mode or explicitly
    # unsupported transit/unknown. Historical Draft decoders remain unchanged.
    transport_mode: Literal["walk", "driving", "transit", "unknown"]


class CandidateDraftPlan(DraftPlan):
    schema_version: Literal[2] = 2
    schedule_constraints: CandidateSchedule


class DurationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_ref: str = Field(min_length=1, max_length=100)
    source_quote: str = Field(min_length=1, max_length=1000)
    duration_minutes: int = Field(strict=True, ge=1, le=1440)
    operation: Literal["set", "increase", "decrease"] = "set"
    quantity_source: Literal["user_explicit", "planning_allocation"] = "user_explicit"


class CandidateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["generate", "modify", "adopt", "discard"]
    source_quote: str = Field(min_length=1, max_length=1000)
    plan: CandidateDraftPlan | None = None
    patches: list[DurationPatch] = Field(default_factory=list, max_length=12)
    source_refs: dict[str, str] = Field(default_factory=dict, max_length=36)


def validate_command(command, message):
    from app.assistant_capabilities import affirmative_action_source
    from app.requirement_language import current_user_evidence_reason
    verbs = ACTION_VERBS
    quote = command.source_quote
    if message.count(quote) != 1:
        raise ValueError('操作原句无法唯一定位，请明确本次操作。')
    # Restore the containing clause before classifying questions. A model may
    # not strip "会怎样" from a hypothetical edit, while an independent later
    # question need not cancel a genuine preview request.
    from .sources import action_clause
    clause = action_clause(message,quote)
    if current_user_evidence_reason(message, quote):
        raise ValueError("假设、转述和引述不是本轮实际修改或保存的授权。")
    quoted = any(quote in match[0] for match in re.finditer(r"‘[^’]*’|“[^”]*”|\"[^\"]*\"|'[^']*'|「[^」]*」", message))
    inquiry = bool(re.search(r"会怎样|会如何|怎么|怎样|如何|是什么|什么意思|是否", clause))
    explicit_request = bool(re.search(r"(?:请|帮我|替我|给我|能不能帮我|能否帮我).{0,24}(?:保存|采用|改|调整|创建|生成|安排|规划)", clause))
    read_request = bool(re.search(r"告诉|解释|说明|介绍|想知道|了解|会怎样|会如何|怎么|如何", clause))
    if command.action in {"adopt", "discard"}:
        # Recover the complete containing user clause. A model extracting only
        # the word 保存 from a question cannot create adoption authority.
        clauses = [part.strip() for part in re.split(r"[，,；;。!?！？\n]", message) if part.strip()]
        prefix = r"(?:(?:请|麻烦(?:你)?|现在|就|直接|确认|同意)*(?:帮我|替我|给我|请你)?)"
        action = r"(?:采用并保存|保存|采用)" if command.action == "adopt" else r"(?:放弃|撤回|丢弃|取消)"
        target = r"(?:(?:(?:当前|这|上述|刚才)(?:的|份|个)?)*(?:修改|调整后)?(?:候选|安排|方案|行程|计划))?"
        destination = (r"(?:并保存)?" if command.action == 'adopt' else '') + r"(?:到我的安排)?(?:吧|即可|就行|一下)?"
        approved = [clause for clause in clauses if (quote in clause or clause in quote)
            and re.fullmatch(prefix+action+target+destination, clause)]
        neutral = {"可以", "好的", "好", "确认", "我确认", "同意", "没问题", "就这样", "就这样安排", "按这个来"}
        if not approved or any(clause not in approved and clause not in neutral for clause in clauses):
            raise ValueError("请明确说“帮我保存这份安排”后再采用；询问保存方式或结果不会执行保存。")
    if (quote not in message or quoted or inquiry and (not explicit_request or read_request) or not affirmative_action_source(message, quote, verbs[command.action])
        or command.action == "adopt" and re.search(r"(?:等|待|确认后|之后|以后|再保存|先看|先展示|先给我看)", message)):
        raise ValueError("这项操作需要本次明确请求，不能借用引述、否定或未来的保存授权。")
    if command.action != "generate" and command.plan is not None:
        raise ValueError("调整只接受当前候选的局部操作，不能替换整份草稿。")
    if command.action != "modify" and command.patches:
        raise ValueError("时长修改必须绑定当前候选。")
    if command.source_refs and command.action != 'generate':
        raise ValueError('来源片段仅用于新候选生成；修改需引用当前活动。')


def literal_minutes(quote):
    values = [int(m) for m in re.findall(r"(\d+)\s*分钟", quote)]
    values += [round(float(m) * 60) for m in re.findall(r"(\d+(?:\.\d+)?)\s*(?:个)?小时", quote)]
    for word, number in {"半小时": 30, "一小时": 60, "一个小时": 60, "两小时": 120,
                         "两个小时": 120, "三小时": 180, "三个小时": 180}.items():
        if word in quote:
            values.append(number)
    return values


def apply_patches(plan, command, message):
    validate_command(command, message)
    if not command.patches:
        raise ValueError("这次调整尚缺少可核对的活动和时长，原候选保持不变。")
    result = plan.model_dump(mode="json")
    items = {item["item_ref"]: item for day in result["days"] for item in day["items"]}
    refs = [patch.item_ref for patch in command.patches]
    if len(set(refs)) != len(refs):
        raise ValueError("一个活动不能同时应用两项时长。")
    from app.assistant_capabilities import affirmative_action_source, affirmative_entity_source
    clauses = [part.strip() for part in re.split(r"[，,；;。!?！？\n]|但是|但现在|而现在", message) if part.strip()]
    # A directive naming only the working copy selects the mutation surface;
    # it proposes no additional activity operation. Unknown targets/quantities
    # remain obligations and cannot disappear from a compound request.
    changes = [clause for clause in clauses if affirmative_action_source(message, clause, CHANGE_VERBS)
        and not re.fullmatch(r'(?:先|这次)?(?:只|仅)(?:改|修改|调整)(?:当前)?(?:候选|草案|方案)', clause)]
    patch_clauses = {patch.source_quote.strip().rstrip("。.!！?？") for patch in command.patches}
    if any(clause not in patch_clauses for clause in changes):
        raise ValueError("本轮还有未处理的变更，整项修改尚未生效。请先核对所有变化，再单独确认保存。")
    required = {item["item_ref"] for item in items.values() if item["kind"] == "visit" and any(
        affirmative_entity_source(message, clause, CHANGE_VERBS, item["name"].removesuffix("景区"), permission_particles=True) for clause in changes)}
    if not required.issubset(set(refs)):
        raise ValueError("候选操作漏掉了本轮要求调整的活动，尚未应用部分结果。")
    for patch in command.patches:
        validate_command(CandidateCommand(action="modify", source_quote=patch.source_quote), message)
        item = items.get(patch.item_ref)
        # A target and its action must belong to the same source clause. The
        # full compound sentence cannot lend another place's verb or quantity.
        clauses = [part for part in re.split(r"[，,；;。!?！？\n]|但是|但现在|而现在", patch.source_quote) if part.strip()]
        label = item["name"].removesuffix("景区") if item else ""
        local = [part for part in clauses if label and label in part]
        if len(clauses) != 1 or len(local) != 1:
            raise ValueError("每项修改需要对应同一地点的完整独立原句。")
        verbs = {"set": r"改成|改为|调整为|调整到|停留|逛|留", "increase": r"多留|多待|增加|延长",
            "decrease": r"少留|少待|少逛|减少|缩短"}
        if (sum(other["kind"] == "visit" and other["name"].removesuffix("景区") == label for other in items.values()) != 1
            or not affirmative_entity_source(message, patch.source_quote, verbs[patch.operation], label, permission_particles=True)):
            raise ValueError("修改目标存在同名或跨子句歧义，原候选保持不变。")
        supported_actions = list(re.finditer(verbs[patch.operation], patch.source_quote))
        if any(not any(action.start() <= match.start() and action.end() >= match.end() for action in supported_actions)
            for match in re.finditer(CHANGE_VERBS, patch.source_quote)):
            raise ValueError("同一子句还含有未支持的其他操作，尚未应用。")
        target = re.search(r"(?:"+verbs[patch.operation]+r")([^，,；;。]*)$", patch.source_quote)
        final_minutes = literal_minutes(target[1]) if target else []
        explicit = final_minutes == [patch.duration_minutes]
        allocated = (patch.operation in {"increase", "decrease"} and patch.quantity_source == "planning_allocation"
            and target is not None and not literal_minutes(patch.source_quote) and re.search(r"一点|一些|稍微", target[1]))
        if (item is None or item["kind"] != "visit" or not label or label not in patch.source_quote
            or patch.source_quote not in message or not (explicit or allocated)
            or patch.operation == "set" and re.search(r"再多|再少|多留|少留|增加|减少|延长", patch.source_quote)):
            raise ValueError("修改目标或时长无法绑定本次原句，原候选保持不变。")
        # An explicit fixed interval cannot silently change its end boundary.
        if item.get("end_time"):
            raise ValueError("这个活动有明确起止时间，请同时确认新的结束时间。")
        duration = (item["duration_minutes"] + patch.duration_minutes if patch.operation == "increase" else
            item["duration_minutes"] - patch.duration_minutes if patch.operation == "decrease" else patch.duration_minutes)
        item.update(duration_minutes=duration, duration_source="user_explicit" if explicit else "planning_allocation", source_quote=patch.source_quote)
    return DraftPlan.model_validate(result)
