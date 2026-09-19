# Evaluation framework

A reproducible evaluation & benchmarking suite for this project's hybrid
retrieval + generation pipeline. Every number this framework produces comes
from actually running these scripts against the real pipeline — nothing is
hand-typed or estimated. See `RESULTS.md` for narrative results and
`results/FINAL_REPORT.md` for the latest full report.

## Layout

```
eval/
├── datasets/
│   ├── documents/                 fixture documents the labeled queries are written against
│   └── knowledge_base_eval.json   110 labeled queries: question, category, ground-truth
│                                  chunks (as verbatim content_markers), reference answer,
│                                  answerable flag
├── metrics/
│   ├── retrieval_metrics.py       Recall@K, Precision@K, MRR, NDCG@K
│   └── generation_metrics.py      LLM-as-judge faithfulness/relevance/answer-correctness,
│                                  deterministic citation correctness/completeness
├── corpus.py                      indexes the fixture documents through the real parsing/
│                                  chunking/embedding pipeline into a throwaway eval user,
│                                  resolves each query's content_marker to real chunk ids
├── fakes.py                       deterministic offline stand-ins used only when no real
│                                  embedding/chat backend is available (see "Modes" below)
├── run_eval.py                    retrieval (5 configurations) + generation/groundedness
│                                  evaluation
├── evaluate_hallucination.py      hallucination guard confusion matrix (TP/TN/FP/FN,
│                                  accuracy/precision/recall/F1) — no LLM call needed
├── benchmark_latency.py           real per-stage latency (retrieval/rerank/generation/
│                                  end-to-end), mean/p50/p95/p99 over many repetitions
├── run_all.py                     runs everything above in one command, writes
│                                  results/final_report.json
├── generate_final_report.py       renders final_report.json into results/FINAL_REPORT.md
├── results/                       every run's JSON output (timestamped + a `*_latest.json`
│                                  per phase)
├── reranker_training/              fine-tunes the cross-encoder reranker on this corpus —
│                                  see README.md's reranker fine-tuning section and this
│                                  directory's own scripts' docstrings for the full story
│   ├── generate_training_data.py  deterministic query/positive/hard-negative dataset
│                                  generation, document-level train/calibration split
│   ├── train_reranker.py          fine-tunes cross-encoder/ms-marco-MiniLM-L-6-v2 via
│                                  sentence-transformers' CrossEncoderTrainer
│   ├── evaluate_baseline_vs_finetuned.py   baseline vs. fine-tuned on the full, untouched
│                                  116-query benchmark
│   ├── calibrate_threshold.py     checks whether rag_min_rerank_score needs recalibrating
│                                  for the fine-tuned model, using the calibration split only
│   ├── data/                      generated train/calibration examples (gitignored —
│                                  regenerable) + dataset_stats.json (committed)
│   ├── models/                    the fine-tuned checkpoint (gitignored — binary weights)
│                                  + training_metadata.json (committed)
│   └── tests/                     unit tests for the deterministic parts of dataset
│                                  generation
└── tests/                         unit tests for the metrics math itself
```

## The one command

From `backend/` (needs `uv sync --dev`, migrations applied, and a real Postgres + Qdrant —
see the repo root README's Quickstart):

```bash
uv run python ../eval/run_all.py
uv run python ../eval/generate_final_report.py
```

This runs dataset stats, retrieval (5 configurations), the hallucination guard evaluation,
latency benchmarking, and the backend test suite + coverage — everything that needs no real
LLM generation call, which is fast (a few minutes). Generation/groundedness evaluation is
**opt-in** (`--generation-sample N`) because a real generation call is slow on local CPU
hardware (Ollama) or costs money (OpenAI); by default `run_all.py` reuses
`results/generation_latest.json` from a prior run if one exists, or skips that section with
a clear note otherwise.

```bash
uv run python ../eval/run_all.py --generation-sample 20
```

Each phase is also independently runnable (and is what `run_all.py` actually shells out to
— see its docstring):

```bash
uv run python ../eval/run_eval.py --retrieval-only          # retrieval only, no LLM calls
uv run python ../eval/run_eval.py --query-ids q01,q22,q35   # generation on a specific sample
uv run python ../eval/evaluate_hallucination.py             # hallucination guard confusion matrix
uv run python ../eval/benchmark_latency.py                  # latency percentiles
uv run pytest --cov --cov-report=term-missing               # test suite + coverage
```

## Reranker fine-tuning

Fine-tunes the cross-encoder reranker on this project's own corpus, then evaluates it
against the frozen baseline on the full 116-query held-out benchmark. See README.md's
"Reranker fine-tuning" section for the real results and full write-up.

```bash
uv run python ../eval/reranker_training/generate_training_data.py
uv run python ../eval/reranker_training/train_reranker.py
uv run python ../eval/reranker_training/evaluate_baseline_vs_finetuned.py
uv run python ../eval/reranker_training/calibrate_threshold.py
```

## Modes: what's real and what isn't

The embedding backend and the chat/judge backend are each selected independently based on
what's actually reachable right now, not just which environment variables are set:

| Backend | Real when | Falls back to |
|---|---|---|
| Embeddings | `EMBEDDING_PROVIDER=local` (always — no network dependency) or `=openai` with a working key | Deterministic hashing-trick bag-of-words (`eval/fakes.py`) |
| Chat/judge | `CHAT_PROVIDER=ollama` and the `ollama` service responds, or `=openai` with a working key | Deterministic lexical-overlap extractive stand-in |

Every report's `meta.embedding_mode`/`meta.chat_mode` fields (and the printed banner) say
plainly which combination produced that run's numbers — a "local embeddings + synthetic
chat" run is real for retrieval and synthetic for generation, and the two halves are not
interchangeable with a fully-real or fully-synthetic run. See `RESULTS.md` for the full
history of what each mode has and hasn't demonstrated.

## Ground truth

Every labeled query's `relevant_chunks` is a `content_marker`: a verbatim substring of the
real source document, not a precomputed chunk id (chunk ids don't exist until indexing
happens). `corpus.py` resolves markers to real chunk ids after indexing and refuses to
produce a report if any marker fails to resolve — a dataset/parsing mismatch is a bug to
fix, not a query to silently drop.
