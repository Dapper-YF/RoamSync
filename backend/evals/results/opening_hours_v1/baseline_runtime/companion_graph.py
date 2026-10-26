"""Independent, bounded Companion workflow. It has no mutation capabilities."""
import re
from datetime import UTC, datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from app.dialogue_observation import observed_stage

from app.companion_contracts import (AgentAnswerText, CompanionAnswerDraft, CompanionContext,
    CompanionDraft, CompanionExplanation, CompanionProvider, CompanionResult, CompanionSuggestion,
    ContextReaderPort, EntityReference, EvidenceApplicability, GroundedAnswerClaim,
    InformationGap, InformationNeed, KnowledgeRetrievalSummary, KnowledgeToolPort, KnowledgeToolRequest, KnowledgeToolResult,
    SuggestionInteraction)
from app.companion_state import (destination_from_text, interaction_status, project_conversation,
    resolve_suggestions, stable_identity)
from app.companion_information import determine_information_need, explicit_destination, is_formal_decision_question
from app.companion_grounding import (GroundingContractError, advice_issue, assemble_claims,
    validate_provided_refs)
from app.companion_facts import FactToolPort, ForecastPlan, forecast_text


class CompanionContractError(ValueError):
    pass


class CompanionGraphState(TypedDict, total=False):
    session_id: str
    turn_id: str
    messages: list[dict]
    context: CompanionContext
    need: InformationNeed
    gaps: list[InformationGap]
    selected: list[CompanionSuggestion]
    draft: CompanionDraft | CompanionAnswerDraft
    explanation: CompanionExplanation | None
    claim_issues: list[str]
    trace: list[str]
    result: CompanionResult


_TOPIC_LABELS = {
    "lake_formation_year": "西湖形成的确切年份", "lake_formation_history": "西湖形成的历史",
    "heritage_inscription_year": "列入世界遗产名录的年份", "west_lake_construction_period": "堤岛人工要素形成时期",
    "dynasty_history": "相关朝代细节", "historical_figures": "具体历史人物姓名", "origin_story": "起源传说",
    "fame_reasons": "完整的成名原因", "cultural_significance": "更具体的文化意义",
    "landscape_components": "景观构成", "landscape_influence": "对其他园林设计的影响",
    "photography_authority": "官方是否推荐摄影或机位", "photography_elements": "摄影要素",
    "photography_time": "最佳拍摄时段", "photography_scope": "杭州全市摄影适宜性",
    "senior_destination_suitability": "杭州对长辈的具体适宜性", "senior_activity_guidance": "长辈活动强度原则",
    "senior_continuous_visit_time": "连续游览时间建议", "senior_slow_travel": "具体慢游安排",
    "autumn_custom": "秋季赏桂文化", "local_tea_lifestyle": "杭州茶生活主题",
    "daily_local_tea_generalization": "杭州居民每日喝茶的普遍情况", "destination_scope": "杭州全市其他自然景点",
    "source_page_title": "来源网页的原始标题",
}

_ATTRIBUTION_LANGUAGE = re.compile(
    r"资料(?:显示|指出|记载|认为|表明)|根据(?:检索|资料|来源|官方|UNESCO)|"
    r"(?:UNESCO|联合国教科文(?:组织)?|官方).{0,16}(?:推荐|认为|指出|表示|建议)|"
    r"来源.{0,6}(?:指出|表示|认为)|《[^》]{1,80}》.{0,8}(?:指出|认为|推荐|建议)"
)


def _applicability(assertion, evidence) -> EvidenceApplicability:
    value = assertion.applicability
    return value


def _stable_claim_id(session_id: str, turn_id: str, index: int) -> str:
    return stable_identity("claim", session_id, turn_id, index)


