# RAG Knowledge Assistant

**[Live demo →](https://hybridrag-nithya-prakash.vercel.app)** (backend is on Render's free
tier — the first request after a period of inactivity may take 30-50s to wake up)

A production-grade, multi-user RAG (Retrieval-Augmented Generation) knowledge assistant: upload
documents, ask questions about them in a chat interface, and get answers grounded in your own
content with inline citations back to the exact source passage — not a generic LLM chat wrapper.

Built to demonstrate production engineering judgment: multi-tenant isolation, structure-aware
document parsing, hybrid dense+keyword retrieval with reciprocal rank fusion and cross-encoder
reranking, two layers of hallucination mitigation, rate limiting and security hardening, a
labeled retrieval/generation evaluation harness, and a deployable production configuration.
Full design rationale, including mistakes found and fixed along the way, is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/PROGRESS.md`](docs/PROGRESS.md).

![Demo: register, upload a document, and ask a question in the chat UI](docs/screenshots/demo.gif)

*Register → upload → chat, end to end, against a live local instance. Runs entirely on local
models by default (`sentence-transformers` + Ollama) — no API key required. OpenAI is a
supported alternate provider for either or both.*

## What it does

1. **Register / log in** — email + password, JWT access + refresh tokens in `httpOnly` cookies.
2. **Upload a document** (PDF, DOCX, TXT, or Markdown) — parsed into structure-aware chunks
   (respecting headings, not fixed-size windows), embedded, and indexed in the background.
3. **Ask a question in the chat UI** — the system rewrites your question using conversation
   history, retrieves from dense vector search + Postgres BM25, fuses with Reciprocal Rank
   Fusion, reranks with a local cross-encoder, and generates a **streamed, cited answer** — or
   **honestly declines** if nothing retrieved is actually relevant.
4. Every other user's documents are invisible to you — isolation is enforced at the query
   level, not just the UI.

## Screenshots

| Document processing, ready with local embeddings | A grounded, cited answer in the chat UI |
|---|---|
| ![Documents page showing a document in the ready state after local processing](docs/screenshots/05_documents_result.png) | ![Chat UI showing a generated answer with an inline citation chip](docs/screenshots/09_chat_response.png) |

Both captured with `EMBEDDING_PROVIDER=local`, `CHAT_PROVIDER=ollama` — no API key configured.
More frames in [`docs/screenshots/`](docs/screenshots/).

## Architecture

```
                         ┌─────────────┐
                         │   Browser   │
                         └──────┬──────┘
                                │ HTTPS (REST + SSE streaming)
                         ┌──────▼──────┐
                         │  Frontend   │  Next.js (App Router) — auth, upload,
                         │  (Next.js)  │  document list, streaming chat UI
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐         ┌─────────────┐
                    ┌───►│   Backend   │◄───────►│    Redis    │  per-user rate
                    │    │  (FastAPI)  │         │             │  limits + Celery
                    │    └──┬───────┬──┘         └──────┬──────┘  broker/results
                    │       │       │                   │
             ┌──────┴───┐   │  ┌────▼───────┐    ┌──────▼──────┐
             │ Postgres │   │  │   Qdrant   │    │   Celery    │
             │ users ·  │◄──┘  │   chunk    │◄───│   worker    │  parse → chunk →
             │ docs ·   │      │  vectors   │    │             │  embed → index
             │ chunks+  │      └────────────┘    └──────┬──────┘  (async, per upload)
             │ FTS      │                                │
             └──────────┘                         ┌──────▼──────┐
                                                    │   OpenAI    │  embeddings + chat
                                                    │  (or eval's │  completion
                                                    │  synthetic  │
                                                    │  fallback)  │
                                                    └─────────────┘
```

The retrieval + generation pipeline:

```
upload ──► parse ──► structure-aware chunk ──► embed ──► index (Qdrant + Postgres FTS)

