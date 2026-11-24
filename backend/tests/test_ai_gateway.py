"""OpenAIGateway: error mapping, run accounting and the not-configured case, without network."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2
import pytest
from openai import DefaultAsyncHttpx2Client
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.ai.gateway import (
    PROBE_INTERVAL_SECONDS,
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


LEAK = "upstream says: secret detail"


def response_body(text: str | None) -> dict[str, Any]:
    output = [
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1,
        "model": "m",
        "status": "completed",
        "output": output if text is not None else [],
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


def sse(*events: tuple[str, dict[str, Any]]) -> bytes:
    lines = []
    for seq, (name, response) in enumerate(events):
        data = json.dumps({"type": name, "sequence_number": seq, "response": response})
        lines.append(f"event: {name}\ndata: {data}\n\n")
    return "".join(lines).encode()


def created(text: str | None) -> tuple[str, dict[str, Any]]:
    return ("response.created", {**response_body(text), "status": "in_progress", "output": []})


def stream(
    text: str | None,
    *,
    terminal: str | None = "response.completed",
    **final_fields: Any,
) -> httpx2.Response:
    """A streamed response: created, then the terminal event (none when `terminal` is None)."""
    events = [created(text)]
    if terminal is not None:
        status = terminal.removeprefix("response.")
        events.append((terminal, {**response_body(text), "status": status, **final_fields}))
    headers = {"content-type": "text/event-stream"}
    return httpx2.Response(200, headers=headers, content=sse(*events))


class CutStream(httpx2.AsyncByteStream):
    """Sends the first event, then the connection drops, as a proxy cutting it would."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield sse(created('{"value": 7}'))
        raise httpx2.RemoteProtocolError("peer closed connection")


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


def assert_no_leak(error: Exception) -> None:
    """Provider error bodies stay out of messages, logs and job rows."""
    assert LEAK not in str(error)
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


@pytest.mark.parametrize(
    ("status", "code", "attempts"),
    [
        (429, None, 3),
        (500, None, 3),
        (503, None, 3),
        (429, "insufficient_quota", 1),
        (401, None, 1),
        (400, None, 1),
    ],
)
async def test_http_errors_are_retried_only_when_transient(
    settings: Settings, status: int, code: str | None, attempts: int
) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        error = {"message": LEAK, "type": "x", "code": code}
        return httpx2.Response(status, json={"error": error})

    gateway = OpenAIGateway(
        configured(settings), http_client=client_with(handler), retry_delays=(0, 0)
    )
    with pytest.raises(AiUnavailableError) as caught:
        await call(gateway)

    assert caught.value.code == "ai.unavailable"
    assert caught.value.retryable is (attempts == 3)
    assert calls == attempts
    assert_no_leak(caught.value)


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


async def runs_of(factory: async_sessionmaker[AsyncSession]) -> list[tuple[str, str | None]]:
    async with factory() as db:
        runs = (await db.execute(select(AiRun).order_by(AiRun.created_at))).scalars().all()
    return [(run.status, run.error_code) for run in runs]


@pytest.mark.parametrize(
    "first",
    [
        lambda: httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, stream=CutStream()
        ),
        lambda: stream('{"value": 7}', terminal=None),
    ],
    ids=["connection-cut", "no-final-event"],
)
async def test_a_stream_that_breaks_off_is_retried(
    settings: Settings, app: Any, first: Callable[[], httpx2.Response]
) -> None:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    responses = [first(), stream('{"value": 7}')]

    def handler(request: httpx2.Request) -> httpx2.Response:
        return responses.pop(0)

    gateway = OpenAIGateway(
        configured(settings), factory, http_client=client_with(handler), retry_delays=(0,)
    )
    assert await call(gateway) == Answer(value=7)
    assert await runs_of(factory) == [("failed", "ai.unavailable"), ("succeeded", None)]


async def test_output_cut_off_by_the_model_is_not_retried(settings: Settings, app: Any) -> None:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        reason = {"reason": "max_output_tokens"}
        return stream('{"value": 4', terminal="response.incomplete", incomplete_details=reason)

    gateway = OpenAIGateway(
        configured(settings), factory, http_client=client_with(handler), retry_delays=(0, 0)
    )
    with pytest.raises(AiInvalidOutputError) as caught:
        await call(gateway)

    assert caught.value.retryable is False
    assert "max_output_tokens" in str(caught.value)
    assert calls == 1
    async with factory() as db:
        run = (await db.execute(select(AiRun))).scalar_one()
    assert (run.status, run.error_code, run.input_tokens) == ("failed", "ai.invalid_output", 11)