def _answer_text(claims: list[GroundedAnswerClaim], gaps: list[InformationGap],
                 suggestions: list[CompanionSuggestion]) -> str:
    sections = []
    facts = [c for c in claims if c.claim_type in {"retrieved_fact", "supported_summary"}]
    interpretations = [c for c in claims if c.claim_type == "curator_inference"]
    advice = [c for c in claims if c.claim_type in {"agent_inference", "recommendation"}]
    if facts:
        sections.append("\n".join(c.text for c in facts))
    if interpretations:
        sections.append("\n".join("如果你喜欢这类体验，可以考虑：" + c.text for c in interpretations))
    if advice:
        sections.append("\n".join(("我的建议是：" if c.claim_type == "recommendation" else "我倾向于认为：") + c.text for c in advice if c.text not in {s.summary for s in suggestions}))
    if suggestions:
        sections.append("\n".join(
            f"{i}. {s.title}：{s.summary}" for i, s in enumerate(suggestions, 1)))
    if gaps:
        distinct = list(dict.fromkeys(g.message for g in gaps if not g.message.startswith("部分生成内容") and g.code in {"knowledge_no_results", "knowledge_unsupported_query", "knowledge_insufficient", "knowledge_unavailable", "live_fact_unavailable"}))
        if distinct and sections:
            shown_scope_gap = False
            for message in distinct:
                if re.search(r"通用|一般", message) and re.search(r"长辈|父母|老人", message):
                    if shown_scope_gap:
                        continue
                    shown_scope_gap = True
                if message.startswith("当前来源资料未覆盖："):
                    sections.append("但关于" + message.split("：", 1)[1] + "，我目前没有足够可靠的资料确认。")
                else:
                    sections.append(message)
        elif distinct:
            sections.append("现有来源不足以核实这个问题。可以补充具体出处，或改为一般介绍。")
    prose = "\n\n".join(sections) or "当前资料不足以给出有来源的确定回答。"
    # Known internal topic names are metadata, including when the model echoes
    # them parenthetically. Keep raw claims for audit; clean final prose only.
    for topic, label in _TOPIC_LABELS.items():
        prose = re.sub(r"[（(]" + re.escape(topic) + r"[）)]", "", prose)
        prose = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(topic) + r"(?![A-Za-z0-9_])", label, prose)
    return prose


def _selected_assertions(context: CompanionContext, need: InformationNeed):
    selected = []
    found_topics = set()
    for evidence in context.knowledge_context:
        for assertion in evidence.answerable_assertions:
            found_topics.update(assertion.topics)
            if not need.requested_fact_topics or set(assertion.topics).intersection(need.requested_fact_topics):
                selected.append((assertion, evidence))
    missing = [topic for topic in need.requested_fact_topics if topic not in found_topics]
    return selected[:10], missing


