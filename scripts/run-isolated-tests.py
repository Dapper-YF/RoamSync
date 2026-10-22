"""Fresh Compose/tmpfs test databases per invocation, with source-bound evidence.

Run from any checkout: python scripts/run-isolated-tests.py
Only the dedicated compose.test.yaml is used. Never loads the official .env.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def source_hash():
    files = {}
    for folder in ("app", "tests", "migrations", "evals"):
        for path in (ROOT / "backend" / folder).rglob("*"):
            if path.is_file() and not {"__pycache__", "results", ".pytest_cache"}.intersection(path.parts) and path.suffix != ".pyc":
                files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("backend/Dockerfile", "backend/pyproject.toml", "backend/uv.lock", "backend/alembic.ini", "backend/.dockerignore", "compose.test.yaml", "scripts/run-isolated-tests.py"):
        files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return dict(sorted(files.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new evidence directory (must not exist)")
    args = parser.parse_args()
    project = "roamsync-test-" + uuid.uuid4().hex[:12]
    out = (args.output or ROOT / "artifacts" / project).resolve()
    out.mkdir(parents=True, exist_ok=False)
    empty_env = out / "empty.env"
    empty_env.write_text("# Deliberately empty; no official environment is loaded.\n")
    compose = ["docker", "compose", "--project-directory", str(ROOT), "--env-file", str(empty_env), "-p", project, "-f", str(ROOT / "compose.test.yaml")]
    evidence = {"project": project, "started_at": datetime.now(timezone.utc).isoformat(), "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "source_files": source_hash(), "stages": []}

    def run(stage, command, *, required=True):
        started = time.monotonic()
        with (out / (stage + ".log")).open("wb") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        evidence["stages"].append({"stage": stage, "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 3)})
        (out / "run.json").write_text(json.dumps(evidence, indent=2))
        print(f"{stage}: exit={result.returncode}, {evidence['stages'][-1]['seconds']}s", flush=True)
        if required and result.returncode:
            raise RuntimeError(f"{stage} failed; see {out / (stage + '.log')}")
        return result.returncode

    # Validate the actual Compose configuration before creating any resource.
    config = json.loads(subprocess.check_output(compose + ["config", "--format", "json"], cwd=ROOT, text=True))
    if set(config["services"]) != {"postgres-test", "api-test"} or config.get("volumes"):
        raise RuntimeError("test configuration must contain only isolated test services and no persistent volumes")
    postgres = config["services"]["postgres-test"]
    if postgres.get("ports") or postgres.get("volumes") or not postgres.get("tmpfs"):
        raise RuntimeError("test Postgres must have tmpfs data and no host port or volume mounts")
    if any(service.get("container_name") for service in config["services"].values()):
        raise RuntimeError("test services must use unique project-scoped container names")
    if any(service.get("ports") or service.get("volumes") for service in config["services"].values()):
        raise RuntimeError("test services cannot mount host data or publish ports")
    if any(network.get("external") for network in config.get("networks", {}).values()):
        raise RuntimeError("test services cannot join external networks")
    expected_env = {"APP_ENV": "test", "DATABASE_URL": "postgresql+psycopg://roamsync_test:roamsync_test_password@postgres-test:5432/roamsync_test", "LANGGRAPH_DATABASE_URL": "postgresql://roamsync_test:roamsync_test_password@postgres-test:5432/roamsync_test"}
    if any(config["services"]["api-test"]["environment"].get(key) != value for key, value in expected_env.items()):
        raise RuntimeError("test API and migrations must use the project-local test Postgres")
    if subprocess.check_output(compose + ["ps", "--all", "--quiet"], text=True).strip():
        raise RuntimeError("refusing to reuse existing test resources")
    failed = False
    try:
        run("build", compose + ["build", "api-test"])
        evidence["test_image"] = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", project + "-api-test"], text=True).strip()
        run("postgres", compose + ["up", "-d", "--wait", "postgres-test"])
        for database in ("roamsync_test_write_protection", "promotion_test"):
            run("create-" + database, compose + ["exec", "-T", "postgres-test", "psql", "-U", "roamsync_test", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", f"CREATE DATABASE {database}"])
        base = compose + ["run", "--rm", "-T", "--volume", out.as_posix() + ":/evidence"]
        target = "postgres-test:5432/roamsync_test_write_protection"
        preflight = "uv run --no-sync python tests/_database_safety.py && uv run --no-sync alembic upgrade head && "
        main_exit = run("backend-main", base + ["-e", "ROAMSYNC_AGENT_B_POSTGRES=1", "-e", "DATABASE_URL=postgresql+psycopg://roamsync_test:roamsync_test_password@" + target, "-e", "LANGGRAPH_DATABASE_URL=postgresql://roamsync_test:roamsync_test_password@" + target, "api-test", "sh", "-c", preflight + "uv run --no-sync pytest --ignore=tests/test_draft_promotion.py --ignore=tests/test_place_content_postgres.py --junitxml=/evidence/backend-main.xml --durations=10"], required=False)
        dedicated_exit = run("backend-dedicated", base + ["-e", "PROMOTION_TEST_DATABASE_URL=postgresql+psycopg://roamsync_test:roamsync_test_password@postgres-test:5432/promotion_test", "api-test", "sh", "-c", preflight + "uv run --no-sync pytest tests/test_draft_promotion.py tests/test_place_content_postgres.py --junitxml=/evidence/backend-dedicated.xml --durations=10"], required=False)
        failed = bool(main_exit or dedicated_exit)
    finally:
        run("cleanup", compose + ["down", "--remove-orphans"], required=False)
        after = source_hash()
        evidence["source_unchanged_during_run"] = after == evidence["source_files"]
        evidence["passed"] = not failed and after == evidence["source_files"] and all(s["exit_code"] == 0 for s in evidence["stages"])
        (out / "run.json").write_text(json.dumps(evidence, indent=2))
    print(f"Evidence: {out}")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
