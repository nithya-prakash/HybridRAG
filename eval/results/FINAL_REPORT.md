# HybridRAG Evaluation — Final Report

Generated: 2026-09-03T17:30:33.729013+00:00

Every number in this report comes from actually running the scripts in `eval/` against this repository's real retrieval and generation pipeline — see each section for the exact command that reproduces it. Nothing here is estimated or hand-typed.

## Dataset

- **Questions:** 110
- **Documents:** 8
- **Chunks indexed:** 50
- **Answerable / unanswerable:** 99 / 11
- **Question categories:**
  - `single_chunk`: 52 (47.3%)
  - `numerical`: 16 (14.5%)
  - `procedural`: 12 (10.9%)
  - `out_of_corpus`: 11 (10.0%)
  - `cross_document_discriminator`: 6 (5.5%)
  - `terminology_mismatch`: 6 (5.5%)
  - `multi_chunk`: 5 (4.5%)
  - `single_chunk_pdf_page`: 2 (1.8%)

Reproduce: `eval/datasets/knowledge_base_eval.json` (static, no script needed).

## Retrieval

Real local embeddings (`local:BAAI/bge-small-en-v1.5`), real BM25 (Postgres full-text), real cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2 (real, local model)`) — fetch depth `top_k=10`, 99 of 110 labeled queries scored (the rest are the unanswerable set, which has no relevant chunk to score recall against).

| Method | Recall@1 | Recall@5 | Recall@10 | MRR | NDCG@5 | NDCG@10 | Precision@5 |
|---|---|---|---|---|---|---|---|
| Dense only | 0.924 | 0.995 | 1.000 | 0.976 | 0.979 | 0.981 | 0.214 |
| BM25 only | 0.788 | 0.985 | 1.000 | 0.895 | 0.912 | 0.917 | 0.215 |
| Dense + BM25 (naive, no RRF) | 0.924 | 1.000 | 1.000 | 0.977 | 0.980 | 0.980 | 0.216 |
| Dense + BM25 + RRF | 0.904 | 1.000 | 1.000 | 0.970 | 0.976 | 0.976 | 0.216 |
| Dense + BM25 + RRF + Reranker | 0.929 | 1.000 | 1.000 | 0.980 | 0.986 | 0.986 | 0.216 |

Reproduce: `uv run python ../eval/run_eval.py --retrieval-only` (from `backend/`).

## Ablation

What does each pipeline stage actually contribute, on this dataset?

- **RRF vs. naive hybrid (Recall@1):** naive 0.924 → RRF 0.904 (-2.2%)
- **Reranking on top of RRF (Recall@1):** 0.904 → 0.929 (+2.8%)
- **Reranking on top of RRF (MRR):** 0.970 → 0.980 (+1.0%)
- **Full pipeline vs. best single leg (Recall@1):** best of dense/BM25 = 0.924 → full pipeline 0.929

Note: on this dataset the naive (non-RRF) hybrid slightly **outperforms** RRF on Recall@1/MRR before reranking — real result, not a typo. See `eval/RESULTS.md` for the reading: this dataset's individual retrieval legs (especially dense, on real semantic embeddings) are already strong, a regime where RRF's rank-based dampening can trail a simple interleave. The full pipeline (RRF + reranking) still wins overall once the reranker is added.

## Generation

Real generation on a **20-query category-stratified sample** (chat backend `ollama:llama3.2:3b`, judge `ollama:llama3.2:3b (same model as generation — a small local model judging its own output; see eval/RESULTS.md's caveat on this)`) — see Limitations for why this is a sample rather than the full dataset.

| Metric | All queries | Answered only |
|---|---|---|
| Faithfulness (groundedness) | 0.645 | 0.719 |
| Relevance | 0.947 | 0.938 |
| Answer correctness | 0.763 | 0.719 |

- **Citation correctness:** 0.788 (n=11 answers with ≥1 citation)
- **Citation completeness:** 0.656 (n=16 queries with a labeled-relevant chunk)
- **Abstention correct:** 17/20

Judge model/prompt: see `eval/metrics/generation_metrics.py` (`FAITHFULNESS_RUBRIC`, `RELEVANCE_RUBRIC`, `ANSWER_CORRECTNESS_RUBRIC`) — the judge is the same chat backend as generation (see Limitations on shared-blind-spot risk). These are LLM-as-judge scores, not ground truth.

Reproduce: `uv run python ../eval/run_eval.py --query-ids <ids>` (from `backend/`, needs the `ollama` service or a real `OPENAI_API_KEY` — see `eval/RESULTS.md`).

## Hallucination Guard

Full dataset (110 queries: 11 unanswerable, 99 answerable), based entirely on real retrieval + the real cross-encoder reranker's score vs. `rag_min_rerank_score=-3.0` — no LLM generation call involved in the guard's decision itself.

- **Accuracy:** 95.5%
- **Precision:** 80.0%
- **Recall:** 72.7%
- **F1:** 0.762
- **Specificity:** 98.0%

Confusion matrix (positive = guard declines to answer):

| | Declined | Answered |
|---|---|---|
| **Unanswerable (should decline)** | TP=8 | FN=3 |
| **Answerable (should answer)** | FP=2 | TN=97 |

Reproduce: `uv run python ../eval/evaluate_hallucination.py` (from `backend/`).

## Performance (latency)

60 real retrieval calls, 5 real generation calls (chat backend: ollama:llama3.2:3b).

| Stage | Mean (ms) | P50 | P95 | P99 |
|---|---|---|---|---|
| Retrieval (dense+BM25+fuse) | 7.8 | 6.3 | 14.8 | 29.0 |
| Reranking | 1078.8 | 1035.2 | 1399.2 | 1947.3 |
| Retrieval+rerank total | 1222.5 | 1195.0 | 1542.3 | 2115.3 |
| Generation | 70044.2 | 69194.6 | 101933.9 | 101933.9 |
| End-to-end | 71363.5 | 70674.8 | 103305.6 | 103305.6 |

Reproduce: `uv run python ../eval/benchmark_latency.py` (from `backend/`).

## Testing

- **Total tests:** 209
- **Passed:** 209
- **Failed:** 0
- **Skipped:** 0
- **Code coverage:** 97%

Reproduce: `uv run pytest --cov --cov-report=term-missing` (from `backend/`).

## Limitations

- **Dataset size and provenance:** 110 labeled questions over 8 documents — 3 are this project's original fixture docs, 5 are additional synthetic fixture documents written specifically to grow this eval corpus with genuinely new, non-redundant material (not real company data). 110 is a deliberate stopping point, not the ~200-250 originally targeted — see the project history for the tradeoff (more real evaluation breadth vs. more labeled questions on the same corpus).
- **Synthetic questions, human-designed ground truth:** questions and reference answers were authored against the actual document text (every `content_marker` is a verbatim substring, verified by the harness itself before any report is trusted), not generated-then-assumed-correct — but they were still authored by one person, not independently reviewed.
- **LLM-as-judge limitations:** faithfulness/relevance/answer-correctness scores come from the same small local model (`llama3.2:3b`) that also generated the answers being judged — a real, known limitation (shared blind spots), not a synthetic-mode artifact. Treat these as a consistent, reproducible signal, not ground truth.
- **Generation sample size:** the generation/groundedness numbers above come from a real but partial, category-stratified sample (not the full 110), because local CPU generation is slow (~1-6 minutes per query across generation + 3 judge calls) — see `eval/RESULTS.md` for the exact sample and why.
- **Model dependency:** retrieval numbers reflect `BAAI/bge-small-en-v1.5` (embeddings) and `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker); generation numbers reflect `llama3.2:3b`. Different models would produce different numbers — these are not universal claims about hybrid RAG.
- **Local hardware:** all numbers were measured on a single development machine under real but not isolated conditions (other local processes competing for CPU/memory at times) — latency numbers in particular should be read as directional, not a clean-room benchmark.
- **Evaluation bias:** the same person who built the system also built the eval dataset and thresholds (e.g. `rag_min_rerank_score`, calibrated against this exact dataset's rerank score distribution) — there is no held-out, independently-authored test set.
