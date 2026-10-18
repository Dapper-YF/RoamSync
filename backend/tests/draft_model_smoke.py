"""Explicit opt-in real-provider smoke; creates ONLY an in-memory Draft database.

python tests/draft_model_smoke.py --env-file <local settings> --output <evidence.json>
No app.database import, no production engine, no Trip writes, no secrets in evidence.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.drafts.contracts import DraftCreate, RunRequest
from app.drafts.repository import DraftRepository, metadata
from app.drafts.service import DraftService, ModelDraftGenerator
from app.place_content.provider import AMapContentProvider
from app.place_content.repository import ContentRepository, metadata as content_metadata
from app.place_content.service import PlaceContentService


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine)
    content_metadata.create_all(engine)
    places = PlaceContentService(AMapContentProvider(settings.amap_rest_key), ContentRepository(engine))
    repo = DraftRepository(engine)
    diagnostics = []
    class DiagnosticGenerator(ModelDraftGenerator):
        async def generate(self, *args):
            try:
                return await super().generate(*args)
            except Exception as exc:
                detail = {"exception_type": type(exc).__name__}
                if hasattr(exc, "errors"):
                    detail["validation"] = [{"loc": e["loc"], "type": e["type"]} for e in exc.errors()]
                if isinstance(exc, ValueError) and str(exc) in {"model_incomplete", "wrong_day_count"}:
                    detail["code"] = str(exc)
                diagnostics.append(detail)
                raise
    service = DraftService(repo, DiagnosticGenerator(settings, places))
    draft = repo.create("controlled-smoke-user", DraftCreate(city="杭州", requirements="轻松游览，喜欢湖边散步和历史文化"))
    started = time.monotonic()
    draft = await service.run("controlled-smoke-user", draft.id, RunRequest(expected_version=draft.version, request_id=uuid4()))
    generated = draft.runs[-1].status == "completed"
    count = len(draft.plan.days) if draft.plan else 0
    confirmed = sum(item.place_id is not None for day in draft.plan.days for item in day.items) if draft.plan else 0
    first_seconds = round(time.monotonic() - started, 3)
    if generated:
        draft = await service.run("controlled-smoke-user", draft.id, RunRequest(expected_version=draft.version, request_id=uuid4(), requirements="第二天减少景点，留出更多休息时间"))
        modified = draft.runs[-1].status == "completed"
        draft = service.action("controlled-smoke-user", draft.id, draft.version, "save")
        draft = service.action("controlled-smoke-user", draft.id, draft.version, "cancel")
        draft = service.action("controlled-smoke-user", draft.id, draft.version, "restore")
        reopened = repo.get("controlled-smoke-user", draft.id)
    else:
        modified, reopened = False, draft
    evidence = {"source": "real_model", "model": settings.planner_model,
        "database": "isolated in-memory SQLite", "generated": generated, "modified": modified,
        "relative_days": count, "provider_confirmed_items": confirmed, "first_generation_seconds": first_seconds,
        "saved_cancelled_restored_reopened": reopened.saved and reopened.status == "active",
        "tables": inspect(engine).get_table_names(), "trip_table_exists": "trips" in inspect(engine).get_table_names(),
        "runs": [{"status": r.status, "source": r.source, "error": r.error} for r in reopened.runs], "diagnostics": diagnostics,
        "note": "Real model calls; provider-confirmed items only from real B service search, others explicitly unknown."}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False))
    engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
