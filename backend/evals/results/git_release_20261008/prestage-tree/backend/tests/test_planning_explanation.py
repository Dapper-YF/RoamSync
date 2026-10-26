from app.planning_explanation import describe_plan_changes
from app.schemas import CandidatePlanSnapshot


def test_summary_uses_actual_changes_and_keeps_unrepresented_locked_stops():
    context = {"candidates": [], "days": [{"date": "2026-09-09", "activities": [
        {"place_id": "locked", "display_name": "固定参观", "status": "planned", "schedule_locked": True},
        {"place_id": "removed", "display_name": "取消的餐厅", "status": "planned", "schedule_locked": False},
    ]}]}
    snapshot = CandidatePlanSnapshot(activities=[], explanation="保留所有地点并增加十个景点。")
    summary = describe_plan_changes(context, snapshot, "减少安排")
    assert "移出取消的餐厅" in summary
    assert "保留原有 1 个地点" in summary
    assert "移出固定参观" not in summary
    assert "十个景点" not in summary
