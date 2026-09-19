#!/usr/bin/env python
"""Runs the FULL, untouched 116-query held-out benchmark
(eval/datasets/knowledge_base_eval.json — never used by
generate_training_data.py or train_reranker.py) through the real production
retrieval pipeline (dense + BM25 + RRF + cross-encoder rerank —
app/services/retrieval/) twice: once with the baseline reranker
(cross-encoder/ms-marco-MiniLM-L-6-v2, as shipped) and once with the
fine-tuned checkpoint produced by train_reranker.py, with every other
component held identical (same corpus, same embeddings, same
hallucination-guard threshold). Reports Recall@1/@5/@10, MRR, NDCG@5, real
measured reranking latency, and hallucination-guard accuracy/precision/
recall/F1 for both, plus computed absolute differences — every number in
the report comes from an actual run of this pipeline, nothing hand-typed.

Both rerankers are evaluated at the CURRENT hallucination-guard threshold
(settings.rag_min_rerank_score) for a fair, apples-to-apples comparison at
today's real operating point — see calibrate_threshold.py for whether the
fine-tuned model's score distribution justifies a different threshold (a
separate, deliberately isolated question, decided on the calibration split,
never on this benchmark).

Also computes real paired statistics on the same 116 queries (see
paired_stats.py): McNemar's exact test on the hallucination guard's per-query
correct/incorrect outcome (the right tool for "did these two paired
classifiers disagree more than chance," not an unpaired test that would
wrongly treat the two runs as independent samples) plus 95% bootstrap
confidence intervals on each model's own Recall@1/MRR (descriptive
estimation uncertainty, not a significance claim about their difference —
that difference is already exactly zero, reported as such, not as "no
significant difference" dressed up in false precision).

Run from backend/:
    uv run python ../eval/reranker_training/evaluate_baseline_vs_finetuned.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app.core.config import get_settings  # noqa: E402
from app.core.db import AsyncSessionLocal  # noqa: E402
from app.core.embeddings import EmbeddingBackend, LocalEmbeddingBackend  # noqa: E402
from app.core.reranker import BASELINE_RERANKER_MODEL, CrossEncoderReranker  # noqa: E402
from app.core.vector_store import get_vector_store  # noqa: E402
from app.services.retrieval import RetrievalService  # noqa: E402
from eval.corpus import Corpus, build_corpus, teardown_corpus  # noqa: E402
from eval.metrics.retrieval_metrics import (  # noqa: E402
    mean_over_queries,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)
from eval.reranker_training.paired_stats import (  # noqa: E402
    mcnemar_exact_test,
    paired_bootstrap_ci,
)

RESULTS_DIR = Path(__file__).parent.parent / "results"
MODELS_DIR = Path(__file__).parent / "models"
RETRIEVAL_TOP_K = 10
RECALL_KS = (1, 5, 10)


async def _evaluate_one_reranker(
    label: str,
    model_name: str,
    corpus: Corpus,
    embedding_backend: EmbeddingBackend,
    session,
    vector_store,
    rag_min_rerank_score: float,
) -> dict:
    reranker = CrossEncoderReranker(model_name=model_name)
    await reranker.warm_up()  # pay model-load cost once, outside the timed loop
    retrieval_service = RetrievalService(
        session, embedding_backend=embedding_backend, vector_store=vector_store, reranker=reranker
    )

    retrieved_by_query: list[list[uuid.UUID]] = []
    relevant_by_query: list[set[uuid.UUID]] = []
    rerank_ms_samples: list[float] = []
    guard_records = []
    # Keyed by query id (stable across both baseline/fine-tuned runs, same
    # corpus and same query list each time) so run() can PAIR each query's
    # outcome between the two models — required for McNemar's test, which
    # needs to know, per query, whether the two models agreed or
    # disagreed, not just each model's own marginal totals.
    per_query: dict[str, dict] = {}

    for q in corpus.queries:
        result = await retrieval_service.retrieve(q.query, corpus.user_id, top_k=RETRIEVAL_TOP_K)
        retrieved_ids = [rc.chunk_id for rc in result.results]

        recall_at_1 = None
        reciprocal_rank_value = None
        if q.relevant_chunk_ids:
            retrieved_by_query.append(retrieved_ids)
            relevant_by_query.append(q.relevant_chunk_ids)
            recall_at_1 = recall_at_k(retrieved_ids, q.relevant_chunk_ids, 1)
            reciprocal_rank_value = reciprocal_rank(retrieved_ids, q.relevant_chunk_ids)

        if "rerank_ms" in result.timings_ms:
            rerank_ms_samples.append(result.timings_ms["rerank_ms"])

        best_score = max(
            (rc.rerank_score for rc in result.results if rc.rerank_score is not None),
            default=None,
        )
        declined = best_score is None or best_score < rag_min_rerank_score
        should_decline = not q.answerable
        if should_decline and declined:
            guard_label = "TP"
        elif not should_decline and not declined:
            guard_label = "TN"
        elif not should_decline and declined:
            guard_label = "FP"
        else:
            guard_label = "FN"
        guard_records.append({"id": q.id, "label": guard_label})

        per_query[q.id] = {
            "guard_label": guard_label,
            "guard_correct": guard_label in ("TP", "TN"),
            "recall_at_1": recall_at_1,
            "reciprocal_rank": reciprocal_rank_value,
        }

    recalls = {k: [] for k in RECALL_KS}
    ndcgs = []
    mrrs = []
    for retrieved, relevant in zip(retrieved_by_query, relevant_by_query, strict=True):
        for k in RECALL_KS:
            recalls[k].append(recall_at_k(retrieved, relevant, k))
        ndcgs.append(ndcg_at_k(retrieved, relevant, 5))
        mrrs.append(reciprocal_rank(retrieved, relevant))

    retrieval_metrics = {}
    for k in RECALL_KS:
        mean, n = mean_over_queries(recalls[k])
        retrieval_metrics[f"recall@{k}"] = round(mean, 4)
    mean_ndcg, _ = mean_over_queries(ndcgs)
    retrieval_metrics["ndcg@5"] = round(mean_ndcg, 4)
    mean_mrr, n_retrieval = mean_over_queries(mrrs)
    retrieval_metrics["mrr"] = round(mean_mrr, 4)
    retrieval_metrics["n_retrieval_queries"] = n_retrieval

    tp = sum(1 for r in guard_records if r["label"] == "TP")
    tn = sum(1 for r in guard_records if r["label"] == "TN")
    fp = sum(1 for r in guard_records if r["label"] == "FP")
    fn = sum(1 for r in guard_records if r["label"] == "FN")
    n = tp + tn + fp + fn
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    latency_mean = (
        round(sum(rerank_ms_samples) / len(rerank_ms_samples), 2) if rerank_ms_samples else None
    )
    latency_sorted = sorted(rerank_ms_samples)
    if latency_sorted:
        p95_idx = min(len(latency_sorted) - 1, round(0.95 * (len(latency_sorted) - 1)))
        latency_p95 = round(latency_sorted[p95_idx], 2)
    else:
        latency_p95 = None

    return {
        "label": label,
        "model_name": model_name,
        "retrieval": retrieval_metrics,
        "hallucination_guard": {
            "rag_min_rerank_score": rag_min_rerank_score,
            "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        },
        "reranking_latency_ms": {
            "mean": latency_mean,
            "p95": latency_p95,
            "n_samples": len(rerank_ms_samples),
        },
        "per_query": per_query,
    }


def _compute_statistics(baseline: dict, finetuned: dict) -> dict:
    """Real paired analysis over the SAME 116 queries both models were
    scored on — see paired_stats.py and this script's module docstring for
    why McNemar (not an unpaired test) is the right tool here, and why the
    bootstrap CIs below describe estimation uncertainty on each model's own
    metric rather than manufacturing a significance claim about a
    difference that's already exactly zero."""
    b_pq, f_pq = baseline["per_query"], finetuned["per_query"]
    shared_ids = sorted(set(b_pq) & set(f_pq))

    # Guard McNemar: b = baseline correct & finetuned wrong, c = the reverse.
    guard_b = sum(
        1 for qid in shared_ids if b_pq[qid]["guard_correct"] and not f_pq[qid]["guard_correct"]
    )
    guard_c = sum(
        1 for qid in shared_ids if not b_pq[qid]["guard_correct"] and f_pq[qid]["guard_correct"]
    )
    guard_mcnemar = mcnemar_exact_test(guard_b, guard_c)

    # Recall@1 McNemar: only over queries with a labeled-relevant chunk
    # (recall_at_1 is None otherwise — the same restriction the aggregate
    # Recall@1 metric already applies).
    recall_ids = [
        qid for qid in shared_ids
        if b_pq[qid]["recall_at_1"] is not None and f_pq[qid]["recall_at_1"] is not None
    ]
    recall_b = sum(
        1 for qid in recall_ids
        if b_pq[qid]["recall_at_1"] == 1.0 and f_pq[qid]["recall_at_1"] == 0.0
    )
    recall_c = sum(
        1 for qid in recall_ids
        if b_pq[qid]["recall_at_1"] == 0.0 and f_pq[qid]["recall_at_1"] == 1.0
    )
    recall_at_1_mcnemar = mcnemar_exact_test(recall_b, recall_c)

    baseline_recall_values = [b_pq[qid]["recall_at_1"] for qid in recall_ids]
    finetuned_recall_values = [f_pq[qid]["recall_at_1"] for qid in recall_ids]
    baseline_rr_values = [
        b_pq[qid]["reciprocal_rank"] for qid in recall_ids
        if b_pq[qid]["reciprocal_rank"] is not None
    ]
    finetuned_rr_values = [
        f_pq[qid]["reciprocal_rank"] for qid in recall_ids
        if f_pq[qid]["reciprocal_rank"] is not None
    ]

    return {
        "n_paired_queries": len(shared_ids),
        "hallucination_guard_mcnemar": guard_mcnemar,
        "recall_at_1_mcnemar": recall_at_1_mcnemar,
        "recall_at_1_bootstrap_ci": {
            "baseline": paired_bootstrap_ci(baseline_recall_values),
            "finetuned": paired_bootstrap_ci(finetuned_recall_values),
        },
        "mrr_bootstrap_ci": {
            "baseline": paired_bootstrap_ci(baseline_rr_values),
            "finetuned": paired_bootstrap_ci(finetuned_rr_values),
        },
    }


