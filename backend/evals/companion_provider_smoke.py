"""Minimal real request through the production client; sanitized diagnostics only."""
import asyncio
import importlib.metadata
import json
import re
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from app.config import get_settings
from app.model_client import build_model_client, create_model_response
from app.openai_planner import translate_model_error


def failure_details(exc):
    chain, seen, current = [], set(), exc
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        item = {"type": type(current).__name__}
        status = getattr(current, "status_code", None)
        if isinstance(status, int):
            item["http_status"] = status
        body = getattr(current, "body", None)
        if isinstance(body, dict):
            error = body.get("error", body)
            code = error.get("code") if isinstance(error, dict) else None
            if isinstance(code, (str, int)) and re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", str(code)):
                item["provider_error_code"] = str(code)
        chain.append(item)
        current = current.__cause__ or current.__context__
    return {"application_code": getattr(exc, "code", None) or translate_model_error(exc).code, "exception_chain": chain}


def public_endpoint(value):
    url = urlparse(value)
    return {"scheme": url.scheme, "host": url.hostname, "port": url.port, "path": url.path}


async def run(output):
    settings = get_settings()
    report = {"config": {"provider": settings.planner_provider, "model": settings.planner_model,
        "base_url": public_endpoint(settings.planner_base_url), "proxy": public_endpoint(settings.planner_proxy_url),
        "credentials_present": bool(settings.planner_api_key.get_secret_value()), "timeout": settings.planner_timeout_seconds,
        "retries": settings.planner_max_retries, "cwd": str(Path.cwd()), "env_file_exists": Path(".env").exists(),
        "openai_sdk": importlib.metadata.version("openai"), "httpx": importlib.metadata.version("httpx")},
        "request": {"input": "Return a JSON object with ok=true.", "max_output_tokens": 256, "reasoning_effort": "low"},
        "real": True, "database_used": False}
    start, client = perf_counter(), None
    try:
        client = build_model_client(settings)
        result = await create_model_response(client, settings, model=settings.planner_model,
            instructions="Return only one JSON object, no other text.", input_text=report["request"]["input"],
            text_format={"type":"json_schema", "name":"provider_smoke", "schema":{"type":"object", "properties":{"ok":{"type":"boolean"}}, "required":["ok"], "additionalProperties":False}},
            reasoning_effort="low", max_output_tokens=256)
        usage = getattr(result, "usage", None)
        report["response"] = {"status": result.status, "finish_reason": result.finish_reason,
            "output": result.output_text, "usage": usage.model_dump() if hasattr(usage, "model_dump") else None}
        report["success"] = result.status == "completed" and json.loads(result.output_text) == {"ok":True}
    except Exception as exc:
        report.update(success=False, failure=failure_details(exc))
    finally:
        if client:
            await client.close()
        report["seconds"] = perf_counter() - start
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    asyncio.run(run(parser.parse_args().output))
