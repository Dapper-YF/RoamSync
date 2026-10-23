"""Best-effort, bounded observations in existing PlanningRun.progress JSON.

Never captures provider requests, prompts, model reasoning or credentials.
Observers cannot change return values, retries, routing or exceptions.
"""
import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime
from functools import wraps
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select, text

from app.database import PlanningRun, session_factory
from app.planning_claim import assert_planning_claim

logger = logging.getLogger(__name__)
FORBIDDEN = re.compile(r"secret|password|credential|authorization|cookie|apikey|accesstoken|refreshtoken|prompt|instructions|reasoning|chainofthought|thought|rawrequest|rawresponse|headers", re.I)


def clean(value, depth=0):
    """Defense in depth after explicit source projection, on write AND read."""
    if depth > 16:
        return "[truncated]"
    if isinstance(value, dict):
        return {str(k): clean(v, depth + 1) for k, v in list(value.items())[:100]
                if not FORBIDDEN.search(re.sub(r"[^a-z0-9]", "", str(k).lower()))
                and re.sub(r"[^a-z0-9]", "", str(k).lower()) not in {"key", "token", "auth", "system", "developer", "messages", "inputtext", "outputtext", "analysis"}}
    if isinstance(value, (list, tuple)):
        return [clean(v, depth + 1) for v in value[:500]]
    if isinstance(value, str):
        # Configured secrets are removed even from provider error strings.
        from app.config import get_settings
        settings = get_settings()
        for name in type(settings).model_fields:
            field = getattr(settings, name)
            if hasattr(field, "get_secret_value") or re.search(r"key|password|secret", name):
                secret = field.get_secret_value() if hasattr(field, "get_secret_value") else str(field or "")
                if secret:
                    value = value.replace(secret, "[redacted]")
        value = re.sub(r"<think>.*?(?:</think>|$)", "[removed]", value, flags=re.S | re.I)
        value = re.sub(r"(?i)bearer\s+[^\s\"']+", "Bearer [redacted]", value)
        value = re.sub(r"(?i)(?:api[_-]?key|secret|password|authorization|token)\s*[=:]\s*[^\s,;&\"']+", "[redacted]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", value)
        # Observation links never need credentials or query parameters.
        def url_clean(match):
            try:
                parsed = urlsplit(match.group(0))
                return urlunsplit((parsed.scheme, parsed.netloc.split("@")[-1], parsed.path, "", ""))
            except ValueError:
                return "[removed URL]"
        value = re.sub(r"https?://[^\s<>\"']+", url_clean, value)
        return value[:4000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def project_context(context):
    result = {key: context[key] for key in (
        "trip", "preferences", "days", "candidates", "actual_budget", "planning_budget",
        "generated_at", "execution_recovery", "planning_goals", "formal_route_facts",
        "destination_research", "decision_context",
    ) if key in context}
    if "decision_context" in result:
        decision = result["decision_context"]
        result["decision_context"] = {key: decision[key] for key in ("formal_itinerary", "protected_constraints", "execution_context", "decision_memory", "provenance", "route_context") if key in decision}
    return clean(result)


def project_state(state):
    result = {key: state[key] for key in (
        "intent_resolution", "planning_goals", "proposed_snapshot", "validation_result",
        "goal_satisfaction", "decision_summary", "schedule_adjustments", "revision_id", "outcome",
    ) if key in state}
    if "planning_context" in state:
        result["planning_context"] = project_context(state["planning_context"])
        facts = state["planning_context"].get("external_facts", {})
        result["external_facts"] = project_facts(facts)
    return clean(result)


def project_facts(facts):
    search = facts.get("search") or {}
    weather = facts.get("weather") or {}
    return clean({"status": facts.get("status"), "search": {
        **{key: search[key] for key in ("status", "provider", "query", "queries", "queried_at", "reason") if key in search},
        "sources": [{"title": item.get("title"), "url": item.get("url"), "content": str(item.get("content", ""))[:800]}
                    for item in search.get("payload", {}).get("results", [])[:8]],
    }, "weather": {key: weather[key] for key in ("status", "provider", "queried_at", "reason") if key in weather}})


async def record(stage, status, *, run_id=None, data=None, duration_ms=None, call_id=None, provider=None, purpose=None):
    from app.planning_progress import active_run
    run_id = run_id or active_run.get()
    if not run_id:
        return
    event = clean({"stage": stage, "status": status, "at": datetime.now(UTC).isoformat(),
                  "duration_ms": duration_ms, "call_id": call_id, "provider": provider,
                  "purpose": purpose, "data": data or {}})

    async def persist():
        async with session_factory() as db:
            await db.execute(text("SET LOCAL lock_timeout = '250ms'"))
            await assert_planning_claim(db, uuid.UUID(str(run_id)))
            run = await db.scalar(select(PlanningRun).where(PlanningRun.id == uuid.UUID(str(run_id))).with_for_update())
            if run is None:
                return
            progress = dict(run.progress or {})
            events = list(progress.get("events") or [])
            sequence = int(progress.get("observation_sequence", 0)) + 1
            event["sequence"] = sequence
            events.append(event)
            progress.update(events=events[-240:], observation_sequence=sequence,
                            observations_truncated=bool(progress.get("observations_truncated") or len(events) > 240))
            run.progress = progress
            await db.commit()
    try:
        await asyncio.wait_for(persist(), timeout=1)
    except Exception:
        logger.warning("Agent observation unavailable: stage=%s", stage)


def observed(stage, *, provider=None, purpose=None, input_summary=None, output_summary=None, graph=False):
    def decorate(function):
        @wraps(function)
        async def wrapper(*args, **kwargs):
            from app.planning_progress import active_run
            run_id = args[0].get("run_id") if graph else active_run.get()
            if not run_id:
                return await function(*args, **kwargs)
            call_id = str(uuid.uuid4())
            # Projections are also best effort; a broken observer must not fail work.
            def summarize(callback, *values):
                try:
                    return callback(*values) if callback else {}
                except Exception:
                    return {"observation": "unavailable"}
            await record(stage, "running", run_id=run_id, call_id=call_id, provider=provider,
                         purpose=purpose, data=summarize(input_summary, args, kwargs))
            start = perf_counter()
            try:
                result = await function(*args, **kwargs)
            except Exception as exc:
                await record(stage, "failed", run_id=run_id, call_id=call_id, provider=provider,
                             purpose=purpose, duration_ms=round((perf_counter() - start) * 1000),
                             data={"error_code": getattr(exc, "code", type(exc).__name__)})
                raise
            duration = round((perf_counter() - start) * 1000)
            data = summarize(output_summary, result)
            await record(stage, "completed", run_id=run_id, call_id=call_id, provider=provider,
                         purpose=purpose, duration_ms=duration, data=data)
            return result
        return wrapper
    return decorate
