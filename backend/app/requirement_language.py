"""Clause polarity shared by typed requirement capture and planning goals.

This classifies reference versus current instruction; it does not resolve venues
or give a natural-language statement authority over a formal itinerary.
"""
import re


def current_user_evidence_reason(message: str, quote: str) -> str | None:
    """Bound literal evidence to a current declaration, across all projections.

    A condition about an accompanying parent is still the user's condition;
    reported speech, quoted text and unadopted hypotheses are not declarations.
    """
    if not quote or quote not in message:
        return "source_quote_not_current_user"
    if re.match(r"^(?:如果|假如|假设|要是)", message.strip()) and not re.search(r"但我|不过我|我决定|还是决定", message):
        return "hypothetical_source"
    if re.search(r"如果|假如|假设|要是|比如|他说|她说|有人说|攻略说|朋友说|[“”「」\"]", quote):
        return "non_declarative_source"
    if any(quote in part for part in re.findall(r'[“「\"](.*?)[”」\"]', message)):
        return "quoted_source"
    prefix = message[:message.find(quote)]
    if re.search(r"(?:如果|假如|假设|要是)[^，。；!?！？]*$", prefix):
        return "hypothetical_source"
    if re.search(r"(?:朋友|他说|她说|有人说|攻略说)[^，。；!?！？]*$", prefix):
        return "third_party_source"
    if re.match(r"(?:(?:我(?:的)?)?朋友|他|她)(?:喜欢|偏好|希望|要求|不喜欢|不想)", quote.strip()):
        return "third_party_source"
    return None


def term_is_negated(clause: str, start: int) -> bool:
    """Only identify negation of this term; never manufacture its opposite."""
    return bool(re.search(r"(?:不(?:再|太)?喜欢|不再偏好|不想|不太想|不要|不必|不用|无需|避免|禁止|不得|不能|不爱|不需要)[^，,；;。\n]{0,12}$", clause[:start]))


def has_continuous_walking_scope(clause: str) -> bool:
    return bool(re.search(r"连续|单次|每次|一次|内部|(?:内|里面|里).{0,8}(?:步行|走路)", clause))


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
    return 'revoke' if re.search(r"取消|撤销|不再(?:要求|喜欢|偏好)", revoke_text) else 'current'


def current_goal_text(text: str) -> str:
    return '，'.join(clause for clause in requirement_clauses(text) if clause_polarity(clause) == 'current')
