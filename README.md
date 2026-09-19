# RAG Knowledge Assistant

**[Live demo →](https://hybridrag-nithya-prakash.vercel.app)** (Render free tier — first
request after inactivity may take 30-50s)

A production-grade, multi-user RAG assistant: upload documents, ask questions in a chat
interface, get answers grounded in your own content with inline citations — not a generic
LLM wrapper. Demonstrates multi-tenant isolation, hybrid dense+keyword retrieval with RRF
and cross-encoder reranking, two layers of hallucination mitigation, security hardening, a
labeled evaluation harness, and a reranker fine-tuning experiment. Full rationale in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/PROGRESS.md`](docs/PROGRESS.md).

![Demo: register, upload a document, and ask a question in the chat UI](docs/screenshots/demo.gif)

*Register → upload → chat, against a live local instance. Local models by default
(`sentence-transformers` + Ollama) — no API key required; OpenAI is a supported alternative.*

## What it does

1. **Register / log in** — JWT access + refresh tokens in `httpOnly` cookies.
2. **Upload a document** (PDF/DOCX/TXT/MD) — structure-aware chunking (respects headings),
   embedded and indexed in the background.
3. **Ask a question** — query rewrite → dense (Qdrant) + BM25 (Postgres) → RRF fusion →
   cross-encoder rerank → **streamed, cited answer**, or an honest decline if nothing
   retrieved is actually relevant.
4. Every other user's documents are invisible to you — isolation enforced at the query
   layer, not just the UI.

## Screenshots

| Document processing | Grounded, cited answer |
|---|---|
| ![Documents page](docs/screenshots/05_documents_result.png) | ![Chat UI](docs/screenshots/09_chat_response.png) |

Both captured local-only (no API key). More in [`docs/screenshots/`](docs/screenshots/).

## Architecture

```
                         ┌─────────────┐
                         │   Browser   │
                         └──────┬──────┘
                                │ HTTPS (REST + SSE streaming)
                         ┌──────▼──────┐
                         │  Frontend   │  Next.js — auth, upload, streaming chat
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐         ┌─────────────┐
                    ┌───►│   Backend   │◄───────►│    Redis    │  rate limits +
                    │    │  (FastAPI)  │         │             │  Celery broker
                    │    └──┬───────┬──┘         └──────┬──────┘
                    │       │       │                   │
             ┌──────┴───┐   │  ┌────▼───────┐    ┌──────▼──────┐
             │ Postgres │   │  │   Qdrant   │    │   Celery    │  parse → chunk
             │ users ·  │◄──┘  │   vectors  │◄───│   worker    │  → embed → index
             │ docs+FTS │      └────────────┘    └──────┬──────┘
             └──────────┘                         ┌──────▼──────┐
                                                    │   OpenAI /  │  embeddings + chat
                                                    │   Ollama    │  (local by default)
                                                    └─────────────┘
