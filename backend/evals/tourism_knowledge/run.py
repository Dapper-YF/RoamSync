"""python -m evals.tourism_knowledge.run --output PATH (offline synthetic only)."""
import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.tourism_knowledge.models import TourismKnowledgeRequest
from app.tourism_knowledge.repository import matches_filters
from app.tourism_knowledge.interfaces import IndexedChunk
from app.tourism_knowledge.service import TourismKnowledgeService
from .fixtures import DeterministicFixtureEmbedding, NOW, ROOT, fixture_repository, load_documents


async def evaluate(mode: str = "lexical") -> dict:
    provider = None if mode == "lexical" else DeterministicFixtureEmbedding()
    repo = await fixture_repository(provider)
    service = TourismKnowledgeService(repo, provider, clock=lambda: NOW)
    documents = {doc.id: doc for doc in load_documents()}
    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    rows = []
    recall, categories, boundaries, filters, sources, empty = [], [], [], [], [], []
    for case in cases:
        if mode not in case.get("modes", ["lexical", "semantic", "hybrid"]):
            continue
        request = TourismKnowledgeRequest(query=case["query"], destination="杭州", top_k=3,
            include_fixtures=True, retrieval_mode=mode, **{k:v for k,v in case.get("filters", {}).items() if k != "destination"})
        if "destination" in case.get("filters", {}):
            request = request.model_copy(update={"destination": case["filters"]["destination"]})
        result = await service.retrieve_tourism_knowledge(request)
        identities = {hit.chunk.document_id for hit in result.hits}
        relevant = set(case["relevant"])
        case_recall = len(identities & relevant) / len(relevant) if relevant else None
        if case_recall is not None:
            recall.append(case_recall)
        category = bool(result.hits and result.hits[0].chunk.knowledge_type == case["category"]) if "category" in case else None
        if category is not None:
            categories.append(category)
        boundary = (result.advisory.live_fact_verification_required == case.get("live", False)
                    and result.advisory.planning_decision_context_required == case.get("decision", False)
                    and (not case.get("live", False) or not result.advisory.knowledge_sufficient))
        boundaries.append(boundary)
        row_filters = [matches_filters(IndexedChunk(hit.chunk), request, now=NOW) for hit in result.hits]
        row_sources = [hit.chunk.source == documents[hit.chunk.document_id].source for hit in result.hits]
        filters.extend(row_filters)
        sources.extend(row_sources)
        empty_ok = not result.hits if case.get("expected_empty") else None
        if empty_ok is not None:
            empty.append(empty_ok)
        rows.append({"id":case["id"], "request":request.model_dump(mode="json"),
            "document_ids":[hit.chunk.document_id for hit in result.hits], "recall_at_3":case_recall,
            "category_match":category, "boundary_correct":boundary, "expected_empty_correct":empty_ok,
            "filter_correct":all(row_filters), "source_preserved":all(row_sources),
            "advisory":result.advisory.model_dump(mode="json")})

    def metric(values):
        return {"numerator":sum(values), "denominator":len(values), "rate":sum(values)/len(values) if values else None}

    return {"mode":mode, "measured_at":datetime.now(UTC).isoformat(), "fixture_clock":NOW.isoformat(),
        "corpus":"synthetic_fixture_not_production_knowledge", "provider_calls":0,
        "embedding":"none" if provider is None else "deterministic_fake_not_real_semantic_quality",
        "case_count":len(rows), "recall_at_3":metric(recall), "category_match_at_1":metric(categories),
        "metadata_filter_accuracy_per_hit":metric(filters), "source_preservation_per_hit":metric(sources),
        "live_fact_boundary_accuracy":metric(boundaries), "empty_result_accuracy":metric(empty), "results":rows}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reports = asyncio.run(_all_modes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k:v for k,v in report.items() if k != "results"} for report in reports], ensure_ascii=False))
    metrics = ("recall_at_3", "category_match_at_1", "metadata_filter_accuracy_per_hit", "source_preservation_per_hit",
               "live_fact_boundary_accuracy", "empty_result_accuracy")
    raise SystemExit(0 if all(report[key]["rate"] == 1 for report in reports for key in metrics) else 1)


async def _all_modes():
    return [await evaluate(mode) for mode in ("lexical", "semantic", "hybrid")]


if __name__ == "__main__":
    main()
