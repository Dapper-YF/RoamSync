"""Validate Planner-authored decision provenance against formal and enriched facts."""
from __future__ import annotations

from datetime import time
from uuid import uuid4

from app.schemas import CandidatePlanSnapshot, DecisionEvidence, DecisionLedgerEntry, PlanValidationIssue


_REASONS = {
    "satisfy_hard_goal": "满足明确的时间或步行限制", "improve_soft_goal": "改善本次规划偏好",
    "respect_user_feedback": "参考上次未采用方案的反馈", "preserve_must_do": "保留你标记为必去的活动",
    "respect_minimum_duration": "遵守最短停留时间", "preserve_locked_activity": "保留锁定安排",
    "reduce_walking": "减少步行", "reduce_travel_time": "减少交通时间",
    "resolve_schedule_conflict": "解决时间冲突", "reduce_day_density": "降低当天安排密度",
    "preserve_existing": "尽量保留现有活动", "other": "依据本次规划事实调整",
}
_GOALS = {"end_before", "max_walking_minutes", "pace", "minimize_walking", "preserve_existing"}
_WALKING_CLAIMS = ("减少步行", "降低步行", "缩短步行", "控制步行", "少走路", "减少走路")


def _minutes(value: str | time) -> int:
    parsed = value if isinstance(value, time) else time.fromisoformat(str(value))
    return parsed.hour * 60 + parsed.minute


def _issue(code: str, decision_id: str | None = None, **details) -> PlanValidationIssue:
    return PlanValidationIssue(code=code, message=code.replace("_", " "), details={"decision_id": decision_id, **details})


def reconcile_route_repair_ledger(*, original: CandidatePlanSnapshot, repaired: CandidatePlanSnapshot,
                                  context: dict, adjustments: list[dict]) -> CandidatePlanSnapshot:
    """Attribute deterministic time-only repair to the system, never to Planner."""
    if original.decision_ledger is None or not adjustments:
        return repaired
    old = {item.candidate_id: item for item in original.activities}
    final = {item.candidate_id: item for item in repaired.activities}
    if set(old) != set(final) or original.route_legs != repaired.route_legs:
        raise ValueError("route repair changed activities or route facts beyond time")
    for key in old:
        if old[key].model_copy(update={"planned_start_time": final[key].planned_start_time}) != final[key]:
            raise ValueError("route repair changed a non-time activity field")
    formal = {str(item["id"]): item for day in context.get("days", []) for item in day.get("activities", [])}
    ledger = [entry.model_copy(deep=True) for entry in original.decision_ledger]
    for adjustment in adjustments:
        candidate_id = adjustment["candidate_id"]
        if candidate_id not in old or candidate_id not in final:
            raise ValueError("route repair referenced an unknown candidate")
        if adjustment["from_time"] != old[candidate_id].planned_start_time.strftime("%H:%M") or adjustment["to_time"] != final[candidate_id].planned_start_time.strftime("%H:%M"):
            raise ValueError("route repair adjustment does not match candidate times")
        activity_id = str(final[candidate_id].replaces_activity_id or "")
        for index, entry in enumerate(ledger):
            if str(entry.target_activity_id or "") != activity_id or entry.action_type == "remove":
                continue
            after = dict(entry.after)
            for name in ("start_time", "scheduled_time", "planned_start_time"):
                if name in after:
                    after[name] = final[candidate_id].planned_start_time.strftime("%H:%M")
            ledger[index] = entry.model_copy(update={"after": after})
        if activity_id not in formal:
            continue  # Addition time is reflected in the final snapshot; no existing activity was moved.
        moved = abs(_minutes(final[candidate_id].planned_start_time) - _minutes(formal[activity_id]["scheduled_time"])) >= 30
        indices = [index for index, entry in enumerate(ledger) if entry.action_type == "move" and str(entry.target_activity_id or "") == activity_id]
        if not moved:
            ledger = [entry for entry in ledger if not (entry.action_type == "move" and str(entry.target_activity_id or "") == activity_id)]
            continue
        system_entry = DecisionLedgerEntry(
            decision_id=f"route-repair:{uuid4()}", source="deterministic_route_repair", action_type="move",
            target_activity_id=final[candidate_id].replaces_activity_id,
            primary_reason="resolve_schedule_conflict",
            supporting_evidence=[DecisionEvidence(source_type="route_fact", fact_key="route_schedule_adjusted", value=candidate_id)],
        )
        if indices:
            ledger[indices[0]] = system_entry
            ledger = [entry for index, entry in enumerate(ledger) if index == indices[0] or index not in indices]
        else:
            ledger.append(system_entry)
    return repaired.model_copy(update={"decision_ledger": ledger})


