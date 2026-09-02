class PlannerNotConfiguredError(RuntimeError):
    pass


class PlannerProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class PlannerConstraintsUnsatisfiedError(RuntimeError):
    def __init__(self, codes: list[str]) -> None:
        self.codes = list(dict.fromkeys(codes))
        super().__init__("candidate plan still violates constraints: " + ", ".join(self.codes))
