"""Fixed A/B/C read-only comparison. Real mode uses the configured model.

No DB, formal writes or live-network facts. Missing fact tools test degradation.
Latency includes runtime, separate measured local retrieval. Usage is provider
reported only; character counts are never presented as tokens.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from app.companion_contracts import CompanionAnswerDraft, CompanionDraft
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.companion_provider import ModelCompanionProvider
from app.companion_runtime import CompanionRuntime
from app.config import get_settings
from app.travel_goal_router import route_travel_goal
from evals.companion_provider_smoke import failure_details, public_endpoint

FIXTURE = Path(__file__).parent / "fixtures/companion_knowledge_strategy_v1.json"
MODES = {"A": "general_only", "B": "forced_rag", "C": "selective"}


class Reader:
    async def load(self, context, need):
        return context


class ControlledProvider:
    observations = []
    async def generate(self, context, need):
        if need.general_knowledge_allowed:
            return CompanionDraft(response_text="受控占位回答，仅验证调度，不用于评估模型回答质量。")
        return CompanionAnswerDraft()


class CountingTool:
    def __init__(self, tool, variant=None):
        self.tool, self.variant = tool, variant
        self.calls, self.seconds = 0, 0.0

    async def retrieve(self, request):
        started = perf_counter()
        self.calls += 1
        result = await self.tool.retrieve(request)
        if self.variant == "untrusted":
            result = result.model_copy(update={"evidence": [e.model_copy(update={
                "source_authority": "ugc"}) for e in result.evidence]})
        self.seconds += perf_counter() - started
        return result


async def run(*, real=False, output: Path, fixture: Path = FIXTURE,
              case_ids: list[str] | None = None, continue_on_error=False):
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    cases = [c for c in payload["cases"] if not case_ids or c["id"] in case_ids]
    if case_ids and set(case_ids) != {c["id"] for c in cases}:
        raise ValueError("unknown evaluation case ID")
    settings = get_settings()
    if real and not (settings.planner_api_key.get_secret_value() and settings.planner_model):
        raise RuntimeError("real evaluation requires configured model credentials")
    report = {"version": payload["version"], "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "fixture": str(fixture), "selected_case_ids": [c["id"] for c in cases],
        "endpoint": public_endpoint(settings.planner_base_url), "proxy": public_endpoint(settings.planner_proxy_url),
        "real_model": real, "model": settings.planner_model if real else "controlled",
        "provider": settings.planner_provider if real else "controlled", "reasoning_effort": "low",
        "max_output_tokens": 8000, "format_repair_limit": 1, "provider_retries": settings.planner_max_retries,
        "temperature": 1.0 if settings.planner_provider in {"glm", "bigmodel", "zhipu"} else "provider default",
        "top_p": 0.95 if settings.planner_provider in {"glm", "bigmodel", "zhipu"} else "provider default",
        "fact_tool": "absent; deliberately measures unavailable-information degradation",
        "rules": payload["rules"], "rows": [], "complete": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    tool = await build_reviewed_knowledge_tool()
    for case in cases:
        history = case.get("history", [])
        goal = route_travel_goal(case["text"], history)
        for mode, strategy in MODES.items():
            provider = ModelCompanionProvider() if real else ControlledProvider()
            counted = CountingTool(tool, case.get("retrieval"))
            started = perf_counter()
            result, error, error_code, failure = None, None, None, None
            try:
                if goal.target_runtime == "companion":
                    result = await CompanionRuntime(Reader(), provider, counted, knowledge_strategy=strategy).run(
                        session_id="knowledge-eval", turn_id=case["id"], message=case["text"], goal=goal, messages=history)
            except Exception as exc:
                # Do not persist upstream response bodies or private credentials.
                error = type(exc).__name__
                error_code = getattr(exc, "code", None)
                failure = failure_details(exc)
            observations = provider.observations
            usages = [o["usage"] for o in observations if o.get("usage")]
            row = {"case_id": case["id"], "mode": mode, "input": case["text"], "goal": goal.model_dump(mode="json"),
                "output": result.model_dump(mode="json") if result else None, "error": error, "error_code": error_code,
                "failure": failure, "history": history,
                "rag_calls": counted.calls, "retrieval_seconds": counted.seconds,
                "latency_seconds": perf_counter() - started, "model_calls": len(observations),
                "usage": usages, "total_tokens": sum(u.get("total_tokens", 0) for u in usages) if usages else None,
                "model_observations": observations,
                "manual_scores": {key: None for key in ("accuracy", "relevance_completeness", "naturalness", "personalization", "source_support", "uncertainty_safety")}}
            if result:
                refs = {e.evidence_ref for e in result.knowledge_evidence}
                row["checks"] = {"citation_refs_valid": set(result.answer_evidence_refs) <= refs,
                    "no_handoff": result.planning_handoff is None,
                    "live_not_generated": not result.information_need.live_fact_required or not observations,
                    "untrusted_discarded": mode != "C" or case.get("retrieval") != "untrusted" or not result.knowledge_evidence,
                    "decision_expected": mode != "C" or "decision" not in case or result.information_need.knowledge_decision == case["decision"]}
            else:
                row["checks"] = {"runtime_expected": goal.target_runtime == case.get("runtime"), "no_runtime_mutation": True}
            report["rows"].append(row)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(case["id"], mode, "error=" + str(error), flush=True)
            if real and error and (not continue_on_error or error_code in {"planner_unavailable", "planner_timeout", "planner_authentication_failed", "planner_permission_denied", "planner_rate_limited", "planner_insufficient_balance"}):
                print("Stopped on first provider error; partial report preserved.", flush=True)
                return report
    report["complete"] = True
    report["summary"] = {}
    for mode in MODES:
        rows = [r for r in report["rows"] if r["mode"] == mode]
        companion = [r for r in rows if r["goal"]["target_runtime"] == "companion"]
        tokens = [r["total_tokens"] for r in rows if r["total_tokens"] is not None]
        report["summary"][mode] = {"cases": len(rows), "companion_cases": len(companion),
            "rag_calls": sum(r["rag_calls"] for r in rows), "rag_rate": sum(r["rag_calls"] > 0 for r in companion) / len(companion),
            "model_calls": sum(r["model_calls"] for r in rows), "provider_reported_tokens": sum(tokens) if tokens else None,
            "usage_missing_model_rows": sum(bool(r["model_calls"]) and r["total_tokens"] is None for r in rows),
            "mean_latency_seconds": mean(r["latency_seconds"] for r in companion) if companion else None,
            "retrieval_seconds": sum(r["retrieval_seconds"] for r in rows),
            "automatic_checks_passed": sum(all(r["checks"].values()) and not r["error"] for r in rows),
            "quality_scores": "manual review pending; no synthetic quality ranking"}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(real=args.real, output=args.output, fixture=args.fixture,
        case_ids=args.case_ids, continue_on_error=args.continue_on_error))
