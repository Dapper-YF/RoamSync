import asyncio
from types import SimpleNamespace

from app.model_client import create_model_response
import pytest


class FakeCompletions:
    def __init__(self):
        self.request = None

    async def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
            usage=SimpleNamespace(total_tokens=12),
            model="glm-5.3-flash",
        )


def test_glm_chat_completion_maps_response_and_uses_json_mode():
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    settings = SimpleNamespace(planner_provider="glm")

    response = asyncio.run(create_model_response(
        client,
        settings,
        model="glm-5.3-flash",
        instructions="Return JSON.",
        input_text='{"request":"test"}',
        text_format={"type": "json_schema", "schema": {"type": "object"}},
        reasoning_effort="max",
        max_output_tokens=1024,
    ))

    assert response.status == "completed"
    assert response.output_text == '{"ok":true}'
    assert response.usage.total_tokens == 12
    assert completions.request["response_format"] == {"type": "json_object"}
    assert completions.request["extra_body"] == {
        "reasoning_effort": "max",
        "thinking": {"type": "enabled", "clear_thinking": False},
        "tool_stream": True,
    }
    assert completions.request["temperature"] == 1.0
    assert completions.request["top_p"] == 0.95
    assert completions.request["stream"] is True
    assert "JSON Schema" in completions.request["messages"][0]["content"]


def test_non_glm_keeps_responses_api():
    class FakeResponses:
        def __init__(self):
            self.request = None

        async def create(self, **kwargs):
            self.request = kwargs
            return "responses-result"

    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)
    settings = SimpleNamespace(planner_provider="deepseek")

    response = asyncio.run(create_model_response(
        client,
        settings,
        model="deepseek-v4-flash",
        instructions="instructions",
        input_text="input",
        text_format={"type": "json_schema"},
        reasoning_effort="low",
        max_output_tokens=1000,
    ))

    assert response == "responses-result"
    assert responses.request["model"] == "deepseek-v4-flash"


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_glm_truncated_or_filtered_content_is_not_complete(reason):
    class IncompleteCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason,
                message=SimpleNamespace(content='{"ok":true}'))], usage=None, model="glm-5.3-flash")
    response = asyncio.run(create_model_response(
        SimpleNamespace(chat=SimpleNamespace(completions=IncompleteCompletions())),
        SimpleNamespace(planner_provider="glm"), model="glm-5.3-flash",
        instructions="Return JSON.", input_text="test"))
    assert response.status == "incomplete"
    assert response.finish_reason == reason


@pytest.mark.parametrize("finish", ["stop", None])
def test_glm_stream_requires_completion_and_ignores_thinking(finish):
    class FakeStream:
        closed = False

        async def __aiter__(self):
            for content, reasoning, end in [(None, "hidden reasoning", None), ('{"ok":', None, None), ('true}', None, finish)]:
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content,
                    reasoning_content=reasoning), finish_reason=end)], usage=None, model="glm-5.3-flash")
            yield SimpleNamespace(choices=[], usage=SimpleNamespace(total_tokens=42), model="glm-5.3-flash")

        async def close(self):
            self.closed = True

    stream = FakeStream()

    class StreamingCompletions:
        async def create(self, **kwargs):
            return stream

    response = asyncio.run(create_model_response(
        SimpleNamespace(chat=SimpleNamespace(completions=StreamingCompletions())),
        SimpleNamespace(planner_provider="glm"), model="glm-5.3-flash",
        instructions="Return JSON.", input_text="test"))
    assert response.status == ("completed" if finish else "incomplete")
    assert response.output_text == '{"ok":true}'
    assert response.usage.total_tokens == 42
    assert stream.closed


def test_stream_timeout_is_not_misreported_as_bad_model_json():
    import httpx
    from app.openai_planner import translate_model_error
    failure = translate_model_error(httpx.ReadTimeout("stream interrupted"))
    assert failure.code == "planner_timeout"
    assert failure.retryable


def test_stream_provider_error_is_not_misreported_as_bad_model_json():
    import httpx
    import openai
    from app.openai_planner import translate_model_error
    failure = translate_model_error(openai.APIError("stream provider failure",
        request=httpx.Request("POST", "https://example.com/chat/completions"), body={"error": {"code": "500"}}))
    assert failure.code == "planner_provider_error"
