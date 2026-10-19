"""Travel goal routing precedes tool selection and planning entity resolution.

Rules establish explicit user authorization; model tool choices cannot promote
an informational turn to a formal itinerary request. Unknown turns stay in
Companion. Signals are short labels, never model reasoning.
"""
import re

from app.schemas import TravelGoalRouting

_DISCOVERY = re.compile(r"不知道去哪|没想好去哪|目的地.{0,4}(?:没定|未定)|出去.{0,6}(?:休息|放松|散心)|散散心|想找个.{0,6}地方|周末想找个")
_QUESTION = re.compile(r"为什么|如何|怎样|怎么|什么|哪个|好不好|是否|值得|适合|会不会|还是|[吗呢][？?。]*$|只问|只解释|先不修改|先别修改")
_INFORMATIONAL = re.compile(r"了解|介绍|聊聊|利弊|我喜欢|我不喜欢|历史|文化|理由|解释|推荐")
_ACTION = re.compile(
    r"^(?:(?:那|就|我想|我希望|我准备|请|帮我|替我|给我|直接|请帮我)\s*)*"
    r"(?:根据.{1,80}?(?=生成|制定|规划|安排))?"
    r"(?:(?:把|将).{0,50})?(?:重新规划|重新安排|重新调整|缩短为|从头规划|规划|安排|生成|制定|创建|"
    r"调整|修改|重排|替换|换掉|换成|改成|改为|改到|改得|移到|挪到|删掉|删除|取消|加进去|加入|添加|增加|排进|放进|控制|降低|调松|放慢)|"
    r"(?:帮我|替我|请帮我|给我).{0,20}(?:规划|安排|排进|放进去|调整|修改|降低|降到|调松|换掉|排一下|做.{0,12}(?:行程|规划))|"
    r"^(?:我希望)?(?:第.{1,6}天|预算|行程|这次旅行).{0,30}(?:换掉|加入|添加|移到|重新调整|控制在|降到|调松|丰富|轻松一点)|"
    r"^(?:我)?希望(?:这次)?行程(?:中|里)?(?:包含|加入)|"
    r"^(?:就)?按.{0,12}(?:建议|方案)(?:[，,]?但保留.{0,25}|来|安排|调整|执行)?[吧。！!]*$"
)
_NEGATED = re.compile(r"不要|先别|暂不|不需要|不用|先不|只(?:问|解释|分析|了解)|假如|假设|如果.*(?:会|怎样|如何)")
# Reuse/rescheduling is an explicit operation. A destination, date or duration
# alone describes a possible trip and never authorizes its creation.
_NEW_TRIP = re.compile(r"^(?:(?:那|请|帮我|替我|给我)\s*)*(?:参考.{0,20}(?:行程|旅行).{0,12}再去|改期)")
_SUPPLEMENT = re.compile(r"^(?:[一二三四五六七八九十两\d]+个人|[一二三四五六七八九十两\d]+天|预算|总预算|每天|每日|\d{1,4}[年月/-]|[一二三四五六七八九十]+月|今天|明天|后天|下周|出发|返程|不是.+改成)")
_EXECUTION = re.compile(r"再待|多待|再停留|延长停留|提前离开|早点离开|结束游玩|extend\s+(?:my\s+)?stay|leave\s+early", re.I)


