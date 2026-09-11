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

Environment-aware backend selection (see `run()`), with the embedding and
chat/judge backends chosen *independently* of each other: `EMBEDDING_PROVIDER
=local` (sentence-transformers) has no runtime network dependency at all, so
it's real whenever configured, regardless of whether Ollama happens to be
reachable — only the chat/judge backend actually needs a live probe (Ollama)
or a real key (OpenAI) to be real, falling back to a synthetic extractive
stand-in (see eval/fakes.py) otherwise. This means retrieval numbers and
generation numbers can come from different real/synthetic combinations in
the same run — the report's `embedding_mode`/`chat_mode` fields and the
printed banner say plainly which, since they are not always comparable
across runs. See eval/RESULTS.md for what each combination's numbers do and
don't demonstrate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from itertools import zip_longest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import httpx  # noqa: E402

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
    extract_citations,
    from_retrieved_chunks,
)
from app.services.retrieval import RetrievalService  # noqa: E402
from app.services.retrieval.fusion import reciprocal_rank_fusion  # noqa: E402
from app.services.retrieval.models import RetrievedChunk  # noqa: E402
from eval.corpus import Corpus, EvalQuery, build_corpus, teardown_corpus  # noqa: E402
from eval.fakes import (  # noqa: E402
    FakeEmbeddingBackend,
    PassthroughReranker,
    SyntheticJudge,
    synthetic_answer,
)
from eval.metrics.generation_metrics import (  # noqa: E402
    Judge,
    citation_completeness,
    citation_correctness,
    score_answer_correctness,
    score_faithfulness,
    score_relevance,
)
from eval.metrics.retrieval_metrics import (  # noqa: E402
    mean_over_queries,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RESULTS_DIR = Path(__file__).parent / "results"
# Recall@1 catches "is the single best-ranked chunk actually right" (matters
# most for a UI that leads with its top hit); @10 matches this harness's
# fetch depth so it isn't a vacuous ceiling. NDCG/Precision@10 add the same
# deeper-window view for rank-sensitivity and result-list purity.
RECALL_KS = (1, 3, 5, 10)
NDCG_KS = (5, 10)
PRECISION_KS = (5, 10)


def has_real_openai_key(settings: Settings) -> bool:
    key = (settings.openai_api_key or "").strip().lower()
    return bool(key) and not key.startswith("sk-changeme")


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
    precisions = {k: [] for k in PRECISION_KS}
    ndcgs = {k: [] for k in NDCG_KS}
    mrrs = []
    for retrieved, relevant in zip(retrieved_ids_by_query, relevant_by_query, strict=True):
        for k in RECALL_KS:
            recalls[k].append(recall_at_k(retrieved, relevant, k))
        for k in PRECISION_KS:
            precisions[k].append(precision_at_k(retrieved, relevant, k))
        for k in NDCG_KS:
            ndcgs[k].append(ndcg_at_k(retrieved, relevant, k))
        mrrs.append(reciprocal_rank(retrieved, relevant))

    result = {}
    for k in RECALL_KS:
        mean, n = mean_over_queries(recalls[k])
        result[f"recall@{k}"] = round(mean, 4)
    for k in PRECISION_KS:
        mean, n = mean_over_queries(precisions[k])
        result[f"precision@{k}"] = round(mean, 4)
    for k in NDCG_KS:
        mean, n = mean_over_queries(ndcgs[k])
        result[f"ndcg@{k}"] = round(mean, 4)
    mean, n = mean_over_queries(mrrs)
    result["mrr"] = round(mean, 4)
    result["n_queries"] = n
    return result


def _interleave_dedup(
    list_a: list[uuid.UUID], list_b: list[uuid.UUID], top_k: int
) -> list[uuid.UUID]:
    """The "closest valid comparison" to a hybrid without RRF: round-robin
    interleaving of the two ranked lists, deduplicated, first occurrence
    wins. There is no production code path for a non-RRF hybrid (RRF is the
    only fusion method this system implements — see fusion.py), so this is a
    standalone baseline built for the ablation study only, not a stand-in for
    a real alternative fusion algorithm. It exists to isolate one specific
    question: does *any* naive combination of dense+BM25 beat either leg
    alone, before crediting RRF specifically for hybrid retrieval's gains.
    """
    merged: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for pair in zip_longest(list_a, list_b):
        for item in pair:
            if item is not None and item not in seen:
                seen.add(item)
                merged.append(item)
                if len(merged) >= top_k:
                    return merged
    return merged


async def evaluate_retrieval(
    corpus: Corpus,
    embedding_backend: EmbeddingBackend,
    chunk_repo: ChunkRepository,
    vector_store: VectorStore,
    retrieval_service: RetrievalService,
    settings: Settings,
    top_k: int,
) -> tuple[dict, dict[str, dict[str, list[uuid.UUID]]], list[list[RetrievedChunk]]]:
    """Runs five retrieval configurations for every query at equal depth
    (`top_k`) so Recall@K/MRR/NDCG/Precision@K are directly comparable across
    them: dense-only, BM25-only, a naive (non-RRF) dense+BM25 hybrid, RRF
    fusion without reranking, and the full production pipeline (RRF +
    cross-encoder rerank). Returns both the aggregated metrics and the raw
    per-query id lists (the latter reused for the per-query section of the
    report and, for the fully reranked variant, for answer generation).
    """
    dense_ids: list[list[uuid.UUID]] = []
    bm25_ids: list[list[uuid.UUID]] = []
    naive_hybrid_ids: list[list[uuid.UUID]] = []
    rrf_ids: list[list[uuid.UUID]] = []
    hybrid_ids: list[list[uuid.UUID]] = []
    hybrid_chunks: list[list[RetrievedChunk]] = []
    relevant: list[set[uuid.UUID]] = []

    for q in corpus.queries:
        relevant.append(q.relevant_chunk_ids)

        query_vector = (await embedding_backend.embed_batch([q.query]))[0]
        dense_hits = await vector_store.search(
            user_id=corpus.user_id, query_vector=query_vector, top_k=top_k
        )
        dense = [uuid.UUID(hit.payload["chunk_id"]) for hit in dense_hits]
        dense_ids.append(dense)

        bm25_hits = await chunk_repo.search_by_keyword(
            user_id=corpus.user_id, query=q.query, top_k=top_k
        )
        bm25 = [chunk.id for chunk, _score in bm25_hits]
        bm25_ids.append(bm25)

        naive_hybrid_ids.append(_interleave_dedup(dense, bm25, top_k))

        # Reuses the exact production RRF implementation (fusion.py), just
        # without the cross-encoder rerank step that the full pipeline
        # applies afterward — isolates RRF's own contribution.
        fused = reciprocal_rank_fusion([dense, bm25], k=settings.hybrid_search_rrf_k)
        rrf_ids.append([chunk_id for chunk_id, _score in fused][:top_k])

        result = await retrieval_service.retrieve(q.query, corpus.user_id, top_k=top_k)
        hybrid_ids.append([rc.chunk_id for rc in result.results])
        hybrid_chunks.append(result.results)

    metrics = {
        "dense_only": _variant_metrics(dense_ids, relevant),
        "bm25_only": _variant_metrics(bm25_ids, relevant),
        "naive_hybrid": _variant_metrics(naive_hybrid_ids, relevant),
        "hybrid_rrf": _variant_metrics(rrf_ids, relevant),
        "hybrid_rrf_reranked": _variant_metrics(hybrid_ids, relevant),
    }
    variant_ids = {
        "dense_only": dense_ids,
        "bm25_only": bm25_ids,
        "naive_hybrid": naive_hybrid_ids,
        "hybrid_rrf": rrf_ids,
        "hybrid_rrf_reranked": hybrid_ids,
    }
    raw = {
        variant: dict(zip((q.id for q in corpus.queries), ids, strict=True))
        for variant, ids in variant_ids.items()
    }
    return metrics, raw, hybrid_chunks


async def generate_and_score(
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
    # The pre-generation guard's own decision, based only on the real
    # retrieval pipeline and the real reranker's score — this is the same
    # signal `evaluate_hallucination.py` measures on its own, no LLM call
    # involved. It is deliberately *not* the last word: the second
    # mitigation layer (the answer-generation prompt's own constraint
    # against inferring a specific answer from general discussion) can
    # still catch a case this threshold missed, once real generation runs —
    # see `declined` below, which reflects the actual final outcome.
    guard_declined = best_score is None or best_score < settings.rag_min_rerank_score

    sources = from_retrieved_chunks(retrieved_chunks)
    context_block, index_map = build_context_block(sources, filenames)

    if guard_declined:
        answer = INSUFFICIENT_CONTEXT_MESSAGE
    elif chat_backend is not None:
        messages = build_messages(history=[], context_block=context_block, question=query.query)
        answer = await chat_backend.complete(messages)
    else:
        answer = synthetic_answer(query.query, sources)

    # The real, final outcome: did the guard decline up front, OR did the
    # model itself decline once it actually saw the (permitted) context?
    # Conflating these two into one flag was a real bug this harness had —
    # `abstention_correct` used to be computed from `guard_declined` alone,
    # which meant it was blind to the second mitigation layer entirely and
    # silently double-counted the guard's own known recall gap as if
    # nothing downstream could ever catch it.
    declined = guard_declined or answer.strip() == INSUFFICIENT_CONTEXT_MESSAGE
    second_layer_catch = (not guard_declined) and declined and not query.answerable

    faithfulness = await score_faithfulness(judge, query.query, context_block, answer)
    relevance = await score_relevance(judge, query.query, answer)
    correctness = await score_answer_correctness(
        judge, query.query, query.reference_answer, answer
    )

    citations = extract_citations(answer, index_map, filenames)
    cited_chunk_ids = [c.chunk_id for c in citations]
    correctness_of_citations = citation_correctness(cited_chunk_ids, query.relevant_chunk_ids)
    completeness_of_citations = citation_completeness(cited_chunk_ids, query.relevant_chunk_ids)

    abstention_correct = declined if not query.answerable else not declined

    return {
        "query_id": query.id,
        "category": query.category,
        "guard_declined": guard_declined,
        "declined": declined,
        "second_layer_catch": second_layer_catch,
        "answer": answer,
        "reference_answer": query.reference_answer,
        "faithfulness": round(faithfulness.score, 4),
        "faithfulness_rationale": faithfulness.rationale,
        "relevance": round(relevance.score, 4),
        "relevance_rationale": relevance.rationale,
        "answer_correctness": round(correctness.score, 4),
        "answer_correctness_rationale": correctness.rationale,
        "n_citations": len(citations),
        "citation_correctness": correctness_of_citations,
        "citation_completeness": completeness_of_citations,
        "abstention_correct": abstention_correct,
    }


def _aggregate_generation(records: list[dict]) -> dict:
    def _mean(key: str, predicate) -> tuple[float, int]:
        values = [r[key] for r in records if predicate(r) and r[key] is not None]
        return (sum(values) / len(values) if values else 0.0, len(values))

    faithfulness_all, n_all = _mean("faithfulness", lambda r: True)
    relevance_all, _ = _mean("relevance", lambda r: True)
    correctness_all, _ = _mean("answer_correctness", lambda r: True)
    faithfulness_answered, n_answered = _mean("faithfulness", lambda r: not r["declined"])
    relevance_answered, _ = _mean("relevance", lambda r: not r["declined"])
    correctness_answered, _ = _mean("answer_correctness", lambda r: not r["declined"])
    # citation_correctness/completeness are already None for a declined answer
    # (no citations possible) or a query with no labeled-relevant chunk, so
    # `_mean`'s None-filter is doing the right restriction on its own.
    citation_correctness_mean, n_citation_correctness = _mean(
        "citation_correctness", lambda r: True
    )
    citation_completeness_mean, n_citation_completeness = _mean(
        "citation_completeness", lambda r: True
    )
    abstention_failures = [r["query_id"] for r in records if not r["abstention_correct"]]
    errored = [r["query_id"] for r in records if r.get("error")]
    second_layer_catches = [r["query_id"] for r in records if r.get("second_layer_catch")]

    return {
        "n_errors": len(errored),
        "errored_query_ids": errored,
        # Queries where the pre-generation guard (rerank-score threshold)
        # missed an unanswerable question, but the answer-generation
        # prompt's own constraint caught it anyway at generation time — the
        # second mitigation layer actually doing something, not just
        # existing. See `evaluate_hallucination.py` for the guard-only
        # confusion matrix these queries "failed" in.
        "second_layer_catch_count": len(second_layer_catches),
        "second_layer_catch_query_ids": second_layer_catches,
        "faithfulness_mean_all_queries": round(faithfulness_all, 4),
        "relevance_mean_all_queries": round(relevance_all, 4),
        "answer_correctness_mean_all_queries": round(correctness_all, 4),
        "n_all_queries": n_all,
        "faithfulness_mean_answered_only": round(faithfulness_answered, 4),
        "relevance_mean_answered_only": round(relevance_answered, 4),
        "answer_correctness_mean_answered_only": round(correctness_answered, 4),
        "n_answered_only": n_answered,
        "citation_correctness_mean": round(citation_correctness_mean, 4),
        "n_citation_correctness": n_citation_correctness,
        "citation_completeness_mean": round(citation_completeness_mean, 4),
        "n_citation_completeness": n_citation_completeness,
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
            "⚠  No real embedding/chat backend available — embeddings, generation, and\n"
            "   the judge are all running in deterministic SYNTHETIC fallback mode. These\n"
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
    elif meta["embedding_mode"] != meta["chat_mode"]:
        print(
            f"ⓘ  MIXED mode: embeddings are {meta['embedding_mode'].upper()} "
            f"(real, no API key needed), chat/judge are {meta['chat_mode'].upper()}.\n"
            "   Retrieval numbers below reflect the embedding_mode; generation numbers\n"
            "   below reflect the chat_mode. See eval/RESULTS.md."
        )
    if meta.get("query_ids") is not None:
        print(
            f"⚠  --query-ids was set — this run only scored a {len(meta['query_ids'])}-query "
            "curated/stratified sample, not the full dataset. Its numbers are a real but "
            "partial sample, not comparable to a full run."
        )
    elif meta["limit_queries"] is not None:
        print(
            f"⚠  --limit-queries {meta['limit_queries']} was set — this run only scored the "
            f"first {meta['limit_queries']} of the labeled dataset's queries, not the full "
            "set. Its numbers are a real but partial sample, not comparable to a full run."
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

    print(f"Retrieval (equal fetch depth = {meta['retrieval_top_k']} across all five variants)")
    header = (
        f"{'variant':<20}{'recall@1':>9}{'recall@5':>9}{'recall@10':>10}"
        f"{'mrr':>8}{'ndcg@5':>8}{'p@5':>7}"
    )
    print(header)
    print("-" * len(header))
    for variant in ("dense_only", "bm25_only", "naive_hybrid", "hybrid_rrf", "hybrid_rrf_reranked"):
        m = report["retrieval"][variant]
        print(
            f"{variant:<20}{m['recall@1']:>9.3f}{m['recall@5']:>9.3f}{m['recall@10']:>10.3f}"
            f"{m['mrr']:>8.3f}{m['ndcg@5']:>8.3f}{m['precision@5']:>7.3f}"
        )
    print()

    gen = report["generation"]
    if gen is None:
        print("Generation: skipped (--retrieval-only)")
    else:
        print("Generation")
        print(f"  faithfulness       (all queries) : {gen['faithfulness_mean_all_queries']:.3f}")
        print(f"  relevance          (all queries) : {gen['relevance_mean_all_queries']:.3f}")
        print(
            f"  answer correctness (all queries) : "
            f"{gen['answer_correctness_mean_all_queries']:.3f}"
        )
        print(f"  faithfulness       (answered)    : {gen['faithfulness_mean_answered_only']:.3f}")
        print(f"  relevance          (answered)    : {gen['relevance_mean_answered_only']:.3f}")
        print(
            f"  answer correctness (answered)    : "
            f"{gen['answer_correctness_mean_answered_only']:.3f}"
        )
        print(
            f"  citation correctness             : {gen['citation_correctness_mean']:.3f} "
            f"(n={gen['n_citation_correctness']})"
        )
        print(
            f"  citation completeness            : {gen['citation_completeness_mean']:.3f} "
            f"(n={gen['n_citation_completeness']})"
        )
        print(
            f"  abstention correct               : "
            f"{gen['abstention_correct_count']}/{gen['abstention_total']}"
        )
        if gen["abstention_failed_query_ids"]:
            print(f"    ⚠ failed on: {', '.join(gen['abstention_failed_query_ids'])}")
        if gen["second_layer_catch_count"]:
            print(
                f"  ✓ second-layer catches           : "
                f"{gen['second_layer_catch_count']} "
                f"({', '.join(gen['second_layer_catch_query_ids'])}) — the guard's own "
                "rerank-threshold missed these, the generation prompt caught them anyway"
            )
        if gen["n_errors"]:
            print(
                f"  ⚠ {gen['n_errors']} quer{'y' if gen['n_errors'] == 1 else 'ies'} errored "
                f"(backend call failed, not scored): {', '.join(gen['errored_query_ids'])}"
            )
    print("=" * 72)
    print()


async def run(args: argparse.Namespace) -> dict:
    settings = get_settings()
    real_key = has_real_openai_key(settings)

    # Embedding backend is selected independently of the chat backend's
    # reachability. `EMBEDDING_PROVIDER=local` (sentence-transformers) has no
    # runtime network dependency at all — it doesn't touch Ollama or OpenAI —
    # so there is no reason a down Ollama service should force *dense
    # retrieval* into synthetic mode too. Coupling the two used to do exactly
    # that (see git history), silently understating Recall@K/MRR/NDCG for the
    # dense-only variant even when a real local embedding model was fully
    # available.
    if settings.embedding_provider == "openai" and real_key:
        embedding_backend: EmbeddingBackend = OpenAIEmbeddingBackend()
        embedding_mode = "real"
        embedding_backend_label = f"openai:{settings.openai_embedding_model}"
    elif settings.embedding_provider == "local":
        embedding_backend = LocalEmbeddingBackend()
        embedding_mode = "local"
        embedding_backend_label = f"local:{settings.local_embedding_model}"
    else:
        embedding_backend = FakeEmbeddingBackend(dim=settings.qdrant_vector_size)
        embedding_mode = "synthetic"
        embedding_backend_label = "synthetic (hashing-trick bag-of-words)"

    # Chat/judge backend: real only if the configured provider is actually
    # usable right now — a live network probe for Ollama, key presence for
    # OpenAI — independent of the embedding backend decision above.
    if settings.chat_provider == "openai" and real_key:
        chat_backend: ChatBackend | None = OpenAIChatBackend()
        chat_mode = "real"
        chat_backend_label = f"openai:{settings.openai_chat_model}"
        judge_backend_label = f"openai:{settings.openai_chat_model} (same model as generation)"
    elif settings.chat_provider == "ollama" and await ollama_reachable(settings):
        chat_backend = OllamaChatBackend()
        chat_mode = "local"
        chat_backend_label = f"ollama:{settings.ollama_chat_model}"
        judge_backend_label = (
            f"ollama:{settings.ollama_chat_model} (same model as generation — a small "
            "local model judging its own output; see eval/RESULTS.md's caveat on this)"
        )
    else:
        if settings.chat_provider == "ollama":
            print(
                f"warning: CHAT_PROVIDER=ollama but {settings.ollama_base_url} is not "
                "reachable; falling back to SYNTHETIC generation/judge for this run "
                "(embeddings/retrieval are unaffected — see the embedding_mode field). "
                "Run with the full docker-compose stack up (including the `ollama` "
                "service — see infra/docker-compose.yml) for real generation numbers.",
                file=sys.stderr,
            )
        chat_backend = None
        chat_mode = "synthetic"
        chat_backend_label = "synthetic (lexical-overlap extractive stand-in)"
        judge_backend_label = "synthetic (lexical-overlap heuristic)"

    judge: Judge = chat_backend if chat_backend is not None else SyntheticJudge()

    if embedding_mode == chat_mode:
        mode = embedding_mode
    else:
        mode = f"mixed ({embedding_mode} embeddings + {chat_mode} chat)"

    reranker, reranker_label = await build_reranker()
    vector_store = get_vector_store()

    async with AsyncSessionLocal() as session:
        corpus = await build_corpus(session, vector_store, embedding_backend)
        if args.query_ids is not None:
            wanted = set(args.query_ids)
            corpus.queries = [q for q in corpus.queries if q.id in wanted]
        elif args.limit_queries is not None:
            corpus.queries = corpus.queries[: args.limit_queries]
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
                corpus,
                embedding_backend,
                chunk_repo,
                vector_store,
                retrieval_service,
                settings,
                args.top_k,
            )

            filenames = {doc.document_id: doc.filename for doc in corpus.documents.values()}
            generation_records = []
            if not args.retrieval_only:
                for i, (query, chunks) in enumerate(
                    zip(corpus.queries, hybrid_chunks, strict=True), start=1
                ):
                    try:
                        record = await generate_and_score(
                            chat_backend, judge, settings, filenames, query, chunks
                        )
                    except Exception as exc:  # noqa: BLE001 - a real backend can hang/error
                        # under sustained CPU-bound local inference; recording the failure and
                        # continuing preserves every query scored so far instead of losing an
                        # entire long run (potentially hours of real LLM calls) to one timeout.
                        print(
                            f"warning: generation/judge call failed for {query.id} "
                            f"({exc.__class__.__name__}: {exc}) — recording as an error and "
                            "continuing",
                            file=sys.stderr,
                        )
                        record = {
                            "query_id": query.id,
                            "category": query.category,
                            "guard_declined": None,
                            "declined": None,
                            "second_layer_catch": False,
                            "answer": None,
                            "reference_answer": query.reference_answer,
                            "faithfulness": None,
                            "faithfulness_rationale": None,
                            "relevance": None,
                            "relevance_rationale": None,
                            "answer_correctness": None,
                            "answer_correctness_rationale": None,
                            "n_citations": None,
                            "citation_correctness": None,
                            "citation_completeness": None,
                            "abstention_correct": False,
                            "error": f"{exc.__class__.__name__}: {exc}",
                        }
                    generation_records.append(record)
                    print(f"  generation/judge: {i}/{len(corpus.queries)} scored", file=sys.stderr)

            per_query = []
            for i, q in enumerate(corpus.queries):
                entry = {
                    "id": q.id,
                    "query": q.query,
                    "category": q.category,
                    "relevant_chunk_ids": sorted(str(c) for c in q.relevant_chunk_ids),
                    "retrieved": {
                        variant: [str(c) for c in retrieval_raw[variant][q.id]]
                        for variant in (
                            "dense_only",
                            "bm25_only",
                            "naive_hybrid",
                            "hybrid_rrf",
                            "hybrid_rrf_reranked",
                        )
                    },
                }
                if generation_records:
                    entry["generation"] = generation_records[i]
                per_query.append(entry)

            report = {
                "meta": {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "mode": mode,
                    "embedding_mode": embedding_mode,
                    "chat_mode": chat_mode,
                    "embedding_backend": embedding_backend_label,
                    "chat_backend": chat_backend_label,
                    "judge_backend": judge_backend_label,
                    "reranker": reranker_label,
                    "retrieval_top_k": args.top_k,
                    "num_queries": len(corpus.queries),
                    "num_retrieval_queries": sum(
                        1 for q in corpus.queries if q.relevant_chunk_ids
                    ),
                    "num_documents": len(corpus.documents),
                    "num_chunks": sum(len(d.chunk_ids) for d in corpus.documents.values()),
                    "retrieval_only": args.retrieval_only,
                    "limit_queries": args.limit_queries,
                    "query_ids": args.query_ids,
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
        "--limit-queries",
        type=int,
        default=None,
        help=(
            "only run the first N labeled queries (in dataset order) instead of all of "
            "them — every document is still fully indexed either way, only the "
            "generation/judge call count drops. Useful for a real (not synthetic) "
            "local-mode run on constrained hardware, where the full dataset's ~60 "
            "sequential CPU-bound Ollama calls can take an hour-plus; a report built "
            "this way is a genuine but partial sample, not the full labeled set — its "
            "retrieval/generation numbers are not comparable to a full run's."
        ),
    )
    parser.add_argument(
        "--query-ids",
        type=lambda s: s.split(","),
        default=None,
        help=(
            "comma-separated dataset query ids to run instead of a --limit-queries prefix "
            "(e.g. q01,q22,q35) — lets a real (slow, CPU-bound) generation run be a "
            "deliberately category-stratified sample instead of an arbitrary dataset-order "
            "prefix. Takes precedence over --limit-queries if both are given."
        ),
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