question ──► rewrite (uses conversation history) ──┬──► dense search (Qdrant)      ──┐
                                                     └──► BM25 search (Postgres FTS) ──┼──► RRF fusion
                                                                                        │
                          grounded, cited answer  ◄── LLM ◄── prompt ◄── cross-encoder rerank
                          (or an honest decline if the best rerank score is too low)
```

## Quickstart (local, one command)

Requires Docker + Docker Compose v2. No API key needed.

```bash
cp backend/.env.example backend/.env
docker compose -f infra/docker-compose.yml up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (interactive docs at `/docs`)
- Health check: `curl localhost:8000/health`

Register, upload a PDF/DOCX/TXT/MD file, wait for it to finish processing, then ask a question
— you'll get a real generated, cited answer since everything runs on local models by default.

First boot pulls the local chat model (`llama3.2:3b`, ~2GB) once; the embedding model and
reranker are baked into the backend image at build time.

### Local-first by default

`EMBEDDING_PROVIDER=local` (`BAAI/bge-small-en-v1.5`) and `CHAT_PROVIDER=ollama`
(`llama3.2:3b`) are both defaults — the whole pipeline works with zero external API key.
OpenAI is a supported alternate provider for either or both (`EMBEDDING_PROVIDER=openai`,
`CHAT_PROVIDER=openai`), for higher answer quality at the cost of a paid key. See
`docs/ARCHITECTURE.md` § Configurable LLM & embedding providers for the full design.

The test suite and eval harness additionally have their own synthetic fallback, so both stay
fully runnable even with the OpenAI providers configured and no real key present.

## Running tests and the evaluation harness

```bash
cd backend
uv sync --dev
uv run alembic upgrade head
uv run pytest                       # 238 tests, ~98% coverage
uv run pytest --cov --cov-report=term-missing

uv run pytest ../eval/tests                     # eval harness's own unit tests (metrics math)
uv run python ../eval/run_all.py                # retrieval + hallucination guard + latency + tests
uv run python ../eval/run_all.py --generation-sample 20   # + real generation/groundedness eval
uv run python ../eval/generate_final_report.py  # renders results/FINAL_REPORT.md
```

See [`eval/README.md`](eval/README.md) for the full framework layout and every phase's
independent command. A terminal recording against the current 116-query dataset and `-0.6`
threshold is in [`docs/screenshots/eval_demo.gif`](docs/screenshots/eval_demo.gif) — real,
unedited command output (retrieval + hallucination guard), captured from an actual run and
replayed rather than recorded live, since these CPU-bound commands run long enough that live
terminal-recording tooling couldn't reliably stay attached for the full duration on this
machine; both commands are fully deterministic (no LLM calls), so a live re-run would show byte-
identical output.

All of the above needs a real Postgres/Qdrant (and Redis, for the main test suite). The backend
test suite runs on every push in CI; the eval harness job runs the same suite on demand
(`workflow_dispatch`) — see `.github/workflows/ci.yml`.

## Evaluation

The full, reproducible evaluation framework lives in [`eval/`](eval/README.md) — every number
below comes from actually running it against the real pipeline. See
[`eval/RESULTS.md`](eval/RESULTS.md) for the full narrative and
[`eval/results/FINAL_REPORT.md`](eval/results/FINAL_REPORT.md) for the complete report.

**Dataset:** 116 labeled queries, 8 documents, 50 chunks — 99 answerable, 17 deliberately
unanswerable, across 8 question categories.

**Retrieval** (real local embeddings, real BM25, real cross-encoder reranker, full dataset):

| Method | Recall@1 | Recall@5 | MRR | NDCG@5 |
|---|---|---|---|---|
| Dense only | 0.924 | 0.995 | 0.976 | 0.979 |
| BM25 only | 0.798 | 0.975 | 0.900 | 0.912 |
| Dense + BM25 + RRF | 0.904 | 1.000 | 0.970 | 0.976 |
| Dense + BM25 + RRF + Reranker | **0.929** | 1.000 | **0.980** | **0.986** |

