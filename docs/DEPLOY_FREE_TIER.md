# Free-tier live demo deployment

This is a second deployment path, separate from `docker-compose.prod.yml`'s
single-VM target (see `README.md` § Deployment and `ARCHITECTURE.md` § Production
deployment for why that one is the right choice for an actual production
deploy). This path exists for one purpose: a real, publicly reachable URL for
this project at zero cost, for a portfolio/job-application context where a
recruiter needs something clickable rather than a repo to clone.

Several substitutions make that possible, none of which are needed (or used)
in the single-VM deploy:

| Piece | Single-VM (`docker-compose.prod.yml`) | Free-tier demo |
|---|---|---|
| LLM | Self-hosted Ollama (4GB+ RAM) | Groq's hosted API (`CHAT_PROVIDER=groq`) — OpenAI-compatible, no cost |
| Redis | Self-hosted `redis:7-alpine` container | Upstash free serverless Redis (`rediss://`, needs `?ssl_cert_reqs=CERT_REQUIRED` — see below) |
| Qdrant | Self-hosted `qdrant/qdrant` container | Qdrant Cloud free 1GB cluster |
| Postgres | Self-hosted `postgres:16-alpine` container | Render managed Postgres (free) |
| Document processing | Separate `celery-worker` container, real async queue | **In-process**, no separate worker — see below |
| Frontend | Same VM, Next.js standalone build | Vercel (free) |

Embeddings stay local (`EMBEDDING_PROVIDER=local`, the existing default) —
`sentence-transformers` runs fine on Render's free CPU tier and this keeps
one fewer moving part than routing embeddings through an API too.

### Why there's no separate worker service

Render's free tier has **no free background-worker instance type at all**
(confirmed directly: the Blueprint silently created `hybridrag-backend` and
`hybridrag-postgres` but dropped `hybridrag-celery-worker` without error —
background workers are paid-plan only). Running a worker alongside uvicorn
inside the same free web service container was tried next and verified
**OOM-killed on the first real upload** — two processes each loading their
own copy of the local embedding model reliably exceeded 512MB.

The actual fix: `CELERY_TASK_ALWAYS_EAGER=true` (`render.yaml`,
`app/core/config.py`) runs document processing in-process — the same
request that uploads a document also processes it, in a threadpool thread,
reusing the one embedding model copy that's already loaded rather than
spinning up a second process. No worker, no second model copy.

This is a real, verified tradeoff, not a free lunch — see Known limitations
below for what it costs.

## 1. Groq (LLM)

1. Create an account at [console.groq.com](https://console.groq.com) — no
   card required.
2. Create an API key.
3. That's the whole setup — `GroqChatBackend` (`backend/app/core/chat.py`)
   talks to Groq's OpenAI-compatible endpoint directly; no other code change
   needed. `CHAT_PROVIDER=groq` selects it.

## 2. Qdrant Cloud (vector store)

1. Create a free cluster at [cloud.qdrant.io](https://cloud.qdrant.io) (1GB,
   no card required).
2. Note the cluster URL and API key — these become `QDRANT_URL` /
   `QDRANT_API_KEY`, the same settings the self-hosted deploy already uses.

## 3. Upstash (Redis — rate limiting, and Celery's app config)

1. Create a free Redis database at [upstash.com](https://upstash.com).
2. Its `rediss://` connection string needs one addition Upstash's own
   connect snippet won't show you: append `?ssl_cert_reqs=CERT_REQUIRED` —
   without it, Celery's redis backend refuses to initialize at all
   (`ValueError: A rediss:// URL must have parameter ssl_cert_reqs...`),
   which crashes every upload even though Celery never actually dispatches
   to a worker in this deployment (see above — `Celery()` still validates
   its configured backend URL at construction). Also: copy the connection
   string itself, not Upstash's `redis-cli --tls -u ...` CLI snippet — the
   `--tls`/`-u` prefix isn't part of the URL.
3. Use the same corrected URL for `REDIS_URL`, `CELERY_BROKER_URL`, and
   `CELERY_RESULT_BACKEND`.

## 4. Render (Postgres + backend)

1. Push this repo to GitHub if it isn't already (it is: `HybridRAG`).
2. Render dashboard → New → **Blueprint**, point it at the repo. Render reads
   `render.yaml` (repo root) and provisions:
   - `hybridrag-postgres` (free managed Postgres)
   - `hybridrag-backend` (free web service). Its `dockerCommand`
     (`infra/docker/render-start.sh`) runs `alembic upgrade head` on every
     boot, then starts uvicorn — Render's free plan doesn't support
     `preDeployCommand` (a paid-plan-only field), so migrations run as part
     of the container's own start command instead, which is safe to repeat
     since a no-op migration just does nothing.
3. Fill in the prompted values (everything marked `sync: false` in
   `render.yaml`): `CORS_ORIGINS` (your Vercel URL, once you have it — you
   can redeploy to update this after step 5), `REDIS_URL`,
   `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` (all three from step 3
   above), `QDRANT_URL`, `QDRANT_API_KEY`, `GROQ_API_KEY`.
4. Render's free web services spin down after 15 minutes idle and take
   ~30-50s to wake on the next request — expected on a free tier, worth a
   one-line note in the demo link you send someone ("first load may take a
   moment to wake up").

`POSTGRES_URL` is wired automatically from the Render database
(`fromDatabase.connectionString`) — a validator in `app/core/config.py`
normalizes whatever scheme Render hands back (`postgres://` or
`postgresql://`) to the `postgresql+asyncpg://` SQLAlchemy's async engine
requires, since managed providers never include that driver suffix
themselves.

## 5. Vercel (frontend)

1. Import the repo at [vercel.com](https://vercel.com/new).
2. Set **Root Directory** to `frontend/` (Vercel auto-detects Next.js from
   there).
3. Add environment variable `NEXT_PUBLIC_API_URL` = the Render backend's
   public URL (`https://hybridrag-backend.onrender.com` or whatever Render
   assigns) — this is baked into the client bundle at build time, same
   constraint as the Docker build arg in `docker-compose.prod.yml`.
4. Deploy. Once you have the Vercel URL, go back to Render and set
   `CORS_ORIGINS` to `["https://your-app.vercel.app"]`, then redeploy the
   backend so cookie-based auth actually works cross-origin.

## Known limitations of this path (documented, not hidden)

- **The free web service periodically gets OOM-killed under real usage —
  verified live, not hypothetical.** Render's own service events show it:
  `oomKilled: {memoryLimit: '512Mi'}`, followed by an automatic restart a
  couple minutes later. Root cause: even with no separate worker process
  (see above), one process holding FastAPI + the local embedding model +
  the local cross-encoder reranker + an active upload's parse/chunk/embed
  work sits close enough to 512MB that real traffic tips it over sometimes.
  It recovers on its own (Render restarts a crashed instance automatically)
  and the core flow does work end to end when it's up — this was a
  deliberate choice to accept, not an oversight: fixing it properly means
  either a paid worker service or a paid larger instance, and the
  free-or-nothing goal here won out. If this stops being an acceptable
  tradeoff, see `render.yaml`'s comments for the two paid options.
- Render's free Postgres expires after 90 days of inactivity-free operation
  on the free plan — fine for an active job-search window, not a permanent
  deploy. Re-provisioning is a `render.yaml` blueprint sync away.
- Free-tier cold starts (Render backend, Groq's queue under load) mean the
  first request after idle can take longer than the local/single-VM deploy.
- This path has not been used in production and doesn't carry the same
  resource limits / restart policies `docker-compose.prod.yml` documents —
  it optimizes for "free and reachable," not for the production hardening
  the single-VM path is written for.
