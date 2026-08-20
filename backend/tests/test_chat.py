import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.chat import ChatBackend, OllamaChatBackend, OpenAIChatBackend, get_chat_backend
from app.core.config import get_settings
from app.core.metrics import LLM_TOKENS_TOTAL


def _completion_response(content: str | None, prompt_tokens: int = 10, completion_tokens: int = 5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


async def _stream_chunks(
    deltas: list[str | None], prompt_tokens: int = 10, completion_tokens: int = 5
):
    for delta in deltas:
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=delta))], usage=None
        )
    # OpenAI's final chunk when stream_options={"include_usage": True} is
    # requested: no choices, just the usage total for the whole stream.
    yield SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


async def test_complete_returns_content_and_passes_configured_model():
    client = AsyncMock()
    client.chat.completions.create.return_value = _completion_response("Paris is the capital.")
    backend = OpenAIChatBackend(client=client)

    result = await backend.complete([{"role": "user", "content": "capital of France?"}])

    assert result == "Paris is the capital."
    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["model"] == backend._model
    assert kwargs["max_tokens"] == backend._max_tokens
    assert "stream" not in kwargs


async def test_complete_returns_empty_string_for_none_content():
    client = AsyncMock()
    client.chat.completions.create.return_value = _completion_response(None)
    backend = OpenAIChatBackend(client=client)

    result = await backend.complete([{"role": "user", "content": "hi"}])

    assert result == ""


async def test_complete_records_token_usage_metric():
    client = AsyncMock()
    client.chat.completions.create.return_value = _completion_response(
        "answer", prompt_tokens=17, completion_tokens=3
    )
    backend = OpenAIChatBackend(client=client)

    prompt_before = LLM_TOKENS_TOTAL.labels("openai", "chat_complete", "prompt")._value.get()
    completion_before = LLM_TOKENS_TOTAL.labels(
        "openai", "chat_complete", "completion"
    )._value.get()

    await backend.complete([{"role": "user", "content": "hi"}])

    assert (
        LLM_TOKENS_TOTAL.labels("openai", "chat_complete", "prompt")._value.get()
        == prompt_before + 17
    )
    assert (
        LLM_TOKENS_TOTAL.labels("openai", "chat_complete", "completion")._value.get()
        == completion_before + 3
    )


async def test_complete_handles_missing_usage_without_crashing():
    client = AsyncMock()
    response = _completion_response("answer")
    response.usage = None
    client.chat.completions.create.return_value = response
    backend = OpenAIChatBackend(client=client)

    result = await backend.complete([{"role": "user", "content": "hi"}])

    assert result == "answer"


async def test_stream_complete_yields_deltas_in_order():
    client = AsyncMock()
    client.chat.completions.create.return_value = _stream_chunks(["Hel", "lo", " world"])
    backend = OpenAIChatBackend(client=client)

    deltas = [d async for d in backend.stream_complete([{"role": "user", "content": "hi"}])]

    assert deltas == ["Hel", "lo", " world"]


async def test_stream_complete_skips_none_and_empty_deltas():
    client = AsyncMock()
    client.chat.completions.create.return_value = _stream_chunks(["Hi", None, "", " there"])
    backend = OpenAIChatBackend(client=client)

    deltas = [d async for d in backend.stream_complete([{"role": "user", "content": "hi"}])]

    assert deltas == ["Hi", " there"]


async def test_stream_complete_requests_usage_and_streaming():
    client = AsyncMock()
    client.chat.completions.create.return_value = _stream_chunks(["hi"])
    backend = OpenAIChatBackend(client=client)

    async for _ in backend.stream_complete([{"role": "user", "content": "hi"}]):
        pass

    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}
    assert kwargs["model"] == backend._model


async def test_stream_complete_records_token_usage_from_final_chunk():
    client = AsyncMock()
    client.chat.completions.create.return_value = _stream_chunks(
        ["hi"], prompt_tokens=8, completion_tokens=2
    )
    backend = OpenAIChatBackend(client=client)

    prompt_before = LLM_TOKENS_TOTAL.labels("openai", "chat_stream", "prompt")._value.get()

    async for _ in backend.stream_complete([{"role": "user", "content": "hi"}]):
        pass

    assert (
        LLM_TOKENS_TOTAL.labels("openai", "chat_stream", "prompt")._value.get()
        == prompt_before + 8
    )


