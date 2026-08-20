from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.config import get_settings
from app.core.embeddings import (
    EmbeddingBackend,
    LocalEmbeddingBackend,
    OpenAIEmbeddingBackend,
    get_embedding_backend,
)


def _fake_response(vectors: list[list[float]]):
    # Deliberately out of order (index 1 before 0) to prove embed_batch sorts
    # by index rather than trusting response ordering.
    data = [SimpleNamespace(index=i, embedding=v) for i, v in enumerate(vectors)]
    data.reverse()
    # Real embeddings.create() responses always carry a usage field (used for
    # the Phase 7 token-usage metric) — matching that shape here, not just
    # the fields embed_batch's own return value depends on.
    usage = SimpleNamespace(total_tokens=len(vectors) * 3)
    return SimpleNamespace(data=data, usage=usage)


async def test_embed_batch_empty_list_makes_no_api_call():
    client = AsyncMock()
    backend = OpenAIEmbeddingBackend(client=client)

    result = await backend.embed_batch([])

    assert result == []
    client.embeddings.create.assert_not_called()


async def test_embed_batch_returns_vectors_in_input_order():
    client = AsyncMock()
    client.embeddings.create.return_value = _fake_response([[0.1, 0.2], [0.3, 0.4]])
    backend = OpenAIEmbeddingBackend(client=client)

    result = await backend.embed_batch(["hello", "world"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_batch_splits_into_configured_batch_size():
    client = AsyncMock()

    async def _create(model, input):
        return _fake_response([[float(i)] for i in range(len(input))])

    client.embeddings.create.side_effect = _create
    backend = OpenAIEmbeddingBackend(client=client)
    backend._batch_size = 2

    texts = ["a", "b", "c", "d", "e"]
    result = await backend.embed_batch(texts)

    assert len(result) == 5
    assert client.embeddings.create.call_count == 3  # batches of 2, 2, 1


async def test_embed_batch_passes_configured_model():
    client = AsyncMock()
    client.embeddings.create.return_value = _fake_response([[0.1]])
    backend = OpenAIEmbeddingBackend(client=client)

    await backend.embed_batch(["hello"])

    _, kwargs = client.embeddings.create.call_args
    assert kwargs["model"] == backend._model


def test_openai_backend_configures_client_max_retries(monkeypatch):
    # Rate limits / transient errors are handled by the SDK's own retry-with-
    # backoff (max_retries passed to the client constructor), not a hand-
    # rolled retry loop — this asserts that wiring is actually in place.
    # No API key is configured in the test environment (embedding calls are
    # always mocked here — see the rest of this file), and the SDK requires
    # *some* credential just to construct a client, so supply a fake one.
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-fake-key")

    backend = OpenAIEmbeddingBackend()

    assert backend._client.max_retries == get_settings().embedding_max_retries


# --- LocalEmbeddingBackend ---
# Real model, not mocked — same reasoning as tests/test_reranker.py: it's
# local, free, needs no API key, and is baked into the Docker image / synced
# venv, so exercising it for real costs nothing extra.


async def test_local_backend_embed_batch_empty_list_returns_empty_without_loading_model():
    backend = LocalEmbeddingBackend()

    result = await backend.embed_batch([])

    assert result == []
    assert backend._model is None


async def test_local_backend_returns_one_normalized_vector_per_text():
    backend = LocalEmbeddingBackend()

    result = await backend.embed_batch(["hello world", "goodbye world"])

    assert len(result) == 2
    assert len(result[0]) == get_settings().qdrant_vector_size
    # normalize_embeddings=True means every vector should already sit on the
    # unit sphere — Qdrant's collection is cosine-distance, so this isn't
    # load-bearing for correctness, but it is exactly what the code asks
    # sentence-transformers to do, so it's worth confirming directly.
    norm = sum(x * x for x in result[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-4


async def test_local_backend_ranks_similar_text_above_dissimilar_text():
    backend = LocalEmbeddingBackend()

    a, b, c = await backend.embed_batch(
        [
            "The cat sat on the mat.",
            "A cat was sitting on a mat.",
            "Quarterly revenue increased by twelve percent.",
        ]
    )

    def cosine(x: list[float], y: list[float]) -> float:
        return sum(xi * yi for xi, yi in zip(x, y, strict=True))  # already unit-normalized

    assert cosine(a, b) > cosine(a, c)


async def test_local_backend_warm_up_forces_model_load():
    backend = LocalEmbeddingBackend()
    assert backend._model is None

    await backend.warm_up()

    assert backend._model is not None


def test_get_embedding_backend_defaults_to_local(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_provider", "local")
    get_embedding_backend.cache_clear()
    try:
        backend = get_embedding_backend()
        assert isinstance(backend, EmbeddingBackend)
        assert isinstance(backend, LocalEmbeddingBackend)
    finally:
        get_embedding_backend.cache_clear()


def test_get_embedding_backend_returns_openai_when_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_provider", "openai")
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-fake-key")
    get_embedding_backend.cache_clear()
    try:
        backend = get_embedding_backend()
        assert isinstance(backend, OpenAIEmbeddingBackend)
    finally:
        get_embedding_backend.cache_clear()