@pytest.mark.parametrize(("code", "attempts"), [("server_error", 3), ("invalid_prompt", 1)])
async def test_a_failed_response_is_retried_only_for_transient_codes(
    settings: Settings, code: str, attempts: int
) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        error = {"code": code, "message": LEAK}
        return stream(None, terminal="response.failed", error=error)

    gateway = OpenAIGateway(
        configured(settings), http_client=client_with(handler), retry_delays=(0, 0)
    )
    with pytest.raises(AiUnavailableError) as caught:
        await call(gateway)

    assert caught.value.retryable is (attempts == 3)
    assert code in str(caught.value)
    assert calls == attempts
    assert_no_leak(caught.value)


async def test_a_completed_response_without_output_is_an_invalid_output(
    settings: Settings,
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return stream(None)

    gateway = OpenAIGateway(configured(settings), http_client=client_with(handler), retry_delays=())
    with pytest.raises(AiInvalidOutputError) as caught:
        await call(gateway)
    assert caught.value.retryable is True


def ping_gateway(
    settings: Settings,
    models_status: int,
    *,
    factory: async_sessionmaker[AsyncSession] | None = None,
    reply: Callable[[], httpx2.Response] = lambda: stream('{"reply": "pong"}'),
) -> tuple[OpenAIGateway, list[str]]:
    """A gateway whose `/models/{id}` answers `models_status`; returns it with the seen paths."""
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path.startswith("/v1/models") or request.url.path.startswith("/models"):
            if models_status == 200:
                body = {"id": "m", "object": "model", "created": 1, "owned_by": "x"}
                return httpx2.Response(200, json=body)
            return httpx2.Response(models_status, json={"error": {"message": LEAK}})
        return reply()

    gateway = OpenAIGateway(
        configured(settings), factory, http_client=client_with(handler), retry_delays=()
    )
    return gateway, seen


async def test_ping_uses_the_models_endpoint_when_it_exists(settings: Settings) -> None:
    gateway, seen = ping_gateway(settings, 200)
    assert await gateway.ping() is True
    assert len(seen) == 1
    assert "models" in seen[0]


@pytest.mark.parametrize("status", [404, 405, 501])
async def test_ping_falls_back_to_a_tiny_call_when_models_is_unsupported(
    settings: Settings, app: Any, status: int
) -> None:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    gateway, seen = ping_gateway(settings, status, factory=factory)

    assert await gateway.ping() is True

    assert [path.split()[0] for path in seen] == ["GET", "POST"]
    async with factory() as db:
        runs = (await db.execute(select(AiRun))).scalars().all()
    assert [(run.purpose, run.status) for run in runs] == [("status.check", "succeeded")]


async def test_ping_does_not_fall_back_on_other_models_errors(settings: Settings) -> None:
    gateway, seen = ping_gateway(settings, 401)
    assert await gateway.ping() is False
    assert len(seen) == 1


async def test_a_successful_fallback_is_not_paid_for_again_soon(settings: Settings) -> None:
    gateway, seen = ping_gateway(settings, 404)
    assert await gateway.ping() is True
    assert await gateway.ping() is True
    assert await gateway.ping() is True
    # The free models check is repeated, the billed call only once.
    assert [path.split()[0] for path in seen].count("POST") == 1


async def test_a_failed_fallback_is_retried_and_not_retried_within_one_ping(
    settings: Settings,
) -> None:
    gateway, seen = ping_gateway(settings, 404, reply=lambda: httpx2.Response(500, json={}))
    assert await gateway.ping() is False
    assert [path.split()[0] for path in seen].count("POST") == 1
    assert await gateway.ping() is False
    assert [path.split()[0] for path in seen].count("POST") == 2


async def test_the_fallback_call_expires_after_the_probe_interval(settings: Settings) -> None:
    gateway, seen = ping_gateway(settings, 404)
    assert await gateway.ping() is True
    # Age the remembered success instead of patching the process-wide clock.
    assert gateway._probed_ok_at is not None
    gateway._probed_ok_at -= PROBE_INTERVAL_SECONDS + 1
    assert await gateway.ping() is True
    assert [path.split()[0] for path in seen].count("POST") == 2


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_ping_does_not_probe_on_transient_models_errors(
    settings: Settings, status: int
) -> None:
    gateway, seen = ping_gateway(settings, status)
    assert await gateway.ping() is False
    assert [path.split()[0] for path in seen] == ["GET"]
