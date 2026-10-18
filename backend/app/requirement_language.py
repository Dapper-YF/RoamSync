"""Clause polarity shared by typed requirement capture and planning goals.

This classifies reference versus current instruction; it does not resolve venues
or give a natural-language statement authority over a formal itinerary.
"""
import re


def requirement_clauses(text: str) -> list[str]:
    return re.split(r"[，,；;。\n]+|但是|但现在|而现在", text)


def clause_polarity(clause: str) -> str:
    historical = bool(re.search(r"已(?:经)?(?:撤销|取消)|(?:之前|此前|曾经)(?:撤销|取消)", clause))
    restoration = re.search(r"恢复|加回|重新启用|重新加入", clause)
    refused_restoration = re.search(r"(?:不要|不必|无需|不再|别|不)[^，,；;。\n]{0,40}(?:恢复|加回|重新启用|重新加入)", clause)
    if refused_restoration or (historical and not restoration):
        return 'historical_reference'
    if restoration:
        return 'current'
    revoke_text = re.sub(r"不要(?:撤销|取消)|别再?(?:撤销|取消)", '', clause)
    return 'revoke' if re.search(r"取消|撤销|不再要求", revoke_text) else 'current'


def current_goal_text(text: str) -> str:
    return '，'.join(clause for clause in requirement_clauses(text) if clause_polarity(clause) == 'current')
