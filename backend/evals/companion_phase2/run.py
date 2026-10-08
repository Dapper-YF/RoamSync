"""Run --mode offline or --mode live; live requires configured credentials, never falls back."""
import argparse
import asyncio
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from app.companion_contracts import CompanionDraft, KnowledgeToolRequest, SuggestionDraft
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.companion_provider import ModelCompanionProvider
from app.companion_runtime import CompanionRuntime
from app.config import get_settings
from app.travel_goal_router import route_travel_goal

CASES = [
    ("history", "西湖有什么历史？", True),
    ("culture", "西湖文化景观有哪些文化特点？", True),
    ("history_paraphrase", "西湖的历史背景能简单介绍一下吗？", True),
    ("profile", "杭州西湖的景观有哪些构成要素？", True),
    ("lifestyle", "杭州有什么当地生活体验？", True),
    ("tea_lifestyle", "杭州茶馆有哪些慢生活体验？", True),
    ("autumn", "秋天去杭州有什么特点？", True),
    ("autumn_culture", "杭州秋季赏桂有哪些文化特色？", True),
    ("parents", "杭州适合带父母玩吗？", True),
    ("senior", "带长辈去杭州如何安排得轻松些？", True),
    ("low_intensity", "带老人游杭州，怎么控制活动强度？", True),
    ("photography", "杭州有哪些适合摄影的地方？", True),
    ("unsupported_claim_trap", "西湖形成于什么精确年份？", True),
    ("no_season_results", "春天去杭州有什么特点？", True),
    ("unsupported_destination", "苏州有什么历史？", True),
    ("live_hours", "西湖今天几点关门？", False),
    ("live_weather", "明天杭州下雨吗？", False),
    ("original_reason", "为什么你推荐18点去西湖？", False),
    ("ack", "谢谢。", False),
    ("liked", "第二个不错。", False),
]


class Reader:
    async def load(self, context, need):
        return context


class CountingTool:
    def __init__(self, tool):
        self.tool, self.calls, self.results = tool, [], []

    async def retrieve(self, request):
        self.calls.append(request)
        result = await self.tool.retrieve(request)
        self.results.append(result)
        return result


class ControlledProvider:
    observations = []
    async def generate(self, context, need):
        if not context.knowledge_context:
            return CompanionDraft(response_text="缺少知识证据，可以继续讨论兴趣。")
        evidence = context.knowledge_context[0]
        suggestions = [SuggestionDraft(suggestion_type="experience", title=name,
            summary="依景观描述提出的摄影讨论方向，不保证最佳机位或时刻。", reasons=[evidence.text],
            evidence_refs=[evidence.evidence_ref]) for name in ("西湖湖面", "西湖堤道", "西湖亭台")] if "摄影" in context.current_message else []
        return CompanionDraft(response_text=evidence.text, suggestions=suggestions, evidence_refs=[evidence.evidence_ref])


