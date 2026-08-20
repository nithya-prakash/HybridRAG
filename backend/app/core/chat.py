import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from functools import lru_cache

import httpx
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.metrics import LLM_CALL_DURATION_SECONDS, LLM_TOKENS_TOTAL


class ChatBackend(ABC):
    """Chat completion, in two shapes: a plain call (query rewriting — one
    short string in, one short string out, no reason to stream) and a
    streaming call (answer generation — tokens forwarded to the client as
    they arrive). Implementations own their own provider-specific request
    shaping, mirroring `EmbeddingBackend`."""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """One-shot completion, returning the full text."""

    @abstractmethod
    def stream_complete(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yields text deltas as they're generated. An empty delta (e.g. the
        first chunk, which carries only a role) is never yielded."""


class OpenAIChatBackend(ChatBackend):
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        self._model = settings.openai_chat_model
        self._max_tokens = settings.rag_max_completion_tokens
        self._client = client or AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete(self, messages: list[dict[str, str]]) -> str:
        t0 = time.perf_counter()
        response = await self._client.chat.completions.create(
            model=self._model, messages=messages, max_tokens=self._max_tokens
        )
        LLM_CALL_DURATION_SECONDS.labels("openai", "chat_complete").observe(
            time.perf_counter() - t0
        )
        if response.usage is not None:
            LLM_TOKENS_TOTAL.labels("openai", "chat_complete", "prompt").inc(
                response.usage.prompt_tokens
            )
            LLM_TOKENS_TOTAL.labels("openai", "chat_complete", "completion").inc(
                response.usage.completion_tokens
            )
        return response.choices[0].message.content or ""

    async def stream_complete(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        t0 = time.perf_counter()
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            stream=True,
            # Without this, a streamed response never reports token usage at
            # all — OpenAI only includes a `usage` field on the final chunk
            # of a stream when it's explicitly asked for.
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.usage is not None:
                LLM_TOKENS_TOTAL.labels("openai", "chat_stream", "prompt").inc(
                    chunk.usage.prompt_tokens
                )
                LLM_TOKENS_TOTAL.labels("openai", "chat_stream", "completion").inc(
                    chunk.usage.completion_tokens
                )
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
        LLM_CALL_DURATION_SECONDS.labels("openai", "chat_stream").observe(time.perf_counter() - t0)


class OllamaChatBackend(ChatBackend):
    """Talks to a local Ollama server's native `/api/chat` endpoint (not the
    OpenAI-compatible shim Ollama also exposes — the native API reports
    prompt/completion token counts directly, which the compat shim doesn't).
    No API key; `httpx.ConnectError`/`httpx.ConnectTimeout` if the `ollama`
    service isn't up, which `app/core/error_handlers.py` classifies into an
    actionable message rather than a bare 503."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._model = settings.ollama_chat_model
        # Local CPU inference is slow relative to a hosted API — a generous
        # timeout here avoids misclassifying "still generating" as "the
        # service is down."
        self._client = client or httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=180.0
        )

    async def complete(self, messages: list[dict[str, str]]) -> str:
        t0 = time.perf_counter()
        response = await self._client.post(
            "/api/chat", json={"model": self._model, "messages": messages, "stream": False}
        )
        response.raise_for_status()
        data = response.json()
        LLM_CALL_DURATION_SECONDS.labels("ollama", "chat_complete").observe(
            time.perf_counter() - t0
        )
        self._record_usage(data, "chat_complete")
        return data.get("message", {}).get("content") or ""

    async def stream_complete(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        t0 = time.perf_counter()
        async with self._client.stream(
            "POST",
            "/api/chat",
            json={"model": self._model, "messages": messages, "stream": True},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if chunk.get("done"):
                    self._record_usage(chunk, "chat_stream")
                    break
                delta = chunk.get("message", {}).get("content")
                if delta:
                    yield delta
        LLM_CALL_DURATION_SECONDS.labels("ollama", "chat_stream").observe(time.perf_counter() - t0)

    @staticmethod
    def _record_usage(data: dict, call_type: str) -> None:
        # Ollama's native API reports these as prompt_eval_count/eval_count
        # rather than OpenAI's prompt_tokens/completion_tokens naming, but
        # they're the same thing — recorded under the same metric names so
        # a dashboard doesn't need to know which provider served a request.
        if "prompt_eval_count" in data:
            LLM_TOKENS_TOTAL.labels("ollama", call_type, "prompt").inc(data["prompt_eval_count"])
        if "eval_count" in data:
            LLM_TOKENS_TOTAL.labels("ollama", call_type, "completion").inc(data["eval_count"])


@lru_cache
def get_chat_backend() -> ChatBackend:
    settings = get_settings()
    if settings.chat_provider == "openai":
        return OpenAIChatBackend()
    return OllamaChatBackend()
