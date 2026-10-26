"""Literal daily-window evidence, distinct from venue clocks and appointments."""
import re

from app.drafts.timing import quoted_clocks
from app.requirement_language import current_user_evidence_reason

CLOCK=r'(?:[01]?\d|2[0-3])(?::[0-5]\d|(?:点|时)(?:[0-5]?\d分?|半|整)?)'


def daily_window_source(message,start,end,history=()):
    desired=((start.hour,start.minute),(end.hour,end.minute))
    def find(text):
        clauses=[part.strip() for part in re.split(r'[。；;!?！？\n]',text) if part.strip()]
        for clause in clauses:
            if current_user_evidence_reason(text,clause):
                continue
            if re.search(r'(?:时间|窗口|时段).{0,8}(?:未定|待定|不定|撤销|取消)|(?:撤销|取消).{0,8}(?:时间|窗口|时段)',clause):
                return (),None
            patterns=[rf'{CLOCK}\s*(?:—|–|-|~|～|至|到)\s*{CLOCK}\s*(?:期间)?\s*(?:游玩|游览|活动|可安排|安排日程)',
                rf'(?:每天|当日|当天|游玩时间|可安排时间|活动时间)?\s*{CLOCK}\s*(?:开始|出发|起)\s*[，,、]?\s*{CLOCK}\s*(?:前)?(?:结束|截止|收工)']
            matches=sorted([m for pattern in patterns for m in re.finditer(pattern,clause)],key=lambda m:m.start())
            if matches:
                match=matches[-1]
                from app.assistant_memory import _affirmative_scalar_token
                if not _affirmative_scalar_token(clause,match.start(),match.end()):
                    return (),None
                # A daily boundary is its own clause, not two venue attributes.
                prefix=re.split(r'[，,]',clause[:match.start()])[-1].strip()
                if prefix and not re.fullmatch(r'(?:我|我们)?(?:每天|当日|当天|游玩时间|可安排时间|活动时间)?(?:是|为|从|在)?',prefix):
                    continue
                times=[next(iter(quoted_clocks(m[0]))) for m in re.finditer(CLOCK,match[0])]
                return tuple(times),match[0]
        return None
    current=find(message)
    if current is not None:
        return current[1] if current[0]==desired else None
    if re.search(r'(?:游玩|每日|活动|安排).{0,6}(?:时间|窗口).{0,8}(?:未定|不定|待定|撤销|取消)',message):
        return None
    reference=r'(?:请)?(?:沿用|按|照)(?:刚才|前面|原来|之前|上一条|上次)(?:的)?'
    inherited=[clause.strip() for clause in re.split(r'[。；;!?！？\n]',message)
        if re.match(reference,clause.strip()) and re.search(r'时间|窗口|要求|条件',clause)
        and current_user_evidence_reason(message,clause.strip()) is None]
    if not inherited:
        return None
    clocks=list(re.finditer(CLOCK,message))
    if clocks:
        # Repeating exactly the prior bounds inside an explicit condition
        # inheritance is not a new venue/appointment clock. Every current
        # clock must belong to that one range; never ignore another time.
        if len(clocks)!=2:
            return None
        ranges=[(clause,match) for clause in inherited for match in re.finditer(
            rf'{CLOCK}\s*(?:—|–|-|~|～|至|到)\s*{CLOCK}',clause)]
        if len(ranges)!=1:
            return None
        clause,match=ranges[0]
        prefix=clause[:match.start()]
        if (not re.fullmatch(reference+r'(?:全部|所有|完整|日期|时间|游玩|每日|活动|要求|条件|窗口|时段|[、，,和与及\s])*',prefix)
            or re.search(r'预约|开放|闭馆|闭园|营业',clause)):
            return None
        times=tuple(next(iter(quoted_clocks(m[0]))) for m in re.finditer(CLOCK,match[0]))
        if times!=desired:
            return None
        from app.requirement_language import is_context_only_statement
        condition=r'(?:[、和与及\s]*(?:(?:[一二三四五六七八九十两\d]+)(?:小时|分钟))?(?:日期|时间|窗口|时段|午餐|步行|交通|要求|条件))*'
        tails=[part.strip() for part in re.split(r'[，,]',clause[match.end():]) if part.strip()]
        if any(not (re.fullmatch(condition,part) or is_context_only_statement(part)) for part in tails):
            return None
    for turn in reversed(history):
        text=turn.get('user','')
        if re.search(r'(?:时间|窗口|时段).{0,8}(?:未定|待定|撤销|取消)|(?:撤销|取消).{0,8}(?:时间|窗口|时段)',text):
            return None
        result=find(text)
        if result is not None:
            return result[1] if result[0]==desired else None
    return None
