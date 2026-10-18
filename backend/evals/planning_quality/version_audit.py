"""Read-only source/runtime binding; credentials are never recorded."""
import argparse
import ast
import difflib
import hashlib
import json
import subprocess
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SAFE_CONFIG = ("APP_ENV", "PLANNER_PROVIDER", "PLANNER_MODEL", "PLANNER_TIMEOUT_SECONDS",
               "PLANNER_MAX_RETRIES", "PLANNER_REASONING_EFFORT", "INTENT_REASONING_EFFORT",
               "RESEARCH_REASONING_EFFORT", "DECISION_LEDGER_VALIDATION_MODE", "WEATHER_PROVIDER",
               "ALLOW_MAP_ESTIMATES", "COMPANION_KNOWLEDGE_STRATEGY")


def command(*args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", check=True)
    return result.stdout.strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_manifest():
    paths = [*ROOT.joinpath("backend/app").rglob("*.py"),
             *ROOT.joinpath("backend/app").rglob("*.json"),
             *ROOT.joinpath("backend/tests").rglob("*.py"),
             *ROOT.joinpath("backend/tests").rglob("*.json")]
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(paths)}


def changed_functions(left, right):
    def functions(value):
        try:
            tree = ast.parse(value)
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        except SyntaxError:
            return {}
    a, b = functions(left), functions(right)
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def collect():
    manifest = source_manifest()
    report = {"schema": "phase0-version-binding-v1", "at_utc": datetime.now(UTC).isoformat(),
              "head": command("git", "--no-optional-locks", "rev-parse", "HEAD"),
              "branch": command("git", "--no-optional-locks", "branch", "--show-current"),
              "status": command("git", "--no-optional-locks", "status", "--porcelain=v1"),
              "source_manifest": manifest,
              "source_manifest_sha256": digest(json.dumps(manifest, sort_keys=True).encode()),
              "runtimes": {}}
    from app.config import Settings
    settings = Settings(_env_file=ROOT / ".env")
    report["workspace_effective_config"] = {k: getattr(settings, k.lower(), None) for k in SAFE_CONFIG}
    report["workspace_effective_config"]["credentials_configured"] = {
        "PLANNER_API_KEY": bool(settings.planner_api_key.get_secret_value()),
        "TAVILY_API_KEY": bool(settings.search_api_key), "AMAP_REST_KEY": bool(settings.amap_rest_key)}
    eval_paths = list(Path(__file__).parent.glob("*.py")) + list(Path(__file__).parent.glob("*.json"))
    report["eval_manifest"] = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(eval_paths)}
    runtime_code = ('import pathlib,hashlib,json; root=pathlib.Path("/app"); '
                    'print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() '
                    'for p in root.joinpath("app").rglob("*") if p.is_file() and p.suffix in (".py",".json")}))')
    for name in ("roamsync-api", "roamsync-agent-worker-1"):
        try:
            info = json.loads(command("docker", "inspect", name))[0]
            remote = json.loads(command("docker", "exec", name, "python", "-B", "-c", runtime_code))
            env = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
            differences = []
            local_names = {k.removeprefix("backend/") for k in manifest if k.startswith("backend/app/")}
            for relative in sorted(local_names | remote.keys()):
                path = ROOT / "backend" / relative
                local_hash = manifest.get("backend/" + relative)
                if local_hash == remote.get(relative):
                    continue
                row = {"file": relative, "local_sha256": local_hash, "runtime_sha256": remote.get(relative)}
                if relative.endswith(".py") and path.exists() and relative in remote:
                    code = 'from pathlib import Path;print(Path(' + repr("/app/" + relative) + ').read_text())'
                    old = command("docker", "exec", name, "python", "-B", "-c", code)
                    new = path.read_text(encoding="utf-8-sig")
                    row["changed_functions"] = changed_functions(old, new)
                    # Code-only diffs; no .env/configuration payloads or DB content.
                    row["diff"] = "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                              fromfile="runtime", tofile="workspace", n=2))[:20000]
                differences.append(row)
            report["runtimes"][name] = {
                "image_id": info["Image"], "container_id": info["Id"], "created": info["Created"],
                "started": info["State"]["StartedAt"], "status": info["State"]["Status"],
                "mounts": info["Mounts"], "file_count": len(remote), "manifest": remote,
                "config": {k: env.get(k) for k in SAFE_CONFIG},
                "credentials_configured": {k: bool(env.get(k)) for k in ("PLANNER_API_KEY", "TAVILY_API_KEY", "AMAP_REST_KEY")},
                "differences": differences}
        except (subprocess.SubprocessError, ValueError, KeyError) as exc:
            report["runtimes"][name] = {"unavailable": type(exc).__name__}
    binding_path = ROOT / "backend/evals/results/planner_reliability_20261008/blocked_final_binding.json"
    if binding_path.exists():
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        bound = binding["full_tracked_manifest"]
        report["latest_independent"] = {
            "application_commit": binding["application_commit"], "status": binding["status"],
            "checkout": binding["final_clean_checkout"],
            "binding_file_sha256": digest(binding_path.read_bytes()),
            "differences": [k for k in sorted(manifest.keys() | {k for k in bound if k.startswith(("backend/app/", "backend/tests/"))})
                            if manifest.get(k) != bound.get(k)]}
        checkout = Path(binding["final_clean_checkout"])
        report["latest_independent"]["checkout_exists"] = checkout.is_dir()
        if checkout.is_dir():
            report["latest_independent"]["actual_checkout_head"] = command("git", "--no-optional-locks", "-C", str(checkout), "rev-parse", "HEAD")
            report["latest_independent"]["checkout_app_test_binding_mismatches"] = [
                k for k, sha in bound.items() if k.startswith(("backend/app/", "backend/tests/"))
                and (not (checkout / k).exists() or digest((checkout / k).read_bytes()) != sha)]
    # Keep the older clean checkout anchor, but never call it the latest
    # chronological acceptance when a newer working-tree acceptance exists.
    if "latest_independent" in report:
        report["latest_independent"]["scope"] = "20261008_clean_checkout_anchor_not_latest_chronological"
    recent_path = ROOT / "backend/evals/results/companion_knowledge_strategy_20261011/verification.json"
    if recent_path.exists():
        recent = json.loads(recent_path.read_text(encoding="utf-8"))
        hashes = recent.get("source_sha256", {})
        report["latest_chronological_independent"] = {
            "evidence": recent_path.relative_to(ROOT).as_posix(),
            "evidence_sha256": digest(recent_path.read_bytes()),
            "git_head": recent.get("git_head"), "working_tree": recent.get("working_tree"),
            "backend": recent.get("backend"), "bound_files": len(hashes),
            "mismatches": [k for k, sha in hashes.items()
                           if not (ROOT / k).exists() or digest((ROOT / k).read_bytes()) != sha],
            "binding_scope": "selected_files_only_not_full_app_test_manifest",
            "full_manifest_acceptance": False,
        }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"head": data["head"], "manifest": data["source_manifest_sha256"],
                      "runtime_differences": {k: len(v.get("differences", [])) for k, v in data["runtimes"].items()},
                      "latest_independent_differences": data.get("latest_independent", {}).get("differences")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
