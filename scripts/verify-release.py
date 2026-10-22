"""Read-only source/image/artifact verification. Does not start services or use SQL.

python scripts/verify-release.py --api NAME --worker NAME --web NAME --output FILE
Old images without build manifests fail explicitly; they cannot be certified by
healthy endpoints alone. Optional --no-worker verifies an isolated API/Web build.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TEXT = {".py", ".json", ".ini", ".toml", ".lock", ".ts", ".tsx", ".js", ".mjs", ".css", ".html", ".yaml", ".template", ".conf"}


def copied_files(container, path):
    """Use Docker's read-only archive API, never shell interpolation or extraction."""
    raw = subprocess.check_output(["docker", "cp", f"{container}:{path}", "-"], stderr=subprocess.PIPE)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {member.name: archive.extractfile(member).read() for member in archive.getmembers() if member.isfile()}


def read_json(container, path):
    files = copied_files(container, path)
    if len(files) != 1:
        raise ValueError("expected one build manifest")
    return json.loads(next(iter(files.values())))


def fingerprint(data, path):
    if Path(path).suffix in TEXT or Path(path).name in {"Dockerfile", ".dockerignore"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def validate_paths(files):
    for path, digest in files.items():
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or "\\" in path or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("invalid build manifest entry")


def expected_web():
    paths = [p for name in ("src", "public") for p in (ROOT / "web" / name).rglob("*") if p.is_file()]
    paths += [ROOT / "web" / p for p in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "index.html", "tsconfig.json", "vite.config.ts", "nginx.local-product.conf.template", "Dockerfile", ".dockerignore", "scripts/write-build-manifest.mjs")]
    return {p.relative_to(ROOT / "web").as_posix(): fingerprint(p.read_bytes(), p) for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="roamsync-api")
    parser.add_argument("--worker", default="roamsync-agent-worker-1")
    parser.add_argument("--web", default="roamsync-web")
    parser.add_argument("--no-worker", action="store_true")
    parser.add_argument("--allow-stopped", action="store_true", help="verify build artifacts only; does not certify service readiness")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("evidence output must not already exist")
    spec = importlib.util.spec_from_file_location("runtime_manifest", ROOT / "backend/scripts/write_build_manifest.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    expected_backend = runtime.manifest(ROOT / "backend")["files"]
    report = {"schema": 1, "scope": "build_artifacts_only" if args.allow_stopped else "running_container_artifacts", "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "checks": [], "passed": True}
    for container, kind in [(args.api, "backend"), *([] if args.no_worker else [(args.worker, "backend")]), (args.web, "web")]:
        check = {"container": container, "kind": kind}
        try:
            info = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
            check.update(image=info["Image"], container_id=info["Id"], running=info["State"]["Running"])
            attestation = read_json(container, "/app/release-manifest.json" if kind == "backend" else "/usr/share/nginx/roamsync-source-manifest.json")
            if attestation.get("schema") != 1 or attestation.get("kind") != kind:
                raise ValueError("unsupported build manifest")
            validate_paths(attestation["files"])
            expected = expected_backend if kind == "backend" else expected_web()
            check["source_mismatches"] = sorted(p for p in set(expected) | set(attestation["files"]) if expected.get(p) != attestation["files"].get(p))
            check["source_files"] = len(expected)
            if kind == "web":
                validate_paths(attestation["artifacts"])
                built = copied_files(container, "/usr/share/nginx/html")
                artifacts = {str(PurePosixPath(p).relative_to("html")): hashlib.sha256(data).hexdigest() for p, data in built.items()}
                check["artifact_mismatches"] = sorted(p for p in set(artifacts) | set(attestation["artifacts"]) if artifacts.get(p) != attestation["artifacts"].get(p))
                check["artifact_files"] = len(artifacts)
                check["build"] = attestation.get("build", {})
            else:
                live = {}
                for folder in ("app", "migrations"):
                    for path, data in copied_files(container, "/app/" + folder).items():
                        if "__pycache__" not in PurePosixPath(path).parts and not path.endswith(".pyc"):
                            live[path] = fingerprint(data, path)
                for name in ("alembic.ini", "pyproject.toml", "uv.lock", "Dockerfile", ".dockerignore", "scripts/write_build_manifest.py"):
                    live[name] = fingerprint(next(iter(copied_files(container, "/app/" + name).values())), name)
                check["artifact_mismatches"] = sorted(p for p in set(live) | set(expected) if live.get(p) != expected.get(p))
            check["passed"] = not check["source_mismatches"] and not check["artifact_mismatches"] and (check["running"] or args.allow_stopped)
        except (subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
            check.update(passed=False, error_type=type(exc).__name__, reason="missing, invalid or mismatched build evidence; health is insufficient")
        report["checks"].append(check)
        report["passed"] &= check["passed"]
        print(f"{'PASS' if check['passed'] else 'FAIL'} {kind}: {container}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
