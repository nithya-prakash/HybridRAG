# HybridRAG

Multi-user document Q&A: hybrid dense + BM25 retrieval, cross-encoder reranking, cited streamed answers, and an honest "I don't know" when the documents don't contain the answer.

[![CI](https://github.com/nithya-prakash/HybridRAG/actions/workflows/ci.yml/badge.svg)](https://github.com/nithya-prakash/HybridRAG/actions/workflows/ci.yml) ![Python 3.12](https://img.shields.io/badge/python-3.12-blue) ![License MIT](https://img.shields.io/badge/license-MIT-green)

![Register, upload a document, ask a question](docs/screenshots/demo.gif)

*Register → upload → chat, against a local instance. This recording used Groq for the answer; local Ollama works without a key.*

## Results

Measured on my own labeled set: 116 questions over 8 documents (99 answerable, 17 not). Retrieval and guard numbers are from 2026-09 runs of the commands below; generation and RAGAS were re-run 2026-10-08.

| What | Result |
|---|---|
| Retrieval, dense + BM25 + RRF + reranker | Recall@1 **0.929**, Recall@5 **1.000**, MRR **0.980** |
| Dense only (baseline) | Recall@1 0.924, Recall@5 0.995, MRR 0.976 |
| BM25 only (baseline) | Recall@1 0.798, Recall@5 0.975, MRR 0.900 |
| **Harder set**: 30 questions over 30 Wikipedia articles in confusable groups (similar languages, rivers, scientists...), Recall@1 | dense 0.483, BM25 0.550, hybrid RRF 0.650, **+ reranker 0.817** (Recall@5 1.00 for all but BM25 at 0.90) |
| Hallucination guard (decline before generating) | accuracy 93.1%, precision 76.5%, recall 76.5% |
| Generation, Groq `gpt-oss-120b`, 20-question sample (17 scored, 3 hit rate limits) | faithfulness 1.00, correctness 0.98 on answered; abstained correctly 14/20 (the 3 errored count as misses) |
| Generation, local `qwen2.5:3b`, same 20 questions | faithfulness 0.43, correctness 0.50; abstained correctly 16/20 |
| RAGAS cross-check (Groq judge, paced), first 20-question sample | faithfulness 0.98, context precision 1.00 on all 11 answered samples |
| Tests | 250 backend + 34 eval, ruff clean |

Honest reading: on my own 8-document corpus retrieval is near ceiling, so the reranker adds only +0.5 point of Recall@1. That is a weakness of the test set, so I added the harder Wikipedia set, where each stage clearly earns its place (Recall@1 0.48 → 0.65 → 0.82). It is still only 30 questions, each written from one source sentence, so lexical overlap flatters retrieval. The 3B local model is the weak link in generation: the same questions score far higher on a 120B hosted model, so retrieval is not the bottleneck. The 120B judges its own answers, so those scores are optimistic. Details and caveats: [eval/RESULTS.md](eval/RESULTS.md).

## Quickstart

```bash
cp backend/.env.example backend/.env
docker compose -f infra/docker-compose.yml up --build
```

Frontend http://localhost:3000, API docs http://localhost:8000/docs. First boot pulls `llama3.2:3b` (~2 GB). There is no hosted demo; it runs locally.

| Variable | Purpose |
|---|---|
| `CHAT_PROVIDER` | `ollama` (default), `openai`, `groq` or `gemini` |
| `EMBEDDING_PROVIDER` | `local` (default, bge-small) or `openai` |
| `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL` | local model endpoint and name |
| `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY` | only for the matching hosted provider |
| `LANGFUSE_*` | optional tracing, see above |
| `JWT_SECRET_KEY`, `CORS_ORIGINS` | must be set to non-defaults outside local/test; the app refuses to start otherwise |

## How it works

```mermaid
flowchart LR
  U[Upload PDF/DOCX/TXT/MD] --> C[Celery: parse, chunk by heading, embed]
  C --> Q[(Qdrant vectors)]
  C --> P[(Postgres full-text)]
  A[Question] --> R[Rewrite with chat history]
  R --> D[Dense search] & B[BM25 search]
  Q --> D
  P --> B
  D & B --> F[RRF fusion] --> X[Cross-encoder rerank]
  X --> G{Score above threshold?}
  G -- no --> N[Decline]
  G -- yes --> L[LLM answer with citations, streamed]
```

Stack: FastAPI, Postgres, Qdrant, Redis/Celery, Next.js. Every query is filtered by user at the retrieval layer, so one user cannot see another's documents. More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Tracing (optional)

Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` and every question becomes a Langfuse trace: `rag.ask` → `rewrite_and_retrieve` (with per-stage timings) → `generate` (model, output). Off by default; install with `uv sync --extra tracing`. Question and answer text are sent only if `LANGFUSE_CAPTURE_CONTENT=true`. Verified against a local Langfuse v4 server; not run against Langfuse Cloud.

![Langfuse trace of one answered question](docs/screenshots/langfuse_trace.png)

## Usage

1. Register, log in (JWT in httpOnly cookies, CSRF token).
2. Upload documents on the Documents page; wait for status `ready`.
3. Ask questions in Chat. Answers stream with inline citations, or the app declines.

Optional: `automation/n8n/document_intake.json` is an n8n workflow that ingests a file by URL. Run end to end once in n8n 2.42.5 (ingest returned `ready`); see `automation/n8n/README.md` for what was and wasn't covered.

## Limitations

- Guard recall tops out at 76.5%: about 1 in 4 unanswerable questions still reaches the LLM. A threshold sweep found no better setting.
- Evaluation set is 116 questions over 8 documents I wrote or chose, so it is small and not independent. Generation numbers use a 20-question sample, and the judge is the same 3B model that wrote the answers.
- Fine-tuning the reranker on this corpus changed no ranking (null result, p = 1.0), so it is not used. Details in [docs/details.md](docs/details.md).
- Local generation is slow on CPU (tens of seconds per answer).
- Groq was run live (above). Gemini and OpenAI chat paths are covered by unit tests only, never run live.
- No hosted demo. A free-tier Render/Vercel setup exists ([docs/DEPLOY_FREE_TIER.md](docs/DEPLOY_FREE_TIER.md)) but is not currently deployed.
- Single-VM Docker Compose deployment; no Kubernetes, TLS proxy or automated CD.

## Repository layout

```
backend/   FastAPI app, Alembic migrations, tests
frontend/  Next.js UI
eval/      labeled datasets (own corpus + Wikipedia), metrics, run scripts, RAGAS, reranker experiment
infra/     dev docker-compose and Dockerfiles
docs/      ARCHITECTURE, API, DEPLOY_FREE_TIER, PROGRESS, details
automation/n8n/  document-intake workflow (run once, see its README)
```

## Checks

```bash
cd backend && uv sync --dev && uv run alembic upgrade head
uv run ruff check . && uv run pytest              # backend tests
uv run pytest ../eval/tests                       # eval tests
uv run python ../eval/run_eval.py --retrieval-only   # retrieval table, no LLM
uv run python ../eval/run_all.py                  # retrieval + guard + latency
EVAL_DATASET=../eval/datasets/wiki_eval.json uv run python ../eval/run_eval.py --retrieval-only   # harder set
pip install -r ../eval/requirements-ragas.txt     # in a separate venv
CHAT_PROVIDER=groq uv run python ../eval/run_eval.py --output ../eval/results/generation_groq.json   # then:
python ../eval/ragas_eval.py ../eval/results/generation_groq.json   # JUDGE_* env vars select the judge
```

CI runs lint, tests, dependency audit, eval and image builds on every push.

## Roadmap and license

Next: evaluate with a stronger judge model, grow the question set beyond 8 documents. MIT, see [LICENSE](LICENSE).
