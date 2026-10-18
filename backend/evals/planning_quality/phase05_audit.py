"""Read-only baseline binding and bounded, DB-free production-client probes."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from evals.planning_quality.version_audit import ROOT, collect, digest


def git_bytes(*args):
    return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=ROOT)


def manifest():
    paths = []
    for folder in ("backend/app", "backend/tests", "backend/evals"):
        paths += [p for p in (ROOT / folder).rglob("*") if p.is_file()
                  and p.suffix in {".py", ".json", ".md"}
                  and "results" not in p.relative_to(ROOT / folder).parts
                  and "__pycache__" not in p.parts]
    for folder in ("backend", "web", "android", "."):
        paths += [p for p in (ROOT / folder).glob("*") if p.is_file() and
                  (p.name in {"pyproject.toml", "uv.lock", "package.json", "pnpm-lock.yaml",
                   "Dockerfile", ".env.example", "gradle.properties", "gradlew", "gradlew.bat",
                   "alembic.ini", ".python-version", ".dockerignore"}
                   or p.name.startswith("tsconfig") and p.suffix == ".json"
                   or p.name.startswith(("vite.config.", "vitest.config."))
                   or p.name.endswith((".gradle.kts", ".toml")) or p.name.startswith("compose") and p.suffix == ".yaml")]
    paths += list((ROOT / "android/gradle").rglob("*.toml"))
    paths += list((ROOT / "android/gradle/wrapper").glob("*"))
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(set(paths)) if p.is_file()}


def bind(output):
    from app.config import Settings
    from evals.companion_provider_smoke import public_endpoint
    data = collect()
    files = manifest()
    data["full_development_manifest"] = files
    data["full_development_manifest_sha256"] = digest(json.dumps(files, sort_keys=True).encode())
    data["installed_local_packages"] = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
    data["local_platform"] = {"python": platform.python_version(), "platform": platform.platform()}
    settings = Settings(_env_file=ROOT / ".env")
    data["provider_config"] = {"base_url": public_endpoint(settings.planner_base_url),
        "proxy": public_endpoint(settings.planner_proxy_url), "max_output_tokens": settings.planner_max_output_tokens,
        "credentials_present": bool(settings.planner_api_key.get_secret_value()),
        "environment_proxy_presence": {key: bool(os.environ.get(key)) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")}}
    runtime = ('import json,importlib.metadata;from app.config import get_settings;s=get_settings();'
        'from urllib.parse import urlsplit;'
        'ep=lambda v:{"scheme":urlsplit(v).scheme,"host":urlsplit(v).hostname,"port":urlsplit(v).port,"path":urlsplit(v).path};'
        'print(json.dumps({"provider":s.planner_provider,"model":s.planner_model,"base_url":ep(s.planner_base_url),'
        '"proxy":ep(s.planner_proxy_url),"timeout":s.planner_timeout_seconds,"retries":s.planner_max_retries,'
        '"reasoning":s.planner_reasoning_effort,"max_output_tokens":s.planner_max_output_tokens,'
        '"packages":{d.metadata["Name"]:d.version for d in importlib.metadata.distributions()}}))')
    for name, entry in data["runtimes"].items():
        entry["effective_provider_and_dependencies"] = json.loads(subprocess.check_output(
            ["docker", "exec", name, "python", "-B", "-c", runtime], encoding="utf-8"))
    latest = ROOT / "backend/evals/results/companion_real_quality_20261011/current_source_manifest.json"
    measured = json.loads(latest.read_text(encoding="utf-8"))
    data["latest_909_binding"] = {"file": latest.relative_to(ROOT).as_posix(),
        "sha256": digest(latest.read_bytes()), "bound_count": len(measured),
        "mismatches": [k for k, sha in measured.items() if files.get("backend/" + k) != sha],
        "not_covered_current_files": [k for k in files if k.startswith(("backend/app/", "backend/tests/"))
                                      and k.removeprefix("backend/") not in measured]}
    tested_image = ROOT / "backend/evals/results/companion_real_quality_20261011/backend_test_image_manifest.json"
    tested = json.loads(tested_image.read_text(encoding="utf-8"))
    data["latest_909_binding"]["saved_image_manifest_sha256"] = digest(tested_image.read_bytes())
    data["latest_909_binding"]["saved_image_manifest_mismatches"] = [k for k,sha in tested.items() if files.get("backend/" + k) != sha]
    verification = json.loads((latest.parent / "verification.json").read_text(encoding="utf-8"))
    image_id = verification["backend"]["test_image_id"]
    image_check = subprocess.run(["docker", "image", "inspect", image_id, "--format", "{{.Id}}"], capture_output=True, text=True)
    data["latest_909_binding"]["image_reinspection"] = {
        "recorded_id": image_id, "available_now": image_check.returncode == 0,
        "saved_manifest_only": True, "contents_reinspected": False}
    old_names = git_bytes("ls-tree", "-r", "--name-only", "322f553", "backend/app", "backend/tests").decode().splitlines()
    differences = []
    for name in sorted(set(old_names) | {k for k in files if k.startswith(("backend/app/", "backend/tests/"))}):
        old = git_bytes("show", "322f553:" + name) if name in old_names else None
        if files.get(name) != (digest(old) if old is not None else None):
            differences.append({"file": name, "reference_sha256": digest(old) if old is not None else None,
                                "current_sha256": files.get(name)})
    data["current_vs_322"] = differences
    fixes = ["backend/app/decision_context.py", "backend/app/planning_intent_service.py",
             "backend/tests/test_decision_context.py", "backend/tests/test_planning_intents.py"]
    virtual = dict(files)
    for name in fixes:
        virtual[name] = digest(git_bytes("show", "322f553:" + name))
    data["proposed_integrated_manifest"] = virtual
    data["proposal"] = {"applied": False, "tested": False, "retain": "all current files except four explicit reference overlays",
        "overlay_from_322": fixes, "manifest_sha256": digest(json.dumps(virtual, sort_keys=True).encode()),
        "test_results": "no inherited 863/891/909 acceptance"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": data["full_development_manifest_sha256"], "909_mismatches": data["latest_909_binding"]["mismatches"],
                      "runtime_differences": {k:len(v.get("differences", [])) for k,v in data["runtimes"].items()}}, ensure_ascii=False))


async def probe(output):
    from app.config import Settings
    from app.model_client import build_model_client, create_model_response
    from evals.companion_provider_smoke import failure_details, public_endpoint
    settings = Settings(_env_file=ROOT / ".env")
    report = {"at_utc": datetime.now(UTC).isoformat(), "database_used": False, "production_config_changed": False,
        "max_probe_requests": 2, "requests": [], "batch_gate": False,
        "sdk": {k:importlib.metadata.version(k) for k in ("openai", "httpx", "httpcore")}}
    for kind in ("configured_native_proxy", "process_local_loopback"):
        if kind == "process_local_loopback":
            settings = settings.model_copy(update={"planner_proxy_url":"http://127.0.0.1:7897"})
        client = build_model_client(settings.model_copy(update={"planner_max_retries":0, "planner_timeout_seconds":30}))
        item = {"kind": kind, "proxy": public_endpoint(settings.planner_proxy_url),
            "base_url": public_endpoint(settings.planner_base_url), "model":settings.planner_model,
            "request_budget":256, "reasoning":"low", "stream":True, "retries":0, "timeout":30,
            "stage":"client_created", "http_response_status": None}
        async def request_hook(request):
            item["stage"] = "request_dispatched_before_response_headers"
        async def response_hook(response):
            item["stage"] = "response_headers_received_stream_or_parse"
            item["http_response_status"] = response.status_code
        client._client.event_hooks["request"].append(request_hook)
        client._client.event_hooks["response"].append(response_hook)
        start = perf_counter()
        try:
            result = await create_model_response(client, settings, model=settings.planner_model,
                instructions="Return only one JSON object, no other text.", input_text="Return a JSON object with ok=true.",
                text_format={"type":"json_schema", "name":"provider_smoke", "schema":{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"],"additionalProperties":False}},
                reasoning_effort="low", max_output_tokens=256)
            item.update(stage="stream_finished", status=result.status, finish_reason=result.finish_reason,
                        success=result.status == "completed" and json.loads(result.output_text) == {"ok":True},
                        usage=result.usage.model_dump() if hasattr(result.usage,"model_dump") else None)
        except Exception as exc:
            item.update(success=False, failure=failure_details(exc))
        finally:
            item["seconds"] = perf_counter() - start
            await client.close()
        report["requests"].append(item)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if item.get("success"):
            report["batch_gate"] = True
            report["selected_proxy"] = settings.planner_proxy_url
            break
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("bind", "probe"))
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "bind":
        bind(args.output)
    else:
        asyncio.run(probe(args.output))
