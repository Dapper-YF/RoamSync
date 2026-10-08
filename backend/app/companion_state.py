"""Pure conversation projection and identity binding; never guesses a place ID."""
import re
import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.companion_contracts import (BriefInterest, CompanionResult, CompanionSuggestion,
    InformationGap, PlanningBrief, PreferenceStatement)
from app.schemas import TravelGoalRouting
from app.travel_language import chinese_number, trip_duration

_NAMESPACE = uuid.UUID("bd44f3e9-dfc5-4780-9bb9-0aa6e08e3b7d")
_ORDINAL = re.compile(r"第([一二三四五六七八九十\d]+)(?:个|项|条)")
_PREFERENCE = re.compile(r"我(?:一直)?(?:不喜欢|喜欢|不想|偏好)|不喜欢商业|偏好|希望.{0,12}(?:轻松|慢游|自然|人文)")


def stable_identity(kind: str, session_id: str, turn_id: str, index: int = 0) -> str:
    return f"{kind}_{uuid.uuid5(_NAMESPACE, f'{session_id}:{turn_id}:{index}').hex}"


def destination_from_text(text: str) -> str | None:
    if re.search(r"历史|文化|来历", text):
        return None  # A named knowledge subject is not a resolved destination.
    planning_destination = re.search(r"(?:规划|安排)(?:一个)?([\u4e00-\u9fff]{2,8}?)(?=[一二三四五六七八九十两\d]+(?:天|日))", text)
    if planning_destination:
        return planning_destination[1]
    match = re.search(r"^(?:那)?([\u4e00-\u9fff]{2,8}?)(?=有什么|有哪些|适合|和|呢[？?。]*$)|"
                      r"(?:就去|就选|就|去)((?!按|第|帮|我)[\u4e00-\u9fff]{2,8}?)(?=吧|[，,]|旅游|三日游|[一二三四五六七八九十两\d]+天)", text)
    return next((group for group in match.groups() if group), None) if match else None


@dataclass
class ConversationState:
    suggestions: dict[str, CompanionSuggestion] = field(default_factory=dict)
    current_batch: list[str] = field(default_factory=list)
    focused_refs: list[str] = field(default_factory=list)
    preferences: list[PreferenceStatement] = field(default_factory=list)
    decisions: list[PreferenceStatement] = field(default_factory=list)
    destination: str | None = None
    pending_handoff: PlanningBrief | None = None


def project_conversation(messages: list[dict]) -> ConversationState:
    state = ConversationState()
    for turn in messages:
        turn_id = str(turn.get("id", "legacy"))
        text = str(turn.get("user", ""))
        if _PREFERENCE.search(text):
            state.preferences.append(PreferenceStatement(text=text[:1000], source_turn_id=turn_id))
        if re.search(r"就去|就选|一定.*(?:去|放进)|必须.*(?:去|包含)", text):
            state.decisions.append(PreferenceStatement(text=text[:1000], source_turn_id=turn_id))
        state.destination = destination_from_text(text) or state.destination
        data = turn.get("companion_result")
        if data:
            try:
                result = CompanionResult.model_validate(data)
            except ValidationError:
                # A corrupt latest batch cannot resolve to an older batch.
                state.current_batch, state.focused_refs = [], []
                continue
            state.destination = result.conversation_destination or state.destination
            if result.suggestions:
                state.current_batch = [item.suggestion_id for item in result.suggestions]
                state.focused_refs = []
                state.suggestions.update({item.suggestion_id: item for item in result.suggestions})
            if result.resolved_suggestion_refs:
                state.focused_refs = [ref for ref in result.resolved_suggestion_refs if ref in state.suggestions]
            for interaction in result.interactions:
                suggestion = state.suggestions.get(interaction.suggestion_id)
                if suggestion:
                    ranks = {"suggested": 0, "discussed": 1, "user_liked": 2, "user_confirmed": 3, "must_do": 4}
                    status = max((suggestion.status, interaction.status), key=ranks.get)
                    state.suggestions[interaction.suggestion_id] = suggestion.model_copy(update={"status": status})
        if turn.get("planning_brief"):
            try:
                state.pending_handoff = PlanningBrief.model_validate(turn["planning_brief"])
            except ValidationError:
                state.pending_handoff = None
    state.preferences = state.preferences[-30:]
    state.decisions = state.decisions[-30:]
    return state


