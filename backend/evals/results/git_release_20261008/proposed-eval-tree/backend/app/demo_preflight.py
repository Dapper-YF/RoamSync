"""Real dependency checks for the Goal-Aware Planning live demonstration."""
from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace

from sqlalchemy import text

from app.config import get_settings
from app.database import session_factory
from app.external_facts import search_tavily
from app.maps_service import _fetch_amap_route, search_amap_places
from app.model_client import build_model_client, create_model_response


async def _check_database() -> str:
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return "postgres"


async def _check_tavily() -> str:
    await search_tavily(get_settings(), query="杭州西湖", max_results=1)
    return "tavily"


async def _check_amap_poi() -> str:
    results = await search_amap_places("西湖", "330100")
    if not results:
        raise RuntimeError("AMap POI returned no result")
    return "amap_poi"


async def _check_amap_route() -> str:
    # This calls the same AMap Route 2.0 adapter used by route enrichment.
    origin = SimpleNamespace(longitude=120.150270, latitude=30.260120)
    destination = SimpleNamespace(longitude=120.148520, latitude=30.231110)
    await _fetch_amap_route(origin, destination, "walk", "0571")
    return "amap_route"


async def _check_planner() -> str:
    settings = get_settings()
    frozen = {
        "provider": settings.planner_provider.strip().lower() in {"glm", "bigmodel", "zhipu"},
        "model": settings.planner_model.strip() == "glm-5.3-flash",
        "reasoning_effort": settings.planner_reasoning_effort == "high",
        "timeout": settings.planner_timeout_seconds == 180,
    }
    mismatches = [name for name, matches in frozen.items() if not matches]
    if mismatches:
        raise RuntimeError("frozen production Planner config mismatch: " + ", ".join(mismatches))
    if not settings.planner_api_key.get_secret_value().strip() or not settings.planner_model.strip():
        raise RuntimeError("planner is not configured")
    client = build_model_client(settings)
    try:
        response = await create_model_response(
            client,
            settings,
            model=settings.planner_model,
            instructions="Return exactly READY. Do not call tools.",
            input_text="Demo preflight",
            # Keep the smoke response small; this checks connectivity only.
            reasoning_effort=settings.planner_reasoning_effort,
            max_output_tokens=1024,
        )
    finally:
        await client.close()
    if response.status != "completed":
        raise RuntimeError(f"planner response status is {response.status}")
    return "glm (glm-5.3-flash, high, streaming, 180s)"


async def run(*, worker_running: bool) -> int:
    checks = {
        "postgres": _check_database(),
        "tavily": _check_tavily(),
        "amap_poi": _check_amap_poi(),
        "amap_route": _check_amap_route(),
        "glm": _check_planner(),
    }
    failed = False
    outcomes = await asyncio.gather(*checks.values(), return_exceptions=True)
    for name, outcome in zip(checks, outcomes, strict=True):
        try:
            if isinstance(outcome, Exception):
                raise outcome
            print(f"PASS {name}")
        except Exception as exc:  # keep secrets and payloads out of the preflight report
            failed = True
            print(f"FAIL {name}: {type(exc).__name__}: {str(exc)[:180]}")
    if worker_running:
        print("PASS agent_worker")
    else:
        failed = True
        print("FAIL agent_worker: Docker service is not running")
    print("DEMO READY" if not failed else "DEMO NOT READY")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real provider checks for Goal-Aware Demo.")
    parser.add_argument("--worker-running", action="store_true", help="Set only after Docker confirms agent-worker is running.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(worker_running=args.worker_running)))


if __name__ == "__main__":
    main()
