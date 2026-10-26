"""Deterministic recovery search-space construction and execution facts.

These small DTOs deliberately contain no database or model-client dependency.
They make the facts that a planner may use inspectable and testable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class RecoveryActivity:
    activity_id: str
    duration_minutes: int
    minimum_duration_minutes: int | None = None
    optional: bool = False


@dataclass(frozen=True)
class RecoveryOption:
    type: Literal["compress_activity", "change_travel_mode", "keep_current_plan"]
    affected_activity_ids: tuple[str, ...]
    recovered_minutes: int
    remaining_deficit_minutes: int
    estimated_cost_delta_fen: int | None
    compressions: tuple[dict, ...] = ()
    mode_changes: tuple[dict, ...] = ()
    constraints: tuple[str, ...] = ()
    explanation_facts: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def enumerate_recovery_options(
    *, deficit_minutes: int, activities: list[RecoveryActivity], travel_alternatives: list[dict] | None = None
) -> list[RecoveryOption]:
    """Return only fact-backed options; deficit is positive minutes to recover."""
    deficit = max(0, deficit_minutes)
    options: list[RecoveryOption] = []
    for activity in activities:
        if activity.minimum_duration_minutes is None:
            continue
        available = max(0, activity.duration_minutes - activity.minimum_duration_minutes)
        recovered = min(deficit, available)
        if recovered:
            options.append(RecoveryOption(
                "compress_activity", (activity.activity_id,), recovered, deficit - recovered, None,
                compressions=({"activity_id": activity.activity_id, "by_minutes": recovered,
                               "resulting_duration_minutes": activity.duration_minutes - recovered},),
                explanation_facts=(f"{activity.activity_id} has {available} compressible minutes",),
            ))
    for alternative in travel_alternatives or []:
        recovered = int(alternative.get("recovered_minutes", 0))
        if recovered <= 0:
            continue
        options.append(RecoveryOption(
            "change_travel_mode", tuple(str(value) for value in alternative.get("affected_activity_ids", ())),
            min(deficit, recovered), max(0, deficit - recovered), alternative.get("estimated_cost_delta_fen"),
            mode_changes=(dict(alternative),), explanation_facts=("provider-backed travel alternative",),
        ))
    options.append(RecoveryOption(
        "keep_current_plan", (), 0, deficit, None,
        constraints=("remaining_negative_slack" if deficit else "no_detected_deficit",),
        explanation_facts=(f"remaining deficit: {deficit} minutes",),
    ))
    return options


def recovery_metrics(*, before_deficit_minutes: int, option: RecoveryOption) -> dict:
    """Recompute display metrics from deterministic option facts, never model prose."""
    before = max(0, before_deficit_minutes)
    recovered = min(before, max(0, option.recovered_minutes))
    return {
        "recovered_delay_minutes": recovered,
        "resulting_minimum_slack_minutes": -(before - recovered),
        "activities_removed": [],
        "activities_compressed": list(option.compressions),
        "travel_mode_changes": list(option.mode_changes),
        "changed_future_activity_count": len(set(option.affected_activity_ids)),
        "remaining_hard_violations": list(option.constraints) if option.remaining_deficit_minutes else [],
        "estimated_cost_delta_fen": option.estimated_cost_delta_fen,
    }
