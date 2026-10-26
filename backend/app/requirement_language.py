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


def continuous_walking_identity(clause: str) -> tuple[str, str, str] | None:
    """Literal subject + walking predicate; uncertain identities never match.

    This is not a person resolver: an unspecified subject cannot stand in for
    a named subject, and an internal scope cannot stand in for continuous scope.
    """
    text = re.sub(r"第[一二三四五六七八九十\d]+天", "", clause)
    text = re.sub(r"^(?:请|现在|这次|撤销|取消|不再要求|：|\s)+", "", text)
    walking = re.search(r"(?P<mode>连续|单次|每次|一次)(?:步行|走路)", text)
    if not walking:
        return None
    subject = text[:walking.start()].strip()
    # A compound or qualified subject needs an explicit identity/clarification.
    if re.search(r"和|与|及|、|或|在|内|里", subject):
        return None
    predicate = text[walking.end():]
    if re.search(r"(?:不|不能|不得|不应)超过|最多|上限", predicate):
        relation = "upper_bound"
    elif re.search(r"至少|下限|不少于", predicate):
        relation = "lower_bound"
    else:
        return None
    return subject, walking["mode"], relation


def is_context_only_statement(clause: str) -> bool:
    """Recognize complete provenance/experience assertions, not word mentions.

    Context stays in the original message. It is not a desired future travel
    outcome, so it must not acquire an active requirement identity. Any explicit
    directive wins, including unusual user constraints mentioning tests/visits.
    Deliberately bounded: unrecognized statements keep existing capture behavior.
    """
    text = clause.strip(" \t。.!！")
    workflow = (r'(?:请|仍然|依然|仍|先|暂且|暂时|现在|还|只|仅|再|等我确认后|看过再|不要|不|别|不用|暂不)*'
        r'(?:保存|采用|展示|生成|修改|调整)(?:(?:当前|这|那)(?:的|份|个)?)?'
        r'(?:候选|方案|草案|安排|行程)?(?:给我看|给我看看|让我看看|供我查看)?(?:并保存|再保存)?(?:了|吧|即可|就行)?')
    if re.fullmatch(workflow, text):
        # Approval/workflow controls are not travel outcome requirements. They
        # remain in source messages and go through the action authorization gate.
        return True
    # A complete instruction to retain named saved fields constrains this
    # edit; it does not create a new durable preference or requirement. Values
    # and unknown subjects cannot match this closed field grammar.
    field = r'(?:活动|安排|午餐留白|午餐|留白|日期|交通方式|个人偏好|行程要求|偏好|要求|预算|人数)'
    preserved = rf'(?:其他|其余|剩余|原有|现有)?{field}(?:[、和及与\s]+(?:其他|其余|剩余|原有|现有)?{field})*(?:都|全部|均)?(?:保持原样|保持不变|维持原样|维持不变|不变)'
    if re.fullmatch(preserved,text):
        return True
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
