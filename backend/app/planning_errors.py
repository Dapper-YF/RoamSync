class PlannerNotConfiguredError(RuntimeError):
    pass


class PlannerProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        self.category = (
            "planner_schema_failure" if code in {"planner_invalid_output", "planner_research_invalid_output"}
            else "planner_semantic_constraint_failure" if code == "planner_requested_place_unresolved"
            else "provider_failure"
        )
        super().__init__(message)


class PlannerConstraintsUnsatisfiedError(RuntimeError):
    def __init__(self, codes: list[str], *, issues: list[dict] | None = None) -> None:
        self.codes = list(dict.fromkeys(codes))
        self.issues = issues or []
        super().__init__("candidate plan still violates constraints: " + ", ".join(self.codes))


class GoalConstraintsUnsatisfiedError(RuntimeError):
    """A candidate is valid but still misses an explicit hard user goal."""
    def __init__(self, feedback: list[dict]) -> None:
        self.feedback = feedback
        super().__init__("candidate plan does not satisfy explicit hard goals")


class DecisionContextInvariantError(RuntimeError):
    def __init__(self, codes: list[str]) -> None:
        self.codes = list(dict.fromkeys(codes))
        super().__init__("decision context invariant failed: " + ", ".join(self.codes))
