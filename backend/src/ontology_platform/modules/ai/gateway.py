"""Model gateway: the only place that talks to the model provider.

Everything else depends on the `ModelGateway` protocol, so tests use a fake and other
OpenAI-compatible providers can be plugged in through `OP_AI_BASE_URL`. The proxy applies to
model calls only; nothing else in the platform goes through it.
"""

import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2
import openai
from openai import AsyncOpenAI, DefaultAsyncHttpx2Client
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.ai.models import AiRun
from ontology_platform.settings import Settings


class AiError(Exception):
    """Base class; `code` is the stable error code shown to users via i18n."""

    code = "ai.unavailable"

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class AiNotConfiguredError(AiError):
    code = "ai.not_configured"

    def __init__(self) -> None:
        super().__init__("No model API key is configured.", retryable=False)


class AiUnavailableError(AiError):
    code = "ai.unavailable"


class AiInvalidOutputError(AiError):
    code = "ai.invalid_output"


@dataclass(frozen=True)
class InputFile:
    """A file passed to a multimodal model, e.g. a scanned PDF."""

    filename: str
    media_type: str
    data_base64: str


class ModelGateway(Protocol):
    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
    ) -> T: ...

    async def ping(self) -> bool: ...


PING_TIMEOUT_SECONDS = 5.0
# Waits before the second and third attempt of a call that failed transiently.
RETRY_DELAYS = (2.0, 8.0)

# Transient failures: retried here; when they persist, the job queue reruns the whole document
# (up to its own attempt limit), so one call can be tried several times over.
_RETRYABLE = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)
# Error codes that look transient but are not: retrying cannot help.
_PERMANENT_CODES = frozenset({"insufficient_quota"})
# `response.failed` codes worth another attempt.
_RETRYABLE_FAILURES = frozenset({"server_error", "rate_limit_exceeded"})
_TERMINAL_EVENTS = frozenset({"response.completed", "response.incomplete", "response.failed"})


@dataclass(frozen=True)
class _Call[T: BaseModel]:
    purpose: str
    model: str
    instructions: str
    message: Any
    schema: type[T]
    document_id: Any


