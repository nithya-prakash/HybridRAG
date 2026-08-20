import time
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.metrics import LLM_CALL_DURATION_SECONDS, LLM_TOKENS_TOTAL


class EmbeddingBackend(ABC):
    """Text -> vector embeddings, batched. Implementations own their own
    provider-specific batching/retry details; callers just pass an arbitrary
    number of texts and get back one vector per text, in the same order."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed `texts`, returning one vector per input in the same order.
        Returns an empty list for empty input without making a network call."""

    async def warm_up(self) -> None:
        """Pay any one-time initialization cost (loading a model, say) now
        rather than on the first real `embed_batch` call. Default is a
        no-op — a hosted API backend has nothing local to load. See
        `LocalEmbeddingBackend` for why this matters there, same reasoning
        as `Reranker.warm_up` (app/core/reranker.py)."""
        return None


class OpenAIEmbeddingBackend(EmbeddingBackend):
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        self._model = settings.openai_embedding_model
        self._batch_size = settings.embedding_batch_size
        # Rate limits and transient 5xx/connection errors are handled by the
        # SDK's own retry-with-backoff (exponential, jittered) rather than
        # hand-rolling a second retry layer on top of it — max_retries is the
        # one knob that matters here.
        self._client = client or AsyncOpenAI(
            api_key=settings.openai_api_key,
            max_retries=settings.embedding_max_retries,
        )

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            t0 = time.perf_counter()
            response = await self._client.embeddings.create(model=self._model, input=batch)
            LLM_CALL_DURATION_SECONDS.labels("openai", "embed").observe(time.perf_counter() - t0)
            if response.usage is not None:
                LLM_TOKENS_TOTAL.labels("openai", "embed", "total").inc(
                    response.usage.total_tokens
                )
            # The API guarantees data[i].index corresponds to input order, but
            # sorting explicitly costs nothing and removes any doubt.
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in ordered)

        return vectors


class LocalEmbeddingBackend(EmbeddingBackend):
    """Runs a local sentence-transformers model in a worker thread — no API
    key, no per-call cost, no network dependency once the model is baked
    into the Docker image (same build-time-cache pattern as the reranker;
    see infra/docker/backend.Dockerfile). This is the default embedding
    backend specifically so a fresh checkout can index documents and answer
    questions with zero external accounts required.

    The model is loaded lazily on first use and cached on the instance
    (mirroring `CrossEncoderReranker`) — `warm_up()` exists so that cost is
    paid once at process startup instead of inside a user's first real
    request; see `app/main.py`'s lifespan and `app/core/celery_app.py`'s
    `worker_ready` handler for where it's actually called."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model_name = settings.local_embedding_model
        self._batch_size = settings.embedding_batch_size
        self._model: Any = None  # lazy: loaded in a worker thread, not at
        # construction, and not blocking the event loop even on that first call.

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        # normalize_embeddings=True: Qdrant's collection here is configured
        # for cosine distance, which is scale-invariant, but normalizing at
        # write time means every vector already sits on the unit sphere —
        # cheap here, and it keeps dot-product and cosine equivalent if the
        # collection's distance metric is ever revisited.
        vectors = model.encode(
            texts, batch_size=self._batch_size, normalize_embeddings=True, convert_to_numpy=True
        )
        return [v.tolist() for v in vectors]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        t0 = time.perf_counter()
        vectors = await run_in_threadpool(self._encode, texts)
        LLM_CALL_DURATION_SECONDS.labels("local", "embed").observe(time.perf_counter() - t0)
        return vectors

    async def warm_up(self) -> None:
        await run_in_threadpool(self._encode, ["warm up"])


@lru_cache
def get_embedding_backend() -> EmbeddingBackend:
    settings = get_settings()
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingBackend()
    return LocalEmbeddingBackend()
