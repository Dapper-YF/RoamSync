import json
from types import SimpleNamespace
from typing import Any

from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from app.config import Settings


def build_model_client(settings: Settings) -> AsyncOpenAI:
    """Use an explicit model-only proxy when the deployment requires one."""
    transport = (
        DefaultAsyncHttpxClient(proxy=settings.planner_proxy_url.strip())
        if settings.planner_proxy_url.strip()
        else None
    )
    return AsyncOpenAI(
        api_key=settings.planner_api_key.get_secret_value(),
        base_url=settings.planner_base_url,
        timeout=settings.planner_timeout_seconds,
        max_retries=settings.planner_max_retries,
        http_client=transport,
    )


async def create_model_response(
    client: Any,
    settings: Settings,
    *,
    model: str,
    instructions: str,
    input_text: str,
    text_format: dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float = 1.0,
    top_p: float = 0.95,
) -> Any:
    """Use the provider's supported API and normalize its result for callers.

    BigModel exposes Chat Completions rather than the OpenAI Responses API.
    Its documented JSON mode is `json_object`, so the schema is included as
    output guidance and the application continues to enforce its own schemas.
    """
    if settings.planner_provider.strip().lower() not in {"glm", "bigmodel", "zhipu"}:
        return await client.responses.create(
            model=model,
            instructions=instructions,
            input=input_text,
            **({"text": {"format": text_format}} if text_format else {}),
            **({"reasoning": {"effort": reasoning_effort}} if reasoning_effort else {}),
            **({"max_output_tokens": max_output_tokens} if max_output_tokens else {}),
            store=False,
        )

    glm_instructions = instructions
    if text_format and text_format.get("schema"):
        schema_text = json.dumps(text_format["schema"], ensure_ascii=False, separators=(",", ":"))
        glm_instructions += (
            "\n输出必须是符合下列 JSON Schema 的单个 JSON 对象，不要输出 Markdown 或额外文字：\n"
            + schema_text
        )
    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": glm_instructions},
            {"role": "user", "content": input_text},
        ],
        response_format={"type": "json_object"} if text_format else {"type": "text"},
        temperature=temperature,
        top_p=top_p,
        stream=True,
        extra_body={
            "reasoning_effort": reasoning_effort or "max",
            "thinking": {"type": "enabled", "clear_thinking": False},
            "tool_stream": True,
        },
        **({"max_tokens": max_output_tokens} if max_output_tokens else {}),
    )
    if hasattr(completion, "__aiter__"):
        parts: list[str] = []
        finish_reason = None
        usage = None
        response_model = model
        try:
            async for chunk in completion:
                usage = getattr(chunk, "usage", None) or usage
                response_model = getattr(chunk, "model", None) or response_model
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    choice = choices[0]
                    content = getattr(getattr(choice, "delta", None), "content", None)
                    if content:
                        parts.append(content)
                    finish_reason = getattr(choice, "finish_reason", None) or finish_reason
        finally:
            await completion.close()
        # Thinking deltas are deliberately never read, accumulated or persisted.
        content = "".join(parts)
        return SimpleNamespace(
            status="completed" if content and finish_reason == "stop" else "incomplete",
            output_text=content, finish_reason=finish_reason, usage=usage, model=response_model,
        )
    choices = getattr(completion, "choices", None) or []
    choice = choices[0] if choices else None
    content = getattr(getattr(choice, "message", None), "content", None)
    finish_reason = getattr(choice, "finish_reason", None)
    return SimpleNamespace(
        status="completed" if content and finish_reason in {None, "stop"} else "incomplete",
        output_text=content or "",
        finish_reason=finish_reason,
        usage=getattr(completion, "usage", None),
        model=getattr(completion, "model", None) or model,
    )
