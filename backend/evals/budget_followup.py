"""Targeted real-model budget probes; synthetic public inputs, no database writes.

Amounts are controlled estimates, never prices obtained from a venue/provider.
This direct Planner probe does not claim Graph/Validator/Accept acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from app.candidate_decisions import review_candidate_decisions
from app.config import get_settings
from app.openai_planner import OpenAIResponsesPlanner
from app.place_content.contracts import SearchQuery
from app.place_content.provider import AMapContentProvider
from evals.run_bounded_decision_eval import _state


async def run(output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Preserve prior evidence; choose a new output file")
    settings = get_settings().model_copy(update={"planner_max_output_tokens": 6000, "planner_max_retries": 0})
    report = {"started_at": datetime.now(UTC).isoformat(), "model": settings.planner_model,
              "database_writes": 0, "boundary": "direct_Planner_not_Graph_Validator_Accept",
              "cost_source": "controlled_synthetic_estimates_and_spending_not_provider_prices", "calls": []}

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    save()
    provider = AMapContentProvider(settings.amap_rest_key)
    places = []
    for query in ("西湖风景名胜区", "中国丝绸博物馆"):
        result = await provider.search(SearchQuery(query=query, city="杭州", page_size=5))
        exact = [p for p in result.items if p.name.removeprefix("杭州市").removeprefix("杭州") == query]
        if len(exact) != 1:
            report["failure"] = {"stage": "exact_place", "query": query, "count": len(exact)}
            save()
            return report
        places.append(exact[0])
    report["places"] = [{"name": p.name, "id": str(p.ref.place_id), "source": p.source.model_dump(mode="json")} for p in places]
    state, _, _ = _state()
    context = state["planning_context"]
    day_date = (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)).isoformat()
    context["trip"].update(id=state["trip_id"], destination="杭州", start_date=day_date, end_date=day_date,
                           total_budget_fen=None, daily_budget_fen=None)
    context["days"][0].update(date=day_date, activities=[])
    context["preferences"].update(interest_categories=["nature"], requirement_records=[])
    context["planning_goals"] = {"target_days": [day_date], "hard_goals": {}, "soft_goals": {}}
    context["external_facts"] = {}
    context["candidates"] = [{"id": str(p.ref.place_id), "name": p.name,
        "category": "nature" if i == 0 else "culture", "neighborhood": p.district or "",
        "description": "受控验收费用，非真实票价或预订报价", "longitude": p.location.longitude,
        "latitude": p.location.latitude, "suggested_duration_minutes": 60,
        "estimated_cost_fen": 8000 if i == 0 else 2000, "rating": p.rating or 0, "tags": [],
        "source": {"id": str(p.ref.place_id), "provider": "AMap POI", "confidence": "high",
                   "url": p.source.source_url}} for i, p in enumerate(places)]
    costs = {p["id"]: p["estimated_cost_fen"] for p in context["candidates"]}
    record = {"id": "budget-followup-controlled", "key": "daily_budget_fen", "value": 5000,
        "text": "这一天预算不超过50元", "strength": "hard", "status": "active", "supersedes": [],
        "source": {"kind": "user_explicit", "ref": "synthetic-budget-followup"},
        "scope": {"kind": "day", "date": day_date}}
    for scenario in ("active_budget", "revoked_budget", "unknown_spending"):
        case = deepcopy(state)
        ctx = case["planning_context"]
        active = scenario != "revoked_budget"
        current = deepcopy(record)
        if not active:
            current["status"] = "revoked"
        ctx["preferences"]["requirement_records"] = [current]
        ctx["effective_requirements"] = [current] if active else []
        ctx["effective_requirements_by_date"] = {day_date: [current] if active else []}
        ctx["actual_budget"] = {"local_date": day_date, "today_spent_fen": None if scenario == "unknown_spending" else 1000}
        case["user_request"] = "只新增一个地点；偏好西湖景观，但必须遵守当前有效的预算要求。费用为受控估算，不得擅自降低；缺少实际消费时不能声称总消费已满足预算。仅生成候选。"
        entry = {"scenario": scenario, "active_requirement_ids": [r["id"] for r in ctx["effective_requirements"]],
                 "controlled_spent_fen": ctx["actual_budget"]["today_spent_fen"], "input_costs_fen": costs}
        started = time.monotonic()
        stage = "planner"
        try:
            planner = OpenAIResponsesPlanner(settings)
            generated = await planner.generate(case)
            stage = "measurement"
            selected = list(generated.snapshot.activities)
            expected_cost = sum(costs[str(a.place_candidate_id)] for a in selected)
            review = review_candidate_decisions(ctx, generated.snapshot)
            entry.update(status="completed", selected=[{"place_id": str(a.place_candidate_id),
                "model_estimated_cost_fen": a.estimated_cost_fen} for a in selected],
                selected_count=len(selected), input_based_estimate_fen=expected_cost,
                input_based_known_exposure_fen=expected_cost + (entry["controlled_spent_fen"] or 0),
                estimate_preserved=all(a.estimated_cost_fen == costs[str(a.place_candidate_id)] for a in selected),
                explanation=generated.snapshot.explanation,
                decision_ledger=[item.model_dump(mode="json") for item in (generated.snapshot.decision_ledger or [])],
                requirement_review=review["effective_requirement_results"], hard_errors=review["hard_errors"],
                token_usage=generated.token_usage)
        except Exception as exc:
            entry.update(status="failed", stage=stage, code=getattr(exc, "code", type(exc).__name__))
        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["calls"].append(entry)
        save()
        print(json.dumps({"scenario": scenario, "status": entry["status"]}), flush=True)
    report["completed_at"] = datetime.now(UTC).isoformat()
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
