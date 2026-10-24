"""Read-only review probes against A's active implementation.

No model/DB/business writer runs. Proposed commands are deliberately injected to
test the server guard, not reported as actual model output or observed writes.
All questions and data here are newly authored public development inputs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import perf_counter
from uuid import uuid4


FILES = ["conversation_candidate/commands.py", "conversation_candidate/service.py",
         "conversation_candidate/binding.py", "conversation_candidate/presentation.py",
         "draft_promotion/atomic.py", "assistant_capabilities.py", "assistant_turn.py",
         "assistant_context.py", "assistant_memory.py", "requirements.py", "drafts/contracts.py"]


def hashes(root):
    return {name: hashlib.sha256((root / "backend/app" / name).read_bytes()).hexdigest() for name in FILES}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("E:/Study/RoamSync-reliability-a2-20261022"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = hashes(args.root)
    blocked_calls = []
    def deny(*a, **kw):
        blocked_calls.append("network")
        raise RuntimeError("Read-only probe disallows network/DB connections")
    socket.socket.connect = deny
    socket.create_connection = deny
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = "postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_b3_readonly_probe_test"
    os.environ["LANGGRAPH_DATABASE_URL"] = "postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_b3_readonly_probe_test"
    sys.path.insert(0, str(args.root / "backend"))
    from app.conversation_candidate.commands import CandidateCommand, apply_patches, validate_command
    from app.conversation_candidate.binding import conditions_hash
    from app.assistant_context import ContextEnvelope, capture_effective_requirements
    from app.assistant_memory import apply_memory, literal_conditions
    from app.assistant_capabilities import CapabilityDecision, validate_decision
    from app.drafts.contracts import DraftPlan

    rows = []
    cases = [
        ("post-save-question", "保存后还能修改吗？", "保存", False),
        ("can-save-question", "这份安排可以保存了吗？", "保存", False),
        ("saved-state-question", "我保存了吗？", "保存", False),
        ("object-count-question", "保存会创建几个正式对象？", "保存", False),
        ("existing-question-control", "保存当前候选会怎样？", "保存当前候选", False),
        ("hypothetical-across-clause", "假设我确认了，帮我保存当前候选。", "帮我保存当前候选", False),
        ("reported-speech-across-clause", "朋友会说，帮我保存当前候选。", "帮我保存当前候选", False),
        ("withdrawal-after-period", "帮我保存当前候选。算了，我再想想。", "帮我保存当前候选", False),
        ("full-current-save-control", "采用并保存这份安排", "采用并保存这份安排", True),
        ("short-current-save-control", "帮我保存", "帮我保存", True),
    ]
    for case_id, message, quote, expected in cases:
        start = perf_counter()
        command = CandidateCommand(action="adopt", source_quote=quote)
        try:
            validate_command(command, message)
            accepted, error = True, None
        except ValueError as exc:
            accepted, error = False, str(exc)
        checked = validate_decision(CapabilityDecision(intent="direct", reason_code="stable_knowledge", candidate_command=command),
                                    message, [], ContextEnvelope())
        rows.append({"id": case_id, "message": message, "command": command.model_dump(mode="json"),
                     "expected_authorized": expected, "command_accepted": accepted, "error": error,
                     "validated_intent": checked.intent,
                     "validated_action": checked.candidate_command.action if checked.candidate_command else None,
                     "seconds": perf_counter() - start})

    plan = DraftPlan.model_validate({"schema_version": 2, "schedule_constraints": {
        "start_date": "2026-11-09", "daily_start_time": "10:00", "daily_end_time": "18:00", "transport_mode": "walk"},
        "days": [{"day_index": 1, "title": "Synthetic only", "items": [
            {"item_ref": "park", "name": "人民公园", "duration_minutes": 90},
            {"item_ref": "street", "name": "宽窄巷子", "duration_minutes": 90}]}]})
    compound = []
    for case_id, message, command in [
        ("missing-peer-patch", "人民公园改成120分钟，宽窄巷子改成30分钟", CandidateCommand(action="modify",
            source_quote="人民公园改成120分钟", patches=[{"item_ref": "park", "source_quote": "人民公园改成120分钟", "duration_minutes": 120}])),
        ("modify-before-adopt", "人民公园改成120分钟，然后保存当前候选", CandidateCommand(action="adopt", source_quote="保存当前候选")),
        ("modify-and-bare-adopt", "人民公园改成120分钟，保存当前候选", CandidateCommand(action="adopt", source_quote="保存当前候选")),
        ("hypothetical-modify", "假设我改主意了，人民公园改成120分钟", CandidateCommand(action="modify",
            source_quote="人民公园改成120分钟", patches=[{"item_ref": "park", "source_quote": "人民公园改成120分钟", "duration_minutes": 120}])),
    ]:
        envelope, mid = ContextEnvelope(), uuid4()
        updated, history, changed = apply_memory(envelope, [], message, mid, literal_conditions(message))
        updated = capture_effective_requirements(updated, message, message_id=mid)
        try:
            validate_command(command, message)
            revised = apply_patches(plan, command, message) if command.action == "modify" else plan
            accepted, error = True, None
        except ValueError as exc:
            accepted, error, revised = False, str(exc), plan
        compound.append({"id": case_id, "message": message, "command": command.model_dump(mode="json"),
                         "accepted": accepted, "error": error,
                         "durations_after": [i.duration_minutes for day in revised.days for i in day.items],
                         "conditions_hash_unchanged": conditions_hash(envelope) == conditions_hash(updated),
                         "literal_changed": changed, "captured_records": updated.requirement_records,
                         "note": "adopt case inspects guard and unchanged input plan only; no adoption writer executes"})
    duplicate_plan = plan.model_copy(deep=True)
    duplicate_plan.days[0].items[1].name = "人民公园"
    duplicate = []
    for ref in ["park", "street"]:
        command = CandidateCommand(action="modify", source_quote="人民公园改成120分钟", patches=[{
            "item_ref": ref, "source_quote": "人民公园改成120分钟", "duration_minutes": 120}])
        try:
            revised = apply_patches(duplicate_plan, command, command.source_quote)
            accepted, error = True, None
        except ValueError as exc:
            accepted, error, revised = False, str(exc), duplicate_plan
        duplicate.append({"item_ref": ref, "accepted": accepted, "error": error,
                          "durations_after": [i.duration_minutes for day in revised.days for i in day.items]})
    positive_patches = []
    for case_id, message, patches in [
        ("single-explicit-local", "人民公园改成75分钟", [
            {"item_ref": "park", "source_quote": "人民公园改成75分钟", "duration_minutes": 75}]),
        ("both-explicit-local", "人民公园改成75分钟，宽窄巷子改成105分钟", [
            {"item_ref": "park", "source_quote": "人民公园改成75分钟", "duration_minutes": 75},
            {"item_ref": "street", "source_quote": "宽窄巷子改成105分钟", "duration_minutes": 105}]),
    ]:
        command = CandidateCommand(action="modify", source_quote=message, patches=patches)
        try:
            revised = apply_patches(plan, command, message)
            accepted, error = True, None
        except ValueError as exc:
            accepted, error, revised = False, str(exc), plan
        positive_patches.append({"id": case_id, "message": message, "command": command.model_dump(mode="json"),
                                 "accepted": accepted, "error": error,
                                 "durations_after": [i.duration_minutes for day in revised.days for i in day.items]})
    after = hashes(args.root)
    result = {"kind": "Injected-command guard/dispatch probes only; no generated model output or formal writes",
              "captured_utc": datetime.now(timezone.utc).isoformat(),
              "active_root": str(args.root),
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.root, text=True).strip(),
              "published_baseline": False, "hashes_before": before, "hashes_after": after,
              "source_unchanged_during_probe": before == after,
              "network_or_db_calls_attempted": len(blocked_calls),
              "authority_cases": rows, "compound_cases": compound, "duplicate_name_cases": duplicate,
              "positive_patch_controls": positive_patches,
              "limitations": ["A is actively editing uncommitted source; use per-run hashes, not HEAD as product identity.",
                              "A real selector may output another command; probe establishes a server backstop defect, not its frequency.",
                              "No candidate publish, confirm_atomic, resume, SQL or formal Accept is invoked.",
                              "Duplicate names are a local command-boundary probe; full POI resolution may reject some duplicate identities."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_unchanged": before == after, "network_or_db_calls_attempted": len(blocked_calls),
                      "unauthorized_adopt_commands_accepted": [r["id"] for r in rows if not r["expected_authorized"] and r["command_accepted"]],
                      "compound_commands_accepted": [r["id"] for r in compound if r["accepted"]],
                      "duplicate_targets_accepted": sum(r["accepted"] for r in duplicate),
                      "positive_patch_controls_accepted": sum(r["accepted"] for r in positive_patches)}, ensure_ascii=True))
    assert before == after and not blocked_calls


if __name__ == "__main__":
    main()
