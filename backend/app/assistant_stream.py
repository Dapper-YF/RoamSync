"""Request-local public output streaming. Never read provider thinking deltas."""
import asyncio
import json
import re
import logging
from contextvars import ContextVar


stream_sink: ContextVar = ContextVar("assistant_stream_sink", default=None)


def emit(kind: str, **payload):
    sink = stream_sink.get()
    if sink is not None:
        sink({"type": kind, **payload})


class PublicJsonStream:
    """Decode only top-level public string fields, including split JSON escapes.

    Nested suggestion text, IDs and provider reasoning are never UI deltas.
    The partial output is a preview; the validated session replaces it at done.
    """
    def __init__(self, request=""):
        self.depth = 0
        self.in_string = False
        self.escaped = False
        self.expect_key = False
        self.key = None
        self.is_key = False
        self.raw = ""
        self.decoded = ""
        self.request = request
        self.answer_pending = ""
        self.emitted = {"analysis_summary": 0, "response_text": 0}

    def feed(self, content):
        updates = {}
        for char in content:
            if self.in_string:
                if char == '"' and not self.escaped:
                    self.in_string = False
                    if self.is_key:
                        try:
                            self.key = json.loads('"' + self.raw + '"')
                        except ValueError:
                            self.key = None
                        self.expect_key = False
                    continue
                self.raw += char
                self.escaped = char == "\\" and not self.escaped
                if not self.is_key and self.depth == 1 and self.key in {"analysis_summary", "response_text"}:
                    try:
                        decoded = json.loads('"' + self.raw + '"')
                    except ValueError:
                        continue
                    # Avoid emitting a high surrogate before its paired low surrogate.
                    if decoded and 0xD800 <= ord(decoded[-1]) <= 0xDBFF:
                        continue
                    if decoded.startswith(self.decoded):
                        delta = decoded[len(self.decoded):]
                        if delta:
                            updates[self.key] = updates.get(self.key, "") + delta
                    self.decoded = decoded
            elif char == '"':
                self.in_string = True
                self.is_key = self.depth == 1 and self.expect_key
                self.raw = self.decoded = ""
                self.escaped = False
            elif char in "{[":
                self.depth += 1
                if self.depth == 1:
                    self.expect_key = True
            elif char in "}]":
                self.depth -= 1
            elif char == "," and self.depth == 1:
                self.expect_key = True
                self.key = None
        for key, delta in updates.items():
            limit = 600 if key == "analysis_summary" else 3000
            delta = delta[:max(0, limit - self.emitted[key])]
            self.emitted[key] += len(delta)
            if key == "response_text":
                # Check complete clauses before any visible preview, preserving
                # the existing dynamic-state and manufactured-source boundaries.
                self.answer_pending += delta
                ends = list(re.finditer(r"[。！？!?；;\n]", self.answer_pending))
                if not ends:
                    continue
                end = ends[-1].end()
                delta, self.answer_pending = self.answer_pending[:end], self.answer_pending[end:]
                from app.companion_answer_reliability import control_model_text
                delta = control_model_text(delta, self.request).text
                if re.search(r"资料显示|官方认为|根据来源|https?://|knowledge_|\[[^\]]+\]\(", delta):
                    continue
            if not delta:
                continue
            emit("analysis_delta" if key == "analysis_summary" else "answer_delta", delta=delta)


async def session_events(operation, db, *, correlation_id=None):
    """Keep the session lock/idempotency contract and cancel cleanly on disconnect."""
    queue = asyncio.Queue(maxsize=2048)

    async def run():
        token = stream_sink.set(queue.put_nowait)
        try:
            session = await operation()
            await queue.put({"type": "done", "session": session})
        except Exception as exc:
            from app.assistant_reliability import record_failure
            record_failure("stream", exc, correlation_id)
            logging.getLogger(__name__).warning("Assistant streaming request failed: %s", type(exc).__name__)
            try:
                await db.rollback()
            except Exception as rollback_error:
                # A lost DB connection must not leave the browser receiving
                # keep-alives forever after the request task has already failed.
                logging.getLogger(__name__).warning(
                    "Assistant streaming rollback failed: %s", type(rollback_error).__name__)
            # No raw exception or provider payload in the browser.
            conflict = getattr(exc, "status_code", None) == 409
            detail = getattr(exc, "detail", None)
            public_message = detail.get("message", "") if isinstance(detail, dict) else ""
            conversation_changed = isinstance(public_message, str) and public_message.startswith("对话已有新的决定")
            await queue.put({"type": "error", "message": "对话刚刚有了新消息，请重新读取当前状态后再发送。" if conversation_changed else "这份安排刚刚有了新修改。本次没有覆盖它，请刷新并核对后再试。" if conflict else "这次回答未能完成，请重试。",
                "code": "conversation_changed" if conversation_changed else "state_conflict" if conflict else "request_failed", "correlation_id": correlation_id})
        finally:
            stream_sink.reset(token)

    task = asyncio.create_task(run())
    try:
        yield 'data: {"type":"status","message":"正在读取问题与相关行程…"}\n\n'
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            if event["type"] in {"done", "error"}:
                break
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
