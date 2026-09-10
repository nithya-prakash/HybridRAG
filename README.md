# RAG Knowledge Assistant

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
uv run pytest                       # 209 tests, ~97% coverage
uv run pytest --cov --cov-report=term-missing

uv run pytest ../eval/tests                     # eval harness's own unit tests (metrics math)
uv run python ../eval/run_all.py                # retrieval + hallucination guard + latency + tests
uv run python ../eval/run_all.py --generation-sample 20   # + real generation/groundedness eval
uv run python ../eval/generate_final_report.py  # renders results/FINAL_REPORT.md
```

See [`eval/README.md`](eval/README.md) for the full framework layout and every phase's
independent command. A terminal recording of an earlier run is in
[`docs/screenshots/eval_demo.gif`](docs/screenshots/eval_demo.gif) — genuine, unedited output,
though against the dataset's original 21-query scope (now grown to 110 — see § Evaluation).

All of the above needs a real Postgres/Qdrant (and Redis, for the main test suite). The backend
test suite runs on every push in CI; the eval harness job runs the same suite on demand
(`workflow_dispatch`) — see `.github/workflows/ci.yml`.

## Evaluation

The full, reproducible evaluation framework lives in [`eval/`](eval/README.md) — every number
below comes from actually running it against the real pipeline. See
[`eval/RESULTS.md`](eval/RESULTS.md) for the full narrative and
[`eval/results/FINAL_REPORT.md`](eval/results/FINAL_REPORT.md) for the complete report.

**Dataset:** 110 labeled queries, 8 documents, 50 chunks — 99 answerable, 11 deliberately
unanswerable, across 8 question categories.

**Retrieval** (real local embeddings, real BM25, real cross-encoder reranker, full dataset):

| Method | Recall@1 | Recall@5 | MRR | NDCG@5 |
|---|---|---|---|---|
| Dense only | 0.924 | 0.995 | 0.976 | 0.979 |
| BM25 only | 0.788 | 0.985 | 0.895 | 0.912 |
| Dense + BM25 + RRF | 0.904 | 1.000 | 0.970 | 0.976 |
| Dense + BM25 + RRF + Reranker | **0.929** | 1.000 | **0.980** | **0.986** |

**Hallucination guard** (full dataset, real retrieval + reranker score, no LLM call):
**96.4% accuracy**, 88.9% precision, 72.7% recall, F1 0.800 — TP=8, TN=98, FP=1, FN=3
(recalibrated from an exhaustive threshold sweep over the full labeled distribution — see
`eval/RESULTS.md` for the sweep and why recall specifically can't move from a threshold change
alone). The remaining recall gap concentrates in questions where the reranker scores
topically-similar-but-wrong content confidently (see `eval/RESULTS.md` for the exact queries
and the second-layer prompt constraint added to address it directly).

**Generation** (real `llama3.2:3b` via Ollama, 20-query stratified sample): faithfulness 0.719
and answer correctness 0.719 on answered queries; citation correctness 0.788, completeness
0.656. The 3 abstention failures in this sample are the exact same queries the hallucination
guard's confusion matrix flagged independently — a real cross-method consistency check.

**Latency:** retrieval ~8ms mean, reranking ~1.08s mean (p95 1.4s), generation ~70s mean on
CPU-bound local `llama3.2:3b` (a hosted API or GPU inference would be much faster).

**Testing:** 219 tests, 0 failed, 97% code coverage.

## Design decisions

Full depth in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Highlights:

- **Structure-aware chunking, not fixed-size windows.** Chunks never merge across a heading
  boundary, so "Expense Reimbursement" never silently absorbs half of "Code of Conduct."
- **Hybrid retrieval, fused with RRF, then reranked.** Dense and keyword search fail in
  complementary ways; RRF combines both rankings without calibrating incomparable score
  scales, and reranking measurably earns its latency cost (see § Evaluation).
- **Two layers of hallucination mitigation, one deterministic.** The system prompt asks the
  model to cite every claim (a soft constraint); a hard rerank-score threshold in front of
  generation declines before the LLM is ever called if nothing retrieved is relevant enough.
  That threshold was recalibrated from an actual observed score distribution after the eval
  harness caught the original guessed value rejecting a genuinely correct answer.
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
history and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the technical design. Explicitly
deferred, not silently omitted (see `ARCHITECTURE.md`'s "What's deliberately deferred"): S3
storage, a TLS-terminating reverse proxy, and Kubernetes/multi-region deployment (all a
deliberate single-VM scope choice, not a gap — see § Deployment).
