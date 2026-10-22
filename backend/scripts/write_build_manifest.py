"""Build-time attestation of runtime inputs; contains paths and hashes only."""
import hashlib
import json
from pathlib import Path


def runtime_files(root):
    paths = [p for folder in ("app", "migrations") for p in (root / folder).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    return sorted(paths + [root / name for name in ("alembic.ini", "pyproject.toml", "uv.lock", "Dockerfile", ".dockerignore", "scripts/write_build_manifest.py")])


def fingerprint(path):
    data = path.read_bytes()
    if path.suffix in {".py", ".json", ".ini", ".toml", ".lock"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def manifest(root):
    return {"schema": 1, "kind": "backend", "files": {p.relative_to(root).as_posix(): fingerprint(p) for p in runtime_files(root)}}


if __name__ == "__main__":
    root = Path("/app")
    (root / "release-manifest.json").write_text(json.dumps(manifest(root), sort_keys=True, indent=2))
