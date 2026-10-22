"""Request-local budgets and allowlisted diagnostics; never persist provider text."""
import asyncio
import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic

from pydantic import ValidationError


active_turn = ContextVar("assistant_reliable_turn", default=None)


class AnswerBudgetExceeded(RuntimeError):
    code = "answer_budget_exhausted"


def error_details(exc, stage="answer"):
    chain, seen, validation = [], set(), []
    current = exc
    code = getattr(exc, "code", None)
    http_status = None
    finish_reason = None
    while current is not None and id(current) not in seen and len(chain) < 6:
        seen.add(id(current))
        chain.append(type(current).__name__)
        http_status = http_status or getattr(current, "status_code", None) or getattr(getattr(current, "response", None), "status_code", None)
        finish_reason = finish_reason or getattr(current, "finish_reason", None)
        if isinstance(current, ValidationError):
            validation = [{"field": ".".join(map(str, e["loc"])), "type": e["type"]}
                          for e in current.errors(include_input=False, include_url=False)][:12]
        current = current.__cause__ or current.__context__
    if http_status == 409:
        category = "state_conflict"
    elif "AssistantToolError" in chain:
        category = "request_rejected"
    elif "AnswerBudgetExceeded" in chain:
        category = "budget_exhausted"
    elif validation:
        category = "schema_failure"
    elif "JSONDecodeError" in chain:
        category = "json_failure"
    elif any(t in chain for t in ("CompanionContractError", "GroundingContractError", "DuplicateSuggestionsError", "CapabilityContractError", "AdviceContractError")):
        category = "contract_failure"
    elif finish_reason or "CompanionProviderError" in chain:
        category = "incomplete_output"
    elif any(t in chain for t in ("TimeoutError", "APITimeoutError", "ReadTimeout")):
        category = "timeout"
    elif code and str(code).startswith("planner_"):
        category = "provider_failure"
    elif any(t in chain for t in ("AuthenticationError", "PermissionDeniedError", "APIConnectionError", "APIStatusError")):
        category = "provider_failure"
    elif stage not in {"answer", "model", "selection"}:
        category = "tool_failure"
    else:
        category = "provider_failure"
    return {"stage": stage, "code": str(code or category)[:80], "category": category,
            "exception_chain": chain, "http_status": http_status,
            "finish_reason": finish_reason, "validation": validation}


@dataclass
class TurnDiagnostics:
    correlation_id: str
    seconds: float = 90
    started: float = field(default_factory=monotonic)
    answer_attempts: int = 0
    events: list = field(default_factory=list)
    selection: dict = field(default_factory=dict)

    def remaining(self):
        return max(0.001, self.seconds - (monotonic() - self.started))

    def claim_answer(self):
        if self.answer_attempts >= 2 or self.remaining() <= .01:
            raise AnswerBudgetExceeded()
        self.answer_attempts += 1

    def record(self, stage, status, **data):
        event = {"stage": stage, "status": status,
                 "elapsed_ms": round((monotonic() - self.started) * 1000), **data}
        self.events.append(event)
        self.events = self.events[-50:]
        logging.getLogger(__name__).info("assistant_turn %s", json.dumps(
            {"correlation_id": self.correlation_id, **event}, ensure_ascii=False))

    def failure(self, stage, exc):
        detail = error_details(exc, stage)
        self.record(stage, "failed", **{k: v for k, v in detail.items() if k != "stage"})
        logging.getLogger(__name__).warning("assistant_failure %s", json.dumps(
            {"correlation_id": self.correlation_id, **detail}, ensure_ascii=False))
        return detail

    def summary(self, status):
        return {"version": 1, "correlation_id": self.correlation_id,
                "answer_status": status, "answer_attempts": self.answer_attempts,
                "duration_ms": round((monotonic() - self.started) * 1000),
                "selection": self.selection, "events": self.events.copy()}


def record_failure(stage, exc, correlation_id=None):
    turn = active_turn.get()
    if turn:
        return turn.failure(stage, exc)
    detail = error_details(exc, stage)
    logging.getLogger(__name__).warning("assistant_failure %s", json.dumps(
        {"correlation_id": correlation_id, **detail}, ensure_ascii=False))
    return detail


async def bounded_call(operation, *, stage, limit=None):
    turn = active_turn.get()
    seconds = min(limit or 90, turn.remaining()) if turn else limit or 90
    if turn:
        turn.record(stage, "running")
    try:
        async with asyncio.timeout(seconds):
            result = await operation()
    except Exception as exc:
        record_failure(stage, exc)
        raise
    if turn:
        turn.record(stage, "completed")
    return result
