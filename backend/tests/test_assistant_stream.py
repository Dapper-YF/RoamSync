import asyncio
import json
from types import SimpleNamespace

from app.assistant_stream import PublicJsonStream, session_events, stream_sink
from app.model_client import create_model_response


def test_public_fields_split_escapes_and_nested_text_never_leak():
    events = []
    token = stream_sink.set(events.append)
    try:
        decoder = PublicJsonStream()
        text = json.dumps({"analysis_summary": "按区域与节奏解释。", "response_text": "先看\"钟山\"。\n再看博物馆。",
            "suggestions": [{"response_text": "private nested value"}]}, ensure_ascii=True)
        for char in text:
            decoder.feed(char)
    finally:
        stream_sink.reset(token)
    assert "".join(e["delta"] for e in events if e["type"] == "analysis_delta") == "按区域与节奏解释。"
    assert "".join(e["delta"] for e in events if e["type"] == "answer_delta") == '先看"钟山"。\n再看博物馆。'
    assert "private" not in str(events)


def test_preview_cannot_publish_unverified_dynamic_claims():
    events = []
    token = stream_sink.set(events.append)
    try:
        PublicJsonStream("解释行程").feed(json.dumps({"response_text": "这项安排回应文化兴趣。门票只需80元。一定免排队。"}, ensure_ascii=False))
    finally:
        stream_sink.reset(token)
    text = "".join(e["delta"] for e in events)
    assert "文化兴趣" in text
    assert "80" not in text and "免排队" not in text


def test_model_stream_arrives_before_completion_and_discards_hidden_reasoning():
    async def scenario():
        gate = asyncio.Event()
        parts = []
        class Stream:
            closed = False
            async def __aiter__(self):
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content="hidden"), finish_reason=None)])
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="first"), finish_reason=None)])
                await gate.wait()
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="second"), finish_reason="stop")])
            async def close(self): self.closed = True
        stream = Stream()
        async def create(**kwargs): return stream
        task = asyncio.create_task(create_model_response(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
            SimpleNamespace(planner_provider="glm"), model="fixture", instructions="test", input_text="test", on_content=parts.append))
        await asyncio.sleep(0)
        assert parts == ["first"] and not task.done()
        gate.set()
        result = await task
        assert result.output_text == "firstsecond" and stream.closed
    asyncio.run(scenario())


def test_sse_final_and_disconnect_cancel_request_task():
    async def scenario():
        cancelled = asyncio.Event()
        class DB:
            async def rollback(self): pass
        async def operation():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        iterator = session_events(operation, DB())
        assert '"status"' in await anext(iterator)
        await asyncio.sleep(0)
        await iterator.aclose()
        assert cancelled.is_set()
        async def completed(): return {"messages": []}
        output = [frame async for frame in session_events(completed, DB())]
        assert '"done"' in output[-1]
    asyncio.run(scenario())


def test_responses_api_stream_preserves_completion_and_public_text_only():
    async def scenario():
        parts = []
        class Stream:
            closed = False
            async def __aiter__(self):
                for event in [SimpleNamespace(type="response.reasoning.delta", delta="private"),
                    SimpleNamespace(type="response.output_text.delta", delta="公开文本"),
                    SimpleNamespace(type="response.completed", response=SimpleNamespace(status="completed", model="fixture"))]:
                    yield event
            async def close(self): self.closed = True
        stream = Stream()
        async def create(**kwargs):
            assert kwargs["stream"] is True
            return stream
        response = await create_model_response(SimpleNamespace(responses=SimpleNamespace(create=create)),
            SimpleNamespace(planner_provider="openai"), model="fixture", instructions="test", input_text="test", on_content=parts.append)
        assert parts == ["公开文本"] and response.status == "completed" and stream.closed
    asyncio.run(scenario())


def test_sse_failure_terminates_even_when_database_rollback_fails():
    async def scenario():
        class BrokenDB:
            async def rollback(self):
                raise RuntimeError("private database connection details")

        async def failed():
            raise ValueError("private provider response")

        iterator = session_events(failed, BrokenDB())
        assert '"status"' in await anext(iterator)
        try:
            frame = await asyncio.wait_for(anext(iterator), timeout=0.5)
            event = json.loads(frame.removeprefix("data: "))
            assert event["type"] == "error"
            assert "private" not in frame
            try:
                await anext(iterator)
            except StopAsyncIteration:
                pass
            else:
                raise AssertionError("Failure must terminate the stream")
        finally:
            await iterator.aclose()

    asyncio.run(scenario())


def test_sse_conversation_conflict_has_safe_reason_and_correlation(caplog):
    from fastapi import HTTPException
    from app.assistant_service import AssistantToolError
    async def scenario():
        class DB:
            async def rollback(self):pass
        async def failed():
            try:
                raise AssistantToolError('对话已有新的决定，请重新读取当前状态后再查询。')
            except AssistantToolError as exc:
                raise HTTPException(422,{'message':str(exc)}) from exc
        events=[]
        async for frame in session_events(failed,DB(),correlation_id='correlated-message'):
            events.append(json.loads(frame.removeprefix('data: ')))
        assert events[-1]['code']=='conversation_changed'
        assert events[-1]['correlation_id']=='correlated-message'
        assert '重新读取' in events[-1]['message']
    asyncio.run(scenario())
    assert 'AssistantToolError' in caplog.text and 'correlated-message' in caplog.text
