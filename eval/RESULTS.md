# Evaluation results

This documents the most recent `eval/run_eval.py` run against the labeled
dataset in `eval/datasets/knowledge_base_eval.json` (21 queries over 3
fixture documents: an employee handbook, an engineering-practices doc, and a
4-page product FAQ PDF — see that file's `"description"` for the query mix).

**Run:** 2026-08-18T17:34:07Z · mode: **SYNTHETIC** (see below) · 21 queries
(20 scored for retrieval; 1 deliberately out-of-corpus). A first run
(2026-08-18T14:36:31Z) surfaced a real calibration bug in
`rag_min_rerank_score`; it was fixed and this is the re-verified run after
that fix — see § Abstention correctness for the full story.

## Mode: what was real and what wasn't in this run

No `OPENAI_API_KEY` is configured in this environment, so the harness ran in
its synthetic fallback (see `eval/run_eval.py::detect_mode` and
`eval/fakes.py`) rather than failing outright:

| Component | This run | Notes |
|---|---|---|
| Reranker | **Real** — local cross-encoder (`ms-marco-MiniLM-L-6-v2`) | No API key needed; same model production uses. |
| BM25 / Postgres FTS | **Real** | No API key needed; same code path production uses. |
| Dense embeddings | Synthetic — hashing-trick bag-of-words | Captures literal word overlap only, no semantic/paraphrase generalization. |
| Answer generation | Synthetic — extractive stand-in | Picks the most-overlapping source(s) and stitches their opening sentence(s) with citation markers; not an LLM. |
| LLM-as-judge | Synthetic — lexical-overlap heuristic | Not an LLM; see limitations below. |

**Bottom line: the retrieval numbers below are meaningfully real for BM25
and reranking, and a lower-bound/pessimistic proxy for dense retrieval. The
generation numbers (faithfulness/relevance) are mechanics validation only —
they exercise the harness's plumbing, not real system quality.** To get real
generation numbers, set `OPENAI_API_KEY` in `backend/.env` (or as a CI
secret for the `eval` GitHub Actions job) and rerun; no code changes are
needed, the harness switches backends automatically.

To reproduce, from `backend/`:

```bash
uv run python ../eval/run_eval.py
```

## Retrieval: Recall@K, MRR, NDCG@5

All three variants are evaluated at equal fetch depth (top_k=10) so the
numbers are directly comparable.

| Variant | Recall@3 | Recall@5 | MRR | NDCG@5 |
|---|---|---|---|---|
| Dense only (synthetic embeddings) | 0.900 | 1.000 | 0.925 | 0.943 |
| BM25 only (real) | 1.000 | 1.000 | 0.975 | 0.982 |
| Hybrid (RRF) + reranked (real reranker) | **1.000** | **1.000** | **1.000** | **1.000** |

**What this demonstrates:** hybrid+rerank reaches a perfect score across
every metric, matching or exceeding BM25-only despite the dense leg running
on a weak, purely-lexical synthetic embedding. The real cross-encoder
reranker fully compensates for a degraded first-stage dense retriever here —
concrete evidence that reranking earns its latency cost (see the per-query
`rerank_ms` timings in the run log, ~600–1100ms per query on CPU) rather than
just a theoretical justification. This isn't a fair test of *dense* retrieval
quality in isolation (that requires a real embedding model — rerun with a
real API key to get that number), but it *is* a fair, real test of whether
fusion+reranking adds value on top of whatever the dense leg contributes,
which is the actual production configuration.

## Generation: faithfulness and answer relevance

| Metric | All 21 queries | Answered only (20, excludes the 1 correct decline) |
|---|---|---|
| Faithfulness | 0.714 | 0.725 |
| Relevance | 0.060 | 0.063 |

**Faithfulness ≈ 0.7 in synthetic mode is expected and not very informative**:
the synthetic answer generator is *extractive* (it literally copies
sentences from the retrieved context), so a word-overlap-based faithfulness
proxy naturally scores it in the "mostly grounded" range — this mainly
confirms the scoring pipeline runs correctly, not that a real generation
model would score similarly.

**Relevance ≈ 0.06 in synthetic mode is a known, honest weakness of the
synthetic judge, not a real signal.** The heuristic scores relevance by
literal word overlap between the answer and the *question*. A correct,
on-topic answer routinely shares very few literal words with the question it
answers — e.g. for q13 ("Do on-call engineers get any extra time off for
carrying the pager?"), the correct, on-topic retrieved content ("Each
on-call week is compensated with an additional day of PTO...") shares almost
no vocabulary with the question despite directly answering it. A real
LLM-as-judge (the intended, documented approach — see
`eval/metrics/generation_metrics.py`'s module docstring) reasons about
meaning, not surface tokens, and would not have this failure mode. **Do not
read the 0.06 relevance number as "the system is irrelevant 94% of the
time" — it measures the synthetic judge's blind spot, not the system.**

A second, real (not synthetic-artifact) limitation the synthetic generator
surfaced: its source-selection threshold (within 60% of the best
overlap score) is occasionally too permissive and pulls in a second, only
weakly related source — e.g. q01's synthetic answer correctly states the PTO
policy from source [1], then appends an unrelated PDF FAQ line ("How many
team members can I add? [6]") from a source that cleared the threshold on
weak overlap alone. This is purely a synthetic-generator artifact (the real
system's LLM-based generation, instructed to answer only the question asked,
was not exercised in this run) but is worth knowing if synthetic mode is
used for anything beyond harness validation.

## Abstention correctness: 21/21 (after a recalibration this run found and fixed)

The dataset's one deliberately out-of-corpus query (q21, "What is the
company's policy on parental leave?") was correctly declined, and all 20
in-corpus queries were answered. That's a change from the first run of this
harness (2026-08-18T14:36:31Z), which scored 20/21: q09 ("What's the
recommended maximum size for a single pull request?") retrieved the exactly
correct chunk at rank 1, but the system declined to answer anyway. That was
a real finding, independent of synthetic mode, because it came entirely from
the real cross-encoder reranker's score:

```
chunk 4da5ea35... (the correct chunk)  rerank_score = -1.64  <- best candidate, correct
chunk c81b8df8...                       rerank_score = -9.79
chunk bd279054...                       rerank_score = -11.17
```

`app/core/config.py`'s `rag_min_rerank_score` was `0.0` — documented there as
"a heuristic threshold on an uncalibrated score, not a hard guarantee" — and
treated any candidate scoring below 0.0 as not actually relevant, regardless
of how far ahead it was of the alternatives. The cross-encoder's raw output
is an unbounded classifier logit, not a 0–1 relevance probability, so a query
whose best true match happens to score negatively (as q09's did) triggered a
false decline even though retrieval worked perfectly.

**Recalibration.** Rather than fix the one data point, every query's rerank
score was pulled (not just the failing one) to see the actual distribution:

| | score |
|---|---|
| True positives (19 of 20 in-corpus queries) | +2.54 to +10.25 |
| True positive outlier (q09) | **-1.64** |
| The one labeled negative (q21, out-of-corpus) | **-9.85** |

`rag_min_rerank_score` was moved from `0.0` to **`-3.0`**: it clears q09's
-1.64 with a margin (~1.4) rather than sitting exactly on it, while staying
well clear (~6.8) of the one observed negative example. It was deliberately
*not* set closer to -9.85 just because the gap allows it — one labeled
negative isn't enough evidence to trust that the whole gap down to -9.85 is
actually safe against false positives on other out-of-corpus questions this
dataset doesn't yet cover. Re-running the full harness after the change
confirmed the fix (21/21 abstention correct, q09 now answered) without
regressing anything else: retrieval metrics are identical (the rerank
*ranking* didn't change, only the accept/decline threshold), and the
existing test suite's own decline test (`test_ask_declines_when_no_relevant_context`,
which asks an unrelated real question against an unrelated real corpus and
depends on the real reranker scoring it low) still passes — that query's
real score is well below -3.0, so the new threshold doesn't loosen it into a
false answer.

This is exactly the kind of calibration work a labeled eval dataset is
for — `rag_min_rerank_score` had been a plausible-sounding default chosen
with no labeled data to check it against; now there's a real distribution
(20 positives, 1 negative) informing it instead.

## Recommendations

1. **Re-run with a real `OPENAI_API_KEY`** before trusting any generation
   number — the synthetic-mode faithfulness/relevance figures above validate
   the harness, not the product.
2. **Grow the number of labeled negative examples.** The -3.0 threshold is
   informed by exactly one out-of-corpus query (-9.85); a handful more,
   spanning different ways a query can be genuinely unanswerable, would
   justify pushing the threshold closer to that negative cluster with actual
   confidence, rather than leaving a wide, conservative margin as this
   recalibration deliberately did.
3. **Expand the dataset as the corpus grows** — 21 queries over 3 small
   documents is enough to exercise the harness and catch this class of
   calibration issue, but is too small to detect subtler regressions (e.g. a
   change that shaves a few points off Recall@5 without zeroing it).
