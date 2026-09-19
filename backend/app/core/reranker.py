import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings

# The historical default and only baseline this project has ever shipped —
# named explicitly so `RERANKER_MODEL=baseline` has something real to
# resolve back to, independent of Settings.reranker_model's own default
# (which happens to equal this today, but the alias should mean "the
# baseline" even if that field's default is ever repointed for some other
# reason).
BASELINE_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def resolve_reranker_model_name(settings: Settings) -> str:
    """RERANKER_MODEL accepts a plain HF model id/local path directly (the
    original, still-default behavior), or the literals "baseline"/
    "finetuned" as a convenience alias — added alongside
    eval/reranker_training/ so switching between the shipped MS MARCO
    reranker and a fine-tuned checkpoint doesn't require typing out
    `reranker_finetuned_path` by hand."""
    if settings.reranker_model == "baseline":
        return BASELINE_RERANKER_MODEL
    if settings.reranker_model == "finetuned":
        return settings.reranker_finetuned_path
    return settings.reranker_model


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
    def __init__(self, model_name: str | None = None) -> None:
        # Explicit `model_name` bypasses config/alias resolution entirely —
        # for eval/reranker_training/evaluate_baseline_vs_finetuned.py,
        # which needs two live instances (baseline vs. fine-tuned) side by
        # side without mutating global settings between them. The normal
        # app path (no argument) keeps resolving through Settings, same as
        # before this parameter existed.
        self._model_name = model_name or resolve_reranker_model_name(get_settings())
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
