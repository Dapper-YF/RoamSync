import asyncio

from evals.travel_facts.run import benchmark


def test_offline_travel_fact_resolution_benchmark():
    report=asyncio.run(benchmark())
    failures=[row for row in report["cases"] if not all(row["checks"].values())]
    assert not failures,failures
    assert report["case_count"]==28
    assert report["passed_cases"]==28
    assert all(metric["passed"]==metric["total"] for metric in report["metrics"].values())
