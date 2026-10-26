"""Record observed exits and bind final evidence without credentials or private data."""
import hashlib
import json
from pathlib import Path

directory=Path(__file__).parent
root=directory.parents[3]
image=json.loads((directory/"backend_test_image_manifest.json").read_text(encoding="utf-8-sig"))
current=json.loads((directory/"current_source_manifest.json").read_text(encoding="utf-8-sig"))
bound={k:v for k,v in image.items() if k.startswith(("app/","tests/")) or k in ("pyproject.toml","uv.lock")}
differences=[k for k,v in bound.items() if current.get(k)!=v]
assert not differences
reports={name:json.loads((directory/name).read_text(encoding="utf-8")) for name in
    ("fixed18_real.json","holdout_real.json","dialogue_real.json","representative.json","solo_repeat.json")}
replay=json.loads((directory/"handoff_replay_after_fix.json").read_text(encoding="utf-8"))
verification={"baseline":"0b5010fe5a7b06dcec1ab7b159b5b337244247ae","production_deployed":False,
    "production_database_modified":False,"real_eval_database_used":False,
    "provider_smoke":{"original_proxy":"transport failed", "loopback_proxy":"completed", "config_persisted":False},
    "real_batches":{name:{"runner_complete":r["complete"],"rows":len(r["rows"]),
        "errors":sum(bool(row.get("error")) for row in r["rows"])} for name,r in reports.items()},
    "blind_answer_ratings":68,"matched_quality_triplets_fixed":15,"matched_quality_triplets_holdout":7,
    "original_dialogue_destination_checks_failed":3,"handoff_replay_after_fix_all_pass":all(all(r["checks"].values()) for r in replay),
    "backend":{"passed":909,"failed":0,"warnings":2,"seconds":77.10,"exit_code":0,
        "environment":"isolated Linux/Python3.11/PG17 tmpfs, fresh migration0->0034",
        "log":"backend_regression_clean_exit.log", "bound_files":len(bound),"app_tests_dependencies_differences":differences,
        "test_image_id":"dfcf00d565d463d18baf7df858ed94fff960b85d272a609148e5ba64f786d2f8"},
    "web":{"passed":125,"test_exit":0,"typecheck_exit":0,"build_exit":0},
    "local_targeted":{"passed":42,"exit_code":0,"database_endpoint":"unreachable isolated endpoint; tests pure/mocked"},
    "failed_attempts_preserved":["targeted_regression.log: invalid evidence fixture corrected",
        "Windows DB-containing test selection interrupted; isolated diagnostic reproduced Psycopg Proactor pre-connect failure",
        "backend_regression_final.log: 909 assertions passed but wrapper failed after image diagnostic inherited Compose labels; rerun clean exit"],
    "cleanup":"only roamsync-real-quality-test project removed", "quality_gate":"PARTIAL / OPEN",
    "default_recommendation":"retain selective C; not evidence of universal superiority or release approval"}
(directory/"verification.json").write_text(json.dumps(verification,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
manifest={str(p.relative_to(directory)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(directory.rglob("*")) if p.is_file() and p.name!="evidence_manifest.json"}
(directory/"evidence_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"bound_files":len(bound),"differences":differences,"artifacts":len(manifest),"quality_gate":"PARTIAL / OPEN"}))