**Hallucination guard** (full dataset, real retrieval + reranker score, no LLM call):
**93.1% accuracy**, 76.5% precision, 76.5% recall, F1 0.765 — TP=13, TN=95, FP=4, FN=4
(recalibrated from `-3.3` to `-0.6` via an exhaustive threshold sweep over the full labeled
distribution, after growing the unanswerable-question set from 11 to 17 — see `eval/RESULTS.md`
for the sweep and why the remaining 4 false negatives specifically can't be caught by any
threshold). The remaining recall gap concentrates in questions where the reranker scores
topically-similar-but-wrong content confidently (see `eval/RESULTS.md` for the exact queries
and the second-layer prompt constraint added to address it directly).

**Generation** (real `llama3.2:3b` via Ollama, 20-query stratified sample, re-run against the
current threshold): faithfulness 0.864 and answer correctness 0.727 on answered queries;
citation correctness 0.864, completeness 0.588. Abstention 13/20 — including 3 new false
declines on answerable, strongly-retrieved queries with no guard involvement, traced to
`llama3.2:3b`'s generation not being pinned to a fixed seed/temperature (real run-to-run
sampling variance, not a regression from this recalibration). A live test of the second
mitigation layer against known guard-miss cases showed the generation prompt's own constraint
catching them independently of the guard (see `eval/RESULTS.md` for the full breakdown).

**Latency:** retrieval ~8ms mean, reranking ~1.08s mean (p95 1.4s), generation ~46s mean (down
from ~70s — a real bug meant the local backend never bounded output length; see
`eval/RESULTS.md`) on CPU-bound local `llama3.2:3b` (a hosted API or GPU inference would be
much faster).

**Testing:** 238 tests, 98% code coverage — see `eval/RESULTS.md` for 3 pre-existing,
unrelated local-environment failures found while re-verifying this count.

## Reranker fine-tuning

The reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) had never been adapted to this
project's actual corpus — a general-purpose MS MARCO model reordering candidates from an
8-document internal knowledge base it was never trained on. `eval/reranker_training/`
fine-tunes it on this corpus and evaluates the result against the frozen baseline on the
full, untouched 116-query benchmark — proving or honestly disproving an improvement, not
assuming one. The LLM is untouched throughout; only the cross-encoder is fine-tuned.

**Training data, built without an LLM call and without touching the 116-query benchmark:**
every indexed chunk's nearest section heading becomes a natural-sounding pseudo-query via a
small fixed template set (e.g. a chunk under `## Encryption Standards` → "What are the
encryption standards?"), chosen deterministically per chunk (a stable hash, not Python's
randomized `hash()`) — same chunk, same template, every run. The source chunk is the
positive; **hard negatives are mined from the real production retrieval pipeline** — real
dense + BM25 search, fused with the real RRF implementation, top candidates that aren't the
source chunk. The 8 documents are split 75/25 (6 train / 2 calibration) by a seeded shuffle
so no chunk crosses that boundary, and every generated pseudo-query is checked against the
116 real benchmark queries for exact-string collisions (zero found) before anything is
written — see `eval/reranker_training/generate_training_data.py`.

**Real dataset:** 195 training examples (39 positive, 156 hard negative, from 6 documents/39
chunks) and 55 calibration examples (11 positive, 44 hard negative, from 2 held-out
documents/11 chunks) — see `eval/reranker_training/data/dataset_stats.json`.

