"""Export exact synthetic responses with review, hashes and reproducible metrics."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/agent-b-20261022"


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def main():
    review = json.loads((ROOT / "backend/evals/fixtures/agent_b_holdout_review_20261022.json").read_text(encoding="utf-8"))
    assessed = {(r["case"], r["turn"]): r for r in review["records"]}
    report = {"base_sha": "f116ada6d6d46db7aeb48c29c8d5b45da379be00", "product_commit": "c83a93c",
              "holdout_review_scope": review["reviewer"], "runs": {}, "regression": {}}
    transcripts = ["# 完整合成对话、工具与人工审查", "原文按保存记录导出，未改写答案。不是真人用户研究。", ""]
    for name in ("development-before.json", "development-before-tail-replay.json", "development-after.json",
                 "development-final.json", "development-final-exclusive.json", "matched-before.json", "matched-after.json", "matched-final.json", "holdout-once.json"):
        data = read(name)
        records = sorted(data["records"], key=lambda r: (r["case"], r.get("turn", 0)))
        seconds = [r["seconds"] for r in records]
        report["runs"][name] = {"records": len(records), "mean_seconds": round(statistics.mean(seconds), 3),
            "median_seconds": round(statistics.median(seconds), 3), "max_seconds": max(seconds),
            "formal_before": data.get("before"), "formal_after": data.get("after"), "source_sha": data.get("source_sha")}
        eligible = name in {"development-before.json", "development-before-tail-replay.json", "development-final-exclusive.json", "holdout-once.json"}
        report["runs"][name]["eligible_for_write_count_evidence"] = eligible
        transcripts += [f"## {name}", ""]
        if name in {"development-after.json", "development-final.json"}:
            transcripts += ["注意：中间开发轮与回归共享测试库，有其他测试创建的合成Trip；此轮表计数不用于判定助手是否误写。以 final-exclusive 与 holdout 独立库记录为准。", ""]
        if name == "development-before.json":
            transcripts += ["注意：long-food 第11轮漏建内容缓存表。保留失败，但不能用于产品地点检索结论；后面的 tail-replay 已用相同前10轮上下文重放。", ""]
        for record in records:
            raw = record.get("raw", {})
            transcripts += [f"### {record['case']} / {record.get('turn', 0)}", "", "用户：" + record.get("user", "同一合成地点材料的条件比较"),
                "", "完整回复：", "", raw.get("assistant", "[no saved answer]"), "", f"耗时：{record['seconds']:.3f}s", ""]
            choices = record.get("choices", [])
            if choices:
                transcripts += ["语义决策：", "```json", json.dumps(choices, ensure_ascii=False, indent=2), "```", ""]
            sources = raw.get("read_tools", {}).get("web_search", {}).get("sources", [])
            if sources:
                transcripts += ["来源（完整引用绑定见同名原始JSON）：", ""]
                for source in sources:
                    transcripts += [f"- {source.get('source_id','')} / {source.get('title','')} / {source.get('read_level','')} / {source.get('url','')}"]
                transcripts.append("")
            if name == "holdout-once.json":
                item = assessed[(record["case"], record["turn"])]
                item["pass"] = not item["critical"] and min(item["scores"]) >= 1 and item["scores"][0] == 2 and item["scores"][4] == 2
                transcripts += ["人工审查：" + item["note"], f"评分（意图/工具/条件/事实/实用/完成）：{item['scores']}；通过={item['pass']}；关键失败={item['critical']}", ""]
    report["holdout"] = {"turns": len(review["records"]), "passed": sum(r["pass"] for r in review["records"]),
        "critical_failures": sum(r["critical"] for r in review["records"]), "verdict": "NO_GO",
        "unauthorized_formal_writes_observed": False, "review": review}
    for name in ("development-before.json", "development-final-exclusive.json"):
        records = [r for r in read(name)["records"] if r["case"] == "withdraw-city" and r["turn"] >= 2]
        correct = 0
        for r in records:
            context = r["raw"]["context"]
            slots = context["conversation_memory"]["slots"]
            correct += context.get("browsing_city") is None and "city" not in slots and "start_date" not in slots
        report["runs"][name]["withdrawal_state_correct"] = {"correct": correct, "assessed": len(records)}
    # Merge overlapping test suites by node ID instead of adding pass counts.
    outcomes = {}
    for name in ("full-windows-configured.xml", "dedicated-windows.xml", "b-final.xml", "promotion-windows.xml", "linux-main.xml"):
        p = OUT / name
        if not p.exists():
            continue
        tree = ET.parse(p).getroot()
        report["regression"][name] = [s.attrib for s in tree.iter("testsuite")]
        if name.startswith("linux"):
            continue
        for case in tree.iter("testcase"):
            key = (case.attrib["classname"], case.attrib["name"])
            status = "error" if case.find("error") is not None else "failed" if case.find("failure") is not None else "skipped" if case.find("skipped") is not None else "passed"
            if outcomes.get(key) != "passed":
                outcomes[key] = status
    report["windows_unique_final_outcomes"] = {s: sum(v == s for v in outcomes.values()) for s in ("passed", "failed", "error", "skipped")}
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "FULL_CONVERSATIONS.md").write_text("\n".join(transcripts), encoding="utf-8")
    manifests = {}
    for name in ("assistant_memory.py", "assistant_capabilities.py", "assistant_practical.py", "assistant_research.py", "assistant_turn.py", "companion_provider.py"):
        path = "backend/app/" + name
        before = subprocess.check_output(["git", "show", report["base_sha"] + ":" + path], cwd=ROOT)
        after = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        manifests[path] = {"base_lf_sha256": hashlib.sha256(before.replace(b"\r\n", b"\n")).hexdigest(), "final_lf_sha256": hashlib.sha256(after).hexdigest()}
    manifests["frozen_fixture_sha256"] = hashlib.sha256((ROOT / "backend/evals/fixtures/agent_b_20261022.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    manifests["evidence_hash_normalization"] = "SHA256 of bytes with CRLF normalized to LF (Git checkout portable)"
    manifests["evidence_files"] = {p.name: hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "manifest.json"}
    (OUT / "manifest.json").write_text(json.dumps(manifests, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"holdout_passed": report["holdout"]["passed"], "holdout_total": report["holdout"]["turns"], "windows_unique": report["windows_unique_final_outcomes"]}))


if __name__ == "__main__":
    main()
