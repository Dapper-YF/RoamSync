"""Bounded local control for model-authored state assertions, not a fact checker.

Never certify free model prose from a nearby fact/source. Verified live values
remain owned by the existing server Fact Resolver renderers. No model retry.
"""
import re
from dataclasses import dataclass, field

MONEY = re.compile(r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千两几数]+)(?:\s*[—–~至到-]\s*\d+)?\s*(?:元|块钱|美元|日元|欧元)")
QUEUE = re.compile(r"(?:排队|等候|等待).{0,10}(?:\d+|[一二三四五六七八九十两几]+)\s*(?:分钟|小时)|(?:几乎|基本|完全)?(?:不(?:用|需要|需|要)|无需|免)排队|排队.{0,6}(?:很短|很快)|(?:保证|一定|肯定|必定).{0,10}(?:避开|躲开).{0,8}(?:排队|人流|人群)")
CROWD = re.compile(r"(?:行人|游客|游人|人流|人群|旅行团|人)(?:非常|特别|相对|比较|更|很|通常|一般|往往)?(?:少(?:得多)?|不多|很少|多得多|很多)|(?:几乎|基本)(?:没有|不见)(?:人|游客|旅行团)|(?:一定|保证|肯定|必定|绝对|十分|非常|特别|相对|比较|很)(?:安静|清幽)|小而静|人(?:立刻|马上|也)少|(?:尤其|特别|一定|肯定|能)(?:安静|清静)|基本没什么人|人流(?:最|较)?集中|主街人多|人数多|人流明显更多|比.{0,18}(?:安静|清静|清净|清幽)|没有.{0,8}拥挤|(?:比.{0,18})?(?:安静|清静|清净|清幽)(?:得多|许多)|氛围安静|人流高峰.{0,15}(?:点|时)|(?:能|天然|最大程度).{0,8}(?:避开|躲开).{0,8}(?:排队|人流|人群)")
OPERATING = re.compile(r"(?:今天|明天|今晚|现在|目前|当天|下午场|上午场).{0,20}(?:开门|开放|营业|闭馆|演出|场次|场多|多是|有\d+场)|(?:每天|每日|每晚|每周).{0,15}(?:开放|营业|演出|场)|(?:开门|开馆|营业|开放).{0,8}\d{1,2}(?:点|时|[:：]\d{2})|(?:今晚|当晚|晚上)(?:可以|可|能)?看一场|(?:偶有|常有|经常有).{0,20}(?:演出|场次)")
AVAILABILITY = re.compile(r"(?:还有|有|剩余|剩下|可以|能|无需).{0,8}(?:预约名额|余票|空位)|(?:预约|门票|名额).{0,8}(?:充足|可用|售罄|约满|已满|有余|紧张|压力小)|(?:保证|一定|肯定).{0,8}(?:入馆|进馆|订到|约到)")
PHOTO = re.compile(r"摄影|拍照|拍摄|出片|机位|构图|长焦|快门|感光度|镜头")
HISTORICAL = re.compile(r"(?:公元|建于|始建|历史上|古代|唐代|宋代|明代|清代|民国时期|曾经|当时)")


@dataclass
class TextControl:
    text: str
    issues: list[str] = field(default_factory=list)
    removed_clauses: int = 0


def control_model_text(text: str, request: str) -> TextControl:
    """Remove affected clauses, keep adjacent culture/recommendation clauses.

    Numeric dates, dynasties, quantities and user budget strategies survive.
    '通常/据说/可能' never supply evidence for a price or state assertion.
    This lexical coverage is intentionally measured, not claimed exhaustive.
    """
    output, issues, removed = [], [], 0
    photo_requested = bool(PHOTO.search(request) or re.search(r"照片|照相",request))
    # Delimiters retained with each clause; do not truncate/salvage model JSON.
    for clause in re.findall(r"[^，,。；;！？!?\n]+[，,。；;！？!?\n]*|[，,。；;！？!?\n]+",text):
        reasons=[]
        caveat = bool(re.search(r"不能保证|无法保证|不保证|无法确认|尚未确认|需要核实|需确认|不能确认", clause))
        if MONEY.search(clause) and not (re.search(r"预算|预留|控制在|支出上限",clause)
            and not re.search(r"票价|售价|收费|只需|只要|每人|茶位费",clause)):
            reasons.append("output_unverified_price")
        if QUEUE.search(clause) and not caveat: reasons.append("output_unverified_queue")
        if CROWD.search(clause) and not HISTORICAL.search(clause) and not caveat:
            # A preference/conditional strategy is not an observation or promise.
            if not re.search(r"(?:喜欢|偏好|想找|希望|寻找|选择).{0,8}(?:安静|清幽)|(?:如果|若|假如).{0,12}(?:人多|拥挤)",clause):
                reasons.append("output_unverified_crowding")
        if OPERATING.search(clause) and not HISTORICAL.search(clause) and not caveat: reasons.append("output_unverified_operation")
        if AVAILABILITY.search(clause) and not caveat and not re.search(r"(?:核实|确认|查询|查看|留意).{0,12}(?:预约|名额|余票|场次)",clause):
            reasons.append("output_unverified_availability")
        # Unsolicited extensions are prompt-controlled; do not erase useful culture by keyword.
        if reasons:
            # Keep paragraph boundaries when a deleted clause ended a list item.
            if "\n" in clause:
                output.append("\n" * clause.count("\n"))
            removed+=1
            issues.extend(reasons)
        else:
            output.append(clause)
    if not removed:
        return TextControl(text)
    cleaned="".join(output).strip("，,；;。 \n")
    cleaned=re.sub(r"[，,][ \t]*(\n+\s*\d+[.)）])",r"。\1",cleaned)
    # Remove empty headings/list items left by clause deletion, not numbers.
    cleaned=re.sub(r"(?m)^\s*\d+[.)、]\s*[^\n。]{0,35}[：:]\s*$","",cleaned).strip()
    if cleaned and cleaned[-1] not in "。！？!?": cleaned+="。"
    return TextControl(cleaned,list(dict.fromkeys(issues)),removed)


