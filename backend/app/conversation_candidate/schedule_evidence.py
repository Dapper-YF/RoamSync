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
    if quoted_clocks(message) or re.search(r'(?:游玩|每日|活动|安排).{0,6}(?:时间|窗口).{0,8}(?:未定|不定|待定|撤销|取消)',message):
        return None
    if not re.search(r'(?:沿用|按|照)(?:刚才|前面|原来|之前)(?:的)?(?:全部|所有|完整)?(?:日期[、，,和与及 ]*)?(?:时间|要求|条件)',message):
        return None
    for turn in reversed(history):
        text=turn.get('user','')
        if re.search(r'(?:时间|窗口|时段).{0,8}(?:未定|待定|撤销|取消)|(?:撤销|取消).{0,8}(?:时间|窗口|时段)',text):
            return None
        result=find(text)
        if result is not None:
            return result[1] if result[0]==desired else None
    return None
