"""python -m evals.companion_phase1.run --output PATH (offline, fake provider)."""
import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.companion_contracts import CompanionDraft, SuggestionDraft
from app.companion_runtime import CompanionRuntime
from app.companion_state import build_planning_brief, project_conversation
from app.travel_goal_router import route_travel_goal


class Reader:
    async def load(self, context, need):
        return context


class Provider:
    calls = 0
    async def generate(self, context, need):
        self.calls += 1
        return CompanionDraft(response_text="三个待核实的兴趣候选。", suggestions=[
            SuggestionDraft(title=title, summary="待核实的摄影兴趣。", reasons=[f"{title}可作为本次兴趣讨论的选项。"])
            for title in ("西湖", "九溪", "北山街")])


async def evaluate():
    provider, records = Provider(), []
    runtime = CompanionRuntime(Reader(), provider)
    history = []

    async def run(text, expected_refs=None):
        # Simulate durable JSON reload rather than sharing runtime objects.
        messages = json.loads(json.dumps(history, ensure_ascii=False))
        turn_id = f"eval-turn-{len(history)}"
        result = await runtime.run(session_id="eval-session", turn_id=turn_id, message=text,
            goal=route_travel_goal(text, messages[-12:]), messages=messages)
        history.append({"id": turn_id, "user": text, "assistant": result.response_text,
            "companion_result": result.model_dump(mode="json")})
        return result

    def check(group, name, passed):
        records.append({"group": group, "name": name, "passed": bool(passed)})

    history_result = await run("西湖有什么历史？")
    check("runtime_entry", "independent_graph_trace", "determine_information_need" in history_result.runtime_trace)
    check("grounding_honesty", "knowledge_gap_is_explicit", any(g.code == "knowledge_unavailable" for g in history_result.information_gaps))
    check("grounding_honesty", "knowledge_subject_is_not_destination", history_result.conversation_destination is None)
    recommendation = await run("杭州有什么适合摄影的地方？")
    refs = [s.suggestion_id for s in recommendation.suggestions]
    check("suggestion_identity", "unique_server_owned_ids", len(set(refs)) == 3 and all(r.startswith("suggestion_") for r in refs))
    check("grounding_honesty", "proposals_are_unverified", all(s.grounding == "unverified_proposal" for s in recommendation.suggestions))
    explanation = await run("第二个为什么值得去？")
    check("suggestion_resolution", "ordinal_two", explanation.resolved_suggestion_refs == [refs[1]])
    check("grounding_honesty", "saved_rationale_matches", explanation.explanation.reasons == recommendation.suggestions[1].reasons)
    check("grounding_honesty", "original_has_source_turn", explanation.explanation.source_turn_ref == recommendation.suggestions[1].conversation_turn_id)
    liked = await run("第二个挺不错。")
    check("conversation_continuity", "liked_not_formally_confirmed", liked.interactions[0].status == "user_liked")
    check("handoff_accuracy", "liking_has_no_handoff", liked.planning_handoff is None)
    for index in range(15):
        history.append({"id": f"filler-{index}", "user": "谢谢", "assistant": "收到"})
    pronoun = await run("它为什么值得去？")
    check("suggestion_resolution", "pronoun_after_long_history_reload", pronoun.resolved_suggestion_refs == [refs[1]])
    check("conversation_continuity", "interaction_projection_survives", project_conversation(history).suggestions[refs[1]].status == "user_liked")
    await run("我不喜欢商业化的地方。")
    followup = await run("那苏州呢？")
    check("conversation_continuity", "destination_followup", followup.conversation_destination == "苏州")
    check("conversation_continuity", "user_preference_sources", any("不喜欢" in p.text for p in project_conversation(history).preferences))
    # A new recommendation batch is authoritative for ordinal references.
    latest_refs = [s.suggestion_id for s in followup.suggestions]
    text = "那就按第二个和第三个给我规划三天。"
    brief = build_planning_brief("eval-session", "handoff", text, route_travel_goal(text, history[-12:]), history)
    check("handoff_accuracy", "explicit_planning_has_brief", brief is not None and brief.status == "prepared")
    check("handoff_accuracy", "refs_two_and_three", brief.suggestion_refs == latest_refs[1:3])
    check("handoff_accuracy", "candidate_interest_not_must_do", not brief.must_do)
    check("handoff_accuracy", "duration_from_user", brief.duration_days == 3)
    invalid = await run("第九个为什么值得去？")
    check("suggestion_resolution", "out_of_range_clarifies", invalid.status == "needs_clarification" and not invalid.resolved_suggestion_refs)
    original = await run("为什么你之前把西湖放在晚上？")
    # A saved Companion suggestion with this exact name can explain its own
    # proposal, but cannot establish the reason for a formal schedule decision.
    check("grounding_honesty", "formal_schedule_rationale_not_faked", original.explanation.explanation_type == "rationale_unavailable")
    live = await run("西湖今天几点关门？")
    check("grounding_honesty", "live_gap_cannot_be_filled", "无法核实" in live.response_text and not live.suggestions)
    groups = {group: {"passed": sum(r["passed"] for r in records if r["group"] == group), "total": total}
              for group, total in Counter(r["group"] for r in records).items()}
    return {"measured_at": datetime.now(UTC).isoformat(), "mode": "offline_runtime_fake_provider",
        "real_provider_calls": 0, "fake_provider_calls": provider.calls, "database_access": False,
        "mutation_safety_evidence": "Linux/PostgreSQL integration suite, not inferred from this offline eval",
        "checks": len(records), "passed": sum(r["passed"] for r in records), "groups": groups, "results": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(evaluate())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] == result["checks"] else 1)
