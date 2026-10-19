"""Capture local review evidence; no model, database or deployment writes."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = Path("E:/Study/RoamSync")
OUT = ROOT / "docs/evidence/write-integration-review"


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd).decode().strip()


results = {}
for path in sorted(OUT.glob("*.xml")):
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    counts = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    counts["seconds"] = round(sum(float(s.get("time", 0)) for s in suites), 3)
    results[path.name] = counts
names = set(git("diff", "--name-only", "25a62cb", "--", "backend/app").splitlines())
names |= {"backend/tests/test_formal_write_protection.py", "backend/tests/test_formal_write_integration_review.py",
          "backend/scripts/run-write-integration-review.ps1", "backend/scripts/capture_write_integration_review.py"}
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = {
    "verdict": "READY for scoped integration; canonical not merged or deployed",
    "captured_at": datetime.now(UTC).isoformat(), "canonical_head": git("rev-parse", "HEAD", cwd=CANONICAL),
    "canonical_tracked_dirty": git("status", "--short", "--untracked-files=no", cwd=CANONICAL),
    "canonical_preserved_sha256": {n: sha(CANONICAL / n) for n in ("README.md", "web/nginx.conf")},
    "review_branch": git("branch", "--show-current"), "original_commit": "7b67f68", "applied_commit": "f06a847",
    "source_sha256": {n: sha(ROOT / n) for n in sorted(names)}, "tests": results,
    "ignore_as_proof": {"review-red-missing.xml": "incorrect URL; corrected URL tested in review-red-missing-corrected.xml"},
    "database": {"container": "roamsync-write-integration-pg", "postgres": "17.11", "mounts": "tmpfs only; no production volumes",
                 "names": ["roamsync_test_write_protection", "promotion_test", "roamsync_test"]},
    "linux_test_image": "sha256:826a6a1062806cbb61077891830bb40f2b2aa69f4df1331bed7f2b06e0ee3ab5",
    "runtimes": {"windows-full.xml": "Python 3.14.3", "linux-full.xml": "Python 3.11.16"},
    "full_suite_skip": "favorite concurrency requires exact roamsync_test; separately executed favorites.xml",
    "real_model_validation": False, "live_map_validation": False,
    "scope_exclusions": ["production merge/deploy", "mixed precision", "route/time separation implementation", "Web/Android changes", "max_walking_minutes algorithm fix"],
}
(OUT / "verification.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, indent=2))
