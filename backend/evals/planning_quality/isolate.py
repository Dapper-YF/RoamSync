"""Own one disposable PostgreSQL container; never address production services."""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("mock", "real"), required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.mode == "real" and args.repetitions < 3:
        parser.error("real comparisons require at least 3 repetitions")
    token = uuid.uuid4().hex
    name = "roamsync-phase0-eval-" + token[:12]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    resource = {"container_name": name, "owner_label": token, "image": "postgres:17-alpine",
        "storage": "tmpfs /var/lib/postgresql/data; no production volume", "cleanup": "pending",
        "api_worker_web_started": False, "production_network_joined": False}
    inventory = output.with_suffix(".resource.json")
    container_id = None
    try:
        container_id = docker("run", "--pull=never", "-d", "--name", name,
            "--label", "roamsync.phase0.owner=" + token, "--tmpfs", "/var/lib/postgresql/data",
            "-p", "127.0.0.1::5432", "-e", "POSTGRES_USER=roamsync_phase0_eval",
            "-e", "POSTGRES_DB=roamsync_phase0_eval", "-e", "POSTGRES_PASSWORD=phase0_disposable_only",
            "postgres:17-alpine")
        resource["container_id"] = container_id
        port = int(docker("port", container_id, "5432/tcp").rsplit(":", 1)[1])
        resource["loopback_port"] = port
        inventory.write_text(json.dumps(resource, indent=2), encoding="utf-8")
        for _ in range(40):
            probe = subprocess.run(["docker", "exec", container_id, "pg_isready", "-U", "roamsync_phase0_eval"],
                                   capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("isolated postgres did not become ready")
        url = f"postgresql+psycopg://roamsync_phase0_eval:phase0_disposable_only@127.0.0.1:{port}/roamsync_phase0_eval"
        env = {**os.environ, "APP_ENV": "test", "DATABASE_URL": url,
            "LANGGRAPH_DATABASE_URL": url.replace("postgresql+psycopg://", "postgresql://"),
            "ROAMSYNC_PHASE0_ISOLATED": "1", "ROAMSYNC_PHASE0_OWNER": token,
            "AMAP_REST_KEY": "", "TAVILY_API_KEY": "", "ROAMSYNC_TAVILY_API_KEY": "",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
        subprocess.run([sys.executable, "-B", "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)
        sql = "CREATE TABLE phase0_eval_marker(owner_token text NOT NULL); INSERT INTO phase0_eval_marker VALUES ('" + token + "');"
        docker("exec", container_id, "psql", "-X", "-U", "roamsync_phase0_eval", "-d", "roamsync_phase0_eval",
               "-v", "ON_ERROR_STOP=1", "-c", sql)
        result = subprocess.run([sys.executable, "-B", "-m", "evals.planning_quality.run", "--mode", args.mode,
            "--repetitions", str(args.repetitions), "--output", str(output)], cwd=BACKEND, env=env)
        resource["evaluation_exit_code"] = result.returncode
        code = result.returncode
    finally:
        if container_id:
            info = json.loads(docker("inspect", container_id))[0]
            if info["Id"] != container_id or info["Config"]["Labels"].get("roamsync.phase0.owner") != token or info["Name"] != "/" + name:
                raise RuntimeError("cleanup refused: resource identity changed")
            docker("rm", "-f", container_id)
            resource["cleanup"] = "only_owned_container_removed; tmpfs_discarded; artifacts_retained"
        inventory.write_text(json.dumps(resource, indent=2), encoding="utf-8")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