def test_get_chat_backend_returns_a_chat_backend_singleton(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-fake-key")
    monkeypatch.setattr(get_settings(), "chat_provider", "openai")
    get_chat_backend.cache_clear()
    try:
        backend = get_chat_backend()
        assert isinstance(backend, ChatBackend)
        assert isinstance(backend, OpenAIChatBackend)
        assert get_chat_backend() is backend
    finally:
        get_chat_backend.cache_clear()


def test_get_chat_backend_defaults_to_ollama(monkeypatch):
    monkeypatch.setattr(get_settings(), "chat_provider", "ollama")
    get_chat_backend.cache_clear()
    try:
        backend = get_chat_backend()
        assert isinstance(backend, OllamaChatBackend)
    finally:
        get_chat_backend.cache_clear()


# --- OllamaChatBackend ---
# Mocked at the HTTP layer (httpx.MockTransport), same reasoning as
# OpenAIChatBackend's tests above: this asserts request/response shaping and
# metric recording, not that a real model produces good text. Unlike the
# reranker/embedding models (small, free, baked into the image), a real
# Ollama chat model is a multi-GB download not worth requiring for the main
# test suite — verified for real separately via live smoke testing, same
# treatment OpenAIChatBackend's own tests already give the real OpenAI API.


def _ollama_transport(handler):
    return httpx.MockTransport(handler)


async def test_ollama_complete_returns_content_and_posts_configured_model():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi there"}})

    client = httpx.AsyncClient(transport=_ollama_transport(handler), base_url="http://ollama:11434")
    backend = OllamaChatBackend(client=client)

    result = await backend.complete([{"role": "user", "content": "hello"}])

    assert result == "hi there"
    assert captured["json"]["model"] == backend._model
    assert captured["json"]["stream"] is False
    assert captured["json"]["messages"] == [{"role": "user", "content": "hello"}]


async def test_ollama_complete_returns_empty_string_when_message_missing():
    client = httpx.AsyncClient(
        transport=_ollama_transport(lambda r: httpx.Response(200, json={})),
        base_url="http://ollama:11434",
    )
    backend = OllamaChatBackend(client=client)

    result = await backend.complete([{"role": "user", "content": "hi"}])

    assert result == ""


async def test_ollama_complete_records_token_usage_metric():
    client = httpx.AsyncClient(
        transport=_ollama_transport(
            lambda r: httpx.Response(
                200,
                json={
                    "message": {"content": "answer"},
                    "prompt_eval_count": 11,
                    "eval_count": 4,
                },
            )
        ),
        base_url="http://ollama:11434",
    )
    backend = OllamaChatBackend(client=client)

    prompt_before = LLM_TOKENS_TOTAL.labels("ollama", "chat_complete", "prompt")._value.get()
    completion_before = LLM_TOKENS_TOTAL.labels(
        "ollama", "chat_complete", "completion"
    )._value.get()

    await backend.complete([{"role": "user", "content": "hi"}])

    assert (
        LLM_TOKENS_TOTAL.labels("ollama", "chat_complete", "prompt")._value.get()
        == prompt_before + 11
    )
    assert (
        LLM_TOKENS_TOTAL.labels("ollama", "chat_complete", "completion")._value.get()
        == completion_before + 4
    )


async def test_ollama_complete_raises_on_http_error_status():
    client = httpx.AsyncClient(
        transport=_ollama_transport(lambda r: httpx.Response(500, text="boom")),
        base_url="http://ollama:11434",
    )
    backend = OllamaChatBackend(client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await backend.complete([{"role": "user", "content": "hi"}])


def _ndjson_lines(*objs) -> bytes:
    return b"".join((json.dumps(o) + "\n").encode() for o in objs)


async def test_ollama_stream_complete_yields_deltas_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        body = _ndjson_lines(
            {"message": {"content": "Hel"}, "done": False},
            {"message": {"content": "lo"}, "done": False},
            {"message": {"content": " world"}, "done": False},
            {"done": True, "prompt_eval_count": 5, "eval_count": 3},
        )
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=_ollama_transport(handler), base_url="http://ollama:11434")
    backend = OllamaChatBackend(client=client)

    deltas = [d async for d in backend.stream_complete([{"role": "user", "content": "hi"}])]

    assert deltas == ["Hel", "lo", " world"]


async def test_ollama_stream_complete_requests_streaming_mode():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        body = _ndjson_lines({"done": True})
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=_ollama_transport(handler), base_url="http://ollama:11434")
    backend = OllamaChatBackend(client=client)

    async for _ in backend.stream_complete([{"role": "user", "content": "hi"}]):
        pass

    assert captured["json"]["stream"] is True
    assert captured["json"]["model"] == backend._model


async def test_ollama_stream_complete_records_token_usage_from_final_chunk():
    def handler(request: httpx.Request) -> httpx.Response:
        body = _ndjson_lines(
            {"message": {"content": "hi"}, "done": False},
            {"done": True, "prompt_eval_count": 9, "eval_count": 6},
        )
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=_ollama_transport(handler), base_url="http://ollama:11434")
    backend = OllamaChatBackend(client=client)

    prompt_before = LLM_TOKENS_TOTAL.labels("ollama", "chat_stream", "prompt")._value.get()

    async for _ in backend.stream_complete([{"role": "user", "content": "hi"}]):
        pass

    assert (
        LLM_TOKENS_TOTAL.labels("ollama", "chat_stream", "prompt")._value.get()
        == prompt_before + 9
    )