def build_companion_graph(reader: ContextReaderPort, provider: CompanionProvider,
                          knowledge_tool: KnowledgeToolPort | None = None, fact_tool: FactToolPort | None = None):
    async def interpret_goal(state):
        context = state["context"]
        if context.travel_goal.target_runtime != "companion":
            raise CompanionContractError("Companion runtime cannot handle Planning or Execution goals")
        return {"trace": ["interpret_goal"]}

    async def resolve_conversation(state):
        context = state["context"]
        conversation = project_conversation(state["messages"])
        selected, gaps = resolve_suggestions(context.current_message, conversation)
        if context.travel_goal.clarification_needed and not gaps:
            gaps = [InformationGap(code="ambiguous_suggestion", message="你指的是哪个目的地或哪条建议？请补充一下。")]
        if not re.search(r"第.+(?:个|项)|suggestion_[0-9a-f]{32}", context.current_message) and (
            is_formal_decision_question(context.current_message) or determine_information_need(context, []).live_fact_required
            or re.search(r"历史|文化|来历", context.current_message)):
            # A raw knowledge/fact/schedule subject is not a Suggestion ref just
            # because its name also occurs in one or more recommendation batches.
            selected, gaps = [], []
        with_current = project_conversation([*state["messages"], {"id": state["turn_id"], "user": context.current_message}])
        prior = selected or [conversation.suggestions[ref] for ref in conversation.current_batch][-10:]
        context = context.model_copy(update={
            "current_destination": explicit_destination(context.current_message) or destination_from_text(context.current_message) or conversation.destination,
            "relevant_user_preferences": with_current.preferences,
            "relevant_prior_suggestions": prior,
            "resolved_entities": [EntityReference(kind="suggestion", value=s.suggestion_id) for s in selected],
            "pending_planning_handoff": conversation.pending_handoff,
        })
        return {"context": context, "selected": selected, "gaps": gaps,
                "trace": [*state["trace"], "resolve_conversation"]}

    async def information_need(state):
        context = state["context"]
        need = determine_information_need(context, state["selected"])
        updates = {"pending_planning_handoff": None}
        if need.forecast_required and fact_tool is not None:
            try:
                plan = await fact_tool.plan_forecast(context.current_message,
                    project_conversation(state["messages"]).destination, context.recent_turns)
            except Exception:
                plan = ForecastPlan(message="我现在没有拿到可靠的地点或天气预报数据。")
            updates["forecast_plan"] = plan
            if plan.place_result and plan.place_result.usable_as_current:
                updates["current_destination"] = plan.place_result.requirement.subject.destination
            need = need.model_copy(update={"fact_requirements": plan.requirements})
        if "history_culture" in need.knowledge_types and not state["selected"]:
            updates.update(relevant_user_preferences=[], relevant_prior_suggestions=[])
        return {"need": need, "context": context.model_copy(update=updates),
                "trace": [*state["trace"], "determine_information_need"]}

    async def gather_context(state):
        context, need, gaps = state["context"], state["need"], list(state["gaps"])
        if not gaps:
            context = await reader.load(context, need)
            if context.forecast_plan and context.forecast_plan.requirements and fact_tool is not None:
                try:
                    resolved = list(await fact_tool.resolve_facts(need.fact_requirements))
                    # Trust only typed results for these exact requirements in order.
                    if len(resolved) != len(need.fact_requirements) or any(r.requirement != q for r,q in zip(resolved,need.fact_requirements)):
                        raise ValueError("unrelated fact tool result")
                    context = context.model_copy(update={"resolved_facts": resolved})
                except Exception:
                    context = context.model_copy(update={"forecast_plan": context.forecast_plan.model_copy(update={"message": "我现在没有拿到可靠的天气预报数据。"})})
            if context.forecast_plan:
                if context.forecast_plan.message or not context.resolved_facts or any(not r.usable_as_current for r in context.resolved_facts):
                    gaps.append(InformationGap(code="live_fact_unavailable", message=forecast_text(context.forecast_plan,context.resolved_facts)))
            if need.live_fact_required and (not context.forecast_plan or any(t != "weather" for t in need.fact_types)):
                message = "实时部分目前无法核实；当天开放、天气、花况、价格或交通请以官方最新信息为准。" if not context.forecast_plan else "实时部分的开放、花况、价格或交通目前无法核实，请以官方最新信息为准。"
                gaps.append(InformationGap(code="live_fact_unavailable", message=message))
            if need.knowledge_required:
                result = KnowledgeToolResult(status="unavailable", outcome="retriever_unavailable")
                if knowledge_tool:
                    try:
                        # Project only stable subjects into the knowledge query.
                        # Sending the live clause would correctly trip the
                        # adapter's backstop and discard the stable answer too.
                        query = context.current_message
                        if need.live_fact_required:
                            stable_labels = {"history_general": "西湖历史文化", "autumn_custom": "杭州满觉陇赏桂文化", "landscape_components": "西湖湖泊山体寺塔堤道景观"}
                            query = " ".join(stable_labels.get(t, _TOPIC_LABELS.get(t, t)) for t in need.requested_fact_topics)
                        result = KnowledgeToolResult.model_validate(await knowledge_tool.retrieve(KnowledgeToolRequest(
                            query=query, destination=context.current_destination, knowledge_types=need.knowledge_types,
                            audience_tags=need.audience_tags, season_tags=need.season_tags, experience_tags=need.experience_tags)))
                    except Exception:
                        # A read-tool outage cannot turn into invented evidence.
                        result = KnowledgeToolResult(status="unavailable", outcome="retriever_unavailable")
                summary = KnowledgeRetrievalSummary.model_validate(
                    {**result.model_dump(exclude={"evidence"}),
                     "retrieved_document_refs": list(dict.fromkeys(e.document_id for e in result.evidence if e.document_id)),
                     "retrieved_chunk_refs": [e.chunk_id for e in result.evidence if e.chunk_id]})
                context = context.model_copy(update={"knowledge_retrieval": summary})
                advisory = result.advisory
                if advisory and (advisory.live_fact_verification_required or advisory.planning_decision_context_required):
                    need = need.model_copy(update={
                        "live_fact_required": need.live_fact_required or advisory.live_fact_verification_required,
                        "decision_history_required": need.decision_history_required or advisory.planning_decision_context_required})
                    if need.live_fact_required:
                        gaps.append(InformationGap(code="live_fact_unavailable", message="检索边界要求实时验证，当前没有实时事实工具。"))
                    if need.decision_history_required:
                        gaps.append(InformationGap(code="rationale_unavailable", message="旅游知识不能证明原始规划决定理由。"))
                    # Background hits can be recorded for audit but are not
                    # supplied as answer evidence for live/decision questions.
                elif result.status == "available" and (not advisory or advisory.knowledge_sufficient):
                    all_topics = {topic for item in result.evidence for assertion in item.answerable_assertions for topic in assertion.topics}
                    if any(item.source_page_title for item in result.evidence):
                        all_topics.add("source_page_title")
                    matched = []
                    for item in result.evidence:
                        assertions = [a for a in item.answerable_assertions
                            if not need.requested_fact_topics or set(a.topics).intersection(need.requested_fact_topics)]
                        # Page titles are curated source metadata and only enter
                        # the server-rendered answer on an explicit title query.
                        title_query = "source_page_title" in need.requested_fact_topics
                        if assertions or (title_query and item.source_page_title):
                            matched.append(item.model_copy(update={"answerable_assertions": assertions}))
                    missing_topics = [topic for topic in need.requested_fact_topics if topic not in all_topics]
                    title_missing = "source_page_title" in need.requested_fact_topics and not any(e.source_page_title for e in result.evidence)
                    if missing_topics or title_missing:
                        message = "当前来源资料未覆盖：" + "、".join(_TOPIC_LABELS.get(t, "该项具体事实") for t in missing_topics)
                        if "senior_destination_suitability" in missing_topics:
                            message = "现有资料只有通用的长辈出行原则，不能据此确认杭州是否适合同行的长辈。"
                        elif title_missing:
                            message = "当前资料保存了整理标题，但没有核实到该页面的原始标题。"
                        gaps.append(InformationGap(code="knowledge_insufficient", message=message))
                        advisory_data = summary.advisory.model_dump() if summary.advisory else {}
                        advisory_data.update(knowledge_sufficient=False,
                            warnings=[*advisory_data.get("warnings", []), "requested_fact_topic_not_covered"][:10])
                        context = context.model_copy(update={"knowledge_retrieval": summary.model_copy(update={
                            "outcome": "knowledge_insufficient", "advisory": type(summary.advisory).model_validate(advisory_data)
                                if summary.advisory else None})})
                    if matched:
                        context = context.model_copy(update={"knowledge_context": matched})
                    elif not gaps:
                        code, text = {"no_results": ("knowledge_no_results", "知识库没有检索到与问题相关的资料。"),
                            "unsupported_query": ("knowledge_unsupported_query", "当前小型知识库不覆盖这个目的地或主题。"),
                            "knowledge_insufficient": ("knowledge_insufficient", "检索到了资料，但不足以支持这个问题。")}.get(
                                result.outcome, ("knowledge_insufficient", "检索到了资料，但没有覆盖问题要求的具体事实。"))
                        gaps.append(InformationGap(code=code, message=text))
                else:
                    code, text = {"no_results": ("knowledge_no_results", "知识库没有检索到与问题相关的资料。"),
                        "unsupported_query": ("knowledge_unsupported_query", "当前小型知识库不覆盖这个目的地或主题。"),
                        "knowledge_insufficient": ("knowledge_insufficient", "检索到了资料，但不足以支持这个问题。")}.get(
                            result.outcome, ("knowledge_unavailable", "当前没有可用的知识检索证据，检索服务不可用。"))
                    gaps.append(InformationGap(code=code, message=text))
        return {"context": context, "need": need, "gaps": gaps, "trace": [*state["trace"], "gather_read_only_context"]}

    async def generate(state):
        context, selected, need = state["context"], state["selected"], state["need"]
        gaps, explanation = list(state["gaps"]), None
        claim_issues = []
        if any(g.code in {"unknown_suggestion", "ambiguous_suggestion"} for g in gaps):
            draft = CompanionDraft(response_text=gaps[0].message)
        elif need.live_fact_required and not need.decision_history_required:
            # Server-owned degradation: an unsafe model is never asked to fill
            # this gap, so prompt compliance is not the only safety mechanism.
            limitation = "当前没有可用的实时事实工具，我无法核实今天的天气、开放时间、票价或交通情况。请以官方当天信息为准。"
            if context.forecast_plan or (context.knowledge_context and need.knowledge_required):
                # Only stable server assertions; the model cannot fill live gaps.
                draft = CompanionAnswerDraft()
            else:
                draft = CompanionDraft(response_text=limitation)
        elif need.decision_history_required:
            if context.referenced_decision and context.referenced_decision.explanation_type == "original_validated_decision":
                explanation = context.referenced_decision
                draft = CompanionDraft(response_text="该已接受行程版本中验证并保存的原始决定理由是："
                    + "；".join(explanation.reasons) + "。这不代表实时事实已经核实。")
            elif len(selected) == 1 and selected[0].reasons and not is_formal_decision_question(context.current_message):
                suggestion = selected[0]
                explanation = CompanionExplanation(subject_ref=EntityReference(kind="suggestion", value=suggestion.suggestion_id),
                    explanation_type="original_saved_suggestion", reasons=suggestion.reasons,
                    evidence_refs=suggestion.evidence_refs, based_on_prior_decision=True,
                    source_turn_ref=suggestion.conversation_turn_id,
                    fact_freshness_warning="保存的是当时提出建议的理由，不代表地点或实时事实已经核实。")
                draft = CompanionDraft(response_text=f"关于“{suggestion.title}”，当时保存的建议理由是：" + "；".join(suggestion.reasons)
                    + "。这些理由不代表实时事实已核实。")
            else:
                subject = selected[0] if len(selected) == 1 else None
                explanation = CompanionExplanation(subject_ref=EntityReference(kind="suggestion", value=subject.suggestion_id) if subject else None,
                    explanation_type="rationale_unavailable", missing_evidence=["persisted_original_rationale"],
                    fact_freshness_warning="无法证明任何重建解释是原始规划理由。")
                gaps.append(InformationGap(code="rationale_unavailable", message="没有找到可验证的原始理由记录。"))
                draft = CompanionDraft(response_text="当前没有保存可验证的原始理由，我不能把重新推测的解释说成当时的理由。"
                    + ("旅游背景知识不能代替原始决定，也不能证明实时条件。" if need.live_fact_required else ""))
        elif need.answer_mode == "factual" and need.knowledge_required:
            # Factual answers are rendered from reviewed server-owned assertions;
            # no free-text generation runs for this mode.
            draft = CompanionAnswerDraft()
        elif selected and interaction_status(context.current_message) in {"user_liked", "user_confirmed"}:
            draft = CompanionDraft(response_text="记住了，你对“" + "、".join(s.title for s in selected)
                + "”感兴趣。这只是本次对话中的选择，没有加入正式行程。")
        elif need.knowledge_required and not context.knowledge_context and (
            "history_culture" in need.knowledge_types or context.travel_goal.goal_type in {"destination_exploration", "explanation"}):
            detail = next((gap.message for gap in gaps if gap.code.startswith("knowledge_")), "当前没有可用的知识检索证据。")
            draft = CompanionDraft(response_text=detail + "我不能给出有来源的确定回答，可以缩小或换一个主题再查询。")
        else:
            generated = await provider.generate(context, need)
            try:
                validate_provided_refs(generated, context.knowledge_context)
            except GroundingContractError as exc:
                raise CompanionContractError(str(exc)) from exc
            if isinstance(generated, CompanionAnswerDraft):
                draft = generated
            elif not need.knowledge_required and not context.knowledge_context:
                draft = CompanionDraft.model_validate(generated)
            else:
                # Legacy free text cannot carry factual claims through a
                # knowledge-required turn. Preserve only the deterministic
                # server assertions and record an explicit degradation.
                draft = CompanionAnswerDraft()
                claim_issues.append("legacy_unstructured_answer_downgraded")
            advice = list(draft.agent_claims) if isinstance(draft, CompanionAnswerDraft) else []
            suggestions_for_check = draft.suggestions if isinstance(draft, CompanionAnswerDraft) else []
            displayed_model_text = "\n".join([a.text for a in advice] + [
                f"{s.title} {s.summary} {' '.join(s.reasons)}" for s in suggestions_for_check])
            safe_advice = []
            for claim in advice:
                if _ATTRIBUTION_LANGUAGE.search(claim.text):
                    claim_issues.append("unvalidated_source_attribution_removed")
                    continue
                if any(e.curator_title and e.curator_title != e.source_page_title and e.curator_title in claim.text
                       for e in context.knowledge_context):
                    claim_issues.append("curator_title_as_source_title_removed")
                    continue
                if (any(e.applicability in {"audience", "general_strategy"} for e in context.knowledge_context)
                    and re.search(r"(?:杭州|西湖|这个目的地).{0,12}(?:最适合|很适合|适合).{0,8}(?:老人|长辈|父母)|"
                        r"(?:老人|长辈|父母).{0,8}(?:最适合|很适合|适合).{0,8}(?:杭州|西湖)", claim.text)):
                    claim_issues.append("general_guidance_scope_overreach_removed")
                    gaps.append(InformationGap(code="knowledge_insufficient", message="通用长辈原则不能确认杭州或西湖对具体长辈的适宜性。"))
                    continue
                if (any(e.applicability == "place" for e in context.knowledge_context)
                    and re.search(r"(?:杭州全市|整个杭州|杭州所有).{0,12}(?:适合|最佳|最适合).{0,8}(?:摄影|拍照)", claim.text)):
                    claim_issues.append("place_to_destination_scope_overreach_removed")
                    continue
                safe_advice.append(claim)
            if isinstance(draft, CompanionAnswerDraft):
                draft = draft.model_copy(update={"agent_claims": safe_advice})
            if (context.knowledge_context and all(e.applicability in {"audience", "general_strategy"}
                    for e in context.knowledge_context)
                and re.search(r"(?:杭州|西湖|这个目的地).{0,12}(?:最适合|很适合|适合).{0,8}(?:老人|长辈|父母)", displayed_model_text)):
                # Keep the measured guard for legacy/simple test providers too.
                claim_issues.append("general_guidance_scope_overreach_removed")
                gaps.append(InformationGap(code="knowledge_insufficient", message="通用长辈原则不能确认杭州对具体长辈的适宜性。"))
                if isinstance(draft, CompanionAnswerDraft):
                    draft = draft.model_copy(update={"agent_claims": [], "suggestions": []})
        return {"draft": draft, "explanation": explanation, "gaps": gaps, "claim_issues": claim_issues,
                "trace": [*state["trace"], "generate_interaction"]}

    async def extract_outcome(state):
        context, draft = state["context"], state["draft"]
        if state["explanation"] and state["explanation"].source_turn_ref:
            origin = next((m for m in state["messages"] if str(m.get("id")) == state["explanation"].source_turn_ref), {})
            saved = origin.get("companion_result", {}).get("knowledge_evidence", [])
            refs = set(state["explanation"].evidence_refs)
            from app.companion_contracts import KnowledgeEvidence
            original_evidence = [KnowledgeEvidence.model_validate(e) for e in saved if e.get("evidence_ref") in refs]
            context = context.model_copy(update={"knowledge_context": original_evidence[:10]})
        available = {item.evidence_ref for item in context.knowledge_context}
        structured = isinstance(draft, CompanionAnswerDraft)
        claims, issues = [], list(state.get("claim_issues", []))
        gaps = list(state["gaps"])
        if structured:
            try:
                claims, suggestion_drafts, assembly_issues = assemble_claims(context, state["need"], draft,
                    state["session_id"], state["turn_id"])
            except GroundingContractError as exc:
                raise CompanionContractError(str(exc)) from exc
            issues.extend(assembly_issues)
            used = {ref for claim in claims for ref in claim.evidence_refs}
        else:
            suggestion_drafts = draft.suggestions
            used = set(draft.evidence_refs) | {ref for item in draft.suggestions for ref in item.evidence_refs}
        if state["explanation"]:
            used |= set(state["explanation"].evidence_refs) & available
        visible_refs = set(re.findall(r"knowledge_[A-Za-z0-9_]+", draft.model_dump_json()))
        if not visible_refs <= available:
            raise CompanionContractError("Companion output references unknown evidence")
        if not used <= available:
            raise CompanionContractError("Companion output references unknown evidence")
        titles = [s.title for s in suggestion_drafts]
        if len(titles) != len(set(titles)):
            raise CompanionContractError("suggestion titles within a batch must be unique")
        now = datetime.now(UTC)
        suggestions = [CompanionSuggestion(suggestion_id=stable_identity("suggestion", state["session_id"], state["turn_id"], index),
            suggestion_type=s.suggestion_type, title=s.title, summary=s.summary,
            entity_refs=[EntityReference(kind="raw_mention", value=s.title)], destination=context.current_destination,
            reasons=s.reasons, evidence_refs=s.evidence_refs,
            grounding="unverified_proposal" if structured else "knowledge_supported" if s.evidence_refs else "unverified_proposal",
            created_at=now, conversation_turn_id=state["turn_id"]) for index, s in enumerate(suggestion_drafts)]
        if issues:
            gaps.append(InformationGap(code="knowledge_insufficient", message="部分生成内容未通过来源或适用范围检查，已移除；其余建议仍是助手推断。"))
        if structured:
            response = _answer_text(claims, gaps, suggestions)
        else:
            response = draft.response_text
            if not state["need"].general_knowledge_allowed and (any(not s.evidence_refs for s in suggestions) or (state["need"].knowledge_required and not context.knowledge_context and not state["explanation"])):
                response = "以下是待核实的讨论建议，不是正式规划决定。\n" + response
            if suggestions and not state["need"].general_knowledge_allowed:
                response = response[:2000] + "\n" + "\n".join(f"{index + 1}. {s.title}：{s.summary[:100]}" for index, s in enumerate(suggestions))
        if context.forecast_plan:
            # Dynamic facts are server-rendered separately from Knowledge claims.
            # Remove weather gap prose here to avoid duplicating the forecast section.
            stable_response = _answer_text(claims, [g for g in gaps if g.code != "live_fact_unavailable"], suggestions) if claims or suggestions or state["need"].knowledge_required else ""
            extra = [g.message for g in gaps if g.code == "live_fact_unavailable" and g.message.startswith("实时部分")]
            response = "\n\n".join([x for x in [stable_response,forecast_text(context.forecast_plan,context.resolved_facts),*extra] if x])
        grounding = "not_applicable"
        if state["need"].live_fact_required:
            grounding = "live_verification_required"
            if context.forecast_plan and context.resolved_facts and all(r.usable_as_current for r in context.resolved_facts) and not any(g.code=="live_fact_unavailable" for g in gaps):
                grounding = "verified_forecast"
        elif state["need"].decision_history_required:
            grounding = "decision_context_required"
        elif state["need"].knowledge_required:
            grounding = "citations_validated" if used else "insufficient_evidence"
            if context.knowledge_context and not used:
                gaps.append(InformationGap(code="knowledge_insufficient", message="模型回答没有关联所提供的知识证据。"))
                # No citation means no grounded factual answer is published.
                if not suggestions and not structured:
                    response = "检索到了资料，但这次回答没有提供可核对的证据引用，暂不作为有来源的确定回答。"
        elif suggestions:
            grounding = "unverified_proposal"
        status = "needs_clarification" if (context.forecast_plan and context.forecast_plan.clarification) or any(g.code in {"unknown_suggestion", "ambiguous_suggestion"} for g in gaps) else "needs_information" if gaps else "completed"
        result = CompanionResult(response_text=response[:5000], goal_type=context.travel_goal.goal_type,
            status=status, suggestions=suggestions, resolved_suggestion_refs=[s.suggestion_id for s in state["selected"]],
            interactions=[SuggestionInteraction(suggestion_id=s.suggestion_id, status=interaction_status(context.current_message),
                source_turn_id=state["turn_id"]) for s in state["selected"]], comparison=draft.comparison if not structured or (
                    draft.comparison and not advice_issue(draft.comparison.summary, context, state["need"])) else None,
            explanation=state["explanation"], information_need=state["need"], information_gaps=gaps,
            conversation_destination=context.current_destination,
            knowledge_evidence=context.knowledge_context, answer_evidence_refs=sorted(used),
            knowledge_retrieval=context.knowledge_retrieval, grounding_status=grounding,
            grounding_limitations=["claim_entailment_not_verified", "tourism_knowledge_not_live_verified"] if used else
                ["model_general_knowledge_unverified"] if state["need"].general_knowledge_allowed else [],
            claims=claims, claim_validation_issues=list(dict.fromkeys(issues))[:12],
            forecast_plan=context.forecast_plan, resolved_facts=context.resolved_facts,
            runtime_trace=[*state["trace"], "extract_interaction_outcome"])
        return {"result": result, "trace": result.runtime_trace}

    async def handoff_boundary(state):
        # Handoff is built by the adapter only when Router receives an explicit
        # Planning turn. This graph may offer discussion, never self-authorize.
        return {"trace": [*state["trace"], "planning_handoff_not_authorized"]}

    async def prepare_persistence(state):
        return {"result": state["result"].model_copy(update={"runtime_trace": [*state["trace"], "prepare_conversation_persistence"]})}

    graph = StateGraph(CompanionGraphState)
    nodes = {"interpret_goal": interpret_goal, "resolve_conversation": resolve_conversation,
        "determine_information_need": information_need, "gather_context": gather_context,
        "generate": generate, "extract_outcome": extract_outcome,
        "handoff_boundary": handoff_boundary, "prepare_persistence": prepare_persistence}
    previous = START
    for name, node in nodes.items():
        graph.add_node(name, observed_stage(name)(node))
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()
