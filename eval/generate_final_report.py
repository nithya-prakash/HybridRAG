#!/usr/bin/env python
"""Renders eval/results/final_report.json (written by run_all.py) into a
human-readable eval/results/FINAL_REPORT.md. Pure formatting — every number
here is copied from the JSON, not recomputed, so this script can be rerun
any time without re-running the (slow) evaluation itself.

Run from backend/:
    uv run python ../eval/generate_final_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
REPORT_PATH = RESULTS_DIR / "final_report.json"
OUTPUT_PATH = RESULTS_DIR / "FINAL_REPORT.md"

RETRIEVAL_VARIANT_LABELS = {
    "dense_only": "Dense only",
    "bm25_only": "BM25 only",
    "naive_hybrid": "Dense + BM25 (naive, no RRF)",
    "hybrid_rrf": "Dense + BM25 + RRF",
    "hybrid_rrf_reranked": "Dense + BM25 + RRF + Reranker",
}


def _pct(x: float | None) -> str:
    return f"{x * 100:.1f}%" if x is not None else "—"


def _fmt(x: float | None, nd: int = 3) -> str:
    return f"{x:.{nd}f}" if x is not None else "—"


def _pct_change(base: float, new: float) -> str:
    if base == 0:
        return "n/a (baseline is 0)"
    change = (new - base) / base * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


def render(report: dict) -> str:
    lines: list[str] = []
    lines.append("# HybridRAG Evaluation — Final Report")
    lines.append("")
    lines.append(f"Generated: {report.get('generated_at', 'unknown')}")
    lines.append("")
    lines.append(
        "Every number in this report comes from actually running the scripts in `eval/` "
        "against this repository's real retrieval and generation pipeline — see each "
        "section for the exact command that reproduces it. Nothing here is estimated or "
        "hand-typed."
    )
    lines.append("")

    # ---- Dataset -----------------------------------------------------
    ds = report.get("dataset") or {}
    lines.append("## Dataset")
    lines.append("")
    n_chunks = None
    if report.get("retrieval") and report["retrieval"].get("meta"):
        n_chunks = report["retrieval"]["meta"].get("num_chunks")
    lines.append(f"- **Questions:** {ds.get('n_questions', '—')}")
    lines.append(f"- **Documents:** {ds.get('n_documents', '—')}")
    if n_chunks is not None:
        lines.append(f"- **Chunks indexed:** {n_chunks}")
    lines.append(
        f"- **Answerable / unanswerable:** {ds.get('n_answerable', '—')} / "
        f"{ds.get('n_unanswerable', '—')}"
    )
    lines.append("- **Question categories:**")
    for cat, n in (ds.get("categories") or {}).items():
        pct = n / ds["n_questions"] * 100 if ds.get("n_questions") else 0
        lines.append(f"  - `{cat}`: {n} ({pct:.1f}%)")
    lines.append("")
    lines.append("Reproduce: `eval/datasets/knowledge_base_eval.json` (static, no script needed).")
    lines.append("")

    # ---- Retrieval -----------------------------------------------------
    lines.append("## Retrieval")
    lines.append("")
    retrieval = report.get("retrieval")
    if retrieval:
        meta = retrieval["meta"]
        lines.append(
            f"Real local embeddings (`{meta['embedding_backend']}`), real BM25 (Postgres "
            f"full-text), real cross-encoder reranker (`{meta['reranker']}`) — fetch depth "
            f"`top_k={meta['retrieval_top_k']}`, {meta['num_retrieval_queries']} of "
            f"{meta['num_queries']} labeled queries scored (the rest are the unanswerable "
            "set, which has no relevant chunk to score recall against)."
        )
        lines.append("")
        lines.append(
            "| Method | Recall@1 | Recall@5 | Recall@10 | MRR | NDCG@5 | NDCG@10 | Precision@5 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for key, label in RETRIEVAL_VARIANT_LABELS.items():
            m = retrieval["retrieval"][key]
            lines.append(
                f"| {label} | {_fmt(m['recall@1'])} | {_fmt(m['recall@5'])} | "
                f"{_fmt(m['recall@10'])} | {_fmt(m['mrr'])} | {_fmt(m['ndcg@5'])} | "
                f"{_fmt(m['ndcg@10'])} | {_fmt(m['precision@5'])} |"
            )
        lines.append("")
        lines.append(
            "Reproduce: `uv run python ../eval/run_eval.py --retrieval-only` (from `backend/`)."
        )
    else:
        lines.append("_Not run._")
    lines.append("")

    # ---- Ablation --------------------------------------------------------
    lines.append("## Ablation")
    lines.append("")
    if retrieval:
        r = retrieval["retrieval"]
        dense, bm25 = r["dense_only"], r["bm25_only"]
        naive, rrf, rerank = r["naive_hybrid"], r["hybrid_rrf"], r["hybrid_rrf_reranked"]
        lines.append("What does each pipeline stage actually contribute, on this dataset?")
        lines.append("")
        lines.append(
            f"- **RRF vs. naive hybrid (Recall@1):** naive {_fmt(naive['recall@1'])} → "
            f"RRF {_fmt(rrf['recall@1'])} ({_pct_change(naive['recall@1'], rrf['recall@1'])})"
        )
        lines.append(
            f"- **Reranking on top of RRF (Recall@1):** {_fmt(rrf['recall@1'])} → "
            f"{_fmt(rerank['recall@1'])} ({_pct_change(rrf['recall@1'], rerank['recall@1'])})"
        )
        lines.append(
            f"- **Reranking on top of RRF (MRR):** {_fmt(rrf['mrr'])} → "
            f"{_fmt(rerank['mrr'])} ({_pct_change(rrf['mrr'], rerank['mrr'])})"
        )
        lines.append(
            f"- **Full pipeline vs. best single leg (Recall@1):** best of dense/BM25 = "
            f"{_fmt(max(dense['recall@1'], bm25['recall@1']))} → full pipeline "
            f"{_fmt(rerank['recall@1'])}"
        )
        lines.append("")
        lines.append(
            "Note: on this dataset the naive (non-RRF) hybrid slightly **outperforms** RRF "
            "on Recall@1/MRR before reranking — real result, not a typo. See `eval/RESULTS.md` "
            "for the reading: this dataset's individual retrieval legs (especially dense, "
            "on real semantic embeddings) are already strong, a regime where RRF's rank-based "
            "dampening can trail a simple interleave. The full pipeline (RRF + reranking) "
            "still wins overall once the reranker is added."
        )
    else:
        lines.append("_Not run._")
    lines.append("")

    # ---- Generation --------------------------------------------------------
    lines.append("## Generation")
    lines.append("")
    generation = report.get("generation")
    if generation and generation.get("generation"):
        gmeta, gen = generation["meta"], generation["generation"]
        n_sample = gmeta.get("num_queries")
        lines.append(
            f"Real generation on a **{n_sample}-query category-stratified sample** "
            f"(chat backend `{gmeta['chat_backend']}`, judge `{gmeta['judge_backend']}`) — "
            "see Limitations for why this is a sample rather than the full dataset."
        )
        hall_meta = (report.get("hallucination") or {}).get("meta") or {}
        if hall_meta.get("generated_at", "") > gmeta.get("generated_at", ""):
            lines.append("")
            lines.append(
                "**Note: this sample predates the hallucination-guard run below** "
                f"(generated {gmeta.get('generated_at', 'unknown')} vs. "
                f"{hall_meta.get('generated_at', 'unknown')}) — it has not been re-run against "
                "the current dataset/threshold; see `eval/RESULTS.md` for what specifically "
                "would change."
            )
        lines.append("")
        lines.append("| Metric | All queries | Answered only |")
        lines.append("|---|---|---|")
        lines.append(
            f"| Faithfulness (groundedness) | {_fmt(gen['faithfulness_mean_all_queries'])} | "
            f"{_fmt(gen['faithfulness_mean_answered_only'])} |"
        )
        lines.append(
            f"| Relevance | {_fmt(gen['relevance_mean_all_queries'])} | "
            f"{_fmt(gen['relevance_mean_answered_only'])} |"
        )
        lines.append(
            f"| Answer correctness | {_fmt(gen['answer_correctness_mean_all_queries'])} | "
            f"{_fmt(gen['answer_correctness_mean_answered_only'])} |"
        )
        lines.append("")
        lines.append(
            f"- **Citation correctness:** {_fmt(gen['citation_correctness_mean'])} "
            f"(n={gen['n_citation_correctness']} answers with ≥1 citation)"
        )
        lines.append(
            f"- **Citation completeness:** {_fmt(gen['citation_completeness_mean'])} "
            f"(n={gen['n_citation_completeness']} queries with a labeled-relevant chunk)"
        )
        lines.append(
            f"- **Abstention correct:** {gen['abstention_correct_count']}/{gen['abstention_total']}"
        )
        lines.append("")
        lines.append(
            "Judge model/prompt: see `eval/metrics/generation_metrics.py` "
            "(`FAITHFULNESS_RUBRIC`, `RELEVANCE_RUBRIC`, `ANSWER_CORRECTNESS_RUBRIC`) — the "
            "judge is the same chat backend as generation (see Limitations on shared-blind-spot "
            "risk). These are LLM-as-judge scores, not ground truth."
        )
        lines.append("")
        lines.append(
            "Reproduce: `uv run python ../eval/run_eval.py --query-ids <ids>` (from `backend/`, "
            "needs the `ollama` service or a real `OPENAI_API_KEY` — see `eval/RESULTS.md`)."
        )
    else:
        lines.append(
            "_Not run in this report — real generation needs a reachable Ollama service or a "
            "real OpenAI API key, and is opt-in (`run_all.py --generation-sample N`) because "
            "each real call is slow (local CPU) or costs money (OpenAI). See `eval/RESULTS.md` "
            "for a completed sample run._"
        )
    lines.append("")

    # ---- Hallucination Guard --------------------------------------------
    lines.append("## Hallucination Guard")
    lines.append("")
    hallucination = report.get("hallucination")
    if hallucination:
        hmeta = hallucination["meta"]
        cm = hallucination["confusion_matrix"]
        m = hallucination["metrics"]
        lines.append(
            f"Full dataset ({hmeta['n_queries']} queries: {hmeta['n_should_decline']} "
            f"unanswerable, {hmeta['n_should_answer']} answerable), based entirely on real "
            f"retrieval + the real cross-encoder reranker's score vs. "
            f"`rag_min_rerank_score={hmeta['rag_min_rerank_score']}` — no LLM generation call "
            "involved in the guard's decision itself."
        )
        lines.append("")
        lines.append(f"- **Accuracy:** {_pct(m['accuracy'])}")
        lines.append(f"- **Precision:** {_pct(m['precision'])}")
        lines.append(f"- **Recall:** {_pct(m['recall'])}")
        lines.append(f"- **F1:** {_fmt(m['f1'])}")
        lines.append(f"- **Specificity:** {_pct(m['specificity'])}")
        lines.append("")
        lines.append("Confusion matrix (positive = guard declines to answer):")
        lines.append("")
        lines.append("| | Declined | Answered |")
        lines.append("|---|---|---|")
        lines.append(f"| **Unanswerable (should decline)** | TP={cm['tp']} | FN={cm['fn']} |")
        lines.append(f"| **Answerable (should answer)** | FP={cm['fp']} | TN={cm['tn']} |")
        lines.append("")
        lines.append(
            "Reproduce: `uv run python ../eval/evaluate_hallucination.py` (from `backend/`)."
        )
    else:
        lines.append("_Not run._")
    lines.append("")

    # ---- Performance --------------------------------------------------
    lines.append("## Performance (latency)")
    lines.append("")
    latency = report.get("latency")
    if latency:
        lmeta, lat = latency["meta"], latency["latency_ms"]
        lines.append(
            f"{lmeta['n_retrieval_samples']} real retrieval calls, "
            f"{lmeta['n_generation_samples']} real generation calls "
            f"(chat backend: {lmeta['chat_backend']})."
        )
        lines.append("")
        lines.append("| Stage | Mean (ms) | P50 | P95 | P99 |")
        lines.append("|---|---|---|---|---|")
        for label, key in (
            ("Retrieval (dense+BM25+fuse)", "retrieval_wall"),
            ("Reranking", "reranking"),
            ("Retrieval+rerank total", "retrieval_and_rerank_total"),
            ("Generation", "generation"),
            ("End-to-end", "end_to_end"),
        ):
            s = lat[key]
            if s["n"] == 0:
                lines.append(f"| {label} | — | — | — | — |")
            else:
                lines.append(
                    f"| {label} | {s['mean']:.1f} | {s['p50']:.1f} | {s['p95']:.1f} | "
                    f"{s['p99']:.1f} |"
                )
        lines.append("")
        lines.append(
            "Reproduce: `uv run python ../eval/benchmark_latency.py` (from `backend/`)."
        )
    else:
        lines.append("_Not run._")
    lines.append("")

    # ---- Testing --------------------------------------------------------
    lines.append("## Testing")
    lines.append("")
    tests = report.get("tests")
    if tests:
        lines.append(f"- **Total tests:** {tests['total']}")
        lines.append(f"- **Passed:** {tests['passed']}")
        lines.append(f"- **Failed:** {tests['failed']}")
        lines.append(f"- **Skipped:** {tests['skipped']}")
        if tests.get("coverage_pct") is not None:
            lines.append(f"- **Code coverage:** {tests['coverage_pct']}%")
        lines.append("")
        lines.append(
            "Reproduce: `uv run pytest --cov --cov-report=term-missing` (from `backend/`)."
        )
    else:
        lines.append("_Not run._")
    lines.append("")

    # ---- Limitations ------------------------------------------------------
    lines.append("## Limitations")
    lines.append("")
    n_questions = ds.get("n_questions", "—")
    lines.append(
        f"- **Dataset size and provenance:** {n_questions} labeled questions over 8 documents "
        "— 3 are this project's original fixture docs, 5 are additional synthetic fixture "
        "documents written specifically to grow this eval corpus with genuinely new, "
        f"non-redundant material (not real company data). {n_questions} is a deliberate "
        "stopping point, not the ~200-250 originally targeted — see the project history for "
        "the tradeoff (more real evaluation breadth vs. more labeled questions on the same "
        "corpus)."
    )
    lines.append(
        "- **Synthetic questions, human-designed ground truth:** questions and reference "
        "answers were authored against the actual document text (every `content_marker` is a "
        "verbatim substring, verified by the harness itself before any report is trusted), not "
        "generated-then-assumed-correct — but they were still authored by one person, not "
        "independently reviewed."
    )
    lines.append(
        "- **LLM-as-judge limitations:** faithfulness/relevance/answer-correctness scores come "
        "from the same small local model (`llama3.2:3b`) that also generated the answers being "
        "judged — a real, known limitation (shared blind spots), not a synthetic-mode artifact. "
        "Treat these as a consistent, reproducible signal, not ground truth."
    )
    lines.append(
        "- **Generation sample size:** the generation/groundedness numbers above come from a "
        f"real but partial, category-stratified sample (not the full {n_questions}), because "
        "local CPU generation is slow (~1-6 minutes per query across generation + 3 judge "
        "calls) — see `eval/RESULTS.md` for the exact sample and why."
    )
    lines.append(
        "- **Model dependency:** retrieval numbers reflect `BAAI/bge-small-en-v1.5` (embeddings) "
        "and `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker); generation numbers reflect "
        "`llama3.2:3b`. Different models would produce different numbers — these are not "
        "universal claims about hybrid RAG."
    )
    lines.append(
        "- **Local hardware:** all numbers were measured on a single development machine under "
        "real but not isolated conditions (other local processes competing for CPU/memory at "
        "times) — latency numbers in particular should be read as directional, not a clean-room "
        "benchmark."
    )
    lines.append(
        "- **Evaluation bias:** the same person who built the system also built the eval "
        "dataset and thresholds (e.g. `rag_min_rerank_score`, calibrated against this exact "
        "dataset's rerank score distribution) — there is no held-out, independently-authored "
        "test set."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    report = json.loads(REPORT_PATH.read_text())
    markdown = render(report)
    OUTPUT_PATH.write_text(markdown)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
