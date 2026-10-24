"""Synthetic-provider probe of the real V2 build/prepare boundary, no network.

The deliberately wrong model plan is injected. All place/route data is synthetic,
not a current Amap observation. No publication or formal writer is invoked.
"""
import asyncio
import argparse
from datetime import datetime, timezone, timedelta, date
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from uuid import UUID

root = Path("E:/Study/RoamSync-reliability-a2-20261022")
paths = ["conversation_candidate/commands.py", "conversation_candidate/service.py", "assistant_operation.py",
         "draft_promotion/preparation.py", "requirements.py", "drafts/contracts.py",
         "assistant_capabilities.py", "flexible_creation.py", "requirement_language.py"]
def hashes():
    return {p: hashlib.sha256((root / "backend/app" / p).read_bytes()).hexdigest() for p in paths}
before = hashes()
# Windows implements asyncio's internal wakeup socketpair using loopback TCP.
# Initialize that interpreter mechanism before denying application connections.
loop = asyncio.new_event_loop()
attempts = []
def deny(*a, **kw):
    attempts.append("network")
    raise RuntimeError("Read-only synthetic probe disallows network/DB")
socket.socket.connect = deny
socket.create_connection = deny
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "postgresql+psycopg://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_b3_readonly_probe_test"
os.environ["LANGGRAPH_DATABASE_URL"] = "postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_b3_readonly_probe_test"
sys.path.insert(0, str(root / "backend"))
from app.assistant_capabilities import CapabilityDecision, validate_decision
from app.assistant_context import ContextEnvelope
from app.conversation_candidate.commands import CandidateCommand
from app.conversation_candidate.service import build_candidate
from app.conversation_candidate.presentation import candidate_presentation
from app.place_content.contracts import Place, RouteResult


class SyntheticPlaces:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.calls = []
        self.items = [Place(ref={"place_id": UUID(int=n), "external_ref": {"provider_place_id": f"SYNTHETIC{n}"}},
            name=name, city="成都", category="attraction", location={"longitude": 104+n/1000, "latitude": 30},
            source={"source_url": f"https://fixture.invalid/{n}", "fetched_at": now, "expires_at": now+timedelta(hours=1)})
            for n, name in [(1, "人民公园"), (2, "宽窄巷子")]]
    async def search(self, query):
        self.calls.append({"type": "synthetic_search", "query": query.query})
        return SimpleNamespace(items=[p for p in self.items if p.name == query.query])
    async def get_place(self, place_id, **kw):
        self.calls.append({"type": "synthetic_place", "id": str(place_id)})
        return next(p for p in self.items if p.ref.place_id == place_id)
    async def query_route(self, query):
        self.calls.append({"type": "synthetic_route"})
        now = datetime.now(timezone.utc)
        return RouteResult(origin=query.origin, destination=query.destination, mode=query.mode,
            distance_meters=800, duration_seconds=600, path=[query.origin, query.destination],
            source={"source_url": "https://fixture.invalid/route", "fetched_at": now, "expires_at": now+timedelta(hours=1)})


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["excluded", "optional", "positive", "hypothetical"], default="excluded")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = "请生成成都2026年11月9日玩1天的安排，每天10点出发18点结束，步行，"
    conditions = {"excluded": "不去人民公园，宽窄巷子要去。", "optional": "人民公园只作备选，宽窄巷子要去。",
                  "positive": "人民公园和宽窄巷子都要去。", "hypothetical": "人民公园和宽窄巷子都要去。"}
    message = ("假设我确认了，" if args.variant == "hypothetical" else "") + base + conditions[args.variant]
    source_quote = base + conditions[args.variant] if args.variant == "hypothetical" else message
    park_quote = {"excluded": "不去人民公园", "optional": "人民公园只作备选",
                  "positive": "人民公园和宽窄巷子都要去", "hypothetical": "人民公园和宽窄巷子都要去"}[args.variant]
    command = CandidateCommand(action="generate", source_quote=source_quote, plan={"schema_version": 2,
        "schedule_constraints": {"start_date": "2026-11-09", "daily_start_time": "10:00", "daily_end_time": "18:00", "transport_mode": "walk"},
        "days": [{"day_index": 1, "title": "Synthetic injected wrong selection", "items": [
            {"item_ref": "excluded", "name": "人民公园", "duration_minutes": 60, "source_quote": park_quote},
            {"item_ref": "wanted", "name": "宽窄巷子", "duration_minutes": 60,
             "source_quote": "宽窄巷子要去" if args.variant in {"excluded", "optional"} else park_quote}]}]})
    envelope = ContextEnvelope()
    decision = validate_decision(CapabilityDecision(intent="create", city="成都", reason_code="explicit_write", candidate_command=command),
                                 message, [], envelope)
    places = SyntheticPlaces()
    result = {"kind": "Injected wrong plan with synthetic provider; real build/prepare code, no model/DB/publication/adoption",
              "captured_utc": datetime.now(timezone.utc).isoformat(), "message": message,
              "command": command.model_dump(mode="json"), "hashes_before": before,
              "variant": args.variant, "validated_intent": decision.intent, "actual_model_output": False}
    try:
        if decision.intent not in {"create", "modify"} or decision.candidate_command is None:
            raise ValueError("Validated decision does not dispatch a candidate command; build was not invoked")
        draft, prepared = await build_candidate(command, decision, message, [], envelope,
            SimpleNamespace(service=places), None, today=date(2026,10,24))
        view = candidate_presentation(prepared)
        result.update({"built": True, "prepared_stage": view["stage"], "blockers": view["blockers"],
                       "activity_names": [a.name for a in prepared.activities],
                       "constraint_checks": view["constraint_checks"], "requirement_records": draft.requirement_records})
    except Exception as exc:
        result.update({"built": False, "error_type": type(exc).__name__, "error": str(exc)})
    after = hashes()
    result.update({"hashes_after": after, "source_unchanged": before == after,
                   "network_or_db_attempts": len(attempts), "synthetic_provider_calls": places.calls})
    output = args.output
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:result.get(k) for k in ["built", "prepared_stage", "blockers", "activity_names", "error_type", "error", "source_unchanged", "network_or_db_attempts"]}, ensure_ascii=True))
    assert before == after and not attempts


try:
    loop.run_until_complete(main())
finally:
    loop.close()