def route_travel_goal(message: str, history: list[dict] | None = None, *, pending_action: dict | None = None) -> TravelGoalRouting:
    text = message.strip()
    history = history or []
    clauses = [clause.strip() for clause in re.split(r"[，,。；;？?]|然后|并且|并(?=帮我|把|将)|就(?=帮我|请|把|将)", text) if clause.strip()]
    action = any(_ACTION.search(clause) and not _NEGATED.search(clause) and not _QUESTION.search(clause)
                 for clause in clauses)
    action = action or any(re.search(r"(?:请|帮我|替我|给我).{0,6}(?:形成|整理|保存).{0,12}(?:旅行安排|出游安排|安排建议|灵活安排)", clause)
        and not _NEGATED.search(clause) and not _QUESTION.search(clause) for clause in clauses)
    # "能不能帮我安排" asks the assistant to act; "怎么安排" asks for advice.
    action = action or any(re.search(r"(?:能不能|能否|可以)(?:请)?帮我.{0,20}(?:安排|规划|调整|修改)", clause)
                           and not _NEGATED.search(clause) for clause in clauses)
    previous = bool(re.search(r"刚才|之前|前面|第.{1,4}个建议|上面|那个安排|你推荐|^那", text) and history)
    references = list(dict.fromkeys(re.findall(r'[《「“"]([^》」”"]{1,40})[》」”"]', text)))[:20]
    common = dict(referenced_entities=references, referenced_previous_decision=previous,
        live_fact_likely_required=bool(re.search(r"天气|营业|开放|闭馆|票价|门票|路况|实时|当前GPS|现在|今天", text)))
    if _EXECUTION.search(text) and not _QUESTION.search(text) and not _NEGATED.search(text):
        return TravelGoalRouting(goal_type="trip_execution", target_runtime="execution", confidence=0.98,
            mutation_requested=False, trip_context_required=True, knowledge_required=False,
            signals=["explicit_execution_action"], **common)

    discovery = bool(_DISCOVERY.search(text))
    creation = bool(_NEW_TRIP.search(text)) and not _QUESTION.search(text) and not _INFORMATIONAL.search(text) and not discovery and not _NEGATED.search(text)
    if action or creation:
        replan = bool(re.search(r"重新规划|重排|重新安排整个|从头规划", text))
        modification = bool(re.search(r"换|改|移到|挪到|删|替换|加入|添加|增加|排进|控制|预算|调松|放慢|重新调整|按.{0,12}建议|(?:把|将).{0,20}安排到|安排进去", text))
        full_first_plan = bool(re.search(r"(?:生成|制定|规划|安排).{0,12}(?:完整|整趟|整个|首版|初版).{0,8}(?:行程|旅行)|(?:生成|制定).{0,8}(?:行程|旅行)", text))
        goal = "replan" if replan else "trip_modification" if modification and not creation and not full_first_plan else "trip_planning"
        return TravelGoalRouting(goal_type=goal, target_runtime="planning", confidence=0.96,
            mutation_requested=True, trip_context_required=goal != "trip_planning", knowledge_required=False,
            signals=["explicit_user_planning_request"], **common)

    # A field answer continues only a user-authorized planning request. New
    # questions and destination choices cannot inherit mutation authorization.
    latest = history[-1] if history else {}
    prior_goal = latest.get("goal_routing")
    prior_planning = (prior_goal.get("target_runtime") == "planning" if prior_goal else
                      bool(history and route_travel_goal(str(latest.get("user", ""))).target_runtime == "planning"))
    selection = bool(re.fullmatch(r"(?:就)?第[一二三四五六七八九十\d]+个[。！!]*", text))
    budget_answer = bool(re.fullmatch(r"\d+(?:(?:元|块)(?:左右|以内)?|左右|以内)[。！!]*", text))
    time_answer = bool(re.fullmatch(r"(?:早上|上午|中午|下午|晚上)(?:吧)?[。！!]*", text))
    holiday_date_answer = bool(re.fullmatch(r"(?:国庆|春节|五一|中秋)(?:第[一二三四五六七八九十\d]+天)?出发[。！!]*", text))
    duration_correction = bool(re.fullmatch(r"还是[一二三四五六七八九十两\d]+天[。！!]*", text))
    if (_SUPPLEMENT.search(text) or duration_correction or selection or budget_answer or time_answer or holiday_date_answer) and (duration_correction or not _QUESTION.search(text)) and not discovery and prior_planning and latest.get("status") not in {"rejected", "failed", "cancelled"}:
        return TravelGoalRouting(goal_type="trip_planning", target_runtime="planning", confidence=0.86,
            mutation_requested=False, trip_context_required=False, knowledge_required=False,
            signals=["planning_field_follow_up"], **common)

    if discovery:
        goal, confidence = "destination_discovery", 0.94
    elif re.search(r"为什么|理由|解释|历史|文化|来历|特色", text):
        goal, confidence = "explanation", 0.94
    elif re.search(r"对比|比较一下|相比|还是|和.{0,12}(?:哪个|更适合|比较)|有什么不同", text):
        goal, confidence = "comparison", 0.94
    elif re.search(r"推荐|建议|适合|值得|住哪个|住哪里|住哪", text):
        goal, confidence = "recommendation", 0.93
    elif re.search(r"有什么|有哪些|开放|天气|多少钱|票价|门票", text):
        goal, confidence = "destination_exploration", 0.93
    elif _QUESTION.search(text) or re.search(r"你觉得|你怎么看|我喜欢|我不喜欢|不太喜欢|不喜欢", text):
        goal, confidence = "travel_advice", 0.92
    else:
        goal, confidence = "travel_chat", 0.55
    if text in {"你好", "谢谢", "你好。", "谢谢。"}:
        confidence = 0.95
    return TravelGoalRouting(goal_type=goal, target_runtime="companion", confidence=confidence,
        mutation_requested=False, trip_context_required=previous,
        knowledge_required=goal not in {"travel_chat", "destination_discovery"},
        clarification_needed=not history and bool(re.fullmatch(r"那呢[？?。]*|那个[？?。]*", text)),
        signals=[f"companion_{goal}" if confidence >= 0.9 else "uncertain_no_mutation_authorization"], **common)
