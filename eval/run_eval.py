#!/usr/bin/env python
"""RAG evaluation harness: indexes the fixture corpus (eval/datasets/), runs
the labeled queries (eval/datasets/knowledge_base_eval.json) against the real
retrieval pipeline in three configurations (dense-only, BM25-only,
fused+reranked) and the real answer-generation pipeline, scores all of it
with Recall@K/MRR/NDCG (retrieval) and LLM-as-judge faithfulness/relevance
(generation), and writes a JSON report plus a human-readable summary table.

Must be run with the backend's own virtualenv/dependencies (openai,
qdrant-client, sqlalchemy, sentence-transformers, ...), against a real
Postgres (migrated) and Qdrant instance — the same infrastructure the test
suite needs. From the backend/ directory:

    uv run python ../eval/run_eval.py

Environment-aware backend selection, three modes (see `detect_mode`): "real"
(OpenAI for both embeddings and generation, needs a real `OPENAI_API_KEY`),
"local" (the same local embedding model + Ollama chat backend the live app
defaults to — no API key needed, but the `ollama` service must actually be
reachable), and "synthetic" (deterministic, offline stand-ins — see
eval/fakes.py) as the universal fallback when neither of the above is
available. Mode selection mirrors whichever `EMBEDDING_PROVIDER`/
`CHAT_PROVIDER` the app is actually configured with, not just OpenAI-key
presence, so the harness reports on the real, currently-configured pipeline
rather than always assuming OpenAI. The report's "mode" field and printed
banner say plainly which mode produced a given run's numbers, since they are
not comparable. See eval/RESULTS.md for what each mode's numbers do and
don't demonstrate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import httpx  # noqa: E402
from eval.corpus import Corpus, EvalQuery, build_corpus, teardown_corpus  # noqa: E402
from eval.fakes import (  # noqa: E402
    FakeEmbeddingBackend,
    PassthroughReranker,
    SyntheticJudge,
    synthetic_answer,
)
from eval.metrics.generation_metrics import Judge, score_faithfulness, score_relevance  # noqa: E402
from eval.metrics.retrieval_metrics import (  # noqa: E402
    mean_over_queries,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)

from app.core.chat import ChatBackend, OllamaChatBackend, OpenAIChatBackend  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.embeddings import (  # noqa: E402
    EmbeddingBackend,
    LocalEmbeddingBackend,
    OpenAIEmbeddingBackend,
)
from app.core.reranker import CrossEncoderReranker, Reranker  # noqa: E402
from app.core.vector_store import VectorStore, get_vector_store  # noqa: E402
from app.repositories.chunk_repository import ChunkRepository  # noqa: E402
from app.services.rag.prompts import (  # noqa: E402
    INSUFFICIENT_CONTEXT_MESSAGE,
    build_context_block,
    build_messages,
    from_retrieved_chunks,
)
from app.services.retrieval import RetrievalService  # noqa: E402
from app.services.retrieval.models import RetrievedChunk  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
RECALL_KS = (3, 5)
NDCG_K = 5


def detect_mode(settings: Settings) -> str:
    """Settings-driven, not just key-presence-driven: mirrors whichever
    embedding/chat provider combination the app is actually configured with
    (`EMBEDDING_PROVIDER`/`CHAT_PROVIDER`), so this harness evaluates the real
    running pipeline rather than always assuming OpenAI. "local" mode's
    actual availability (is `ollama` reachable right now?) can only be
    checked with a real network call, so that check happens later in `run()`
    — this function only reads static config, and downgrades to "synthetic"
    at runtime if the local-mode probe fails."""
    key = (settings.openai_api_key or "").strip().lower()
    has_real_openai_key = bool(key) and not key.startswith("sk-changeme")
    if (
        settings.embedding_provider == "openai"
        and settings.chat_provider == "openai"
        and has_real_openai_key
    ):
        return "real"
    if settings.embedding_provider == "local" and settings.chat_provider == "ollama":
        return "local"
    return "synthetic"


async def ollama_reachable(settings: Settings) -> bool:
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=3.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return True
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.HTTPStatusError):
        return False


async def build_reranker() -> tuple[Reranker, str]:
    reranker = CrossEncoderReranker()
    try:
        await reranker.warm_up()
        return reranker, "cross-encoder/ms-marco-MiniLM-L-6-v2 (real, local model)"
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any load failure -> fallback
        print(
            f"warning: could not load the local cross-encoder reranker ({exc}); "
            "falling back to a passthrough (no real reranking). Run inside the backend "
            "Docker image (which bakes the model in at build time) for real numbers.",
            file=sys.stderr,
        )
        return PassthroughReranker(), "passthrough (real reranker unavailable in this environment)"


def _variant_metrics(
    retrieved_ids_by_query: list[list[uuid.UUID]], relevant_by_query: list[set[uuid.UUID]]
) -> dict:
    recalls = {k: [] for k in RECALL_KS}
    mrrs, ndcgs = [], []
    for retrieved, relevant in zip(retrieved_ids_by_query, relevant_by_query, strict=True):
        for k in RECALL_KS:
            recalls[k].append(recall_at_k(retrieved, relevant, k))
        mrrs.append(reciprocal_rank(retrieved, relevant))
        ndcgs.append(ndcg_at_k(retrieved, relevant, NDCG_K))

    result = {}
    for k in RECALL_KS:
        mean, n = mean_over_queries(recalls[k])
        result[f"recall@{k}"] = round(mean, 4)
    mean, n = mean_over_queries(mrrs)
    result["mrr"] = round(mean, 4)
    mean, n = mean_over_queries(ndcgs)
    result[f"ndcg@{NDCG_K}"] = round(mean, 4)
    result["n_queries"] = n
    return result


async def evaluate_retrieval(
    corpus: Corpus,
    embedding_backend: EmbeddingBackend,
    chunk_repo: ChunkRepository,
    vector_store: VectorStore,
    retrieval_service: RetrievalService,
    top_k: int,
) -> tuple[dict, dict[str, dict[str, list[uuid.UUID]]], list[list[RetrievedChunk]]]:
    """Runs all three retrieval variants for every query at equal depth
    (`top_k`) so Recall@K/MRR/NDCG are directly comparable across them, and
    returns both the aggregated metrics and the raw per-query id lists (the
    latter reused for the per-query section of the report and, for the
    hybrid+reranked variant, for answer generation).
    """
    dense_ids: list[list[uuid.UUID]] = []
    bm25_ids: list[list[uuid.UUID]] = []
    hybrid_ids: list[list[uuid.UUID]] = []
    hybrid_chunks: list[list[RetrievedChunk]] = []
    relevant: list[set[uuid.UUID]] = []

    for q in corpus.queries:
        relevant.append(q.relevant_chunk_ids)

        query_vector = (await embedding_backend.embed_batch([q.query]))[0]
        dense_hits = await vector_store.search(
            user_id=corpus.user_id, query_vector=query_vector, top_k=top_k
        )
        dense_ids.append([uuid.UUID(hit.payload["chunk_id"]) for hit in dense_hits])

        bm25_hits = await chunk_repo.search_by_keyword(
            user_id=corpus.user_id, query=q.query, top_k=top_k
        )
        bm25_ids.append([chunk.id for chunk, _score in bm25_hits])

        result = await retrieval_service.retrieve(q.query, corpus.user_id, top_k=top_k)
        hybrid_ids.append([rc.chunk_id for rc in result.results])
        hybrid_chunks.append(result.results)

    metrics = {
        "dense_only": _variant_metrics(dense_ids, relevant),
        "bm25_only": _variant_metrics(bm25_ids, relevant),
        "hybrid_reranked": _variant_metrics(hybrid_ids, relevant),
    }
    raw = {
        "dense_only": dict(zip((q.id for q in corpus.queries), dense_ids, strict=True)),
        "bm25_only": dict(zip((q.id for q in corpus.queries), bm25_ids, strict=True)),
        "hybrid_reranked": dict(zip((q.id for q in corpus.queries), hybrid_ids, strict=True)),
    }
    return metrics, raw, hybrid_chunks


async def generate_and_score(
    mode: str,
    chat_backend: ChatBackend | None,
    judge: Judge,
    settings: Settings,
    filenames: dict[uuid.UUID, str],
    query: EvalQuery,
    retrieved_chunks: list[RetrievedChunk],
) -> dict:
    best_score = max(
        (c.rerank_score for c in retrieved_chunks if c.rerank_score is not None), default=None
    )
    declined = best_score is None or best_score < settings.rag_min_rerank_score

    sources = from_retrieved_chunks(retrieved_chunks)
    context_block, index_map = build_context_block(sources, filenames)

    if declined:
        answer = INSUFFICIENT_CONTEXT_MESSAGE
    elif mode in ("real", "local"):
        messages = build_messages(history=[], context_block=context_block, question=query.query)
        answer = await chat_backend.complete(messages)
    else:
        answer = synthetic_answer(query.query, sources)

    faithfulness = await score_faithfulness(judge, query.query, context_block, answer)
    relevance = await score_relevance(judge, query.query, answer)

    is_out_of_corpus = query.category == "out_of_corpus"
    abstention_correct = declined if is_out_of_corpus else not declined

    return {
        "query_id": query.id,
        "category": query.category,
        "declined": declined,
        "answer": answer,
        "reference_answer": query.reference_answer,
        "faithfulness": round(faithfulness.score, 4),
        "faithfulness_rationale": faithfulness.rationale,
        "relevance": round(relevance.score, 4),
        "relevance_rationale": relevance.rationale,
        "abstention_correct": abstention_correct,
    }


def _aggregate_generation(records: list[dict]) -> dict:
    def _mean(key: str, predicate) -> tuple[float, int]:
        values = [r[key] for r in records if predicate(r)]
        return (sum(values) / len(values) if values else 0.0, len(values))

    faithfulness_all, n_all = _mean("faithfulness", lambda r: True)
    relevance_all, _ = _mean("relevance", lambda r: True)
    faithfulness_answered, n_answered = _mean("faithfulness", lambda r: not r["declined"])
    relevance_answered, _ = _mean("relevance", lambda r: not r["declined"])
    abstention_failures = [r["query_id"] for r in records if not r["abstention_correct"]]

    return {
        "faithfulness_mean_all_queries": round(faithfulness_all, 4),
        "relevance_mean_all_queries": round(relevance_all, 4),
        "n_all_queries": n_all,
        "faithfulness_mean_answered_only": round(faithfulness_answered, 4),
        "relevance_mean_answered_only": round(relevance_answered, 4),
        "n_answered_only": n_answered,
        "abstention_correct_count": len(records) - len(abstention_failures),
        "abstention_total": len(records),
        "abstention_failed_query_ids": abstention_failures,
    }


def print_summary(report: dict) -> None:
    meta = report["meta"]
    print()
    print("=" * 72)
    print(f"RAG EVALUATION REPORT — mode: {meta['mode'].upper()}")
    print("=" * 72)
    if meta["mode"] == "synthetic":
        print(
            "⚠  No real OPENAI_API_KEY configured — embeddings, generation, and the\n"
            "   judge are all running in deterministic SYNTHETIC fallback mode. These\n"
            "   numbers validate the harness's mechanics, not real system quality.\n"
            "   See eval/RESULTS.md."
        )
    elif meta["mode"] == "local":
        print(
            "ⓘ  Real local models throughout (embeddings + Ollama generation), no API\n"
            "   key used. The judge is the SAME small model doing generation grading its\n"
            "   own output — a real, known limitation (shared blind spots), not a\n"
            "   synthetic-mode caveat. See eval/RESULTS.md."
        )
    print(f"embedding backend : {meta['embedding_backend']}")
    print(f"chat backend      : {meta['chat_backend']}")
    print(f"judge backend     : {meta['judge_backend']}")
    print(f"reranker          : {meta['reranker']}")
    print(
        f"queries           : {meta['num_queries']} "
        f"({meta['num_retrieval_queries']} scored for retrieval)"
    )
    print()

    print(f"Retrieval (equal fetch depth = {meta['retrieval_top_k']} across all three variants)")
    header = f"{'variant':<18}{'recall@3':>10}{'recall@5':>10}{'mrr':>10}{'ndcg@5':>10}"
    print(header)
    print("-" * len(header))
    for variant in ("dense_only", "bm25_only", "hybrid_reranked"):
        m = report["retrieval"][variant]
        print(
            f"{variant:<18}{m['recall@3']:>10.3f}{m['recall@5']:>10.3f}"
            f"{m['mrr']:>10.3f}{m[f'ndcg@{NDCG_K}']:>10.3f}"
        )
    print()

    gen = report["generation"]
    print("Generation")
    print(f"  faithfulness (all queries)     : {gen['faithfulness_mean_all_queries']:.3f}")
    print(f"  relevance    (all queries)     : {gen['relevance_mean_all_queries']:.3f}")
    print(f"  faithfulness (answered only)   : {gen['faithfulness_mean_answered_only']:.3f}")
    print(f"  relevance    (answered only)   : {gen['relevance_mean_answered_only']:.3f}")
    print(
        f"  abstention correct             : "
        f"{gen['abstention_correct_count']}/{gen['abstention_total']}"
    )
    if gen["abstention_failed_query_ids"]:
        print(f"    ⚠ failed on: {', '.join(gen['abstention_failed_query_ids'])}")
    print("=" * 72)
    print()


async def run(args: argparse.Namespace) -> dict:
    settings = get_settings()
    mode = detect_mode(settings)

    if mode == "local" and not await ollama_reachable(settings):
        print(
            f"warning: CHAT_PROVIDER=ollama but {settings.ollama_base_url} is not reachable; "
            "falling back to SYNTHETIC mode for this run. Run with the full docker-compose "
            "stack up (including the `ollama` service — see infra/docker-compose.yml) for "
            "real local-mode numbers.",
            file=sys.stderr,
        )
        mode = "synthetic"

    if mode == "real":
        embedding_backend: EmbeddingBackend = OpenAIEmbeddingBackend()
        chat_backend: ChatBackend | None = OpenAIChatBackend()
        judge: Judge = chat_backend
        embedding_backend_label = f"openai:{settings.openai_embedding_model}"
        chat_backend_label = f"openai:{settings.openai_chat_model}"
        judge_backend_label = f"openai:{settings.openai_chat_model} (same model as generation)"
    elif mode == "local":
        embedding_backend = LocalEmbeddingBackend()
        chat_backend = OllamaChatBackend()
        judge = chat_backend
        embedding_backend_label = f"local:{settings.local_embedding_model}"
        chat_backend_label = f"ollama:{settings.ollama_chat_model}"
        judge_backend_label = (
            f"ollama:{settings.ollama_chat_model} (same model as generation — a small "
            "local model judging its own output; see eval/RESULTS.md's caveat on this)"
        )
    else:
        embedding_backend = FakeEmbeddingBackend(dim=settings.qdrant_vector_size)
        chat_backend = None
        judge = SyntheticJudge()
        embedding_backend_label = "synthetic (hashing-trick bag-of-words)"
        chat_backend_label = "synthetic (lexical-overlap extractive stand-in)"
        judge_backend_label = "synthetic (lexical-overlap heuristic)"

    reranker, reranker_label = await build_reranker()
    vector_store = get_vector_store()

    async with AsyncSessionLocal() as session:
        corpus = await build_corpus(session, vector_store, embedding_backend)
        if corpus.unresolved_markers:
            print(
                "ERROR: the following eval dataset content_markers did not match any indexed "
                "chunk (dataset/parsing mismatch — fix before trusting any report):",
                file=sys.stderr,
            )
            for m in corpus.unresolved_markers:
                print(f"  - {m}", file=sys.stderr)
            await teardown_corpus(session, vector_store, corpus)
            raise SystemExit(1)

        try:
            chunk_repo = ChunkRepository(session)
            retrieval_service = RetrievalService(
                session,
                embedding_backend=embedding_backend,
                vector_store=vector_store,
                reranker=reranker,
            )

            retrieval_metrics, retrieval_raw, hybrid_chunks = await evaluate_retrieval(
                corpus, embedding_backend, chunk_repo, vector_store, retrieval_service, args.top_k
            )

            filenames = {doc.document_id: doc.filename for doc in corpus.documents.values()}
            generation_records = []
            if not args.retrieval_only:
                for query, chunks in zip(corpus.queries, hybrid_chunks, strict=True):
                    record = await generate_and_score(
                        mode, chat_backend, judge, settings, filenames, query, chunks
                    )
                    generation_records.append(record)

            per_query = []
            for i, q in enumerate(corpus.queries):
                entry = {
                    "id": q.id,
                    "query": q.query,
                    "category": q.category,
                    "relevant_chunk_ids": sorted(str(c) for c in q.relevant_chunk_ids),
                    "retrieved": {
                        variant: [str(c) for c in retrieval_raw[variant][q.id]]
                        for variant in ("dense_only", "bm25_only", "hybrid_reranked")
                    },
                }
                if generation_records:
                    entry["generation"] = generation_records[i]
                per_query.append(entry)

            report = {
                "meta": {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "mode": mode,
                    "embedding_backend": embedding_backend_label,
                    "chat_backend": chat_backend_label,
                    "judge_backend": judge_backend_label,
                    "reranker": reranker_label,
                    "retrieval_top_k": args.top_k,
                    "num_queries": len(corpus.queries),
                    "num_retrieval_queries": sum(
                        1 for q in corpus.queries if q.relevant_chunk_ids
                    ),
                    "retrieval_only": args.retrieval_only,
                },
                "retrieval": retrieval_metrics,
                "generation": (
                    _aggregate_generation(generation_records) if generation_records else None
                ),
                "per_query": per_query,
            }
        finally:
            await teardown_corpus(session, vector_store, corpus)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="fetch depth used for all three retrieval variants (default: 10)",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="skip generation/judge scoring (faster, no LLM calls)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="path to write the JSON report (default: eval/results/<timestamp>.json)",
    )
    args = parser.parse_args()

    report = asyncio.run(run(args))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output or RESULTS_DIR / f"{timestamp}.json"
    output_path.write_text(json.dumps(report, indent=2))
    latest_path = RESULTS_DIR / "latest.json"
    latest_path.write_text(json.dumps(report, indent=2))

    print_summary(report)
    print(f"Full report written to {output_path}")


if __name__ == "__main__":
    main()
