"""Conservative advisory, never an authoritative intent router or fact resolver.

Rules are a backstop with known recall limits. Consumers must also enforce the
unconditional evidence_kind and verify any operational claim independently.
"""
import re
import unicodedata

from .models import RetrievalAdvisory

_OPERATIONAL = re.compile(
    r"营业|开放时间|开门|关门|闭馆|闭园|开到|几点开|几点关|(?:何时|什么时候).*开放|开放吗|能进去|可以进去|门票|票价|票库存|余票|价格|多少钱|"
    r"天气|气温|下雨|降雨|路况|交通状况|实时交通|堵车|拥堵|ETA|GPS|定位|日落|日出|"
    r"玩了多久|待了多久|停留了多久|走了多久|到达时间|多久能到|要走多久|要开多久|车次|班次|预约|"
    r"opening\s+hours?|open\s+(?:today|now)|clos(?:ed|es?|ing)|tickets?|prices?|costs?|weather|"
    r"rain(?:ing)?|traffic|congestion|\beta\b|\bgps\b|sunset|sunrise|availability|sold\s+out|"
    r"how\s+long.*(?:get|reach|been|spent)|current\s+location",
    re.IGNORECASE,
)
_TEMPORAL = re.compile(r"今天|今日|明天|现在|当前|实时|此刻|临时|最新|今晚|today|tomorrow|tonight|currently|right now", re.I)
_DECISION = re.compile(r"为什么.*(?:建议|推荐|安排)|为何.*(?:建议|推荐|安排)|why.*(?:recommend|suggest|schedule)", re.I)
_SCHEDULE = re.compile(r"\d{1,2}\s*(?:点|[:：]\d{2}|[ap]m)|前后活动|行程约束|schedule|itinerary", re.I)


def assess_suitability(query: str) -> RetrievalAdvisory:
    text = unicodedata.normalize("NFKC", query)
    live = bool(_OPERATIONAL.search(text) or _TEMPORAL.search(text))
    decision = bool(_DECISION.search(text) and _SCHEDULE.search(text))
    reasons = []
    if live:
        reasons.append("operational_or_time_sensitive_question_requires_live_evidence")
    if decision:
        reasons.append("recommendation_timing_requires_planning_decision_context_and_live_conditions")
        live = True
    return RetrievalAdvisory(live_fact_verification_required=live,
                             planning_decision_context_required=decision, reasons=tuple(reasons))