def resolve_suggestions(text: str, state: ConversationState) -> tuple[list[CompanionSuggestion], list[InformationGap]]:
    refs = re.findall(r"suggestion_[0-9a-f]{32}", text)
    ordinals = _ORDINAL.findall(text)
    if ordinals:
        for ordinal in ordinals:
            position = chinese_number(ordinal)
            if not position or position > len(state.current_batch):
                return [], [InformationGap(code="unknown_suggestion", message="这条建议序号没有对应记录，请明确说出要讨论的建议。")]
            refs.append(state.current_batch[position - 1])
    elif not refs:
        named = [ref for ref, item in state.suggestions.items() if item.title in text]
        if len({state.suggestions[ref].title for ref in named}) < len(named):
            return [], [InformationGap(code="ambiguous_suggestion", message="同名建议出现过多次，请明确建议序号或身份。")]
        refs.extend(named)
        # A named subject followed by a redundant pronoun (e.g. 南京它是...)
        # is not a reference to an unresolved saved suggestion. This does not
        # resolve a place or create suggestion identity from the subject.
        named_subject = bool(re.match(r"^(?!我|你|他|她|它|这|那)[\u4e00-\u9fff]{2,8}它(?:是|有|适合)", text))
        if not refs and not named_subject and re.search(r"它|那个地方|那条建议|这个建议", text):
            focus = state.focused_refs or (state.current_batch if len(state.current_batch) == 1 else [])
            if len(focus) != 1:
                return [], [InformationGap(code="ambiguous_suggestion", message="你说的是哪一条建议？可以告诉我序号。")]
            refs.extend(focus)
    refs = list(dict.fromkeys(refs))
    if len(refs) > 10 or any(ref not in state.suggestions for ref in refs):
        return [], [InformationGap(code="unknown_suggestion", message="找不到这条建议的保存记录，请重新指定。")]
    return [state.suggestions[ref] for ref in refs], []


def interaction_status(text: str) -> str:
    if re.search(r"不想|不要|不喜欢|先别|不一定", text):
        return "discussed"
    if re.search(r"一定|必须|必去", text) and re.search(r"放进|排进|安排|包含|加入", text):
        return "must_do"
    if re.search(r"就选|确定选|就按|就去", text):
        return "user_confirmed"
    if re.search(r"不错|喜欢|挺好|心动|想去|听起来好", text):
        return "user_liked"
    return "discussed"


def build_planning_brief(session_id: str, turn_id: str, message: str,
                         goal: TravelGoalRouting, messages: list[dict]) -> PlanningBrief | None:
    if goal.target_runtime != "planning" or not goal.mutation_requested:
        return None
    state = project_conversation(messages)
    selected, gaps = resolve_suggestions(message, state)
    status = "must_do" if interaction_status(message) == "must_do" else "user_confirmed"
    interests = [BriefInterest(suggestion_ref=s.suggestion_id, display_name=s.title,
        entity_refs=s.entity_refs, status=status, source_turn_ref=s.conversation_turn_id) for s in selected]
    current = PreferenceStatement(text=message[:1000], source_turn_id=turn_id)
    preferences = state.preferences + ([current] if _PREFERENCE.search(message) else [])
    relevant_turns = [p.source_turn_id for p in preferences] + [d.source_turn_id for d in state.decisions]
    relevant_turns += [s.conversation_turn_id for s in selected] + [turn_id]
    # Budget/party/date values remain user statements. No assistant arithmetic
    # or invented exact dates become Planning constraints through this contract.
    user_texts = [str(m.get("user", "")) for m in messages] + [message]
    latest = lambda pattern: next((t[:1000] for t in reversed(user_texts) if re.search(pattern, t)), None)
    duration = trip_duration(message)
    return PlanningBrief(brief_id=stable_identity("brief", session_id, turn_id),
        status="needs_clarification" if gaps else "prepared", authorization_turn_id=turn_id,
        user_request=message, destination=destination_from_text(message) or state.destination,
        date_request=latest(r"\d{1,4}[年月/-]|下周|出发|返程|国庆|元旦"),
        duration_days=duration if duration and 1 <= duration <= 31 else None,
        party_statement=latest(r"[一二三四五六七八九十两\d]+个人|两人|一个人|带父母"),
        budget_statement=latest(r"预算|\d+元"), confirmed_preferences=preferences[-30:],
        avoidances=[p for p in preferences if re.search(r"不喜欢|不想|避开", p.text)][-30:],
        candidate_interests=interests, must_do=[s.suggestion_id for s in selected] if status == "must_do" else [],
        user_decisions=[*state.decisions, current][-30:], open_questions=[gap.message for gap in gaps],
        source_turn_refs=list(dict.fromkeys(relevant_turns))[-60:], suggestion_refs=[s.suggestion_id for s in selected])
