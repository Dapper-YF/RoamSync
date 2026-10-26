"""Describe the actual proposed changes, independently of model arithmetic."""
from app.schemas import CandidatePlanSnapshot


def describe_plan_changes(context: dict, snapshot: CandidatePlanSnapshot, request: str) -> str:
    names = {item["id"]: item["name"] for item in context.get("candidates", [])}
    names.update({item["place_id"]: item["display_name"] for day in context["days"] for item in day["activities"]})
    lines = [f"本次回应你的要求：{request[:300]}", "候选与正式行程相比："]
    for day in context["days"]:
        original = {item["place_id"]: item for item in day["activities"] if item["status"] != "skipped"}
        proposed = {str(item.place_candidate_id) for item in snapshot.activities if item.day_date.isoformat() == day["date"]}
        protected = {key for key, item in original.items() if item["schedule_locked"] or item["status"] in {"active", "completed"}}
        final = proposed | protected
        added, removed = sorted(final - original.keys()), sorted(original.keys() - final)
        parts = []
        if added:
            parts.append("增加" + "、".join(names.get(key, "新地点") for key in added))
        if removed:
            parts.append("移出" + "、".join(names.get(key, "原地点") for key in removed))
        retained = len(final & original.keys())
        if retained:
            parts.append(f"保留原有 {retained} 个地点")
        if not parts:
            parts.append("保持空闲")
        lines.append(f"{day['date']}：{'；'.join(parts)}。")
    research = context.get("destination_research", {}).get("places", {})
    chosen = {str(item.place_candidate_id) for item in snapshot.activities}
    for key, evidence in research.items():
        if key in chosen:
            lines.append(f"选择{evidence['name']}：{evidence['reason']}（{evidence['prominence']}）。")
    for day in context["days"]:
        ordered = sorted((item for item in snapshot.activities if item.day_date.isoformat() == day["date"]), key=lambda item: item.planned_start_time)
        if len(ordered) > 1:
            lines.append(day["date"] + "的游览顺序：" + " → ".join(names.get(str(item.place_candidate_id), "地点") for item in ordered) + "。交通衔接已通过路线时间校验；每项安排的体验与节奏理由见下方。")
    lines.append("具体时间与每项选择的理由见下方；预计费用按候选内容计算，确认后才写入正式行程。")
    return "\n".join(lines)
