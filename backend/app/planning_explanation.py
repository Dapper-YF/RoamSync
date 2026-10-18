"""Describe the actual proposed changes, independently of model arithmetic."""
from app.schemas import CandidatePlanSnapshot


def candidate_cost_totals(context: dict, snapshot: CandidatePlanSnapshot) -> tuple[int, int]:
    original = [item for day in context["days"] for item in day["activities"] if item["status"] != "skipped"]
    represented = {str(item.replaces_activity_id) for item in snapshot.activities if item.replaces_activity_id}
    recovery = context.get("execution_recovery") or {}
    protected = set(recovery.get("protected_activity_ids") or []) | set(recovery.get("frozen_activity_ids") or [])
    protected |= set(((context.get("decision_context") or {}).get("protected_constraints") or {}).get("protected_activity_ids") or [])
    retained = sum(item["estimated_cost_fen"] for item in original if item["id"] not in represented and (
        item["id"] in protected or item["schedule_locked"] or item["status"] in {"active", "completed"}))
    return sum(item.estimated_cost_fen for item in snapshot.activities) + retained, sum(item["estimated_cost_fen"] for item in original)


def describe_plan_changes(context: dict, snapshot: CandidatePlanSnapshot, request: str, *, decision_review: dict | None = None) -> str:
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
    review = decision_review or {}
    for tradeoff in review.get("selection_tradeoffs", []):
        long_name = names.get(tradeoff["longer_place_candidate_id"], "较长步行候选")
        short_name = names.get(tradeoff["shorter_place_candidate_id"], "较短步行候选")
        if tradeoff["selected"] == "longer":
            benefits = {"explicitly_requested_place": "用户明确指定", "matches_saved_interest_category": "符合已保存的兴趣类别",
                        "matches_reviewed_landscape_interest": "精确审核的景观组件与当前自然或摄影兴趣匹配（非摄影效果保证）",
                        "matches_explicit_photography_interest": "符合摄影兴趣", "fewer_soft_category_conflicts": "较少软性类别冲突",
                        "lower_weather_penalty_from_exposure_hint_not_shelter_proof": "按地点类型提示推测天气影响较低（非避雨保证）", "suggested_duration_fits_known_free_slot": "建议时长更适合已知空档",
                        "lower_supplied_estimated_cost_not_verified_price": "输入预计费用较低（非核实票价）"}
            supported = "、".join(benefits[k] for k in tradeoff["longer_option_supported_advantages"])
            lines.append(f"{tradeoff['date']}选择{long_name}而非{short_name}，到同一固定活动的已查询步行腿多{tradeoff['extra_directed_walk_minutes']}分钟；"
                         + (f"输入依据提示的竞争收益为{supported}，是否值得由你决定。" if supported else "现有证据未显示补偿收益，少走路目标仍有改进空间。"))
        else:
            lines.append(f"{tradeoff['date']}选择{short_name}，到同一固定活动的已查询步行腿比{long_name}少{tradeoff['extra_directed_walk_minutes']}分钟；这不代表全天总步行或整体体验最优。")
    for requirement in review.get("effective_requirement_results", []):
        evidence = requirement["evidence"]
        if evidence.get("limit_fen") is not None:
            if requirement["status"] == "not_evaluable":
                lines.append("预算尚无法完整核验：目标范围的实际消费未知，候选费用只是剩余活动估算，不能据此认定总预算合规。")
            elif requirement["status"] == "satisfied":
                lines.append("已记录消费加剩余活动估算未超过该项预算限制；预付重叠及未记录费用不在此结论内。")
    lines.append("未核实的营业、预约和天气仍需在出行前确认；本次流程不承诺后续自动核验。")
    lines.append("具体时间与每项选择的理由见下方；预计费用按候选内容计算，确认后才写入正式行程。")
    return "\n".join(lines)
