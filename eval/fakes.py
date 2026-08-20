"""Deterministic, offline stand-ins for the real OpenAI-backed embedding and
chat components, used automatically when no real `OPENAI_API_KEY` is
configured (see `eval/run_eval.py::detect_mode`). None of this is meant to
produce numbers that represent true system quality — it exists so the
harness's *mechanics* (indexing, retrieval, scoring, reporting) can be
exercised and verified without a paid API key, with every report clearly
labeled as synthetic-mode. See eval/RESULTS.md for the honest read on what
synthetic-mode numbers do and don't tell you.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Sequence

from app.core.reranker import Reranker
from app.services.rag.prompts import INSUFFICIENT_CONTEXT_MESSAGE, CitationSource

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def fake_embed(text: str, dim: int) -> list[float]:
    """A hashing-trick bag-of-words embedding: each distinct word deterministically
    votes (+1/-1, via a stable hash, not Python's salted `hash()`) into one of `dim`
    buckets, then the vector is L2-normalized. Texts that share vocabulary end up with
    positive cosine similarity, so dense search over these vectors produces a
    meaningful (if crude, lexical-only) ranking — good enough to test the retrieval
    *pipeline*, but with none of a real embedding model's semantic/paraphrase
    generalization. Uses hashlib rather than `hash()` so results are stable across
    process runs, which matters for eval reproducibility.
    """
    vector = [0.0] * dim
    for word in _tokenize(text):
        digest = int(hashlib.md5(word.encode()).hexdigest(), 16)
        idx = digest % dim
        sign = 1.0 if (digest // dim) % 2 == 0 else -1.0
        vector[idx] += sign
    norm = sum(v * v for v in vector) ** 0.5
    return vector if norm == 0 else [v / norm for v in vector]


class FakeEmbeddingBackend:
    def __init__(self, dim: int) -> None:
        self._dim = dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [fake_embed(t, self._dim) for t in texts]


def synthetic_answer(question: str, sources: Sequence[CitationSource]) -> str:
    """Stand-in for real LLM generation: picks the source(s) whose content
    shares the most vocabulary with the question and stitches together their
    opening sentence(s) with citation markers, mimicking the real system's
    `[n]`-citation format closely enough that `extract_citations` and the
    faithfulness/relevance judges still have something realistic to grade.
    Declines (matching the real system's own wording) when no source clears
    a minimal overlap bar, so the out-of-corpus eval query exercises the
    same abstention path in synthetic mode as in real mode.
    """
    question_words = set(_tokenize(question))
    if not question_words or not sources:
        return INSUFFICIENT_CONTEXT_MESSAGE

    scored = []
    for i, source in enumerate(sources, start=1):
        source_words = set(_tokenize(source.content))
        overlap = len(question_words & source_words) / len(question_words)
        scored.append((overlap, i, source))
    scored.sort(key=lambda t: t[0], reverse=True)

    best_overlap = scored[0][0]
    if best_overlap < 0.2:
        return INSUFFICIENT_CONTEXT_MESSAGE

    selected = [t for t in scored if t[0] >= max(0.2, best_overlap * 0.6)][:2]
    sentences = []
    for _, marker, source in selected:
        first_sentence = re.split(r"(?<=[.!?])\s+", source.content.strip())[0]
        sentences.append(f"{first_sentence.rstrip('.')} [{marker}].")
    return " ".join(sentences)


class PassthroughReranker(Reranker):
    """Used only if the real local cross-encoder model can't be loaded (no
    network to Hugging Face and no pre-baked model cache — e.g. running this
    harness outside the backend Docker image, which bakes the model in at
    build time). Preserves the fused (RRF) candidate order rather than
    actually reranking, so the harness can still run end to end — but this
    means the "reranked" retrieval variant's numbers, if this fallback is
    active, do NOT demonstrate the reranker's contribution and must be
    labeled as such in the report. See eval/run_eval.py's mode detection.
    """

    async def rerank(
        self, query: str, candidates: list[tuple[uuid.UUID, str]]
    ) -> list[tuple[uuid.UUID, float]]:
        n = len(candidates)
        return [(chunk_id, float(n - i)) for i, (chunk_id, _) in enumerate(candidates)]


class SyntheticJudge:
    """Implements the same `complete(messages) -> str` shape the real
    `ChatBackend`/LLM-as-judge uses, but scores via lexical overlap instead
    of an actual model call. It parses the section headers that
    `eval/metrics/generation_metrics.py` writes into its judge prompts
    (`"Context the answer was supposed to be grounded in:"`, `"Answer to
    grade:"`, `"Question:"`) to recover the pieces it needs — brittle in the
    sense that it depends on that exact prompt shape, but that shape is
    owned by this same codebase, not an external API, so the coupling is
    contained.
    """

    async def complete(self, messages: list[dict[str, str]]) -> str:
        user_content = next((m["content"] for m in messages if m["role"] == "user"), "")

        question_match = re.search(r"Question:\s*(.*?)\n\n", user_content, re.DOTALL)
        answer_match = re.search(r"Answer to grade:\s*(.*)", user_content, re.DOTALL)
        question = question_match.group(1).strip() if question_match else ""
        answer = answer_match.group(1).strip() if answer_match else ""

        if "Context the answer was supposed to be grounded in:" in user_content:
            context_match = re.search(
                r"Context the answer was supposed to be grounded in:\s*(.*?)\n\nAnswer to grade:",
                user_content,
                re.DOTALL,
            )
            reference = context_match.group(1).strip() if context_match else ""
            metric = "faithfulness (answer vs. context)"
        else:
            reference = question
            metric = "relevance (answer vs. question)"

        if answer.strip() == INSUFFICIENT_CONTEXT_MESSAGE:
            score, rationale = 5, "honest decline when context/question overlap is low"
        else:
            answer_words = set(_tokenize(answer))
            reference_words = set(_tokenize(reference))
            overlap = (
                len(answer_words & reference_words) / len(answer_words) if answer_words else 0.0
            )
            score = max(1, min(5, 1 + round(overlap * 4)))
            rationale = (
                f"synthetic heuristic ({metric}): {overlap:.0%} token overlap, "
                "no real LLM judge configured"
            )

        return json.dumps({"score": score, "rationale": rationale})