class CountingProvider:
    def __init__(self, provider):
        self.provider, self.calls = provider, 0

    async def generate(self, context, need):
        self.calls += 1
        return await self.provider.generate(context, need)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def run(mode: str, output: Path, case_ids: list[str] | None = None):
    settings = get_settings()
    if mode == "live" and (not settings.planner_api_key.get_secret_value() or not settings.planner_model):
        raise RuntimeError("live eval requires the current model configuration; no fake fallback")
    tool = CountingTool(await build_reviewed_knowledge_tool())
    provider = CountingProvider(ModelCompanionProvider() if mode == "live" else ControlledProvider())
    runtime = CompanionRuntime(Reader(), provider, tool)
    rows, photograph_history = [], []
    report = {"measured_at": datetime.now(UTC).isoformat(), "mode": mode,
        "model_configuration": {"provider": settings.planner_provider, "model": settings.planner_model,
            "reasoning_effort": settings.intent_reasoning_effort} if mode == "live" else None,
        "corpus": "hangzhou_reviewed_v1_real_source_paraphrases", "database_access": False,
        "mutation_evidence": "No DB and no mutation port in this eval; formal snapshots measured separately in PostgreSQL tests",
        "claim_entailment": "manual review required; valid refs are not sentence verification",
        "results": rows, "complete": False}
    selected_cases = [case for case in CASES if not case_ids or case[0] in case_ids]
    if case_ids and set(case_ids) - {case[0] for case in selected_cases}:
        raise ValueError("unknown eval case ID")
    for index, (id, text, expected_call) in enumerate(selected_cases):
        history = photograph_history if id == "liked" else []
        goal = route_travel_goal(text, history[-12:])
        calls_before, provider_before = len(tool.calls), provider.calls
        observations_before = len(provider.provider.observations)
        started = time.perf_counter()
        row = {"id": id, "message": text, "goal": goal.model_dump(mode="json"),
               "knowledge_tool_required": expected_call, "mutation_tools_available": 0}
        try:
            result = await runtime.run(session_id=f"phase2-{mode}", turn_id=f"turn-{index}", message=text, goal=goal, messages=history)
            data = result.model_dump(mode="json")
            row.update(result=data, invalid_refs=[], error=None)
            if id == "photography":
                photograph_history = [{"id": f"turn-{index}", "user": text, "assistant": result.response_text,
                    "goal_routing": goal.model_dump(mode="json"), "companion_result": data}]
            row["live_fact_violation"] = (result.grounding_status != "live_verification_required") if id.startswith("live_") else None
            row["original_rationale_violation"] = bool(result.explanation and result.explanation.based_on_prior_decision) if id == "original_reason" else None
        except Exception as exc:
            row.update(result=None, error=type(exc).__name__, invalid_refs="rejected" if type(exc).__name__ == "CompanionContractError" else None,
                live_fact_violation=None, original_rationale_violation=None)
        row.update(latency_seconds=round(time.perf_counter() - started, 3),
            knowledge_tool_called=len(tool.calls) > calls_before, knowledge_tool_calls=len(tool.calls) - calls_before,
            provider_attempts=provider.calls - provider_before,
            provider_observations=provider.provider.observations[observations_before:],
            knowledge_requests=[r.model_dump(mode="json") for r in tool.calls[calls_before:]],
            retrieval_results=[r.model_dump(mode="json") for r in tool.results[calls_before:]])
        rows.append(row)
        write(output, report)
        print(json.dumps({"id": id, "error": row["error"], "tool_calls": row["knowledge_tool_calls"],
            "provider_attempts": row["provider_attempts"], "latency_seconds": row["latency_seconds"]}, ensure_ascii=False), flush=True)
    tp = sum(r["knowledge_tool_required"] and r["knowledge_tool_called"] for r in rows)
    fp = sum(not r["knowledge_tool_required"] and r["knowledge_tool_called"] for r in rows)
    fn = sum(r["knowledge_tool_required"] and not r["knowledge_tool_called"] for r in rows)
    report.update(complete=True, case_count=len(rows), real_provider_attempts=provider.calls if mode == "live" else 0,
        fake_provider_calls=provider.calls if mode == "offline" else 0,
        knowledge_tool_precision=tp/(tp+fp) if tp+fp else None, knowledge_tool_recall=tp/(tp+fn) if tp+fn else None,
        tool_confusion={"true_positive":tp,"false_positive":fp,"false_negative":fn},
        errors=sum(r["error"] is not None for r in rows),
        live_fact_violations=sum(r.get("live_fact_violation") is True for r in rows),
        original_rationale_violations=sum(r.get("original_rationale_violation") is True for r in rows))
    write(output, report)
    print(json.dumps({k:v for k,v in report.items() if k != "results"}, ensure_ascii=False), flush=True)
    return report


async def benchmark(output: Path):
    tool = await build_reviewed_knowledge_tool()
    cases = [
        ("西湖历史文化", "history_culture", None, None, "hz-westlake-history"),
        ("杭州西湖景观", "destination_profile", None, None, "hz-westlake-profile"),
        ("西湖摄影体验", "place_experience", None, None, "hz-westlake-experience"),
        ("杭州茶馆当地生活", "local_lifestyle", None, None, "hz-tea-lifestyle"),
        ("杭州秋天满觉陇赏桂", "seasonal_experience", "autumn", None, "hz-autumn-osmanthus"),
        ("带父母杭州轻松慢游", "audience_strategy", None, "senior", "hz-senior-strategy"),
        ("杭州慢游休息节奏", "travel_strategy", None, "senior", "hz-slow-travel-strategy"),
        ("杭州春天赏花", "seasonal_experience", "spring", None, None),
    ]
    rows = []
    for query, type, season, audience, expected in cases:
        request = KnowledgeToolRequest(query=query, destination="杭州", knowledge_types=[type],
            season_tags=[season] if season else [], audience_tags=[audience] if audience else [], max_results=3)
        result = await tool.retrieve(request)
        rows.append({"request":request.model_dump(mode="json"),"expected_document":expected,
            "correct":expected in [e.document_id for e in result.evidence] if expected else not result.evidence,
            "result":result.model_dump(mode="json")})
    value = {"measured_at":datetime.now(UTC).isoformat(),"mode":"real_curated_corpus_lexical_no_model",
        "cases":len(rows),"passed":sum(r["correct"] for r in rows),"results":rows,"holdout":False}
    write(output,value)
    return value


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("--mode",choices=["offline","live","benchmark"],required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--case-id",action="append",help="Reproduce a measured bad case without rerunning the whole model batch")
    args=parser.parse_args()
    report=asyncio.run(benchmark(args.output) if args.mode == "benchmark" else run(args.mode,args.output,args.case_id))
    raise SystemExit(0 if (report.get("passed")==report.get("cases") if args.mode == "benchmark" else report["errors"]==0) else 1)


if __name__ == "__main__":
    main()