def validate_decision_ledger(*, context: dict, snapshot: CandidatePlanSnapshot,
                             schedule_adjustments: list[dict] | None = None) -> tuple[list[PlanValidationIssue], dict]:
    """No model judgement: compare records with the actual final candidate and sourced facts.

    A None ledger is a pre-MVP historical snapshot. A Planner-produced empty list
    is not exempt from provenance requirements.
    """
    if snapshot.decision_ledger is None:
        issues = [_issue(code) for code in sorted(set(snapshot.provenance_parse_errors))]
        return issues, {"status": "invalid" if issues else "unavailable", "entries": [],
                        "error_codes": [issue.code for issue in issues],
                        "supported_change_count": 0, "unsupported_change_count": 0}

    decision = context.get("decision_context") or {}
    formal = {
        str(item["id"]): {**item, "day_date": day["date"]}
        for day in context.get("days", []) for item in day.get("activities", [])
        if item.get("status") != "skipped"
    }
    candidate = {str(item.replaces_activity_id): item for item in snapshot.activities if item.replaces_activity_id}
    additions = {str(item.place_candidate_id): item for item in snapshot.activities if not item.replaces_activity_id}
    formal_incoming_modes = {str(leg["to_activity_id"]): leg["mode"] for day in context.get("days", []) for leg in day.get("route_legs", []) if leg.get("to_activity_id")}
    protected = set((decision.get("protected_constraints") or {}).get("protected_activity_ids") or [])
    editable = set((decision.get("protected_constraints") or {}).get("editable_activity_ids") or [])
    target_dates = set(((decision.get("goal_context") or {}).get("target_days") or []))
    if not target_dates:
        target_dates = {day["date"] for day in context.get("days", [])}
    semantics = {str(item["activity_id"]): item for item in decision.get("activity_decision_semantics", [])}
    memory_by_id = {str(item["source_revision_id"]): item for item in decision.get("decision_memory", []) if item.get("source_revision_id")}
    memories = set(memory_by_id)
    goals = decision.get("goal_context") or context.get("planning_goals") or {}
    hard = goals.get("hard_goals") or {}
    soft = goals.get("soft_goals") or {}
    active_goals = {key for key in _GOALS if (hard.get(key) if key in hard else soft.get(key)) not in (None, False, "")}
    before_walk = sum(leg["duration_minutes"] for day in context.get("days", []) if day["date"] in target_dates for leg in day.get("route_legs", []) if leg["mode"] == "walk")
    after_walk = sum(leg.duration_minutes for leg in snapshot.route_legs if leg.day_date.isoformat() in target_dates and leg.mode == "walk")
    before_route = sum(leg["duration_minutes"] for day in context.get("days", []) if day["date"] in target_dates for leg in day.get("route_legs", []))
    after_route = sum(leg.duration_minutes for leg in snapshot.route_legs if leg.day_date.isoformat() in target_dates)
    route_available = bool(snapshot.route_legs) and all(not leg.is_estimated for leg in snapshot.route_legs) and any(
        day.get("route_legs") and all(not leg.get("is_estimated", False) for leg in day["route_legs"])
        for day in context.get("days", []) if day["date"] in target_dates)
    required: set[tuple[str, str]] = set()
    for activity_id, before in formal.items():
        if before["day_date"] not in target_dates or activity_id in protected or (editable and activity_id not in editable):
            continue
        after = candidate.get(activity_id)
        if after is None:
            required.add(("remove", activity_id))
            continue
        if after.duration_minutes < before["duration_minutes"]:
            required.add(("shorten", activity_id))
        if after.duration_minutes > before["duration_minutes"]:
            required.add(("extend", activity_id))
        if after.day_date.isoformat() != before["day_date"] or abs(_minutes(after.planned_start_time) - _minutes(before["scheduled_time"])) >= 30:
            required.add(("move", activity_id))
        if activity_id in formal_incoming_modes and after.transport_mode_to_here != formal_incoming_modes[activity_id]:
            required.add(("change_travel_mode", activity_id))
    required.update(("add", place_id) for place_id in additions)

    issues: list[PlanValidationIssue] = [_issue(code) for code in sorted(set(snapshot.provenance_parse_errors))]
    matched: set[tuple[str, str]] = set()
    entries: list[dict] = []
    seen_decisions: set[str] = set()
    repairs = {item["candidate_id"]: item for item in schedule_adjustments or []}
    for entry in snapshot.decision_ledger:
        errors: list[str] = []
        target = str(entry.target_place_candidate_id if entry.action_type == "add" else entry.target_activity_id or "")
        before = formal.get(target)
        after = additions.get(target) if entry.action_type == "add" else candidate.get(target)
        key = (entry.action_type, target)
        if entry.decision_id in seen_decisions or key in matched:
            errors.append("decision_provenance_duplicate")
        seen_decisions.add(entry.decision_id)
        matched.add(key)
        if entry.action_type == "add":
            if not after:
                errors.append("decision_action_mismatch")
        elif not before:
            errors.append("decision_target_unknown")
        elif entry.action_type == "remove" and after is not None:
            errors.append("decision_action_mismatch")
        elif entry.action_type != "remove" and after is None and target not in protected:
            errors.append("decision_action_mismatch")
        elif after is not None:
            delta = after.duration_minutes - before["duration_minutes"]
            moved = after.day_date.isoformat() != before["day_date"] or _minutes(after.planned_start_time) != _minutes(before["scheduled_time"])
            if entry.action_type == "shorten" and delta >= 0 or entry.action_type == "extend" and delta <= 0 or entry.action_type == "move" and not moved:
                errors.append("decision_action_mismatch")
            if entry.action_type == "preserve" and str(after.place_candidate_id) != str(before["place_id"]):
                errors.append("decision_action_mismatch")
            if entry.action_type == "change_travel_mode" and (target not in formal_incoming_modes or after.transport_mode_to_here == formal_incoming_modes[target]):
                errors.append("decision_action_mismatch")
        if not entry.supporting_evidence:
            errors.append("decision_evidence_missing")
        if entry.source == "deterministic_route_repair":
            evidence = [fact for fact in entry.supporting_evidence if fact.source_type == "route_fact" and fact.fact_key == "route_schedule_adjusted"]
            repair = repairs.get(str(evidence[0].value)) if len(evidence) == 1 else None
            if (entry.action_type != "move" or entry.primary_reason != "resolve_schedule_conflict" or
                repair is None or after is None or after.candidate_id != repair["candidate_id"] or
                after.planned_start_time.strftime("%H:%M") != repair["to_time"]):
                errors.append("decision_route_repair_provenance_invalid")
        resolved_goal_refs = set(entry.goal_refs)
        resolved_memory_refs = {str(ref) for ref in entry.memory_refs}
        resolved_semantic_refs = {str(ref.activity_id) for ref in entry.semantic_refs}
        for fact in entry.supporting_evidence:
            if fact.source_type == "goal" and fact.fact_key in active_goals:
                resolved_goal_refs.add(fact.fact_key)
            if fact.source_type == "activity_semantics" and target in semantics and fact.fact_key in {"importance", "can_skip", "minimum_duration_minutes"}:
                resolved_semantic_refs.add(target)
            if fact.source_type == "decision_memory" and fact.fact_key == "source_revision_id" and str(fact.value) in memories:
                resolved_memory_refs.add(str(fact.value))
        for ref in entry.goal_refs:
            if ref not in active_goals:
                errors.append("decision_goal_ref_invalid")
        for ref in entry.memory_refs:
            if str(ref) not in memories:
                errors.append("decision_memory_ref_invalid")
        for ref in entry.semantic_refs:
            official = semantics.get(str(ref.activity_id))
            if official is None or any(getattr(ref, field) is not None and getattr(ref, field) != official.get(field) for field in ("importance", "can_skip", "minimum_duration_minutes")):
                errors.append("decision_semantic_ref_invalid")
        for fact in entry.supporting_evidence:
            if fact.source_type == "goal" and (fact.fact_key not in resolved_goal_refs or fact.value not in (None, hard.get(fact.fact_key) if fact.fact_key in hard else soft.get(fact.fact_key))):
                errors.append("decision_evidence_unresolved")
            if fact.source_type == "decision_memory":
                if fact.fact_key == "source_revision_id" and str(fact.value) not in resolved_memory_refs:
                    errors.append("decision_evidence_unresolved")
                elif fact.fact_key == "rejection_reason_code" and not any(memory_by_id.get(ref, {}).get("rejection_reason_code") == fact.value for ref in resolved_memory_refs):
                    errors.append("decision_evidence_unresolved")
                elif fact.fact_key not in {"source_revision_id", "rejection_reason_code"}:
                    errors.append("decision_evidence_unresolved")
            if fact.source_type == "activity_semantics" and (target not in resolved_semantic_refs or fact.fact_key not in {"importance", "can_skip", "minimum_duration_minutes"} or fact.value != semantics.get(target, {}).get(fact.fact_key)):
                errors.append("decision_evidence_unresolved")
            if fact.source_type == "provider_fact" and (fact.fact_key != "place_candidate_id" or str(fact.value) != target or target not in {item["id"] for item in context.get("candidates", [])}):
                errors.append("decision_evidence_unresolved")
            if fact.source_type == "execution_state" and fact.fact_key not in (decision.get("execution_context") or {}):
                errors.append("decision_evidence_unresolved")
            if fact.source_type == "decision_context" and fact.fact_key not in {"formal_itinerary", "protected_constraints", "route_context", "user_preferences"}:
                errors.append("decision_evidence_unresolved")
            route_values = {"walking_before_minutes": before_walk, "walking_after_minutes": after_walk, "route_before_minutes": before_route, "route_after_minutes": after_route}
            if fact.source_type == "route_fact" and fact.fact_key == "route_schedule_adjusted":
                if entry.source != "deterministic_route_repair" or str(fact.value) not in repairs:
                    errors.append("decision_route_evidence_mismatch")
            elif fact.source_type == "route_fact" and (not route_available or fact.fact_key not in route_values or fact.value != route_values[fact.fact_key]):
                errors.append("decision_route_evidence_mismatch")
        if entry.primary_reason == "reduce_walking" and (not route_available or after_walk >= before_walk):
            errors.append("decision_route_claim_unsupported")
        if entry.primary_reason == "reduce_walking" and not {"walking_before_minutes", "walking_after_minutes"} <= {fact.fact_key for fact in entry.supporting_evidence if fact.source_type == "route_fact"}:
            errors.append("decision_route_evidence_missing")
        if entry.primary_reason == "reduce_travel_time" and (not route_available or after_route >= before_route):
            errors.append("decision_route_claim_unsupported")
        if entry.primary_reason == "reduce_travel_time" and not {"route_before_minutes", "route_after_minutes"} <= {fact.fact_key for fact in entry.supporting_evidence if fact.source_type == "route_fact"}:
            errors.append("decision_route_evidence_missing")
        if entry.primary_reason == "satisfy_hard_goal" and not resolved_goal_refs & {"end_before", "max_walking_minutes"}:
            errors.append("decision_goal_basis_missing")
        if entry.primary_reason == "respect_user_feedback" and not resolved_memory_refs:
            errors.append("decision_memory_basis_missing")
        if entry.primary_reason == "preserve_must_do" and semantics.get(target, {}).get("importance") != "must_do":
            errors.append("decision_semantic_basis_invalid")
        if entry.primary_reason == "preserve_locked_activity" and target not in protected:
            errors.append("decision_semantic_basis_invalid")
        if entry.primary_reason == "respect_minimum_duration" and semantics.get(target, {}).get("minimum_duration_minutes") is None:
            errors.append("decision_semantic_basis_invalid")
        if entry.action_type == "add" and not any(
            (f.source_type == "goal" and f.fact_key in resolved_goal_refs)
            or (f.source_type == "decision_memory" and f.fact_key == "source_revision_id" and str(f.value) in resolved_memory_refs)
            or (f.source_type == "provider_fact" and f.fact_key == "place_candidate_id" and str(f.value) == target)
            for f in entry.supporting_evidence
        ):
            errors.append("unsupported_addition")
        if entry.action_type == "remove" and before and semantics.get(target, {}).get("can_skip") is False:
            errors.append("decision_semantic_basis_invalid")
        if entry.action_type == "remove" and target in semantics and target not in resolved_semantic_refs:
            errors.append("decision_semantic_basis_missing")
        if entry.action_type == "shorten" and before and after and semantics.get(target, {}).get("minimum_duration_minutes") is not None and after.duration_minutes < semantics[target]["minimum_duration_minutes"]:
            errors.append("decision_semantic_basis_invalid")
        # A record must describe the observed state, not just name its action.
        if before and entry.before:
            if "duration_minutes" in entry.before and entry.before["duration_minutes"] != before["duration_minutes"]:
                errors.append("decision_before_mismatch")
            before_time = entry.before.get("start_time", entry.before.get("scheduled_time"))
            if before_time is not None and _minutes(before_time) != _minutes(before["scheduled_time"]):
                errors.append("decision_before_mismatch")
        if after and entry.after:
            if "duration_minutes" in entry.after and entry.after["duration_minutes"] != after.duration_minutes:
                errors.append("decision_after_mismatch")
            after_time = entry.after.get("start_time", entry.after.get("scheduled_time"))
            if after_time is not None and _minutes(after_time) != _minutes(after.planned_start_time):
                errors.append("decision_after_mismatch")
        if entry.action_type == "preserve" and target in protected and after is None and before and entry.after:
            if "duration_minutes" in entry.after and entry.after["duration_minutes"] != before["duration_minutes"]:
                errors.append("decision_after_mismatch")
            protected_time = entry.after.get("start_time", entry.after.get("scheduled_time"))
            if protected_time is not None and _minutes(protected_time) != _minutes(before["scheduled_time"]):
                errors.append("decision_after_mismatch")
        observed_cost = {
            "removed_activity_count": 1 if entry.action_type == "remove" else 0,
            "lost_stay_minutes": before["duration_minutes"] if entry.action_type == "remove" and before else
                max(0, before["duration_minutes"] - after.duration_minutes) if entry.action_type == "shorten" and before and after else 0,
            "activity_identity_change": entry.action_type in {"remove", "add"},
        }
        for metric, supplied in entry.tradeoff_cost.items():
            if metric in observed_cost and supplied != observed_cost[metric]:
                errors.append("decision_tradeoff_cost_mismatch")
            elif metric not in observed_cost:
                errors.append("decision_tradeoff_cost_unverified")
        if errors:
            issues.extend(_issue(code, entry.decision_id, action_type=entry.action_type, target=target,
                                 actual_start_time=after.planned_start_time.isoformat() if after else None,
                                 actual_duration_minutes=after.duration_minutes if after else None,
                                 evidence_keys=[f"{fact.source_type}.{fact.fact_key}" for fact in entry.supporting_evidence])
                          for code in sorted(set(errors)))
            continue
        name = before["display_name"] if before else next((item["name"] for item in context.get("candidates", []) if item["id"] == target), "新增地点")
        verified_before = {"start_time": str(before["scheduled_time"])[:5], "duration_minutes": before["duration_minutes"]} if before else {}
        verified_after = {"start_time": after.planned_start_time.strftime("%H:%M"), "duration_minutes": after.duration_minutes} if after else verified_before if entry.action_type == "preserve" and target in protected else {}
        entries.append({"decision_id": entry.decision_id, "action_type": entry.action_type, "target_activity_id": str(entry.target_activity_id) if entry.target_activity_id else None,
                        "source": entry.source,
                        "target_place_candidate_id": str(entry.target_place_candidate_id) if entry.target_place_candidate_id else None,
                        "activity_name": name, "before": verified_before, "after": verified_after, "reason": _REASONS[entry.primary_reason],
                        "primary_reason": entry.primary_reason, "goal_refs": sorted(resolved_goal_refs), "memory_refs": sorted(resolved_memory_refs),
                        "semantic_refs": [semantics[ref] for ref in sorted(resolved_semantic_refs) if ref in semantics], "tradeoff_cost": observed_cost,
                        "evidence_status": "validated"})
    for action, target in sorted(required - matched):
        issues.append(_issue("unsupported_addition" if action == "add" else "decision_provenance_missing", action_type=action, target=target))
    if route_available and after_walk >= before_walk and any(claim in snapshot.explanation for claim in _WALKING_CLAIMS):
        issues.append(_issue("decision_explanation_unsupported", walking_before_minutes=before_walk, walking_after_minutes=after_walk))
    supported_changes = {(item["action_type"], item["target_place_candidate_id"] if item["action_type"] == "add" else item["target_activity_id"])
                         for item in entries if item["action_type"] != "preserve"}
    unsupported_changes = required - supported_changes
    return issues, {"status": "validated" if not issues else "invalid", "entries": entries if not issues else [],
                    "error_codes": sorted({issue.code for issue in issues}),
                    "supported_change_count": len(supported_changes), "unsupported_change_count": len(unsupported_changes),
                    "walking_before_minutes": before_walk if route_available else None,
                    "walking_after_minutes": after_walk if route_available else None}
