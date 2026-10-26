"""Bounded process-local telemetry for synchronous assistant turns.

Only stage names, status and measured times are retained. No prompts, model
reasoning, messages or credentials enter this store. The existing session JSON
remains the durable source for completed Companion runtime_trace.
"""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, datetime
from functools import wraps
from time import monotonic, perf_counter

_active = ContextVar("dialogue_observation", default=None)
_turns = OrderedDict()
MAX_TURNS = 64
TTL_SECONDS = 1800


def _prune():
    now = monotonic()
    for key in list(_turns):
        if now - _turns[key]["updated"] > TTL_SECONDS:
            del _turns[key]
    while len(_turns) > MAX_TURNS:
        _turns.popitem(last=False)


def emit(stage, status, duration_ms=None):
    """Never let a telemetry failure change the original operation."""
    try:
        key = _active.get()
        turn = _turns.get(key)
        if turn is None:
            return
        turn["updated"] = monotonic()
        turn["events"].append({"sequence": len(turn["events"]) + 1,
            "stage": stage, "status": status,
            "at": datetime.now(UTC).isoformat(), "duration_ms": duration_ms})
        turn["events"] = turn["events"][-80:]
    except Exception:
        pass


@contextmanager
def stage(name):
    emit(name, "running")
    start = perf_counter()
    try:
        yield
    except BaseException:
        emit(name, "failed", round((perf_counter() - start) * 1000))
        raise
    else:
        emit(name, "completed", round((perf_counter() - start) * 1000))


def observed_stage(name):
    def decorate(operation):
        @wraps(operation)
        async def wrapped(*args, **kwargs):
            with stage(name):
                return await operation(*args, **kwargs)
        return wrapped
    return decorate


def observe_message(operation):
    @wraps(operation)
    async def wrapped(db, session_id, message, message_id, **kwargs):
        key = (str(session_id), str(message_id))
        token = _active.set(key)
        try:
            _prune()
            _turns[key] = {"updated": monotonic(), "status": "running", "events": []}
            _prune()
        except Exception:
            pass
        emit("message", "completed")
        try:
            result = await operation(db, session_id, message, message_id, **kwargs)
        except BaseException:
            emit("request_failed", "failed")
            if key in _turns:
                _turns[key]["status"] = "failed"
            raise
        else:
            # send_message commits before it returns; this is not a graph promise.
            emit("response_returned", "completed")
            if key in _turns:
                _turns[key]["status"] = "completed"
            return result
        finally:
            _active.reset(token)
    return wrapped


def snapshot(session_id, message_id):
    _prune()
    turn = _turns.get((str(session_id), str(message_id)))
    if turn is None:
        return {"status": "unavailable", "events": [], "source": "process_local"}
    return {"status": turn["status"], "events": deepcopy(turn["events"]), "source": "process_local"}