def _diff(baseline: dict, finetuned: dict) -> dict:
    def _d(path: list[str]) -> float | None:
        b, f = baseline, finetuned
        for key in path:
            b, f = b[key], f[key]
        if b is None or f is None:
            return None
        return round(f - b, 4)

    return {
        "recall@1": _d(["retrieval", "recall@1"]),
        "recall@5": _d(["retrieval", "recall@5"]),
        "recall@10": _d(["retrieval", "recall@10"]),
        "mrr": _d(["retrieval", "mrr"]),
        "ndcg@5": _d(["retrieval", "ndcg@5"]),
        "hallucination_guard_accuracy": _d(["hallucination_guard", "accuracy"]),
        "hallucination_guard_precision": _d(["hallucination_guard", "precision"]),
        "hallucination_guard_recall": _d(["hallucination_guard", "recall"]),
        "hallucination_guard_f1": _d(["hallucination_guard", "f1"]),
        "reranking_latency_mean_ms": _d(["reranking_latency_ms", "mean"]),
    }


async def run() -> dict:
    settings = get_settings()
    embedding_backend: EmbeddingBackend = LocalEmbeddingBackend()
    vector_store = get_vector_store()

    finetuned_path = MODELS_DIR / "finetuned"
    if not finetuned_path.exists():
        print(
            f"ERROR: no fine-tuned checkpoint at {finetuned_path} — run train_reranker.py first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    async with AsyncSessionLocal() as session:
        corpus = await build_corpus(session, vector_store, embedding_backend)
        if corpus.unresolved_markers:
            print(
                "ERROR: unresolved content_markers — fix before trusting any report.",
                file=sys.stderr,
            )
            await teardown_corpus(session, vector_store, corpus)
            raise SystemExit(1)

        try:
            baseline = await _evaluate_one_reranker(
                "baseline",
                BASELINE_RERANKER_MODEL,
                corpus,
                embedding_backend,
                session,
                vector_store,
                settings.rag_min_rerank_score,
            )
            finetuned = await _evaluate_one_reranker(
                "finetuned",
                str(finetuned_path),
                corpus,
                embedding_backend,
                session,
                vector_store,
                settings.rag_min_rerank_score,
            )
        finally:
            await teardown_corpus(session, vector_store, corpus)

    return {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "benchmark": "eval/datasets/knowledge_base_eval.json (full, untouched, 116 queries)",
            "n_queries": 116,
            "embedding_backend": f"local:{settings.local_embedding_model}",
            "rag_min_rerank_score_used_for_both": settings.rag_min_rerank_score,
        },
        "baseline": baseline,
        "finetuned": finetuned,
        "diff_finetuned_minus_baseline": _diff(baseline, finetuned),
        "statistics": _compute_statistics(baseline, finetuned),
    }