**Training:** `sentence-transformers`'s native `CrossEncoderTrainer` +
`BinaryCrossEntropyLoss` (the same loss family the base MS MARCO models were themselves
trained with) — 4 epochs, batch size 16, learning rate 2e-5, seed 42 fixed throughout
(`random`/`numpy`/`torch`/the HF Trainer's own `seed=`), CPU-only. Real training run: 117s
wall time, calibration-split eval loss 0.0671 → 0.0581 → 0.0598 → 0.0622 across the 4
epochs — drops sharply then ticks back up slightly, real evidence of mild overfitting by
epoch 4 on a genuinely tiny dataset, reported as measured rather than only showing the best
epoch. See `eval/reranker_training/models/training_metadata.json` for the full config/log.

**Baseline vs. fine-tuned, on the full, untouched 116-query benchmark, same threshold for
both:**

| Metric | Baseline | Fine-tuned | Diff |
|---|---|---|---|
| Recall@1 | 0.9293 | 0.9293 | +0.0000 |
| Recall@5 | 1.0000 | 1.0000 | +0.0000 |
| MRR | 0.9798 | 0.9798 | +0.0000 |
| NDCG@5 | 0.9864 | 0.9864 | +0.0000 |
| Hallucination-guard precision | 0.7647 | 0.8462 | +0.0815 |
| Hallucination-guard recall | 0.7647 | 0.6471 | −0.1176 |
| Hallucination-guard F1 | 0.7647 | 0.7333 | −0.0314 |
| Reranking latency (mean) | 863.3ms | 983.1ms | +119.8ms |

**Read honestly — this is not an improvement, and isn't reported as one:** retrieval-ranking
quality (Recall@1/5/10, MRR, NDCG@5) is **exactly unchanged** — the fine-tuned model puts
the same chunk at the same rank on every one of the 116 real queries as the baseline does.
The hallucination guard shows a real tradeoff, not a win: precision improved (fewer
answerable questions wrongly declined) at the cost of recall (2 fewer genuinely unanswerable
questions caught), landing F1 slightly *below* the baseline at the current threshold.
Latency: three separate real runs measured gaps of +27ms/+56ms/+120ms on an unchanged
~850-900ms baseline — a consistent direction, a 4x-noisy magnitude, most plausibly real
system-load variance on this shared machine rather than a genuine per-inference cost
difference between two architecturally identical models. The most likely honest explanation
for the null ranking result: 39 positive training examples from a single 8-document corpus
is a genuinely small fine-tuning set — plausibly too small to move a cross-encoder's
relative ranking behavior, while still being enough to measurably shift its absolute score
distribution (see below). **The statement this work supports is: "fine-tuned a cross-encoder
reranker using hard-negative retrieval examples and evaluated it against the frozen MS MARCO
baseline on a held-out benchmark" — not a claim of improvement, because the benchmark doesn't
show one.**

**Statistical analysis, not just observation:** McNemar's exact test (the right tool for two
classifiers paired on the same items — see `eval/reranker_training/paired_stats.py`, no new
dependency added) on the guard's per-query correct/incorrect outcome found the precision/
recall tradeoff above is **not statistically significant** (b=2, c=2, p=1.0 — a perfectly
symmetric split, exactly what pure chance would produce). Recall@1's paired comparison found
literally **zero** disagreement between the two models on any of the 116 queries
(0 discordant pairs). 95% bootstrap CIs on each model's own Recall@1 (`[0.879, 0.970]`) and
MRR (`[0.960, 0.995]`) are identical between baseline and fine-tuned, since every per-query
value is. Full numbers and methodology in `eval/RESULTS.md`.

**Threshold recalibration — checked, not blindly applied:** the fine-tuned model's scores
did shift measurably from the baseline's (median score difference of 2.70 on the calibration
split), and a sweep on that split alone found a much higher candidate threshold (F1 0.989 at
threshold ≈1.63 on that split). This candidate is **not** adopted: `rag_min_rerank_score`
stays at `-0.6`. Three real reasons — the calibration split's label (this chunk vs. a
same-split hard negative *for this specific pseudo-query*) is a narrower proxy than the
benchmark's real target (a genuinely *unanswerable question* — no good chunk anywhere in the
corpus); the split is small (55 examples) and skewed toward negatives (80%), the opposite
imbalance from the real benchmark (85% answerable); and re-running this exact calibration
against an independently-retrained checkpoint moved the recommended threshold from ≈3.34 to
≈1.63 — a large swing for what should be a stable number, itself real evidence this
candidate is fitting the split's specific quirks rather than a generalizable shift. See
`eval/RESULTS.md` for the full reasoning and `eval/reranker_training/calibrate_threshold.py`.

