"""Clause polarity shared by typed requirement capture and planning goals.

This classifies reference versus current instruction; it does not resolve venues
or give a natural-language statement authority over a formal itinerary.
"""
import re


def is_context_only_statement(clause: str) -> bool:
    """Recognize complete provenance/experience assertions, not word mentions.

    Context stays in the original message. It is not a desired future travel
    outcome, so it must not acquire an active requirement identity. Any explicit
    directive wins, including unusual user constraints mentioning tests/visits.
    Deliberately bounded: unrecognized statements keep existing capture behavior.
    """
    text = clause.strip(" \t。.!！")
    if re.search(r"希望|要求|请|不要|不想|必须|不能|不得|禁止|避免|需要|安排|确认|标记", text):
        return False
    purpose = r"(?:这(?:次|趟)?(?:旅行|行程|记录|请求|操作)?|本次(?:旅行|行程|记录|请求|操作)?|此(?:旅行|行程|记录|请求|操作)?)?\s*(?:只是|仅|只)?(?:用于|用来|作为|供)\s*(?:(?:软件|系统|应用|功能|接口|产品)\s*)?(?:验收|测试|调试)(?:使用|之用)?"
    experience_subject = r"(?:我(?:们)?|(?:此次|这次|本次|本轮)(?:(?:软件|系统|应用|功能|接口|产品)\s*)?(?:验收|测试|调试))"
    experience = rf"(?:{experience_subject}\s*)?(?:(?:此前|之前|目前|现在|实际|并|尚|还)\s*)*(?:未|没有|并未|从未)\s*(?:实际|真正)?\s*(?:到访|去过|到过|游览)(?:过|这些地方|该地点|此地|这里|那里)?"
    return bool(re.fullmatch(rf"(?:{purpose}|{experience})(?:\s*[/、（(]\s*(?:{purpose}|{experience})\s*[）)]?)?", text))


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