```

## Quickstart

```bash
cp backend/.env.example backend/.env
docker compose -f infra/docker-compose.yml up --build
```

Frontend: http://localhost:3000 · API: http://localhost:8000/docs · Health:
`curl localhost:8000/health`. First boot pulls `llama3.2:3b` (~2GB) once; embedding model
and reranker are baked into the image. `EMBEDDING_PROVIDER=openai`/`CHAT_PROVIDER=openai`
swap in OpenAI for either.

## Evaluation

Full, reproducible framework in [`eval/`](eval/README.md) — every number below is from an
actual run against the real pipeline. Full narrative in [`eval/RESULTS.md`](eval/RESULTS.md).

```bash
cd backend && uv sync --dev && uv run alembic upgrade head
uv run pytest                                  # 238 tests, 98% coverage
uv run python ../eval/run_all.py               # retrieval + guard + latency (no LLM calls)
uv run python ../eval/run_all.py --generation-sample 20   # + real generation eval
```

**Dataset:** 116 labeled queries, 8 documents, 50 chunks (99 answerable, 17 unanswerable),
across 8 question categories.

| Retrieval | Recall@1 | Recall@5 | MRR | NDCG@5 |
|---|---|---|---|---|
| Dense only | 0.924 | 0.995 | 0.976 | 0.979 |
| BM25 only | 0.798 | 0.975 | 0.900 | 0.912 |
| Dense + BM25 + RRF | 0.904 | 1.000 | 0.970 | 0.976 |
| Dense + BM25 + RRF + Reranker | **0.929** | 1.000 | **0.980** | **0.986** |

- **Hallucination guard** (real retrieval + reranker score, no LLM call): 93.1% accuracy,
  76.5% precision/recall, F1 0.765 — TP=13, TN=95, FP=4, FN=4. Threshold calibrated via
  exhaustive sweep over the full labeled score distribution, recalibrated three times as the
  dataset grew.
- **Generation** (real `llama3.2:3b` via Ollama, 20-query stratified sample): faithfulness
  0.864, answer correctness 0.727, citation correctness 0.864 on answered queries;
  abstention 13/20.
- **Latency:** retrieval ~8ms mean, reranking ~1.08s mean (p95 1.4s), generation ~46s mean
  (down from ~70s after fixing a real unbounded-output-length bug) — CPU-bound local model.
- **Testing:** 238 tests, 98% coverage.

## Reranker fine-tuning

`eval/reranker_training/` fine-tunes the shipped reranker (`cross-encoder/ms-marco-
MiniLM-L-6-v2`) on this project's own corpus and A/B tests it against the frozen baseline on
the full, untouched 116-query benchmark. Training data: each chunk's heading becomes a
deterministic pseudo-query (no LLM call), the chunk is the positive, **hard negatives are
mined from the real dense+BM25+RRF pipeline**. 8 documents split 75/25 (6 train/2
calibration, seeded) so no chunk crosses that boundary; every query checked against the 116
benchmark queries for collisions (zero found). Real dataset: 195 train examples (39
positive/156 hard negative) + 55 calibration examples. Training: `CrossEncoderTrainer` +
`BinaryCrossEntropyLoss`, 4 epochs, seed 42 throughout, CPU-only, 117s wall time.

| Metric | Baseline | Fine-tuned | Diff |
|---|---|---|---|
| Recall@1 / Recall@5 / MRR / NDCG@5 | 0.9293 / 1.000 / 0.9798 / 0.9864 | identical | +0.0000 |
| Hallucination-guard precision | 0.7647 | 0.8462 | +0.0815 |
| Hallucination-guard recall | 0.7647 | 0.6471 | −0.1176 |
| Hallucination-guard F1 | 0.7647 | 0.7333 | −0.0314 |
| Reranking latency (mean) | 863.3ms | 983.1ms | +119.8ms (noisy) |

**Honest result: a null finding, not an improvement.** Retrieval ranking is unchanged on
every query. The guard's precision/recall tradeoff is real but **not statistically
significant** (McNemar's exact test, b=2, c=2, p=1.0 — a perfectly symmetric split).
Threshold recalibration was checked on a held-out calibration split and rejected (the
recommendation swung from ≈3.34 to ≈1.63 across independent retrains — unstable). **Not
promoted to production** — `RERANKER_MODEL=baseline` is the enforced default; `finetuned` is
actively blocked outside local/test at startup, fail-fast. Full write-up, statistical
methodology, and a real reproducibility-bug fix found along the way:
[`eval/RESULTS.md`](eval/RESULTS.md).

## Design decisions

Full depth in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

- **Structure-aware chunking** — never merges content across a heading boundary.
- **Hybrid retrieval, RRF, then reranked** — reranking measurably earns its latency cost.
- **Two independent hallucination-mitigation layers** — a rerank-score threshold before
  generation, recalibrated three times against real evidence, plus a generation-prompt
  constraint that live-tested catches what the threshold misses.
- **Multi-tenant isolation at the query layer** — no "search everything" method exists.
- **Fail-fast on insecure production config** — refuses to start with default secrets, a
  wildcard CORS origin, or the unvalidated fine-tuned reranker.
- **CSRF defense-in-depth** — non-httpOnly double-submit-cookie token.

## Deployment

```bash
cp .env.prod.example .env
docker compose -f docker-compose.prod.yml up -d --build
./scripts/smoke_test.sh
```

Single VM + Docker Compose, chosen over Kubernetes/managed PaaS to keep the deployment
story fully inspectable. No public ports on internal services, resource limits, auto
migrations. CI builds/pushes images to GHCR on every merge. The live demo above uses a
separate $0/month path (Render + Qdrant Cloud + Upstash + Vercel) — see
[`docs/DEPLOY_FREE_TIER.md`](docs/DEPLOY_FREE_TIER.md).

## Project structure

```
.
├── backend/    FastAPI application (Python, uv)
├── frontend/   Next.js application (TypeScript)
├── infra/      dev docker-compose.yml + Dockerfiles
├── eval/       evaluation harness + reranker fine-tuning
├── docs/       ARCHITECTURE.md + PROGRESS.md
└── .github/workflows/   CI: lint, test, audit, image build+push
```

## Status

Full planned scope complete. What remains is disclosed, deliberate tradeoffs, not gaps: a
proven 76.5% hallucination-guard recall ceiling (exhaustive sweep confirmed no threshold
moves it further), and no managed cloud/Kubernetes (a deliberate single-VM scope choice).
See `docs/ARCHITECTURE.md`'s "What's deliberately deferred" for the full list.