**Integrate it yourself:**

```bash
RERANKER_MODEL=baseline    # default — cross-encoder/ms-marco-MiniLM-L-6-v2, unchanged
RERANKER_MODEL=finetuned   # resolves to RERANKER_FINETUNED_PATH's checkpoint
```

**The fine-tuned model was NOT promoted to production, and this is enforced in code, not
just in this paragraph.** The default (`RERANKER_MODEL` unset, or explicitly `baseline`)
stays the shipped MS MARCO reranker. `app/core/startup_checks.py::validate_production_settings`
actively **rejects** `RERANKER_MODEL=finetuned` outside `local`/`test` environments at
startup — an accidental `RERANKER_MODEL=finetuned` in a deploy config fails loud at boot
with a message pointing back to this section, rather than silently serving a
worse-evaluated model.

**Scope of this finding:** this is a domain-specific evaluation — one small model,
fine-tuned on one 8-document internal corpus, with deterministic heading-derived synthetic
queries. It's evidence about *this* experiment, not a general claim that reranker
fine-tuning doesn't help RAG systems, or that it wouldn't help with a larger, more diverse
training set or real user query logs. See `eval/RESULTS.md` for the full scoping discussion.

**Limitations, stated plainly:** the training corpus is this project's own 8 fixture
documents (50 chunks) — real content, but small; pseudo-queries are heading-derived
templates, not real user questions (a disclosed, deliberate choice — see the confirmed
design decision in this feature's commit history — over depending on this machine's
documented Ollama flakiness for a core reproducibility artifact); the fine-tuned checkpoint
is not baked into the production Docker image (`RERANKER_MODEL=finetuned` is a local/
eval-only path today, not a supported deployment target); and the exact hard-negative
examples mined for training have a real, root-caused, and only partially fixable source of
run-to-run non-determinism (CPU floating-point + approximate vector search) — dataset
composition (counts, splits, zero benchmark leakage) is fully reproducible; the exact
low-ranked negative selected at the margin isn't always. Full diagnosis in
`eval/RESULTS.md`.

**Reproduce exactly:**

```bash
cd backend
uv sync --group training
uv run python ../eval/reranker_training/generate_training_data.py
uv run python ../eval/reranker_training/train_reranker.py
uv run python ../eval/reranker_training/evaluate_baseline_vs_finetuned.py
uv run python ../eval/reranker_training/calibrate_threshold.py
```

## Design decisions

Full depth in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Highlights:

- **Structure-aware chunking, not fixed-size windows.** Chunks never merge across a heading
  boundary, so "Expense Reimbursement" never silently absorbs half of "Code of Conduct."
- **Hybrid retrieval, fused with RRF, then reranked.** Dense and keyword search fail in
  complementary ways; RRF combines both rankings without calibrating incomparable score
  scales, and reranking measurably earns its latency cost (see § Evaluation).
- **Two layers of hallucination mitigation, tested independently.** A hard rerank-score
  threshold in front of generation declines before the LLM is ever called if nothing retrieved
  is relevant enough — recalibrated from an actual observed score distribution three times
  (`0.0`→`-3.0`→`-3.3`→`-0.6`), each time after the eval harness caught real mis-calibration
  or grew the labeled evidence it was calibrated against (see § Evaluation). A second,
  independent layer sits in the generation prompt itself, constrained against inferring a
  specific answer from context that only discusses the topic generally — live-tested against
  the 3 questions the first layer is known to miss, and caught all 3.
- **An evaluation harness that's honest about its own limitations.** `eval/RESULTS.md` states
  plainly which numbers are real versus synthetic-mode mechanics validation.
