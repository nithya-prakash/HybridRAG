import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings


class Reranker(ABC):
    """Cross-encoder reranking: given a query and a set of (id, text)
    candidates, returns (id, score) pairs — higher score means more relevant
    — sorted descending. This is a distinct, final refinement step over the
    fused candidate set rather than a third leg fed into RRF, because a
    cross-encoder scores the query and a candidate's text *together* in one
    forward pass (unlike dense/keyword search, which score precomputed,
    independent representations) — too slow to run against a whole corpus,
    accurate enough to meaningfully reorder a small candidate set."""

    @abstractmethod
    async def rerank(
        self, query: str, candidates: list[tuple[uuid.UUID, str]]
    ) -> list[tuple[uuid.UUID, float]]:
        """One (id, score) pair per candidate, sorted by score descending.
        Empty input returns an empty list without loading a model."""

    async def warm_up(self) -> None:
        """Pay any one-time initialization cost (loading a model, say) now,
        rather than on the first real `rerank()` call. Default is a no-op —
        not every backend has meaningful warm-up work (a hosted API reranker
        has nothing local to load). See `CrossEncoderReranker` for why this
        matters here: verified during development that the first `rerank()`
        call after process startup cost ~12s (model load) against ~18ms for
        every call after — an app that lazily eats that on its first real
        user request instead of at startup is a real latency bug, not a
        theoretical one."""
        return None


class CrossEncoderReranker(Reranker):
    def __init__(self) -> None:
        settings = get_settings()
        self._model_name = settings.reranker_model
        self._model: Any = None  # lazy: loaded on first rerank() call, in a
        # worker thread — not at construction, and not blocking the event
        # loop even on that first call.

    async def rerank(
        self, query: str, candidates: list[tuple[uuid.UUID, str]]
    ) -> list[tuple[uuid.UUID, float]]:
        if not candidates:
            return []
        pairs = [(query, text) for _, text in candidates]
        scores = await run_in_threadpool(self._predict, pairs)
        scored = [
            (chunk_id, float(score))
            for (chunk_id, _), score in zip(candidates, scores, strict=True)
        ]
        return sorted(scored, key=lambda pair: pair[1], reverse=True)

    def _predict(self, pairs: list[tuple[str, str]]) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model.predict(pairs)

    async def warm_up(self) -> None:
        await run_in_threadpool(self._predict, [("warm up", "warm up")])


@lru_cache
def get_reranker() -> Reranker:
    return CrossEncoderReranker()
