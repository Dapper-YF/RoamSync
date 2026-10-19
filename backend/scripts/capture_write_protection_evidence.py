"""Record test counts and source hashes; never connects to a database."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/write-protection"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


results = {}
for path in sorted(OUT.glob("*.xml")):
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    counts = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    counts["seconds"] = round(sum(float(s.get("time", 0)) for s in suites), 3)
    results[path.name] = counts

names = set(git("diff", "--name-only", "HEAD", "--", "backend/app").splitlines())
names |= {"backend/app/formal_write.py", "backend/tests/test_formal_write_protection.py"}
names |= {str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "backend/scripts").glob("*") if p.is_file()}
source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                 for name in sorted(names)}
manifest = {
    "captured_at": datetime.now(UTC).isoformat(),
    "scope": "isolated stage 1 formal itinerary write protection; not integrated/deployed",
    "base": "25a62cbeec4b7c5ac5b66c383c98b86f35440c21",
    "branch": git("branch", "--show-current"),
    "worktree": str(ROOT),
    "database": {"container": "roamsync-write-protection-pg", "image": "postgres:17-alpine",
                 "version": "17.11", "storage": "tmpfs; no production volume",
                 "database": "roamsync_test_write_protection", "additional_database": "promotion_test"},
    "runtimes": {"full-first.xml": "Windows Python 3.14.3", "linux-full.xml": "Linux Python 3.11.16"},
    "results": results,
    "historical_failures": ["red.xml", "red-matrix.xml", "red-metadata.xml", "focused-third.xml"],
    "known_skip": "place_content_postgres concurrent favorite requires exact database roamsync_test",
    "known_probe_failure": "focused-third: bare max_walking_minutes not universally enforced by existing Accept; unchanged",
    "external_services": "no real model or map calls; route fixture only",
    "source_sha256": source_hashes,
}
(OUT / "verification.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"branch": manifest["branch"], "results": results}, indent=2))
