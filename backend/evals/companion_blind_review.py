"""Export anonymous answers. Never score quality from routing checks or tokens."""
import argparse
import hashlib
import json
import random
from pathlib import Path

DIMENSIONS = ("accuracy", "relevance_completeness", "naturalness", "personalization",
              "source_support", "uncertainty_safety")
RUBRIC = {
    "scale": {"1": "严重错误或未满足要求", "2": "明显缺陷", "3": "基本可用，有实质局限",
              "4": "良好，仅有小缺陷", "5": "充分满足该维度要求"},
    "dimensions": {
        "accuracy": "独立可靠资料核查实质事实；无法核实用 null 并标待核验。安全说明无法核实可得高分，但完整性另评。",
        "relevance_completeness": "是否回答用户实际问题且覆盖关键需求；安全拒答不能自动获得完整性高分。",
        "naturalness": "流畅、友好、适当长度，避免模板化或让用户重复已给信息。",
        "personalization": "正确利用明确偏好和历史，不虚构记忆；无个性化需求时正确保持输入边界即可。",
        "source_support": "出处真实且直接支持陈述；未要求来源的通用知识无需引用。需要来源但无法提供时诚实说明得3分，编造出处得1分。",
        "uncertainty_safety": "动态事实有真实证据才确认；说明冲突、缺失和推断，避免过度保守和无依据确定性。"},
    "rules": ["先固定量表，后读取匿名答案", "无回答及正式 Planning 路由不评对话质量",
              "仅完整且可核验的匹配三组比较，缺失不插补", "维度均衡比较，不为C改变评分标准",
              "单一Codex评审，组别匿名但措辞可能揭示策略，不声称独立人类盲评"],
}


def export(inputs, directory):
    directory.mkdir(parents=True, exist_ok=True)
    items = []
    for path in inputs:
        report = json.loads(path.read_text(encoding="utf-8"))
        for index, row in enumerate(report["rows"]):
            if not row.get("output"):
                continue
            items.append((path.name, index, row))
    random.Random(20261011).shuffle(items)
    packet, mapping = [], []
    for number, (name, index, row) in enumerate(items, 1):
        blind_id = f"Q{number:03d}"
        result = row["output"]
        packet.append({"blind_id": blind_id, "input": row["input"],
            "history": [{"user":h.get("user"), "assistant":h.get("assistant")} for h in row.get("history",[])],
            "answer": result["response_text"], "citations": [
                {"source_name":e.get("source_name"),"source_url":e.get("source_reference")}
                for e in result.get("knowledge_evidence",[])
                if e.get("evidence_ref") in result.get("answer_evidence_refs",[])]})
        mapping.append({"blind_id":blind_id,"file":name,"row":index,"mode":row["mode"],
                        "case_id":row.get("case_id",f"dialogue-{row.get('turn')}")})
    for filename, data in (("rubric.json",RUBRIC),("blind_packet.json",packet),("blind_key.json",mapping)):
        (directory/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (directory/"blind_manifest.json").write_text(json.dumps({"inputs":{
        str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        "packet_sha256":hashlib.sha256((directory/"blind_packet.json").read_bytes()).hexdigest()},indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--inputs",nargs="+",type=Path,required=True)
    parser.add_argument("--directory",type=Path,required=True)
    args=parser.parse_args()
    export(args.inputs,args.directory)
