#!/usr/bin/env python
"""Evaluates whether the hallucination guard actually works: does
`rag_min_rerank_score` (app/core/config.py) correctly decline to answer
genuinely unanswerable (ungrounded) questions, without also declining
questions the corpus can actually answer?

The guard's decision — decline iff the best candidate's real cross-encoder
rerank score falls below `rag_min_rerank_score` — needs only real retrieval
and the real reranker, not LLM generation (mirrors the same
`declined = best_score is None or best_score < threshold` logic
`eval/run_eval.py::generate_and_score` uses). That means this script can
score a genuinely complete, real evaluation across the FULL labeled dataset
regardless of whether a chat backend (OpenAI/Ollama) happens to be reachable
— unlike faithfulness/relevance/citation scoring, which do need one.

Binary-classification framing (the guard's decision is "positive" when it
declines):
  - a query is a real positive (guard *should* decline) when it is labeled
    `answerable: false` — genuinely not supported by the corpus
  - TP: unanswerable question, correctly declined
  - TN: answerable question, correctly answered
  - FP: answerable question, incorrectly declined (a false abstention — the
    corpus could answer it, the guard refused anyway)
  - FN: unanswerable question, incorrectly answered (the guard's actual
    failure mode: a hallucination-risk question got through)

Run from backend/:
    uv run python ../eval/evaluate_hallucination.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app.core.config import get_settings  # noqa: E402
from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.embeddings import (  # noqa: E402
    EmbeddingBackend,
    LocalEmbeddingBackend,
    OpenAIEmbeddingBackend,
)
from app.core.vector_store import get_vector_store  # noqa: E402
from app.services.retrieval import RetrievalService  # noqa: E402
from eval.corpus import build_corpus, teardown_corpus  # noqa: E402
from eval.fakes import FakeEmbeddingBackend  # noqa: E402
from eval.run_eval import build_reranker, has_real_openai_key  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
RETRIEVAL_TOP_K = 10


async def run() -> dict:
    settings = get_settings()

    if settings.embedding_provider == "openai" and has_real_openai_key(settings):
        embedding_backend: EmbeddingBackend = OpenAIEmbeddingBackend()
        embedding_label = f"openai:{settings.openai_embedding_model}"
    elif settings.embedding_provider == "local":
        embedding_backend = LocalEmbeddingBackend()
        embedding_label = f"local:{settings.local_embedding_model}"
    else:
        embedding_backend = FakeEmbeddingBackend(dim=settings.qdrant_vector_size)
        embedding_label = "synthetic (hashing-trick bag-of-words)"

    reranker, reranker_label = await build_reranker()
    vector_store = get_vector_store()

    async with AsyncSessionLocal() as session:
        corpus = await build_corpus(session, vector_store, embedding_backend)
        if corpus.unresolved_markers:
            print(
                "ERROR: the following eval dataset content_markers did not match any "
                "indexed chunk (dataset/parsing mismatch — fix before trusting any report):",
                file=sys.stderr,
            )
            for m in corpus.unresolved_markers:
                print(f"  - {m}", file=sys.stderr)
            await teardown_corpus(session, vector_store, corpus)
            raise SystemExit(1)

        try:
            retrieval_service = RetrievalService(
                session,
                embedding_backend=embedding_backend,
                vector_store=vector_store,
                reranker=reranker,
            )

            records = []
            for q in corpus.queries:
                result = await retrieval_service.retrieve(
                    q.query, corpus.user_id, top_k=RETRIEVAL_TOP_K
                )
                best_score = max(
                    (c.rerank_score for c in result.results if c.rerank_score is not None),
                    default=None,
                )
                declined = best_score is None or best_score < settings.rag_min_rerank_score
                should_decline = not q.answerable

                if should_decline and declined:
                    label = "TP"
                elif not should_decline and not declined:
                    label = "TN"
                elif not should_decline and declined:
                    label = "FP"
                else:
                    label = "FN"

                records.append(
                    {
                        "id": q.id,
                        "query": q.query,
                        "category": q.category,
                        "answerable": q.answerable,
                        "declined": declined,
                        "best_rerank_score": (
                            round(best_score, 4) if best_score is not None else None
                        ),
                        "label": label,
                    }
                )
        finally:
            await teardown_corpus(session, vector_store, corpus)

    tp = sum(1 for r in records if r["label"] == "TP")
    tn = sum(1 for r in records if r["label"] == "TN")
    fp = sum(1 for r in records if r["label"] == "FP")
    fn = sum(1 for r in records if r["label"] == "FN")
    n = tp + tn + fp + fn

    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0

    return {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "embedding_backend": embedding_label,
            "reranker": reranker_label,
            "rag_min_rerank_score": settings.rag_min_rerank_score,
            "n_queries": n,
            "n_should_decline": tp + fn,
            "n_should_answer": tn + fp,
        },
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "metrics": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "specificity": round(specificity, 4),
        },
        "per_query": records,
    }


def print_summary(report: dict) -> None:
    meta, cm, m = report["meta"], report["confusion_matrix"], report["metrics"]
    print()
    print("=" * 72)
    print("HALLUCINATION GUARD EVALUATION")
    print("=" * 72)
    print(f"embedding backend      : {meta['embedding_backend']}")
    print(f"reranker               : {meta['reranker']}")
    print(f"rag_min_rerank_score   : {meta['rag_min_rerank_score']}")
    print(
        f"queries                : {meta['n_queries']} "
        f"({meta['n_should_decline']} should-decline, {meta['n_should_answer']} should-answer)"
    )
    print()
    print(f"Accuracy    : {m['accuracy']:.1%}")
    print(f"Precision   : {m['precision']:.1%}")
    print(f"Recall      : {m['recall']:.1%}")
    print(f"F1          : {m['f1']:.3f}")
    print(f"Specificity : {m['specificity']:.1%}")
    print()
    print("Confusion matrix")
    print("                  declined   answered")
    print(f"  unanswerable  {cm['tp']:>10}{cm['fn']:>11}   <- TP / FN")
    print(f"  answerable    {cm['fp']:>10}{cm['tn']:>11}   <- FP / TN")
    print("=" * 72)
    print()


def main() -> None:
    report = asyncio.run(run())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"hallucination_{timestamp}.json"
    output_path.write_text(json.dumps(report, indent=2))
    (RESULTS_DIR / "hallucination_latest.json").write_text(json.dumps(report, indent=2))
    print_summary(report)
    print(f"Full report written to {output_path}")


if __name__ == "__main__":
    main()
