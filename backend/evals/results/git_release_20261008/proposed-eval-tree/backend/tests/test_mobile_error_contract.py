import pytest
from pydantic import TypeAdapter
from app.schemas import PlanningRunErrorCode


@pytest.mark.parametrize("code", [
    "planner_requested_place_unresolved",
    "planner_search_authentication_failed",
    "planner_research_unavailable",
    "planner_research_incomplete_output",
    "planner_research_invalid_output",
])
def test_research_failure_codes_remain_readable_in_planning_history(code):
    # These persisted worker failures must not turn GET run/history into HTTP 500.
    assert TypeAdapter(PlanningRunErrorCode).validate_python(code) == code
