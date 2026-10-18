"""Opt-in read-only real model diagnostic. No repository/database/Trip writes.

Run inside the isolated API image with a private Draft JSON snapshot and optional
service-file. Emits response metadata only, never model/user text or credentials.
"""
import argparse
import asyncio
import importlib.util
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.drafts.contracts import Draft
from app.drafts import service
from app.place_content.contracts import SearchResponse


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-file", required=True)
    parser.add_argument("--service-file")
    parser.add_argument("--places-file")
    args = parser.parse_args()
    module = service
    if args.service_file:
        spec = importlib.util.spec_from_file_location("app.drafts.diagnostic_service", args.service_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    original = module.create_model_response

    async def response(*positional, **kwargs):
        result = await original(*positional, **kwargs)
        usage = getattr(result, "usage", None)
        print(json.dumps({"event": "model_response", "status": result.status,
            "finish_reason": getattr(result, "finish_reason", None),
            "output_characters": len(result.output_text or ""),
            "completion_tokens": getattr(usage, "completion_tokens", None)}, ensure_ascii=False), flush=True)
        return result

    module.create_model_response = response
    draft = Draft.model_validate_json(Path(args.draft_file).read_text(encoding="utf-8-sig"))
    places_service = None
    if args.places_file:
        places = SearchResponse.model_validate_json(Path(args.places_file).read_text(encoding="utf-8-sig"))
        async def search(_query):
            return places
        places_service = SimpleNamespace(search=search)
    started = time.monotonic()
    try:
        plan = await asyncio.wait_for(module.ModelDraftGenerator(Settings(), places_service).generate(
            draft, draft.runs[-1].requirements), timeout=180)
        print(json.dumps({"event": "validated", "days": len(plan.days),
            "items": sum(len(d.items) for d in plan.days), "seconds": round(time.monotonic() - started, 2)}))
    except Exception as exc:
        print(json.dumps({"event": "failed", **module._safe_failure(exc),
            "seconds": round(time.monotonic() - started, 2)}), flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