def print_summary(report: dict) -> None:
    b, f, d = report["baseline"], report["finetuned"], report["diff_finetuned_minus_baseline"]
    print()
    print("=" * 78)
    print("BASELINE vs FINE-TUNED RERANKER — full 116-query held-out benchmark")
    print("=" * 78)
    header = f"{'metric':<28}{'baseline':>12}{'finetuned':>12}{'diff':>12}"
    print(header)
    print("-" * len(header))
    rows = [
        ("Recall@1", b["retrieval"]["recall@1"], f["retrieval"]["recall@1"], d["recall@1"]),
        ("Recall@5", b["retrieval"]["recall@5"], f["retrieval"]["recall@5"], d["recall@5"]),
        ("Recall@10", b["retrieval"]["recall@10"], f["retrieval"]["recall@10"], d["recall@10"]),
        ("MRR", b["retrieval"]["mrr"], f["retrieval"]["mrr"], d["mrr"]),
        ("NDCG@5", b["retrieval"]["ndcg@5"], f["retrieval"]["ndcg@5"], d["ndcg@5"]),
        (
            "Guard accuracy",
            b["hallucination_guard"]["accuracy"],
            f["hallucination_guard"]["accuracy"],
            d["hallucination_guard_accuracy"],
        ),
        (
            "Guard precision",
            b["hallucination_guard"]["precision"],
            f["hallucination_guard"]["precision"],
            d["hallucination_guard_precision"],
        ),
        (
            "Guard recall",
            b["hallucination_guard"]["recall"],
            f["hallucination_guard"]["recall"],
            d["hallucination_guard_recall"],
        ),
        (
            "Guard F1",
            b["hallucination_guard"]["f1"],
            f["hallucination_guard"]["f1"],
            d["hallucination_guard_f1"],
        ),
    ]
    for name, bv, fv, dv in rows:
        print(f"{name:<28}{bv:>12.4f}{fv:>12.4f}{dv:>+12.4f}")
    print()
    print(
        f"{'Rerank latency mean (ms)':<28}"
        f"{b['reranking_latency_ms']['mean']:>12.2f}"
        f"{f['reranking_latency_ms']['mean']:>12.2f}"
        f"{d['reranking_latency_mean_ms']:>+12.2f}"
    )
    print(
        f"{'Rerank latency p95 (ms)':<28}"
        f"{b['reranking_latency_ms']['p95']:>12.2f}"
        f"{f['reranking_latency_ms']['p95']:>12.2f}"
    )
    print()
    print("Confusion matrices:")
    print(f"  baseline : {b['hallucination_guard']['confusion_matrix']}")
    print(f"  finetuned: {f['hallucination_guard']['confusion_matrix']}")
    print("=" * 78)

    s = report["statistics"]
    print()
    print("STATISTICAL ANALYSIS (paired, same 116 queries)")
    print("-" * 78)
    gm = s["hallucination_guard_mcnemar"]
    print(
        f"Guard McNemar's exact test: b={gm['b']} c={gm['c']} "
        f"n_discordant={gm['n_discordant']} p={gm['p_value']} "
        f"significant@0.05={gm.get('significant_at_0.05')}"
    )
    rm = s["recall_at_1_mcnemar"]
    print(
        f"Recall@1 McNemar's exact test: b={rm['b']} c={rm['c']} "
        f"n_discordant={rm['n_discordant']} p={rm['p_value']} "
        f"significant@0.05={rm.get('significant_at_0.05')}"
    )
    r_ci = s["recall_at_1_bootstrap_ci"]
    print(
        f"Recall@1 95% bootstrap CI: baseline "
        f"[{r_ci['baseline']['ci_low']}, {r_ci['baseline']['ci_high']}], finetuned "
        f"[{r_ci['finetuned']['ci_low']}, {r_ci['finetuned']['ci_high']}]"
    )
    mrr_ci = s["mrr_bootstrap_ci"]
    print(
        f"MRR 95% bootstrap CI:      baseline "
        f"[{mrr_ci['baseline']['ci_low']}, {mrr_ci['baseline']['ci_high']}], finetuned "
        f"[{mrr_ci['finetuned']['ci_low']}, {mrr_ci['finetuned']['ci_high']}]"
    )
    print("=" * 78)
    print()


def main() -> None:
    report = asyncio.run(run())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"reranker_comparison_{timestamp}.json"
    output_path.write_text(json.dumps(report, indent=2))
    (RESULTS_DIR / "reranker_comparison_latest.json").write_text(json.dumps(report, indent=2))
    print_summary(report)
    print(f"Full report written to {output_path}")


if __name__ == "__main__":
    main()