class OpenAIGateway:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        *,
        http_client: httpx2.AsyncClient | None = None,
        retry_delays: Sequence[float] = RETRY_DELAYS,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._http_client = http_client
        self._retry_delays = tuple(retry_delays)
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if not self._settings.ai_configured or self._settings.openai_api_key is None:
            raise AiNotConfiguredError
        if self._client is None:
            try:
                http_client = self._http_client
                if http_client is None:
                    proxy = self._settings.ai_proxy
                    http_client = DefaultAsyncHttpx2Client(
                        proxy=proxy.get_secret_value() if proxy else None,
                        timeout=self._settings.ai_timeout_seconds,
                    )
                self._client = AsyncOpenAI(
                    api_key=self._settings.openai_api_key.get_secret_value(),
                    base_url=self._settings.ai_base_url,
                    timeout=self._settings.ai_timeout_seconds,
                    # Retries happen in `structured`, which also covers streams that break off.
                    max_retries=0,
                    http_client=http_client,
                )
            except Exception as exc:
                # The original message can echo the proxy URL; keep it out of logs and job rows.
                message = f"The model client could not be created: {type(exc).__name__}"
                raise AiUnavailableError(message, retryable=False) from None
        return self._client

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
    ) -> T:
        client = self._get_client()
        content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
        content.extend(
            {
                "type": "input_file",
                "filename": item.filename,
                "file_data": f"data:{item.media_type};base64,{item.data_base64}",
            }
            for item in files
        )
        # The SDK's input TypedDicts overlap, so mypy cannot pick one for a literal message.
        message: Any = {"role": "user", "content": content}
        call = _Call(purpose, model, instructions, message, schema, document_id)
        for delay in (*self._retry_delays, None):
            try:
                return await self._attempt(client, call)
            except AiError as error:
                if not error.retryable or delay is None:
                    raise
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _attempt[T: BaseModel](self, client: AsyncOpenAI, call: "_Call[T]") -> T:
        started = time.monotonic()
        usage: Any = None
        try:
            # Streamed, so that tokens keep the connection busy: proxies that drop idle
            # connections (about a minute is common) would otherwise cut long calls.
            # `ai_timeout_seconds` therefore bounds the gaps between events, not the whole call.
            async with client.responses.stream(
                model=call.model,
                instructions=call.instructions,
                input=[call.message],
                text_format=call.schema,
            ) as stream:
                final: Any = None
                async for event in stream:
                    if event.type in _TERMINAL_EVENTS:
                        final = event
                if final is None:
                    raise _StreamEndedError
                usage = final.response.usage
                if final.type == "response.completed":
                    parsed = (await stream.get_final_response()).output_parsed
                    if parsed is not None:
                        await self._record(call, started, usage, None)
                        return parsed
                    error: AiError = AiInvalidOutputError(
                        "The model returned no structured output.", retryable=True
                    )
                else:
                    error = _terminal_error(final)
        except openai.OpenAIError as exc:
            error = _map_error(exc)
        except (ValidationError, json.JSONDecodeError) as exc:
            # The SDK validates the output against the schema; off-schema output surfaces here
            # rather than as an OpenAIError. Another attempt usually succeeds.
            text = f"The model output did not match the schema: {type(exc).__name__}"
            error = AiInvalidOutputError(text, retryable=True)
        except (httpx2.TransportError, _StreamEndedError) as exc:
            # The connection broke off, or the stream ended without a final event.
            text = f"The model stream ended early: {type(exc).__name__}"
            error = AiUnavailableError(text, retryable=True)
        await self._record(call, started, usage, error.code)
        # No chain: provider error bodies are not ours to log.
        raise error from None

    async def ping(self) -> bool:
        """A quick reachability check: short timeout and no retries, for the status badge."""
        try:
            client = self._get_client().with_options(timeout=PING_TIMEOUT_SECONDS, max_retries=0)
            await client.models.retrieve(self._settings.ai_model)
        except (AiError, openai.OpenAIError):
            return False
        return True

    async def _record(
        self, call: "_Call[Any]", started: float, usage: Any, error_code: str | None
    ) -> None:
        """One row per attempt, so retries show up in the accounting.

        A cancelled attempt (the job lost its lease) is not recorded: writing from a cancelled
        task is unreliable, and the provider may still bill for it.
        """
        if self._session_factory is None:
            return
        run = AiRun(
            purpose=call.purpose,
            model=call.model,
            document_id=call.document_id,
            status="failed" if error_code else "succeeded",
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=int((time.monotonic() - started) * 1000),
            error_code=error_code,
        )
        # Own session: accounting must not depend on the caller's transaction.
        async with self._session_factory() as db:
            db.add(run)
            await db.commit()


class _StreamEndedError(Exception):
    """The response stream closed without a completed, incomplete or failed event."""


def _map_error(exc: openai.OpenAIError) -> AiError:
    code = getattr(exc, "code", None)
    retryable = isinstance(exc, _RETRYABLE) and code not in _PERMANENT_CODES
    status = getattr(exc, "status_code", None)
    detail = f"{type(exc).__name__} (HTTP {status})" if status else type(exc).__name__
    return AiUnavailableError(f"Model call failed: {detail}", retryable=retryable)


def _terminal_error(event: Any) -> AiError:
    """Maps a `response.incomplete` or `response.failed` event; codes only, never messages."""
    response = event.response
    if event.type == "response.incomplete":
        # Cut off at the output limit or by a content filter: the same input would be cut again.
        details = getattr(response, "incomplete_details", None)
        reason = getattr(details, "reason", None) or "unknown"
        return AiInvalidOutputError(f"The model output was cut off: {reason}", retryable=False)
    code = getattr(getattr(response, "error", None), "code", None) or "unknown"
    return AiUnavailableError(
        f"The model call failed: {code}", retryable=code in _RETRYABLE_FAILURES
    )