- **Multi-tenant isolation enforced at the query layer.** Every repository method requires a
  `user_id` and filters on it — no "search everything" method exists to call by accident.
- **Fail fast on insecure production config.** The app refuses to start outside local/test
  with the default JWT secret or a wildcard CORS origin.
- **CSRF defense-in-depth beyond `SameSite`.** A double-submit-cookie token, issued
  non-httpOnly specifically so same-origin JS can echo it back as a header — the property that
  defeats a cross-site attacker, who can't read a victim's cookies at all.

## Deployment

`docker-compose.prod.yml` (repo root): internal services publish no ports, every service has
resource limits and a restart policy, Redis/Qdrant require authentication, and migrations run
automatically before the API/worker start.

```bash
cp .env.prod.example .env    # fill in every value — real secrets, your real domain(s)
docker compose -f docker-compose.prod.yml up -d --build
./scripts/smoke_test.sh      # register -> login -> upload -> ask -> cited answer
```

**Target: a single VM running Docker Compose** — chosen deliberately over Kubernetes or a
managed PaaS for a project at this scope, keeping the deployment story fully inspectable in
this repo rather than "trust the platform." See `docs/ARCHITECTURE.md` § Production deployment
for the full reasoning and what's deferred (TLS/reverse proxy, S3, Kubernetes, multi-region).

CI builds and pushes tagged backend/frontend images to GHCR on every merge to `main`, after
lint, the full test suite, and dependency audits pass. Rolling a new image onto a running VM
is a documented manual step (no real target host in this repo to test auto-deploy against).

**Free-tier live demo:** [hybridrag-nithya-prakash.vercel.app](https://hybridrag-nithya-prakash.vercel.app)
— a separate deployment path (Render + Qdrant Cloud + Upstash + Vercel, Groq instead of
self-hosted Ollama) exists specifically for a zero-cost, publicly reachable instance — see
[`docs/DEPLOY_FREE_TIER.md`](docs/DEPLOY_FREE_TIER.md) and `render.yaml`. It trades some of
the hardening above for $0/month; the single-VM path is still the one to use for an actual
production deployment.

## Project structure

```
.
├── backend/    FastAPI application (Python, uv) — routers/services/repositories/models
├── frontend/   Next.js application (TypeScript) — auth, upload, chat UI
├── infra/      dev docker-compose.yml + Dockerfiles (shared by dev and prod builds)
├── eval/       RAG evaluation harness — dataset, metrics, CLI, results
├── docs/       ARCHITECTURE.md (technical rationale) + PROGRESS.md (build log)
├── docker-compose.prod.yml   production compose file (see Deployment above)
├── .env.prod.example         production secrets/overrides template
└── .github/workflows/        CI: lint, test, dependency audit, image build+push
```

## Status

The full planned scope is complete — see [`docs/PROGRESS.md`](docs/PROGRESS.md) for the full
history and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the technical design. Nothing
left is a real gap: what remains is disclosed, deliberate tradeoffs, each with a real number
and a real reason behind it, not an oversight —

- **76.5% hallucination-guard recall ceiling** — proven, not assumed: after growing the
  labeled unanswerable-question set from 11 to 17, an exhaustive sweep over every real observed
  rerank score confirmed no threshold moves recall further without a worse precision trade-off
  (this raised the honestly-measured ceiling from an earlier 72.7%, found on the smaller
  11-negative set — see § Evaluation and `eval/RESULTS.md`). A second, independent mitigation
  layer was added and live-verified to catch specific cases the threshold misses; the guard's
  own number is correctly left as measured, not inflated.
- **No managed cloud / Kubernetes / S3 / TLS-terminating reverse proxy** — a deliberate
  single-VM scope choice (see § Deployment), not a gap: this project's engineering content is
  the RAG pipeline, kept fully inspectable in this repo rather than delegated to a platform.

See `ARCHITECTURE.md`'s "What's deliberately deferred" for the complete list.
