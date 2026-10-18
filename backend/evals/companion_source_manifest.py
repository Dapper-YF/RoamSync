"""Hash code and dependencies only, never .env or response artifacts."""
import hashlib
import json
from pathlib import Path

if __name__=="__main__":
    root=Path.cwd()
    paths=[*root.glob("app/**/*.py"),*root.glob("tests/**/*.py"),
           *root.glob("evals/companion*.py"),*root.glob("evals/fixtures/companion*.json"),
           root/"pyproject.toml",root/"uv.lock"]
    print(json.dumps({str(p.relative_to(root)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths) if p.is_file()},indent=2))