def control_draft(draft, request):
    """Control every model-authored surface before identities/persistence.

    Only the generation branch calls this; original rationale and server-owned
    fact/assertion rendering bypass it. Empty dependent suggestions are dropped.
    """
    from app.companion_contracts import CompanionDraft
    issues = []
    def clean(value):
        result = control_model_text(value, request)
        issues.extend(result.issues)
        return result.text
    suggestions = []
    for suggestion in draft.suggestions:
        title = clean(suggestion.title).rstrip("。")
        summary = clean(suggestion.summary)
        reasons = [text for reason in suggestion.reasons if (text := clean(reason))]
        if title and summary:
            suggestions.append(suggestion.model_copy(update=dict(title=title, summary=summary, reasons=reasons)))
    updates = {"suggestions": suggestions}
    if isinstance(draft, CompanionDraft):
        response = clean(draft.response_text)
        updates["response_text"] = response or "这次生成的内容没有留下足够可靠的建议。可以先从你的兴趣和步行节奏讨论，具体费用及现场情况需要另行确认。"
        if not response: issues.append("output_no_useful_content")
    else:
        updates["agent_claims"] = [claim.model_copy(update={"text": text}) for claim in draft.agent_claims if (text := clean(claim.text))]
    if draft.comparison:
        comparison = draft.comparison
        options = [value for item in comparison.options if (value := clean(item))]
        dimensions = [value for item in comparison.dimensions if (value := clean(item))]
        summary = clean(comparison.summary)
        updates["comparison"] = comparison.model_copy(update=dict(options=options, dimensions=dimensions, summary=summary)) if len(options) >= 2 and summary else None
    return draft.model_copy(update=updates), list(dict.fromkeys(issues))


def live_gap_text(request: str) -> str:
    if re.search(r"预约|名额|余票|订票",request):
        return "我目前无法核实所问日期的预约名额或余票。请查看场馆官方预约页面的日期和可选时段，以实际可提交的预约结果为准。"
    if re.search(r"票价|门票|价格|多少钱|消费|收费",request):
        return "我目前无法核实适用的最新价格，不能确认这次费用。请查看场馆官方购票页或商家价目表，确认日期、票种及优惠条件。"
    if re.search(r"排队|人流|人群|拥挤|游客|安静",request):
        return "我目前无法核实现场人流或排队情况。可以先查看景区官方客流提示或联系场馆；临行再确认，不能保证某个时段一定安静或免排队。"
    if re.search(r"天气|下雨|气温|降雨",request):
        return "我目前无法核实所问地点和时段的天气，没有取得可靠数据。请查看当地气象部门的最新预报，临行留意更新。"
    if re.search(r"开门|开放|营业|闭馆|关门|开馆",request):
        return "我目前无法核实所问日期的开放安排。请查看场馆官方公告，并确认临时调整和入馆要求。"
    if re.search(r"灯会|活动|节庆|展览|音乐节|场次|演出",request):
        return "我目前无法核实这次活动的具体日期、地点或场次。请查看主办方最新公告及官方售票信息，确认是否有临时调整。"
    if re.search(r"交通|车程|路线|多久|耗时|路况",request):
        return "我目前无法核实所问路线的实时交通情况。请在地图服务中按出发时间和交通方式查询，并留意临时管制。"
    return "我目前无法核实这个状态，没有可靠信息可以确认。请通过相关场馆或主办方的官方渠道核实。"


def source_gap_text(request: str) -> str:
    if re.search(r"碑|拓本|版本|训诂",request):
        return "我目前没有足够可靠的原文或研究资料支持这个具体问题。你可以提供碑名、拓本或文献内容，我再基于材料解释；不会补造出处或版本差异。"
    return "现有来源不足以为这个问题提供可靠出处。你可以提供指定文献或网页内容，我再据此解释；如果只需一般背景，也可以继续讨论。"
