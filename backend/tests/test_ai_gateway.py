"""OpenAIGateway: error mapping, run accounting and the not-configured case, without network."""

import json
from typing import Any

import httpx2
import pytest
from openai import DefaultAsyncHttpx2Client
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.ai.gateway import (
    AiInvalidOutputError,
    AiNotConfiguredError,
    AiUnavailableError,
    OpenAIGateway,
)
from ontology_platform.modules.ai.models import AiRun
from ontology_platform.settings import Settings


class Answer(BaseModel):
    value: int


def configured(settings: Settings) -> Settings:
    return settings.model_copy(update={"openai_api_key": SecretStr("sk-test"), "ai_model": "m"})


def client_with(handler: Any) -> httpx2.AsyncClient:
    return DefaultAsyncHttpx2Client(transport=httpx2.MockTransport(handler))


def response_body(text: str) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1,
        "model": "m",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 11,
            "output_tokens": 3,
            "total_tokens": 14,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def stream(text: str, *, complete: bool = True) -> httpx2.Response:
    """The server-sent events of a streamed response: created, then (unless cut off) completed."""
    final = response_body(text)
    events = [
        (
            "response.created",
            {**final, "status": "in_progress", "output": [], "usage": None},
        )
    ]
    if complete:
        events.append(("response.completed", final))
    lines = []
    for seq, (name, response) in enumerate(events):
        data = json.dumps({"type": name, "sequence_number": seq, "response": response})
        lines.append(f"event: {name}\ndata: {data}\n\n")
    body = "".join(lines)
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content=body.encode()
    )


async def call(gateway: OpenAIGateway) -> Answer:
    return await gateway.structured(
        purpose="test", model="m", instructions="i", text="t", schema=Answer
    )


async def test_not_configured_raises_without_calling_out(settings: Settings) -> None:
    gateway = OpenAIGateway(settings)
    with pytest.raises(AiNotConfiguredError):
        await call(gateway)
    assert await gateway.ping() is False


async def test_parses_structured_output_and_records_the_run(settings: Settings, app: Any) -> None:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    seen: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return stream('{"value": 42}')

    gateway = OpenAIGateway(configured(settings), factory, http_client=client_with(handler))
    answer = await call(gateway)

    assert answer == Answer(value=42)
    assert seen[0]["model"] == "m"
    assert seen[0]["stream"] is True
    assert seen[0]["text"]["format"]["type"] == "json_schema"
    async with factory() as db:
        runs = (await db.execute(select(AiRun))).scalars().all()
    assert [(run.purpose, run.status, run.input_tokens, run.output_tokens) for run in runs] == [
        ("test", "succeeded", 11, 3)
    ]


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(429, True), (500, True), (401, False), (400, False)],
)
async def test_http_errors_map_to_ai_unavailable(
    settings: Settings, status: int, retryable: bool
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": {"message": "nope", "type": "x"}})

    gateway = OpenAIGateway(configured(settings), http_client=client_with(handler), retry_delays=())
    with pytest.raises(AiUnavailableError) as caught:
        await call(gateway)
    assert caught.value.code == "ai.unavailable"
    assert caught.value.retryable is retryable


async def test_connection_errors_are_retryable(settings: Settings) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    gateway = OpenAIGateway(configured(settings), http_client=client_with(handler), retry_delays=())
    with pytest.raises(AiUnavailableError) as caught:
        await call(gateway)
    assert caught.value.retryable is True


async def test_proxy_settings_build_a_client(settings: Settings) -> None:
    proxied = configured(settings).model_copy(
        update={"ai_proxy": SecretStr("http://user:pass@127.0.0.1:7897")}
    )
    gateway = OpenAIGateway(proxied)
    assert gateway._get_client() is gateway._get_client()


@pytest.mark.parametrize("text", ['{"value": 4', '{"value": "many"}'], ids=["truncated", "schema"])
async def test_off_schema_output_is_a_retryable_invalid_output(
    settings: Settings, app: Any, text: str
) -> None:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory

    def handler(request: httpx2.Request) -> httpx2.Response:
        return stream(text)

    gateway = OpenAIGateway(
        configured(settings), factory, http_client=client_with(handler), retry_delays=()
    )
    with pytest.raises(AiInvalidOutputError) as caught:
        await call(gateway)

    assert caught.value.code == "ai.invalid_output"
    assert caught.value.retryable is True
    async with factory() as db:
        runs = (await db.execute(select(AiRun))).scalars().all()
    assert [(run.status, run.error_code) for run in runs] == [("failed", "ai.invalid_output")]


async def test_a_bad_proxy_url_does_not_leak_into_the_error(settings: Settings) -> None:
    proxied = configured(settings).model_copy(
        update={"ai_proxy": SecretStr("socks9://ontology:s3cret@proxy.internal:7897")}
    )
    gateway = OpenAIGateway(proxied)

    with pytest.raises(AiUnavailableError) as caught:
        gateway._get_client()

    error = caught.value
    assert error.retryable is False
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    assert "s3cret" not in str(error)
    assert "proxy.internal" not in str(error)


async def test_a_stream_that_breaks_off_is_retried(settings: Settings, app: Any) -> None:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    responses = [stream('{"value": 7}', complete=False), stream('{"value": 7}')]

    def handler(request: httpx2.Request) -> httpx2.Response:
        return responses.pop(0)

    gateway = OpenAIGateway(
        configured(settings), factory, http_client=client_with(handler), retry_delays=(0,)
    )
    assert await call(gateway) == Answer(value=7)

    async with factory() as db:
        runs = (await db.execute(select(AiRun).order_by(AiRun.created_at))).scalars().all()
    assert [(run.status, run.error_code) for run in runs] == [
        ("failed", "ai.unavailable"),
        ("succeeded", None),
    ]


async def test_retries_stop_after_the_last_attempt(settings: Settings) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(503, json={"error": {"message": "busy", "type": "x"}})

    gateway = OpenAIGateway(
        configured(settings), http_client=client_with(handler), retry_delays=(0, 0)
    )
    with pytest.raises(AiUnavailableError) as caught:
        await call(gateway)

    assert caught.value.retryable is True
    assert calls == 3
