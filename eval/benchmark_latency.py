#!/usr/bin/env python
"""Latency benchmark for the real retrieval + reranking + generation
pipeline, with enough repetitions to report percentiles rather than a single
noisy sample.

Retrieval and reranking timings come straight from
`RetrievalService.retrieve()`'s own internal instrumentation
(`timings_ms` — the same per-stage numbers `retrieval_complete` log lines
carry in production), not a re-implementation, so these numbers describe the
real production code path. Generation timing wraps a real
`ChatBackend.complete()` call directly.

Real local models (CPU cross-encoder reranking, and especially CPU LLM
generation via Ollama) are slow enough that benchmarking every stage over
the *same* large N is impractical: retrieval/reranking easily support
hundreds of repetitions in seconds, while a real generation call can take
10-90s each. `--n-retrieval` and `--n-generation` are therefore independent
sample sizes — see the printed report for exactly how many real
repetitions each stage's numbers rest on.

Run from backend/:
    uv run python ../eval/benchmark_latency.py
    uv run python ../eval/benchmark_latency.py --n-retrieval 60 --n-generation 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
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
from app.services.rag.prompts import (  # noqa: E402
    build_context_block,
    build_messages,
    from_retrieved_chunks,
)
from app.services.retrieval import RetrievalService  # noqa: E402
from eval.corpus import build_corpus, teardown_corpus  # noqa: E402
from eval.fakes import FakeEmbeddingBackend  # noqa: E402
from eval.run_eval import build_reranker, has_real_openai_key, ollama_reachable  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[idx]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values), 2),
        "p50": round(_percentile(values, 50), 2),
        "p95": round(_percentile(values, 95), 2),
        "p99": round(_percentile(values, 99), 2),
    }


async def run(args: argparse.Namespace) -> dict:
    settings = get_settings()
    real_key = has_real_openai_key(settings)

    if settings.embedding_provider == "openai" and real_key:
        embedding_backend: EmbeddingBackend = OpenAIEmbeddingBackend()
        embedding_label = f"openai:{settings.openai_embedding_model}"
    elif settings.embedding_provider == "local":
        embedding_backend = LocalEmbeddingBackend()
        embedding_label = f"local:{settings.local_embedding_model}"
    else:
        embedding_backend = FakeEmbeddingBackend(dim=settings.qdrant_vector_size)
        embedding_label = "synthetic (hashing-trick bag-of-words)"

    chat_backend = None
    chat_label = (
        "not available (no real OpenAI key, Ollama unreachable) — generation latency skipped"
    )
    if settings.chat_provider == "openai" and real_key:
        from app.core.chat import OpenAIChatBackend

        chat_backend = OpenAIChatBackend()
        chat_label = f"openai:{settings.openai_chat_model}"
    elif settings.chat_provider == "ollama" and await ollama_reachable(settings):
        from app.core.chat import OllamaChatBackend

        chat_backend = OllamaChatBackend()
        chat_label = f"ollama:{settings.ollama_chat_model}"

    reranker, reranker_label = await build_reranker()
    vector_store = get_vector_store()

    async with AsyncSessionLocal() as session:
        corpus = await build_corpus(session, vector_store, embedding_backend)
        if corpus.unresolved_markers:
            print("ERROR: unresolved content_markers — fix the dataset before benchmarking.",
                  file=sys.stderr)
            await teardown_corpus(session, vector_store, corpus)
            raise SystemExit(1)

        try:
            retrieval_service = RetrievalService(
                session,
                embedding_backend=embedding_backend,
                vector_store=vector_store,
                reranker=reranker,
            )
            filenames = {doc.document_id: doc.filename for doc in corpus.documents.values()}

            answerable_queries = [q for q in corpus.queries if q.answerable]
            retrieval_sample = (answerable_queries * args.repeats)[: args.n_retrieval]

            stage_ms: dict[str, list[float]] = {
                "embed_query_ms": [],
                "dense_search_ms": [],
                "bm25_search_ms": [],
                "fusion_ms": [],
                "rerank_ms": [],
                "retrieval_wall_ms": [],  # dense+bm25 (concurrent) + fusion, pre-rerank
                "total_ms": [],  # full retrieve() call: embed+search+fuse+rerank
            }
            for q in retrieval_sample:
                result = await retrieval_service.retrieve(q.query, corpus.user_id, top_k=10)
                for key in stage_ms:
                    if key in result.timings_ms:
                        stage_ms[key].append(result.timings_ms[key])

            generation_ms: list[float] = []
            end_to_end_ms: list[float] = []
            generation_errors: list[str] = []
            if chat_backend is not None:
                generation_sample = answerable_queries[: args.n_generation]
                for q in generation_sample:
                    result = await retrieval_service.retrieve(q.query, corpus.user_id, top_k=10)
                    sources = from_retrieved_chunks(result.results)
                    context_block, _ = build_context_block(sources, filenames)
                    messages = build_messages(
                        history=[], context_block=context_block, question=q.query
                    )

                    try:
                        t0 = time.perf_counter()
                        await chat_backend.complete(messages)
                        gen_ms = round((time.perf_counter() - t0) * 1000, 2)
                    except Exception as exc:  # noqa: BLE001 - same reasoning as run_eval.py's
                        # per-query resilience: a real backend can hang/error under
                        # sustained CPU-bound local inference (see eval/RESULTS.md), and
                        # this script previously lost every real measurement gathered so
                        # far to a single such failure instead of reporting them.
                        print(
                            f"warning: generation call failed for {q.id} "
                            f"({exc.__class__.__name__}: {exc}) — skipping, continuing",
                            file=sys.stderr,
                        )
                        generation_errors.append(q.id)
                        continue
                    generation_ms.append(gen_ms)
                    end_to_end_ms.append(round(result.timings_ms["total_ms"] + gen_ms, 2))
        finally:
            await teardown_corpus(session, vector_store, corpus)

    report = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "embedding_backend": embedding_label,
            "chat_backend": chat_label,
            "reranker": reranker_label,
            "n_retrieval_samples": len(retrieval_sample),
            "n_generation_samples": len(generation_ms),
            "n_generation_errors": len(generation_errors),
            "generation_error_query_ids": generation_errors,
        },
        "latency_ms": {
            "embed_query": _stats(stage_ms["embed_query_ms"]),
            "dense_search": _stats(stage_ms["dense_search_ms"]),
            "bm25_search": _stats(stage_ms["bm25_search_ms"]),
            "fusion": _stats(stage_ms["fusion_ms"]),
            "retrieval_wall": _stats(stage_ms["retrieval_wall_ms"]),
            "reranking": _stats(stage_ms["rerank_ms"]),
            "retrieval_and_rerank_total": _stats(stage_ms["total_ms"]),
            "generation": _stats(generation_ms),
            "end_to_end": _stats(end_to_end_ms),
        },
    }
    return report


def print_summary(report: dict) -> None:
    meta, lat = report["meta"], report["latency_ms"]
    print()
    print("=" * 72)
    print("LATENCY BENCHMARK")
    print("=" * 72)
    print(f"embedding backend : {meta['embedding_backend']}")
    print(f"chat backend      : {meta['chat_backend']}")
    print(f"reranker          : {meta['reranker']}")
    print(
        f"samples           : {meta['n_retrieval_samples']} retrieval calls, "
        f"{meta['n_generation_samples']} generation calls"
    )
    print()
    header = f"{'stage':<28}{'n':>5}{'mean':>10}{'p50':>10}{'p95':>10}{'p99':>10}  (ms)"
    print(header)
    print("-" * len(header))
    for label, key in (
        ("Embed query", "embed_query"),
        ("Dense search", "dense_search"),
        ("BM25 search", "bm25_search"),
        ("RRF fusion", "fusion"),
        ("Retrieval (dense+bm25+fuse)", "retrieval_wall"),
        ("Reranking", "reranking"),
        ("Retrieval+rerank total", "retrieval_and_rerank_total"),
        ("Generation", "generation"),
        ("End-to-end", "end_to_end"),
    ):
        s = lat[key]
        if s["n"] == 0:
            print(f"{label:<28}{'—':>5}{'—':>10}{'—':>10}{'—':>10}{'—':>10}")
        else:
            print(
                f"{label:<28}{s['n']:>5}{s['mean']:>10.1f}{s['p50']:>10.1f}"
                f"{s['p95']:>10.1f}{s['p99']:>10.1f}"
            )
    if meta["n_generation_samples"] == 0:
        print()
        print("⚠  Generation/end-to-end latency: no real chat backend was reachable for")
        print("   this run — see eval/RESULTS.md for how to get real numbers here.")
    if meta["n_generation_errors"]:
        print()
        print(
            f"⚠  {meta['n_generation_errors']} generation call(s) failed and were skipped "
            f"(not fatal to the run): {', '.join(meta['generation_error_query_ids'])}"
        )
    print("=" * 72)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n-retrieval", type=int, default=60,
        help="number of real retrieve() calls to time (default: 60, repeats over the "
        "answerable query set as needed)",
    )
    parser.add_argument(
        "--repeats", type=int, default=3,
        help="how many times to cycle through the answerable query set to reach "
        "--n-retrieval (default: 3)",
    )
    parser.add_argument(
        "--n-generation", type=int, default=10,
        help="number of real generation calls to time, only if a real chat backend is "
        "reachable (default: 10 — kept small since local CPU generation is slow)",
    )
    args = parser.parse_args()

    report = asyncio.run(run(args))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"latency_{timestamp}.json"
    output_path.write_text(json.dumps(report, indent=2))
    (RESULTS_DIR / "latency_latest.json").write_text(json.dumps(report, indent=2))
    print_summary(report)
    print(f"Full report written to {output_path}")


if __name__ == "__main__":
    main()
