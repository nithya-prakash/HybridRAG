# Architecture

## Overview

A production-grade, multi-user RAG (Retrieval-Augmented Generation) knowledge assistant.

```
Document Upload → Parsing → Structure-Aware Chunking → Embeddings → Qdrant
  → Hybrid Search (Dense + BM25) → RRF → Reranking → LLM → Grounded Answer + Citations
```

This document covers repository layout and technology choices in depth: scaffolding, auth +
multi-tenancy, document upload + async processing plumbing, parsing + structure-aware chunking,
embeddings + Qdrant indexing + Postgres keyword search, hybrid search (RRF fusion + cross-encoder
reranking + filters), conversational RAG (query rewriting, grounded + cited + streamed answers),
production hardening (rate limiting, security posture, request tracing, metrics, graceful
degradation), a test coverage audit + labeled retrieval/generation evaluation harness, and
production deployment configuration + CI/CD. The full originally planned scope is complete. See §
What's deliberately deferred for what's honestly out of scope beyond that.

## Monorepo layout

```
.
├── backend/                  FastAPI application (Python)
├── frontend/                 Next.js application (TypeScript)
├── infra/                    dev docker-compose.yml, Dockerfiles (shared by dev + prod), CI-adjacent config
├── eval/                     RAG evaluation harness — dataset, metrics, CLI, results
├── docs/                     architecture notes, progress log, API design notes
├── docker-compose.prod.yml   production compose file
├── .env.prod.example         production secrets/overrides template
├── README.md                 top-level quickstart + design-decisions overview
└── .github/workflows/        CI pipeline
```

A monorepo keeps the backend, frontend, and infra definitions versioned together, which matters
for a project where the API contract, retrieval pipeline, and UI evolve in lockstep.

## Backend

### Dependency management: `uv`

We use [`uv`](https://docs.astral.sh/uv/) instead of Poetry:

- Dramatically faster dependency resolution and installs (Rust-based), which matters for CI
  cycle time and Docker build layer caching.
- Single lockfile (`uv.lock`) with reproducible resolution, committed to the repo.
- Native `pyproject.toml` support with no proprietary sections beyond `[tool.uv]`/build-backend,
  so the project stays portable to `pip`/`build` if ever needed.
- One tool for Python version management, virtualenv creation, and dependency installs — fewer
  moving parts than Poetry + pyenv.

### Layered structure

```
backend/app/
├── main.py           FastAPI app factory, middleware, router registration
├── core/              cross-cutting: settings, logging, celery app, db, security, rate limiting,
│                        storage (blob abstraction), file_validation, embeddings (OpenAI wrapper),
│                        vector_store (Qdrant wrapper)
├── api/routers/       HTTP route handlers (thin — delegate to services)
├── api/deps.py         shared dependencies: get_db, get_current_user
├── schemas/           Pydantic request/response models
├── services/           business logic, orchestration (auth_service.py, document_service.py),
│                         plus services/parsing/ — parsing + chunking, not a "service" in the
│                         router-facing sense, but grouped here since it's pure business logic
│                         with no HTTP or DB concerns of its own
├── repositories/       data access, one class per table (user/refresh_token/document/chunk) —
│                         ChunkRepository also does Postgres full-text keyword search
├── models/              SQLAlchemy ORM models (user, refresh_token, document, document_version,
│                         chunk)
└── tasks/               Celery task bodies (document_processing.py)
```

The router → service → repository split keeps HTTP concerns (status codes, request parsing) out
of business logic, and business logic out of data access. This separation matters most once
retrieval and ingestion pipelines are added — each will have a service that composes multiple
repositories (Postgres for metadata, Qdrant for vectors, BM25 for keyword search).

Auth (`auth_service.py` + its two repositories), document upload (`document_service.py`,
`DocumentRepository`, `app/tasks/`), parsing (`services/parsing/`, `ChunkRepository`), and
embeddings/indexing (`core/embeddings.py`, `core/vector_store.py`) are the first real occupants of
this structure — see
[Authentication & multi-tenancy](#authentication--multi-tenancy),
[Document upload & processing](#document-upload--processing),
[Document parsing & chunking](#document-parsing--chunking), and
[Embeddings, indexing & keyword search](#embeddings-qdrant-indexing--keyword-search)
below.

### Configuration

`app/core/config.py` defines a single `pydantic-settings` `Settings` class loaded from
environment variables (with `.env` support for local dev). Every environment variable the full
project will eventually need is declared here with a sane local default, and mirrored in
`backend/.env.example`, even though most (OpenAI key, JWT secret, etc.) are unused until later
work builds on them. This avoids env var drift — one file is the source of truth for "what does
this service need configured."

### Logging

`app/core/logging.py` configures [`structlog`](https://www.structlog.org/) bound to the stdlib
logging module: JSON output in non-local environments (parseable by log aggregators), human-
readable console output locally. Structured logging from day one means everything built later
(auth, ingestion, retrieval) gets contextual, machine-parseable logs for free instead of
retrofitting it.

## Frontend

Next.js (App Router) + TypeScript + Tailwind CSS. App Router was chosen over Pages Router because
it's the actively developed Next.js paradigm and pairs naturally with React Server Components for
work built later. Tailwind avoids hand-rolled CSS churn while the UI was still taking shape.
(The streaming chat UI ended up client-rendered via `fetch` + `ReadableStream` rather than RSC
streaming — see § Conversational RAG — but App Router's flexibility to do either was still the
right bet to make early.)

The original placeholder page (`app/page.tsx` + `components/HealthStatus.tsx`) does a client-side
fetch to the backend `/health` endpoint via `NEXT_PUBLIC_API_URL`, proving frontend ↔ backend
connectivity end to end (including CORS) before any real feature is built.

## Authentication & multi-tenancy

### Schema

Two tables, managed by Alembic (`backend/alembic/`, async env — see below):

- **`users`**: `id` (UUID pk), `email` (unique, indexed), `hashed_password`, `is_active`,
  `created_at`.
- **`refresh_tokens`**: `id` (UUID pk), `user_id` (FK → `users.id`, `ON DELETE CASCADE`),
  `token_hash` (unique, indexed — the token itself is never stored), `expires_at`, `revoked_at`
  (nullable), `created_at`.

Alembic runs against the async engine directly (`alembic/env.py` uses
`async_engine_from_config` + `connection.run_sync`), so there's no second sync driver dependency
just for migrations. The initial migration (`5cc3fae5c3c4_create_users_and_refresh_tokens.py`)
was generated with `alembic revision --autogenerate` against a live Postgres, then reviewed by
hand — autogenerate is a starting point, not something to trust blindly.

### Token strategy

Two tokens, two different trust models:

- **Access token** — a stateless JWT (HS256, `jwt_secret_key`), 15-minute expiry, carries only
  `sub` (user id) and `type`. Stateless means no DB lookup on every request, but also means it
  *can't* be revoked before it expires — that's why it's short-lived.
- **Refresh token** — an opaque random string (`secrets.token_urlsafe(32)`), 7-day expiry, stored
  **hashed** (SHA-256) in `refresh_tokens`, never as plaintext. Every use **rotates** it: the
  presented token is revoked and a new access/refresh pair is issued
  (`AuthService.rotate_refresh_token`). This bounds the damage from a leaked refresh token — it's
  single-use, and reuse of an already-rotated token is a signal worth alerting on as a future
  hardening step (not implemented yet: reuse is made to fail, but not yet flagged).

Both are delivered as separate cookies (see below), not in the JSON response body — the frontend
never sees or handles a raw token.

### Cookie storage, not localStorage

Both tokens are set as `httpOnly` cookies (`app/api/routers/auth.py::_set_auth_cookies`), not
returned to be stored in `localStorage`. Reasoning:

- `localStorage` is readable by any JavaScript running on the page — including anything an XSS
  vulnerability manages to inject. A stolen token from `localStorage` is a stolen session, full
  stop. `httpOnly` cookies are invisible to `document.cookie` and to any JS, injected or not —
  they're never in a place a script could read them.
- The tradeoff is CSRF, not XSS: a cookie is sent automatically on any request to the domain,
  including ones triggered by a malicious third-party site. This is mitigated by `SameSite=Lax`
  (blocks cookies on cross-site `POST`/fetch, only sends them on top-level navigation) plus CORS
  restricted to the exact frontend origin (`cors_origins` in `backend/.env.example`) with
  `allow_credentials=True`. This is a baseline, not the final story — a double-submit CSRF token
  is the natural next step in a future hardening pass, same "down payment" framing as rate
  limiting below.
- The refresh token cookie is additionally scoped with `Path=/auth`, so it's never sent on
  requests outside the auth routes — it doesn't need to be, and narrowing its blast radius is
  free.

`cookie_secure` (settings) is `false` for local dev (plain HTTP) and must be set `true` in any
deployed environment (HTTPS) — the cookie won't be sent over plaintext HTTP if `Secure` is set,
so this is an intentional environment-specific flip, not an oversight.

### `get_current_user` and the multi-tenant isolation convention

`app/api/deps.py::get_current_user` is a FastAPI dependency: reads the `access_token` cookie,
decodes and validates the JWT, loads the `User` row, and 401s (via a single shared
`HTTPException`, so failure responses don't leak *why* — missing cookie, bad signature, and
expired token all look the same from outside) if anything is off. `GET /auth/me` is just this
dependency wired to a route that echoes the user back — it's also literally the pattern every
future protected route follows: add `current_user: User = Depends(get_current_user)` to the
handler signature and the route is protected.

**This is the convention every future addition must follow, without exception:**

> Every resource table added from here onward (`documents`, `chunks`, `conversations`, ...)
> **must** carry a `user_id` FK to `users.id`, and **every** query against that table — list, get,
> update, delete — **must** be scoped to `current_user.id` obtained from `get_current_user`. There
> is no shared/global data model anywhere in this system; a user must never be able to read or
> affect another user's rows, and the only thing standing between "isolated by design" and "one
> missing `WHERE user_id = ...`" is this convention being followed at every single call site.

Concretely: repository methods for tenant-owned resources should take `user_id` as a required
parameter and filter on it (mirroring `UserRepository`/`RefreshTokenRepository`'s shape), not rely
on service-layer callers to remember to filter. The document/chunk repositories built next bake
the `user_id` filter into the repository methods themselves, not leave it to callers to remember.

### Rate limiting

`app/core/rate_limit.py` wires up [`slowapi`](https://github.com/laurentS/slowapi) with a
Redis-backed fixed-window store (`storage_uri=settings.redis_url`), applied via
`@limiter.limit(settings.auth_rate_limit)` (default `5/minute`, per client IP) to `/auth/register`
and `/auth/login` specifically — the two endpoints an attacker would hit to brute-force credentials
or enumerate accounts. This is a down payment on the full rate-limiting story (which will likely
need per-user limits, not just per-IP, and coverage beyond just auth) planned for a later
hardening pass — scoped narrowly here to the two endpoints named in this section's own requirements.

### Frontend

`lib/auth-context.tsx` provides a React context (`AuthProvider`/`useAuth`) that calls
`GET /auth/me` on mount to restore session state (cookies are already on the request — no token
handling needed client-side) and exposes `login`/`register`/`logout`. `lib/auth-api.ts` wraps the
raw `fetch` calls, always with `credentials: "include"` so cookies flow cross-origin between
`localhost:3000` and `localhost:8000` in dev.

`middleware.ts` gates `/dashboard/**` by checking whether the `access_token` cookie is *present* —
it deliberately does not verify the JWT (that would mean duplicating the signing-secret trust
boundary into JS at the edge). This is a UX-level redirect only, to avoid flashing a protected page
before bouncing to `/login`; the backend's `get_current_user` remains the actual authority on every
API call, and is what a client-side check can never substitute for.

## Document upload & processing

### Schema and versioning model

Two tables:

- **`documents`**: `id`, `user_id` (FK, indexed, `ON DELETE CASCADE`), `filename`, `file_type`,
  `file_size_bytes`, `storage_path`, `status`, `error_message`, `version`, `created_at`,
  `updated_at`. This row is the **current-version snapshot** — `filename`/`file_type`/
  `storage_path`/`file_size_bytes`/`status` always describe the latest upload.
- **`document_versions`**: one immutable row per upload (`document_id` FK, `version`, plus its own
  `filename`/`file_type`/`file_size_bytes`/`storage_path`), unique on `(document_id, version)`.
  This is the full history.

Re-uploading is not a separate endpoint — `POST /documents/upload` accepts an optional
`document_id` form field. Without it, a new document is created at version 1. With it (and only if
the document belongs to the calling user — checked via the same `get_for_user` scoping as every
other document query), it appends a new `document_versions` row, bumps `documents.version`, and
overwrites the `documents` row's current-snapshot fields — so "what does this document look like
right now" is always a single-row read, while "what did version 2 look like" is still answerable
from history. Deleting a document cascades to its versions at the DB level (`ON DELETE CASCADE`)
and separately deletes every version's file from storage (the DB cascade doesn't touch the
filesystem).

### Storage abstraction

`app/core/storage.py` defines `StorageBackend` (abstract: `save(key, content) -> storage_path`,
`delete(storage_path) -> None`) and `LocalDiskStorage`, the only implementation today, writing
under `settings.upload_dir` (a shared Docker volume — see `docker-compose.yml`). Nothing in
`document_service.py` or the router imports `LocalDiskStorage` directly; they go through
`get_storage_backend()`. Swapping to S3 later means writing `S3Storage(StorageBackend)` and
changing that one factory function — no business-logic changes.

`key` (what callers pass to `save`) and `storage_path` (what `save` returns and what `delete`
takes back) are deliberately different concepts: `key` is a caller-chosen relative identifier
(`{user_id}/{document_id}/v{version}/{filename}`, sanitized via `safe_filename` to strip any
directory components and block path traversal), while `storage_path` is whatever opaque locator
the backend hands back — for local disk, an absolute path; for a future S3 backend, potentially an
object key or URL that doesn't derive from `key` by simple concatenation. Callers must never
reconstruct a `storage_path` themselves from a `key` — always use what `save` returned.

### File validation

`app/core/file_validation.py` checks both the extension (against an allowlist: `.pdf`, `.docx`,
`.txt`, `.md`) and the content itself — a client-supplied extension is not trustworthy on its own.
PDF/DOCX are checked against their magic bytes (`%PDF-`, the `PK\x03\x04` zip signature); TXT/MD
are checked by attempting a UTF-8 decode. This is a real check, not just an extension rubber-stamp
— a `.pdf` renamed from a `.exe` is rejected with `415`, not silently accepted.

### Task queue design

`app/tasks/document_processing.py` defines `process_document(document_id, version)`, replacing the
original no-op `ping` task as the worker's real workload. It first shipped with a simulated delay
standing in for the real work; parsing and chunking (see
[below](#document-parsing--chunking)) filled that in, and embedding + Qdrant indexing (see
[below](#embeddings-qdrant-indexing--keyword-search)) followed right after — both only ever
extended the *middle* of `_process`. The status-transition, retry, and version-fencing scaffolding
described in this section has needed zero changes since it was first written, exactly as planned.

**Fresh engine per task invocation.** Celery tasks here run via `asyncio.run(...)`, which opens a
new event loop per call. A module-level `AsyncEngine` (the pattern `app/core/db.py` uses for the
FastAPI process, which lives for the process's whole lifetime and is used from one loop
throughout) would have its asyncpg connection pool bound to whichever loop was active on first
use — reused on a second task invocation, in a new loop, that's exactly the
`MissingGreenlet`/"attached to a different loop" failure hit with pytest-asyncio early on. So
`_with_session()` creates a `create_async_engine(...)` scoped to a single call and disposes it in
a `finally` block. This was **not** a hypothetical: an earlier version of this task set
`pool_pre_ping=True` on that short-lived engine (copying `app/core/db.py`'s long-lived-engine
config without thinking about why it's there) and hit exactly this class of greenlet error under
test — removed once the reasoning became clear: pre-ping exists to protect a pool that might have
gone stale between uses, which cannot happen to an engine that's created and torn down within one
call.

**Version fencing.** A re-upload can land while the previous version is still "processing." The
task re-fetches the document (by `document_id`, unscoped — the one legitimate use of
`DocumentRepository.get_by_id`, since a background task has no per-request user context; see
[the isolation convention](#get_current_user-and-the-multi-tenant-isolation-convention)) both
before starting and after parsing/chunking, and compares `document.version` against the version it
was asked to process each time. A mismatch means a newer upload has already superseded this run,
and the task discards its result — including any chunks it computed, which are simply never
persisted — rather than stomping a newer version's state with a stale `ready`.

**Retry and terminal failure.** `process_document` is configured with `autoretry_for=(Exception,)`,
`max_retries=3`, `retry_backoff=True` (exponential, capped, jittered). A custom `Task` subclass
(`DocumentProcessingTask`) overrides `on_failure`, which Celery calls exactly once when a task
ultimately fails (retries exhausted) — it writes `status=failed` with the exception message
attached, via the same fresh-engine pattern. Tested by calling `_process`/`_mark_failed` directly
against a real Postgres rather than by watching real exponential backoff run to completion in a
test — the retry *policy* is asserted declaratively (`process_document.max_retries == 3`, etc.);
the terminal-failure *behavior* (row ends up `failed` with the message stored) is exercised
directly, since that's the part with actual logic worth testing. The full pipeline through a real
broker and worker was verified manually against the running `celery-worker` container instead —
see `PROGRESS.md`.

### API surface

`POST /documents/upload`, `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/status`
(a smaller payload than the full read, meant for polling), `DELETE /documents/{id}` — all behind
`get_current_user`, all scoped via `get_for_user`. Deleting removes the DB rows, every version's
stored file, and the document's Qdrant vectors — see
[Embeddings, indexing & keyword search](#embeddings-qdrant-indexing--keyword-search).

### Frontend polling

`components/DocumentList.tsx` re-fetches the whole document list (not per-row status calls) every
2 seconds *only while at least one document is `uploaded` or `processing`*, and stops polling once
none are pending — no polling loop runs for a screen full of already-`ready`/`failed` documents.

## Document parsing & chunking

### Parser choices

One parser per file type, each producing a common intermediate form
(`ParsedDocument` — a flat list of `ParsedBlock`s, each carrying `text`, `page_number`,
`heading_path`, `block_type`) that the chunker consumes without needing to know which parser
produced it:

- **PDF — [PyMuPDF](https://pymupdf.readthedocs.io/) (`import pymupdf`, the modern name for the
  `fitz` module)**. Chosen over `pdfplumber` (slower, and mainly aimed at table/layout extraction
  we don't need yet) and over `unstructured` (does more out of the box, but pulls in a much
  heavier dependency tree and, in some install modes, system packages like `poppler`/`tesseract`
  — a poor fit for this project's "production-lean images" goal). PyMuPDF is a thin,
  fast C-library binding with prebuilt wheels for the platforms this project actually runs on
  (confirmed: installs and runs cleanly on both the arm64 dev machine and CI's amd64 runners with
  no compilation step), and it gives exact per-page text plus per-span font-size metadata, which
  is exactly what's needed for page numbers and heading detection.
- **DOCX — [python-docx](https://python-docx.readthedocs.io/)**. The standard, well-established
  choice; paragraphs carry a `style.name` (`"Heading 1"`, `"Heading 2"`, `"Title"`, ...) that maps
  directly to a heading level with zero guessing — no heuristic needed, unlike PDF.
- **Markdown — [markdown-it-py](https://markdown-it-py.readthedocs.io/)**. A spec-compliant
  CommonMark parser that returns a real token stream to walk (heading/paragraph/list-item/fence
  open-close pairs), rather than converting to HTML and re-parsing that. Headings, lists, and
  fenced code blocks are walked directly; tables and blockquotes are folded into plain paragraph
  text for now — a documented simplification, not an oversight.
- **TXT — no library**. Plain text has no heading syntax to exploit; the only real structure is
  paragraph breaks (blank lines). `app/services/parsing/text_parser.py` is a handful of lines.

### Heading detection per type

- **DOCX**: authoritative — Word's own style names.
- **Markdown**: authoritative — `#`..`######` are unambiguous.
- **PDF**: heuristic. PDFs generally carry no semantic structure at all (no equivalent of a
  "Heading 1" style) unless the author added bookmarks, which many documents don't have. The
  heuristic: compute the document's most common font size (the "body" baseline), then treat a
  short text block (≤20 words) whose font size is ≥1.15–1.5× that baseline as a heading, with the
  ratio picking the level. Reading a PDF's embedded table-of-contents/outline (when present, via
  `doc.get_toc()`) back onto extracted text blocks would be more reliable when available, but
  requires matching bookmark targets (page + approximate position) back onto extracted blocks,
  which is meaningfully more involved — left as a documented future improvement, not implemented
  here.
- **TXT**: none — plain text has no heading marker convention to detect, so `heading_path` is
  always empty for TXT-derived blocks. Forcing heading detection onto unstructured prose would
  produce noise, not structure.

**A real bug caught by testing, not by reading the code**: the first version of the PDF baseline
computation counted font sizes **per block** (`size_counts[size] += 1`). The test fixture — a
2-page PDF with one heading block and one body block per page — has exactly 2 blocks at each size,
a tie, and `Counter.most_common()` breaks ties by insertion order, so the *heading* size (seen
first) won and got treated as "body." Every heading in the test then silently failed to be
detected — `heading_path` came back empty everywhere. Fixed by weighting the count by **character
length** (`size_counts[size] += len(text)`) instead of block count: body text is reliably far more
voluminous than headings, even in a heading-heavy, text-light document, so this is a much more
robust signal than a per-block tally. This is exactly the kind of bug that only a test against
real extracted structure (not just "does it run") would catch — see `test_parse_pdf_extracts_...`
in `backend/tests/test_parsers.py`.

### Page numbers: real vs. estimated

PDF gets **exact** page numbers — PyMuPDF reports which page each block came from directly. DOCX,
Markdown, and TXT have no page concept in the source file at all (pagination is something a
renderer computes, not something stored in the document), so `app/services/parsing/page_estimate.py`
assigns a rough **estimate**: one page per ~3000 characters of cumulative content, a common
ballpark for standard-format text. This is explicitly a "best estimate," clearly less trustworthy
than PDF's exact numbers — the metadata doesn't distinguish the two today, which is a fair
question for whoever builds citation UX on top of this later (worth surfacing whether a chunk's
`page_number` came from a real PDF page vs. an estimate).

### Structure-aware chunking

`app/services/parsing/chunker.py::chunk_document`:

1. **Group into sections.** Blocks are grouped into maximal runs sharing the same `heading_path` —
   a "section." Chunking, and overlap, happen *within* a section and never across one: content
   under different headings shouldn't blur together just because they happened to be packed
   adjacently.
2. **Pack blocks into chunks up to a token budget.** `chunk_max_tokens` (default 500) and
   `chunk_overlap_tokens` (default 75) are configurable settings. Blocks are greedily packed into
   a chunk until the next block wouldn't fit, then the chunk is emitted and a new one starts. A
   single block that alone exceeds `chunk_max_tokens` (rare — one enormous paragraph with no
   internal structure) is split directly on token boundaries as a fallback
   (`tokenizer.split_by_token_budget`); the pieces may cut mid-word, an accepted tradeoff for
   guaranteeing every chunk stays under the embedding model's real limit.
3. **Overlap.** Each new chunk within a section (except the first) is prefixed with the tail end
   of the *previous* chunk's content, sized to `chunk_overlap_tokens` — so a chunk retrieved on its
   own still carries a bit of leading context from what came just before it. Overlap resets at
   section boundaries (see step 1) and is silently dropped rather than allowed to push a chunk over
   `chunk_max_tokens` — the hard token ceiling always wins over the overlap "nice to have."
4. **Token counting** — `app/services/parsing/tokenizer.py` wraps
   [`tiktoken`](https://github.com/openai/tiktoken), resolving the encoding for
   `settings.openai_embedding_model` (`cl100k_base` for the current `text-embedding-3-*` family)
   so chunk sizes are measured against what the embedding model will actually see, not an
   approximation like word count.

**A second real bug caught by testing**: the first version of the packing loop only checked
whether `pending_tokens + block_tokens + overlap_prefix_tokens` exceeded the budget when
`pending_texts` was already non-empty. The very *first* block added to a fresh chunk (right after
a flush) skipped that check entirely — so a chunk could end up with `overlap_prefix + one block`
exceeding `chunk_max_tokens`, silently violating the "no chunk exceeds the token limit"
requirement. `test_chunk_respects_max_tokens` caught this directly. Fixed by introducing
`effective_budget()` (`max_tokens - overlap_prefix_tokens`) and checking every block addition
against it, including the first one in a chunk — with a fallback to drop the overlap entirely if
even a single fresh block wouldn't fit alongside it.

### `chunks` table

One table, deliberately narrow — per the multi-tenant isolation convention, `user_id` is a direct
FK (not just reachable via `document_id` → `documents.user_id` — the convention requires it on the
table itself), and `document_id`/`user_id` both cascade-delete:

- `id`, `document_id` (FK, indexed, `ON DELETE CASCADE`), `user_id` (FK, indexed,
  `ON DELETE CASCADE`), `content` (the chunk's text — this is the source-of-truth store; the
  Qdrant vectors indexed later key back to these rows, not duplicate the text), `metadata` (JSONB),
  `created_at`.
- The Python attribute for the JSONB column is `chunk_metadata`, not `metadata` — naming it
  `metadata` would shadow SQLAlchemy's `Base.metadata` (the schema registry every model shares).
  The actual database column is still named `metadata`, per the schema this table was specified
  with; `mapped_column("metadata", JSONB, ...)` keeps the DB name and Python name independent.
- `metadata` contents: `chunk_index`, `page_number`, `section_path` (list of ancestor heading
  titles), `char_start`/`char_end` (offsets into a canonical concatenation of the source document's
  blocks — computed once, before any chunking/overlap decisions, so the coordinate system doesn't
  depend on how packing happened to group things), `token_count`, `content_hash` (SHA-256, for
  future dedup), and `document_version` (which version of the document produced this chunk).
- A `search_vector` `tsvector` column was added to this table alongside the keyword-search work —
  see
  [Embeddings, indexing & keyword search](#embeddings-qdrant-indexing--keyword-search).

**Replace, not accumulate, on re-processing.** `ChunkRepository.replace_for_document` deletes all
existing chunks for a `document_id` and inserts the new set, in one unit of work with the
`documents.status → ready` flip — a single commit. If parsing/chunking raises at any point before
that (the common case — it's pure computation with no DB writes until it's fully done), *nothing*
has been touched: the previous version's chunks are left exactly as they were. If it fails, the
`chunks` table is left holding a superseded version's data while `documents.status = failed`
clearly signals the mismatch — a deliberate choice (stale-but-present beats empty) rather than
wiping chunks out on a failed re-processing attempt; see `document_version` in each chunk's
metadata for identifying exactly which version they came from.

### tiktoken and the Docker build

`tiktoken` downloads its BPE encoding file over HTTPS on first use unless it's already cached —
which would otherwise mean every fresh worker container needs live internet access just to count
tokens, an unnecessary runtime dependency and a source of latency/flakiness.
`infra/docker/backend.Dockerfile`'s builder stage pre-warms the cache
(`tiktoken.get_encoding("cl100k_base")`) and pins `TIKTOKEN_CACHE_DIR=/app/.tiktoken_cache` in both
build and runtime stages, so the encoding file is baked into the image layer — no network call at
task-processing time.

### Test fixtures

`backend/tests/fixtures/` holds real, valid files per type (`sample.pdf` — 2 pages, a heading per
page; `sample.docx` — nested headings; `sample.md` — headings/list/fenced code; `sample.txt` —
plain paragraphs), generated programmatically with the same libraries that parse them
(`pymupdf`/`python-docx`, both already project dependencies — no extra tooling needed just for
fixtures) rather than hand-authored binary blobs, plus two corrupt files (`corrupt.pdf`,
`corrupt.docx` — valid magic bytes, garbage body) for the failure path. Parser and chunker tests
assert on real, inspectable structure (exact page numbers, exact heading hierarchy, token counts
via the real tokenizer) rather than just "did it run without throwing."

## Embeddings, Qdrant indexing & keyword search

### Embedding service

`app/core/embeddings.py` defines `EmbeddingBackend` (abstract: `embed_batch(texts) -> vectors`)
and `OpenAIEmbeddingBackend`, the only implementation — mirroring `StorageBackend`/
`LocalDiskStorage`'s shape exactly, for the same reason: nothing outside this one file constructs
an OpenAI client or knows the embeddings API's request/response shape, so swapping providers later
means writing one new class, not hunting down scattered API calls. `get_embedding_backend()`
(`lru_cache`d factory) is how callers get one, matching `get_storage_backend()`/
`get_vector_store()`.

- **Model**: `text-embedding-3-large` (`settings.openai_embedding_model`, set from the start), 3072
  dimensions (`settings.qdrant_vector_size` — kept as an explicit paired setting rather than a
  model-name-to-dimension lookup table, since the two are meant to change together deliberately).
- **Batching**: `embed_batch` splits an arbitrary-length input list into sub-batches of
  `embedding_batch_size` (default 100) and issues one API call per sub-batch, concatenating
  results in the caller's original order (the API's own `data[i].index` is honored via an explicit
  sort, not just trusted, in case a provider ever returns out of order) — callers never need to
  think about batch sizing themselves.
- **Rate limits and retries**: handled by the OpenAI SDK's own retry-with-backoff
  (`max_retries=settings.embedding_max_retries`, passed to the `AsyncOpenAI` client constructor),
  not a hand-rolled retry loop on top of it. The SDK already retries the right things (connection
  errors, 429s, 5xx) and leaves genuinely non-retryable errors (like a bad API key) to fail fast —
  reimplementing that classification would just be a worse copy of what the SDK already does
  correctly.

### Qdrant: one shared collection, not one per user

`app/core/vector_store.py`'s `VectorStore` is the only code in the codebase that imports
`qdrant_client` — everything else goes through it, the same "one wrapper class" pattern as
storage and embeddings.

**The collection is shared across all users** (`settings.qdrant_collection`, default
`"documents"`), not split one-per-user. This was a real design choice, not a default left
unexamined:

- Per-user collections would give strong *physical* isolation (a filter bug literally couldn't
  leak another user's vectors, since the wrong collection has no access to them at all) — but
  Qdrant's own guidance is against this pattern at any real scale: each collection carries fixed
  overhead (its own HNSW index and segment files), so thousands of users means thousands of small
  collections, which hurts indexing/query performance and makes routine operations (backups,
  snapshots, listing) harder, not easier.
- This project already made the equivalent call at the Postgres layer early on — one shared
  `documents`/`chunks` table set, with `user_id` as a required filter enforced by convention and
  by every repository method's signature, not by physical separation. A per-user Qdrant collection
  would be an inconsistent isolation model sitting next to that, adding real operational complexity
  for isolation the application layer already owns.
- Isolation here is enforced the same way as everywhere else in this codebase: not by trusting
  every call site to remember a filter, but by not giving call sites the option to skip it.
  `VectorStore.search` **requires** `user_id` — there is no "search everything" method to misuse,
  mirroring how `DocumentRepository.get_for_user` is the only user-facing document lookup and
  `get_by_id` (unscoped) is clearly marked as the one deliberate exception for the background task.

**Payload schema** (per point, keyed by `chunk_id` = the Qdrant point id = the Postgres `chunks.id`
— the join key back to the source-of-truth text, per the chunking design above): `chunk_id`, `document_id`,
`user_id`, `document_version`, `page_number`, `section_path`, `chunk_index`. Deliberately **no
`content`** — Qdrant holds vectors + enough metadata to filter and to look the chunk back up in
Postgres, not a second copy of the text. `user_id` and `document_id` each get a payload index
(`create_payload_index`, `KEYWORD` schema) so filtering by either is an indexed lookup, not a full
collection scan with a post-filter.

A version-compatibility bug surfaced here during verification, not by reading the code: the
`qdrant-client` dependency was declared as `>=1.12.0` with no upper bound, and when this work
ran `uv lock`, that resolved to `1.19.0` — while the Qdrant *server* pinned in `docker-compose.yml`
from the start is still `v1.12.1`. Qdrant's compatibility contract caps the supported client/server
minor-version skew at 1; 1.19 vs 1.12 is well outside that, and the client warned about it loudly
at runtime. Fixed by pinning `qdrant-client>=1.12.0,<1.13.0` to match the running server — the
alternative (bumping the server) was available too, but re-verifying an already-working, already-
pinned infra piece wasn't in scope here.

### Wiring into `process_document`

After chunking (the earlier part of `_process`), the task now: embeds every chunk's text in one
`embed_batch` call, re-checks version staleness (same guard as before, now covering the embedding
call's latency too), persists the new chunks to Postgres (`ChunkRepository.replace_for_document`,
which now also **returns** the created rows so their real `chunks.id` values are available as
Qdrant point ids), replaces the document's Qdrant vectors
(`VectorStore.replace_for_document` — delete-then-upsert, mirroring the Postgres repository's own
delete-then-insert shape), and only then flips `documents.status` to `ready` — all before a single
`session.commit()`. **The document does not reach `ready` unless indexing succeeded too**: if
`embed_batch` or the Qdrant call raises, nothing here has been committed to Postgres, so the
previous version's chunks *and* vectors are left exactly as they were, and the existing retry/
`on_failure` scaffolding (unchanged since the upload/processing work) turns it into a `failed` row
with the error message, same as a parsing failure would.

This means Qdrant and Postgres are updated as two separate calls, not one distributed transaction
— there's no way to make a Postgres commit and a Qdrant upsert atomic across two different
systems without a saga/compensation layer, which is real overkill here. The accepted
tradeoff: if the Qdrant call fails *after* partially deleting old points but before finishing the
upsert, a retry re-runs the *entire* task (re-parse, re-chunk, re-embed — cheap relative to what a
production parsing pipeline will eventually cost, and each step is idempotent to repeat), so the
system self-heals on the next successful attempt. The failure mode in the meantime is "this
document has no vectors for a moment," never "this document returns another version's stale
vectors" — which is exactly the property the task's reprocessing requirement asked for.

### Document deletion

`DocumentService.delete` now calls `VectorStore.delete_for_document` before deleting the Postgres
row — filling in an earlier `TODO`. Postgres cleanup (chunks, and their full-text index —
see below) still needs no explicit code at all: `chunks.document_id` has `ON DELETE CASCADE`, so
deleting the `documents` row removes them automatically. Qdrant isn't Postgres — there's no FK
cascade to lean on — so it's the one part of deletion that has to be spelled out explicitly.

### Keyword search: Postgres full-text search, not `rank_bm25`

A `search_vector` `tsvector` column was added to `chunks` (migration
`1411acc677a2_add_chunks_search_vector_fts_column.py`), `GENERATED ALWAYS AS
(to_tsvector('english', content)) STORED` — Postgres derives and maintains it automatically on
every insert/update, so it can never drift out of sync with `content` the way an app-code-managed
index could if a code path forgot to update it. A GIN index (the standard index type for tsvector
columns — a plain btree, `mapped_column`'s default, doesn't support the `@@` match operator at
all) backs it. `ChunkRepository.search_by_keyword(user_id, query, top_k, document_id=None)` queries
it via `plainto_tsquery` + `ts_rank_cd`, ranked highest first, `user_id` required on every call —
the same "no unscoped method exists" isolation shape as `VectorStore.search`.

`rank_bm25` (an in-memory, pure-Python BM25 implementation, added speculatively in early
scaffolding and never used since) was **removed** rather than used for this. Every worker process
would need to rebuild its entire corpus index from scratch in memory on startup, with no
persistence and no incremental-update story — new, deleted, or edited chunks would need the whole
index refitted, and that index would vanish and need rebuilding again on every restart. That's a
poor fit for a project where everything else (documents, chunks, auth) is Postgres-backed and
durable by default. A `tsvector` column colocated with the data it indexes, using the same backup/
replication/operational story as everything else in this project, is the more production-realistic
choice — matching this section's brief directly.

One honesty note worth being explicit about: Postgres's `ts_rank_cd` is **not** a literal BM25
implementation — it's a different (simpler, TF-based) relevance function. It fills the same
functional role BM25 would (keyword-based candidate retrieval + ranking, to be fused with dense
vector results by RRF further down), and this is the accepted tradeoff for the durability and
operational-simplicity gains above — but it would be inaccurate to call it BM25 anywhere in this
codebase, and this document doesn't.

### Versioning cleanup: both indexes replaced, not accumulated

The upload/parsing work established that a re-upload must fully replace the previous version's
chunks, never mix with them. This section extends that guarantee to both new indexes, for free in
one case and by direct code in the other:

- **Postgres full-text search** needs no new cleanup logic at all: `search_vector` is derived from
  `content` on the same `chunks` rows `ChunkRepository.replace_for_document` already deletes and
  reinserts — when the old rows go, their tsvector entries go with them, automatically.
- **Qdrant** needs the explicit `VectorStore.replace_for_document` call described above — delete
  every existing point for `document_id`, then upsert the new set. There's a narrow window with
  zero vectors for the document between the two calls; a search landing in it returns nothing for
  that document rather than a stale version's content, which is the correct failure mode (see
  "Wiring into `process_document`" above).

Every chunk's Qdrant payload and Postgres `metadata` both carry `document_version`, so even in the
rare case where Postgres holds a superseded version's chunks (a failed re-processing attempt — see
the earlier "stale-but-present beats empty" reasoning) it's always possible to tell, after the
fact, exactly which version any given chunk or vector came from.

## Hybrid retrieval, fusion & reranking

This is the actual retrieval pipeline — no LLM involved yet, that comes later. It combines the two
independent indexes built earlier (Qdrant dense vectors, Postgres full-text keyword search) into
one ranked, filtered, reranked result set, exposed as a standalone, testable service since
retrieval quality is this project's core IP.

### Pipeline

```
query
  │
  ├─▶ embed_query (OpenAI)
  │
  ├─▶ dense search (Qdrant, scoped to user_id)  ─┐        [run concurrently via asyncio.gather —
  │                                                ├─▶ RRF   independent I/O against two systems,
  └─▶ BM25 search (Postgres FTS, scoped to user_id)┘  fusion  not worth paying sequentially]
                                                        │
                                              fetch full text for fused
                                              candidates (Postgres, batched)
                                                        │
                                              cross-encoder rerank
                                                        │
                                                   final top-K
                                          (dense/bm25/rrf/rerank scores attached)
```

`app/services/retrieval/service.py`'s `RetrievalService.retrieve(query, user_id, filters, top_k)`
is the single entry point. Every call requires `user_id` and scopes both retrieval legs to it —
there is no unscoped `retrieve`, the same isolation shape `VectorStore.search` and
`ChunkRepository.search_by_keyword` already had; a dedicated test (`test_retrieve_user_isolation`)
indexes identical content for two different users and asserts each only ever sees their own.

### Reciprocal Rank Fusion (RRF)

Implemented from first principles in `app/services/retrieval/fusion.py` — a pure, dependency-free
generic function (`reciprocal_rank_fusion[T](ranked_lists, k)`), not a library, since explaining
exactly how it works is part of this section's brief:

```
score(item) = Σ 1 / (k + rank)   summed over every ranked list the item appears in
```

`rank` is 1-indexed; `k=60` (`settings.hybrid_search_rrf_k`) is the constant from the original RRF
paper (Cormack, Clarke & Buettcher, 2009) that most hybrid-search implementations since have
converged on. `k` dampens how much exact rank position matters at the top of a list — without it,
rank 1 vs. rank 2 swings a score by 2x (`1/1` vs `1/2`); with `k=60` it's roughly 1.6%
(`1/61` vs `1/62`). That's deliberate: dense (cosine similarity) and keyword (`ts_rank_cd`) scores
live on completely different, incomparable scales, and fusing on *rank* rather than raw score
sidesteps ever having to normalize or compare them directly. An item present in only one list still
gets a score (just a smaller one, from a single contribution) rather than being excluded — RRF
rewards items multiple signals agree on without punishing single-signal hits out of contention
entirely. Verified against hand-computed values in `tests/test_fusion.py` before it was ever wired
into the service.

### Reranking: local cross-encoder, not a hosted API

`app/core/reranker.py` defines a `Reranker` ABC (`rerank(query, candidates) -> [(id, score)]`,
sorted descending) with one implementation, `CrossEncoderReranker`, wrapping
`sentence-transformers`' `cross-encoder/ms-marco-MiniLM-L-6-v2` run locally in a threadpool (so it
never blocks the event loop). This is a distinct, final refinement step over the fused candidate
set rather than a third leg fed into RRF — a cross-encoder scores the query and a candidate's text
*together* in one forward pass, unlike dense/keyword search which score precomputed, independent
representations; too slow to run against a whole corpus, accurate enough to meaningfully reorder a
small (`retrieval_top_k`, default 20) candidate set.

**Local model vs. a hosted reranking API** was a real choice, not a default left unexamined:

- **Cost**: a local model is free per call, forever, after the one-time model download; a hosted
  reranking API (Cohere Rerank, Voyage, etc.) bills per query, which compounds directly with this
  project's usage and adds a second paid dependency next to OpenAI embeddings/chat.
- **Latency**: a local ~22M-parameter MiniLM cross-encoder scores a ~20-candidate batch in
  single-digit-to-low-double-digit milliseconds once warm (see below) — no network round trip.
  A hosted API adds real network latency on the most latency-sensitive leg of the whole pipeline.
- **Tradeoff accepted**: a hosted API's rerankers are generally larger and can be more accurate,
  and running locally means the backend image carries a `sentence-transformers`/`torch` dependency
  (see below) instead of staying a thin HTTP client. For this project's scale and cost profile,
  free + fast + no extra network dependency won.

**Getting `torch` into the image without the default CUDA bundle was its own multi-step problem.**
Adding `sentence-transformers` alone made `uv lock` resolve `torch` from PyPI's default index —
which bundles full CUDA support (~18 `nvidia-*`/`cuda-*` transitive packages, multi-gigabyte) even
though this project only ever runs on CPU (no GPU in dev, CI, or the target deploy). Fixed with
three things together — any one alone was insufficient:

1. `[tool.uv.sources] torch = [{ index = "pytorch-cpu" }]` pointing at PyTorch's dedicated CPU
   wheel index (`download.pytorch.org/whl/cpu`).
2. `[tool.uv] environments = ["sys_platform == 'linux'"]` — `uv lock` resolves a cross-platform
   lockfile by default, and PyTorch's CPU index has no macOS wheels, which was silently causing the
   whole override to be abandoned for a cross-platform lock. Restricting the lock to Linux only is
   also simply correct: this project only ever runs inside Docker.
3. Promoting `torch` to an **explicit direct dependency** in `[project.dependencies]` (previously
   only transitive, via `sentence-transformers`) — the source override does not reliably apply to a
   purely-transitive dependency.

Verified: `torch==2.13.0+cpu` from the `pytorch-cpu` index, zero `nvidia`/`cuda` packages, and
`torch.cuda.is_available() == False` at runtime.

**Model caching mirrors the earlier `tiktoken` pattern exactly, for the same reason**: the model
downloads from Hugging Face on first use unless cached, so the backend Docker image's builder stage
bakes it in (`HF_HOME=/app/.hf_cache`, `CrossEncoder(...)` instantiated once at build time), and the
runtime stage sets `HF_HUB_OFFLINE=1` so it can only ever use that baked-in cache — verified working
fully offline (`docker run --network none`).

**Cold-start latency was a real bug, found by measuring, not by inspection.** The model loads
lazily on first use (an intentional pattern elsewhere in this codebase — see storage/embeddings/
vector-store factories), but that means whichever request happens to be first after a process
starts eats the ~12-second model load inside its own response time, while every request after pays
only the steady-state ~18ms. An app that lazily eats that on a real user's first request is a
latency bug, not a theoretical one. Fixed with `Reranker.warm_up()` (default no-op — a hosted API
reranker has nothing local to load) and a `CrossEncoderReranker` override that forces the load with
a throwaway prediction; `app/main.py`'s FastAPI `lifespan` calls it before `yield`, so the cost is
paid once at container startup instead of on a live request.

### Filters: same shape on both retrieval legs

`RetrievalFilters` (`document_ids`, `file_types`, `created_after`, `created_before`,
`app/services/retrieval/models.py`) is passed identically to `VectorStore.search` and
`ChunkRepository.search_by_keyword`, so a filtered query is consistent across both legs *before*
fusion — filtering only one side would let unfiltered results leak into the fused/reranked output
by riding along on the other leg's candidate list.

- **Qdrant** carries `file_type` and `document_created_at` directly in each point's payload (added
  here, alongside `KEYWORD`/`DATETIME` payload indexes so filtering by them is an indexed
  lookup, not a collection scan) — `document_ids` uses `MatchAny`, `file_types` uses `MatchAny`,
  the date range uses `DatetimeRange`.
- **Postgres** doesn't need those fields denormalized onto every `chunks` row the way Qdrant's
  payload does — `search_by_keyword` joins to `documents` only when a `file_type`/date filter is
  actually requested, and filters directly on `Document.file_type`/`Document.created_at`.

### A real BM25 bug, found by the fixture corpus, not by reading the code

`ChunkRepository.search_by_keyword` originally built its query with `plainto_tsquery` alone, which
ANDs every significant term together. A natural-language query like "what programming language is
good for data science" lost **all** results the moment a single term (here, the filler word
"good") didn't appear anywhere in the corpus — real BM25-style scoring gives partial credit for
term overlap, it doesn't require every query term present. Verified the diagnosis with a raw `psql`
query before touching code. Fixed by converting `plainto_tsquery`'s AND-joined output to an
OR-joined one (`to_tsquery` re-parsing the same normalized term set with `&` replaced by `|`) —
this keeps `plainto_tsquery`'s stopword-removal/stemming (so "what"/"is"/"for" still drop out and
"programming"/"data"/"science" still stem consistently with how `content` was indexed) while fixing
the all-or-nothing matching. Existing `test_chunk_search.py` tests still passed unchanged; new
tests in `tests/test_retrieval_service.py` exercise the fixed behavior directly.

### API surface

`POST /retrieval/search` (`app/api/routers/retrieval.py`, auth-protected via the same
`get_current_user` dependency every other route uses) accepts `{query, filters?, top_k?}` and
returns `{query, results, timings_ms}`, where each result carries `dense_score`, `bm25_score`,
`rrf_score`, and `rerank_score` (each `null`, not `0.0`, if the chunk didn't reach/pass that stage
— `0.0` would wrongly imply "considered and scored low"). Exposing all four scores, not just the
final rerank score, is deliberate: it's what makes the endpoint useful for debugging retrieval
quality now and for the evaluation work later.

### Latency instrumentation

Every stage — `embed_query_ms`, `dense_search_ms`, `bm25_search_ms`, `retrieval_wall_ms` (the
wall-clock time for the concurrent dense+BM25 gather, distinct from the sum of the two, which would
double-count the overlap), `fusion_ms`, `rerank_ms`, `total_ms` — is timed with
`time.perf_counter()` and logged as one structured `retrieval_complete` event (via `structlog`,
matching this project's logging convention from the start), alongside candidate counts at each stage
and whether the query was filtered. This is the most latency-sensitive part of the system, so
per-stage visibility (not just an overall number) is what makes a future regression diagnosable —
"retrieval got slower" vs. "reranking got slower" point at completely different fixes.

## Conversational RAG

This turns the ranked chunk list from retrieval into an actual grounded, cited, streamed answer —
the first point where the product is usable end to end.

### Data model: `conversations` and `messages`

Two new tables, both following the established multi-tenant convention (`user_id` FK on both,
required on every repository method):

- **`conversations`**: `id`, `user_id`, `title` (nullable — set once, from the first user message,
  truncated to 200 chars; mirrors how most chat products title a thread without asking the user to
  name it upfront), `created_at`, `updated_at`.
- **`messages`**: `id`, `conversation_id`, `user_id` (denormalized, same reasoning as `chunks.user_id`
  — see the chunking section above), `role` (`user`/`assistant`), `content`, `rewritten_query` (assistant messages
  only — the standalone query actually sent to `RetrievalService` for this turn), `retrieved_chunk_ids`
  (assistant messages only, JSONB array, **in rerank order** — see "Citation mapping" below for why
  order matters here), `created_at`.

Deliberately **not stored**: a materialized copy of an assistant message's structured citations.
`retrieved_chunk_ids` plus the message's own `content` (which carries the `[n]` markers the model
wrote) is enough to reconstruct them on demand — see below. Storing a second, derived copy would
just be one more place for citation data to drift out of sync with the `content` it describes.

`ConversationRepository` bundles both tables, the same "one repo covers the parent + its owned
child rows" shape `DocumentRepository` already uses for `DocumentVersion`. One method needs calling
out: `touch(conversation)` explicitly bumps `updated_at` — adding a child `Message` row doesn't by
itself mark the parent `Conversation` row dirty, so its `onupdate=func.now()` never fires on its own;
without an explicit touch, the conversation list's "most recently active first" ordering would only
ever reflect creation time, not actual activity.

### Query rewriting

`QueryRewriter` (`app/services/rag/query_rewriter.py`) turns the latest user turn into a standalone
query before it reaches `RetrievalService` — handling follow-ups like "what about page 3?" that
only make sense with conversation history. Two deliberate design choices:

- **Skipped entirely when there's no history.** A first message in a conversation has nothing to
  rewrite; calling an LLM to echo its own input back unchanged would just add latency and cost for
  a guaranteed no-op. Both cases (skip vs. real rewrite) are logged as distinct structured events
  (`query_rewrite_skipped` / `query_rewrite_complete`) so it's visible after the fact which path a
  given turn took.
- **Falls back to the raw query on any rewrite failure** (LLM error, empty completion), rather than
  failing the whole turn. Rewriting is a retrieval-*quality* optimization, not a correctness
  requirement — retrieval still works on the raw follow-up, just possibly worse for a pronoun-heavy
  one. One flaky LLM call shouldn't be able to take down an entire user turn when a strictly worse
  (but working) fallback exists.

History passed to both the rewriter and the answer generator is capped at
`settings.rag_history_max_turns` (default 10, most-recent-first) — an unbounded history would grow
every prompt's token cost and latency without bound over a long conversation. Older turns are
dropped, not summarized; a documented simplification, not an oversight.

### Prompt construction and grounding

`app/services/rag/prompts.py` builds the answer-generation prompt from retrieval's `RetrievedChunk`
list:

- `build_context_block` numbers each retrieved chunk `[1]`, `[2]`, ... in **rerank order**,
  formatted with its source filename and page number, e.g. `[1] (from "handbook.pdf", page 3)`.
  That numbering is what the model is instructed to cite by — see "Citation mapping" below.
- `build_messages` assembles the final chat-completion request: the system prompt, then prior
  conversation turns as plain `role`/`content` pairs (**without** their own context blocks), then
  the *current* turn's context block as one fresh system message, then the question. Only the
  current turn's context rides along — if every past turn's full context block stayed in the
  prompt forever, token cost would grow unboundedly over a conversation and stale, possibly-
  superseded context could bleed into new answers.
- The system prompt (`ANSWER_SYSTEM_PROMPT`) instructs the model to: answer only from the provided
  context; cite every factual claim with its bracketed source number(s) immediately after the
  claim; and explicitly say so — rather than guessing — when the context doesn't contain enough
  information to answer.

### Citation mapping: parse markers, don't re-derive claims

Rather than attempting claim-by-claim NLP attribution after the fact (fragile, and a much harder
problem than it needs to be), citation extraction trusts the system prompt's instruction and just
parses its result: `extract_citations` scans the generated answer text for `[n]` markers with a
regex and resolves each one back to the `RetrievedChunk` it referred to via the `index_map`
`build_context_block` produced. Only markers that actually appear in the answer become citations —
not every chunk that was retrieved, only the ones the model says it used. An unknown marker number
(the model citing `[9]` when only 5 sources existed) is silently dropped rather than raised — a
model output-formatting slip, not something that should crash answer generation.

This same `extract_citations` function is reused for two different situations, unified behind a
small `CitationSource` shape (`chunk_id`, `document_id`, `content`, `page_number`) with two
adapters (`from_retrieved_chunks`, `from_chunk_models`):

1. **At generation time**, sources come straight from `RetrievalService`'s `RetrievedChunk` list.
2. **At read time** (`GET /conversations/{id}`, rendering message history), a past assistant
   message's citations are *reconstructed* from its stored `retrieved_chunk_ids` — re-fetched from
   Postgres by id, re-adapted into `CitationSource`s, and re-scanned against the message's own
   (already-persisted) `content` for `[n]` markers. This only works because `retrieved_chunk_ids`
   preserves the exact rerank order used to number markers at generation time — the `IN`-based
   batch fetch doesn't preserve order on its own, so reconstruction explicitly re-sorts the fetched
   rows back into that stored order before re-numbering them.

### Hallucination mitigation: two layers, one deterministic

1. **Deterministic, pre-generation guard** (`ConversationService.ask`): if `RetrievalService`
   returns no results, or the best `rerank_score` among them falls below
   `settings.rag_min_rerank_score` (`-3.0`, recalibrated from an initial `0.0` guess — see §
   Evaluation methodology for the full story), the turn short-circuits to a canned
   `INSUFFICIENT_CONTEXT_MESSAGE` — the chat completion API is never even called. This is the
   testable behavior the task asked for: it's this path, not model judgment, that guarantees an
   out-of-corpus question gets declined rather than fabricated. Dense k-NN search always returns
   its top-N *something*, even for a wildly irrelevant query, so "no results" alone isn't a
   reliable signal — a genuine relevance threshold on the (real, local) cross-encoder's score is
   what makes this deterministic. Verified during development with real numbers: a relevant chunk
   scored `+9.2`, irrelevant ones scored `-8.6` to `-11.3` (see the retrieval verification above) —
   a comfortable, if inherently heuristic, line between them.
   - **Honesty note**: `rerank_score` isn't a calibrated probability, so this threshold is a
     reasonable heuristic verified against this specific model's observed score distribution, not
     a hard mathematical guarantee. It reliably catches "nothing in the corpus is even topically
     related" (the case the task's test asks for); it does not, by itself, prevent a subtler
     failure mode where retrieved chunks are topically related but don't actually answer the
     specific question asked.
   - Even on this decline path, `retrieved_chunk_ids` is still persisted (whatever low-relevance
     candidates were found) — useful for later debugging *why* a question was declined, not just
     that it was.
2. **Prompt-level instruction** (defense in depth, not deterministic): the system prompt tells the
   model to say so explicitly rather than guess whenever the provided context doesn't answer the
   question — covering the harder case layer 1 doesn't: topically-relevant-but-insufficient context
   that still clears the rerank-score bar.

### Streaming: SSE via `StreamingResponse`, validated before the stream starts

`POST /conversations/{id}/messages` returns a `StreamingResponse` (`text/event-stream`) yielding
three event types: `token` (one per generated delta), `citations` (once, after generation
completes, carrying the final answer's resolved citations + the turn's `rewritten_query` +
`message_id`), and `done`. `ConversationService.ask` is itself an async generator yielding
`AnswerToken`/`AnswerComplete` domain events; the router's job is purely translating those into
SSE-formatted text — a deliberate separation between "what happened" (service) and "how it's
transported" (router).

One correctness detail worth calling out: conversation ownership is checked **before** the
`StreamingResponse` is constructed, not inside the generator. Once a `StreamingResponse` starts,
its 200 status line has already gone out over the wire — the HTTP status can no longer change, so a
missing or foreign conversation must 404 at the router level, synchronously, before any streaming
begins, rather than surface as an in-stream SSE `error` event after already claiming 200.

The frontend (`lib/conversations-api.ts`) can't use the browser's native `EventSource` for this —
it's GET-only and can't carry the JSON request body a chat message needs — so it reads the raw
streamed response body via `fetch` + a `ReadableStream` reader instead, buffering incoming bytes
until each `\n\n`-terminated SSE record is complete before parsing it.

### Frontend chat UI

`app/chat/page.tsx` + `ConversationSidebar`/`ChatMessages`/`ChatComposer`/`CitationChips`
components: a conversation sidebar (list, create, select), a message list with an in-progress
streaming bubble that grows token-by-token, and citation chips on assistant messages. Sending a
message optimistically appends the user's own message immediately (no round trip needed to show
it), then streams the assistant reply in via the SSE parser above; the citations event's payload
(not a second network round-trip) is what finalizes the rendered message once generation completes.

Citation chips expand in place to show the source filename, page number, and excerpt, rather than
linking to a document viewer — there's no per-document, page-addressable viewer route in this app
yet, so a real deep link isn't available to offer. A documented gap, not an oversight; see
"What's deliberately deferred" below.

### Verifying without a real OpenAI key

Consistent with everything since the embeddings work, no real OpenAI API key is available in this
development environment. Automated tests handle this the same way established earlier: a fake
`EmbeddingBackend` and a fake `ChatBackend` (implementing `complete`/`stream_complete` directly, no
HTTP involved) are injected via the same constructor-level dependency injection every service in
this codebase already supports — `tests/test_conversation_service.py` runs the full grounded-answer
path, including the insufficient-context decline, against real Postgres, real Qdrant, and the real
local reranker, with only the OpenAI-backed pieces faked.

For manual, browser-driven verification of the actual streaming UI (not just the underlying logic),
this work added one more technique: a small mock OpenAI-compatible HTTP server (`/v1/embeddings`,
`/v1/chat/completions`, including a real SSE-streaming response) stood up as a throwaway container,
with the live `backend`/`celery-worker` containers pointed at it via the `OPENAI_BASE_URL` env var
the OpenAI SDK already reads automatically. This is different from the fakes above in one important
way: it exercises the *actual* production code path over a *real* HTTP call — proving the SSE
plumbing, citation-chip rendering, and reranker-driven decline all work through the real browser UI,
not just through directly-invoked service code. Reverted immediately after verification; not part
of the shipped stack.

## Production hardening

No new user-facing functionality here — everything below is about making the auth, upload,
retrieval, and conversational functionality already built robust, secure, and observable under
real (including adversarial and degraded) conditions.

### Rate limiting: per-user, not per-IP

`get_rate_limit_key` (`app/core/rate_limit.py`) replaces slowapi's default `get_remote_address` key
function. It decodes the access-token cookie directly (a pure JWT decode, no DB round trip — the
same reasoning `get_current_user` doesn't apply here: slowapi's `key_func` only receives the raw
`Request`) and keys authenticated requests by `user_id`, falling back to IP for requests with no
valid session (`/auth/login` itself, before a token exists; any request that's about to 401
regardless). Per-IP limiting was the wrong shape for the new limits added here: it would let
every user behind a shared NAT/corporate proxy throttle each other, and let one abusive user dodge
a limit just by rotating IPs — neither problem exists with a per-user key. `/auth/register` and
`/auth/login` keep their existing per-IP limit (`auth_rate_limit`, 5/minute) since both are
necessarily unauthenticated.

Three new limits, applied to the endpoints that either call a paid, per-token-billed API or
otherwise do real work, at a meaningfully tighter budget than the auth endpoints' brute-force-
prevention limit needs:

| Endpoint | Limit | Why this one |
|---|---|---|
| `POST /documents/upload` | 20/hour | Triggers async parsing + an OpenAI embeddings call per chunk |
| `POST /retrieval/search` | 30/minute | One OpenAI embeddings call + a local rerank pass per request |
| `POST /conversations/{id}/messages` | 20/minute | Up to two OpenAI calls (rewrite + chat) per turn — the most expensive endpoint in the app |

Each is declared as `@limiter.limit(lambda: get_settings().X)` — a callable, not a plain string.
slowapi re-evaluates a callable limit on every request rather than baking in whatever the string
was at import time; a plain string (what the original auth limit still uses, deliberately left
as-is since nothing needed it to change) is fixed forever once the module first loads. This
matters for two reasons: it's what let this section's rate-limit tests monkeypatch a real, low
limit and get fast,
deterministic 429s instead of needing to actually exhaust a 20/hour production limit end to end, and
it's a small step toward these limits being tunable without a full redeploy if that's ever wired to
something other than env vars later.

**A real, verification-driven finding**: `headers_enabled` defaults to `False` in slowapi's
`Limiter` — meaning, before this work, `/auth/login`/`/auth/register`'s existing 429 responses
never actually carried `Retry-After` or `X-RateLimit-*` headers at all, silently. Fixed by passing
`headers_enabled=True`. That surfaced a second, sharper bug: slowapi's per-route header injection
only works when the decorated endpoint either returns a `Response` directly or declares a
`response: Response` parameter FastAPI can inject — every endpoint here that returns a plain ORM
object (relying on `response_model` for serialization, the pattern used throughout this codebase
from the start) doesn't have one. Without it, slowapi's header-injection code raises internally,
turning *every* rate-limited endpoint's response — success or failure — into a 500. Fixed by adding
`response: Response` to `register`, `upload_document`, and `search` (`post_message` already returns
a `StreamingResponse` directly, which satisfies slowapi's check on its own). Caught by the full test
suite immediately after flipping `headers_enabled` on — not by reading slowapi's source first.

Also enabled: `in_memory_fallback_enabled=True`, so a Redis outage degrades rate limiting to a
per-process in-memory count rather than taking every request down with it — see § Graceful
degradation below for the general principle this follows.

### Security posture

- **CORS**: already environment-driven from the start (`settings.cors_origins`, defaulting to just
  `http://localhost:3000`, never a wildcard by default). This section adds a startup-time guard
  (`validate_production_settings`, `app/core/startup_checks.py`) that refuses to boot outside
  `local`/`test` if `cors_origins` contains `"*"` — a wildcard combined with `allow_credentials=True`
  (required here, since auth is cookie-based) would let any site read this API's authenticated
  responses. A misconfiguration should crash loudly at startup, not run quietly and insecurely.
- **JWT secret**: the same startup guard refuses to boot outside `local`/`test` if `jwt_secret_key`
  is still `"change-me-in-env"` (the checked-in placeholder default). A wrong-but-quiet default is
  far more dangerous than a loud crash on boot — it can run in production for months unnoticed.
- **JWT secret rotation story**: deliberately not a dual-secret fallback mechanism — rotating
  `jwt_secret_key` and redeploying only ever invalidates outstanding **access** tokens, which are
  short-lived (`jwt_access_token_expire_minutes`, 15 by default) by design. Refresh tokens are
  opaque, DB-backed, hashed random strings (established during auth), not JWTs — rotating the JWT secret doesn't
  touch them at all. A client holding a suddenly-invalid access token gets one 401, which the
  frontend already handles by falling back to `/auth/refresh`; the blast radius of a rotation is
  bounded to at most 15 minutes of transparently-recovered 401s, not a mass logout. That bound is
  what makes a simple single-secret design sufficient here — a busier or more failure-sensitive
  deployment would want a `kid`-header-based multi-key scheme instead, but that's solving a problem
  this app's token lifetimes don't actually have.
- **Security headers** (`SecurityHeadersMiddleware`, `app/core/security_headers.py`):
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy:
  strict-origin-when-cross-origin` on every response; `Strict-Transport-Security` added outside
  `local`/`test` only — HSTS tells a browser "always use HTTPS for this host from now on," which is
  actively wrong advice for plain-http local dev and would lock a developer's browser out of
  `http://localhost` until it expired.
- **SQL injection**: audited directly — grepped the codebase for any raw string interpolation into
  SQL (f-strings/`.format()`/`%` near `execute(`/`text(`). Found none: every query in this codebase
  goes through SQLAlchemy's ORM/Core query builder or `func.*()` helpers (e.g. the keyword-search
  and retrieval work's `func.plainto_tsquery`/`func.to_tsquery` full-text search construction),
  which parameterize
  automatically. This was expected — the task explicitly called it "should already be fine via
  ORM/parameterized queries — verify" — and verification confirmed it, rather than finding a gap.
- **Secrets never logged**: also audited directly — grepped every `logger.*()` call site in the
  codebase for anything resembling `password`/`token`/`secret`/`api_key`. None found. Structured
  logging's kwargs-based call shape (`logger.info("event", key=value, ...)`, used throughout from
  the start) makes this easy to keep true going forward too — a reviewer scanning a log call's kwargs
  for a credential-shaped value is a much easier review than auditing an arbitrary f-string.
- **Dependency vulnerability scanning**, wired into CI for both halves of the app:
  - **Backend**: `pip-audit`, run as a CI step. One finding: `ecdsa` (a transitive dependency of
    `python-jose[cryptography]`, used for JWT handling) has an open advisory (`PYSEC-2026-1325`,
    the long-standing Minerva timing-side-channel issue in pure-Python ECDSA implementations) with
    no fix version available. Explicitly ignored via `pip-audit --ignore-vuln PYSEC-2026-1325`, not
    silently — and genuinely unreachable here: this app signs JWTs exclusively with HS256 (pure
    HMAC), configured in `settings.jwt_algorithm` since auth was first built, and never exercises
    `ecdsa`'s ECDSA code path at all.
  - **Frontend**: `npm audit`, run twice in CI — a hard gate (`--omit=dev --audit-level=critical`,
    currently 0 findings) and a full, non-blocking report (`npm audit || true`) for visibility. The
    full picture: 3 high-severity findings in production dependencies (`next`, transitively via
    `postcss`/`sharp`) and a critical + moderates confined entirely to dev-only build tooling
    (`vitest`/`vite`/`esbuild`, never shipped). `npm audit fix` (the non-breaking form) can't clear
    any of it — the only available fix pulls in `next@16`, a major-version bump this hardening pass
    deliberately doesn't attempt with no feature-testing budget attached. The `next`/`sharp` finding
    specifically concerns image-optimization code paths this app doesn't exercise (no `next/image`
    usage anywhere in the codebase — checked directly). Tracked, not silently ignored; a real
    dependency upgrade is future work, not solved here.

### Structured logging: request ID tracing across the sync/async boundary

`RequestContextMiddleware` (`app/core/request_context.py`) binds a `request_id` — read from an
incoming `X-Request-ID` header if an upstream proxy already set one, otherwise a fresh UUID — into
`structlog.contextvars` for the life of each request, and echoes it back on the response. Because
`structlog.contextvars.merge_contextvars` has been in this project's shared log-processor chain
from the start, *every* log line emitted anywhere during that request — this middleware, a router, a
service, deep inside `RetrievalService`'s own per-stage logging — automatically carries the same
`request_id`, with zero changes needed at any of those call sites.

**A real gap found and fixed here**: `configure_logging()` was never being called for the
Celery worker process at all. Nothing in the worker's import chain calls it — only `app/main.py`
does, and the worker process never imports that module — so every task log was going out through
Celery's own default plain-text formatter, not structlog, and could never carry `request_id`
context. This would have silently defeated the entire point of this tracing work for the
one place it matters most: correlating an upload request with the async task it enqueues, which can
run seconds or minutes later in a different process. Fixed by connecting to Celery's `setup_logging`
signal (`app/core/celery_app.py`) — connecting at all tells Celery "don't configure your own
logging, I'm doing it" — and calling `configure_logging()` from the handler. `process_document`
(`app/tasks/document_processing.py`) now also switched from `celery.utils.log.get_task_logger` to
this project's own `get_logger`, matching the structured-kwargs call shape used everywhere else
instead of the old `%`-style formatting it had used originally.

`DocumentService.upload` reads the current request's `request_id` out of `structlog.contextvars`
and passes it through as an explicit `process_document.delay(..., request_id=request_id)` argument;
the task binds it (alongside Celery's own per-attempt `task_id`, which — unlike `request_id` — is
distinct on every retry of the same logical upload) into its own contextvars at the top of
`process_document`. The result: grep any request's `request_id` across both the API's and the
worker's logs, and every step of that request's lifecycle — the HTTP call that enqueued it, and
everything the worker did to it afterward — comes back as one trace, even though they ran in
different processes, possibly minutes apart.

### Observability: Prometheus-style metrics

`app/core/metrics.py` defines four `prometheus_client` collectors, exposed in standard scrape
format at `GET /metrics` (`app/api/routers/metrics.py`):

- `http_request_duration_seconds` (histogram; `method`, `path`, `status` labels) — every request,
  recorded by `RequestContextMiddleware`. `path` is the route's *template* (e.g.
  `/documents/{document_id}`), read from `request.scope["route"]` after routing has completed —
  never the raw resolved URL, which would mint an unbounded number of time series (one per distinct
  UUID ever requested). A request matching no route at all is labeled `"unmatched"` for the same
  reason.
- `retrieval_stage_duration_seconds` (histogram; `stage` label) — one observation per stage per
  `RetrievalService.retrieve()` call (`embed_query`, `dense_search`, `bm25_search`, `fusion`,
  `rerank`, `total`, plus the `retrieval_wall` concurrent-gather wall-clock time). A second,
  queryable-as-a-distribution view of the exact same numbers the retrieval pipeline's own
  `retrieval_complete` log event already carries — not a replacement for that log line, a
  complementary one.
- `llm_call_duration_seconds` (histogram; `provider`, `call_type` labels) — every outbound OpenAI
  call: `embed`, `chat_complete` (query rewriting), `chat_stream` (answer generation).
- `llm_tokens_total` (counter; `provider`, `call_type`, `token_type` labels) — prompt/completion/
  total token counts, read from each OpenAI response's own `usage` field. Streamed chat completions
  don't report `usage` by default at all; getting it requires explicitly passing
  `stream_options={"include_usage": True}`, which `OpenAIChatBackend.stream_complete` now does — the
  usage arrives as a final, content-less chunk after the real content.

**How this would feed a dashboard in a real deployment** (no Prometheus/Grafana stood up in this
repo — deliberately deferred, since standing up a full metrics stack is a bigger infra lift than
this section's scope): a Prometheus server would scrape `GET /metrics` on an interval
(the endpoint is deliberately unauthenticated, matching how Prometheus itself scrapes — it has no
session cookie to send — but in production it belongs restricted at the network/ingress level, not
exposed publicly, the same way this repo's own `docker-compose.yml` never publishes it outside the
Docker network today). From there:
- p50/p95/p99 request latency per endpoint: `histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket[5m]))`, grouped by `path`.
- Which retrieval stage regressed: the same `histogram_quantile` pattern over
  `retrieval_stage_duration_seconds`, grouped by `stage` — directly answers "did retrieval get
  slower, or did reranking get slower" without guessing.
- LLM cost tracking: `sum(rate(llm_tokens_total[1h])) by (call_type, token_type)` multiplied by a
  per-token price gives a live cost-rate panel; a sudden spike in `chat_stream`/`completion` tokens
  would be the first sign of a runaway or looping conversation.
- Alerting: a Grafana/Alertmanager rule on `http_request_duration_seconds{status=~"5.."}` rate, or
  on `llm_call_duration_seconds` p99 crossing a threshold (an early signal OpenAI itself is
  degraded, ahead of users noticing).

### Error handling: one consistent shape, graceful degradation

Every error response across the API now returns the same JSON shape, `{"detail": "..."}` —
already true for `HTTPException` (FastAPI's default) and Pydantic validation errors; this section
extends it to the two cases that previously had no consistent handling at all:

- **Downstream dependency unavailable** (`app/core/error_handlers.py`): `openai.APIConnectionError`,
  `openai.APITimeoutError`, `openai.RateLimitError`, `openai.InternalServerError`, and Qdrant's
  `ResponseHandlingException` (verified empirically — pointing an `AsyncQdrantClient` at an
  unreachable host raises exactly this, wrapping the underlying `httpx` connection error, not some
  Qdrant-specific type) are all mapped to `503` with a generic "temporarily unavailable, try again
  shortly" message. The streaming conversation endpoint (`POST /conversations/{id}/messages`) can't
  use this — its response has already committed to `200` before generation starts — so it catches
  the same exception tuple inside its own SSE loop and yields a labeled `error` event instead; see
  the conversational RAG streaming design above for why the HTTP status can't change mid-stream.
- **Anything else unexpected**: a catch-all `Exception` handler logs the real exception (full
  traceback, via `logger.exception`, with the request's `request_id` already bound) server-side and
  returns a generic `500` — never the exception's own message, which could leak internal detail (a
  stack frame, a DB error naming a column, a file path). Verified directly with a test that raises a
  `RuntimeError` containing a fake credential string and asserts it never appears in the response.

**Two real bugs found by chaos-testing this, not by reading the code**:

1. **A crashed session, not a clean 503.** The first version of the Qdrant-down test didn't get a
   503 — it got an `asyncpg.exceptions.InterfaceError: cannot perform operation: another operation
   is in progress` and, in one run, hung entirely. Root cause: `RetrievalService.retrieve()` runs
   the dense (Qdrant) and keyword (Postgres) search legs concurrently via `asyncio.gather`. Plain
   `asyncio.gather` cancels every other pending task the instant one of them raises — and cancelling
   the bm25 leg mid-flight cancels an in-progress query on the request's single shared
   `AsyncSession`. asyncpg does not tolerate a query being abandoned mid-flight this way: the
   connection is left in a broken protocol state that then blows up on the next thing that touches
   it, including the session's own cleanup in `get_db`'s teardown. Fixed by switching to
   `asyncio.gather(..., return_exceptions=True)` and re-raising the first real exception only after
   *both* legs have actually finished — the small cost of occasionally letting a doomed bm25 query
   run to completion is far cheaper than a poisoned connection. This is exactly the class of bug
   chaos testing exists to catch: it never reproduces under a normal, both-succeed request.
2. **A 500 with none of this work's own new headers on it.** Starlette/FastAPI unconditionally
   wraps everything added via `app.add_middleware()` inside `ServerErrorMiddleware` — registering a
   handler for bare `Exception` (as `register_error_handlers` does) makes it *that* middleware's
   handler, not a normal one `ExceptionMiddleware` dispatches to, and `ServerErrorMiddleware` is the
   true outermost layer around the whole app regardless of `add_middleware` call order. Concretely:
   a genuinely unhandled exception's `500` response was shipping with **no CORS headers, no
   `X-Request-ID`, no security headers at all** — verified directly by forcing one end to end and
   inspecting the response. A browser's `fetch()` (this frontend always calls with `credentials:
   "include"`) treats a cross-origin response missing CORS headers as an opaque network failure, not
   a readable error — silently hiding every real production crash from both the user and any
   client-side error tracking, and stripping the one header (`X-Request-ID`) most needed to debug
   it. Fixed in `app/main.py` by constructing `CORSMiddleware`/`RequestContextMiddleware`/
   `SecurityHeadersMiddleware` directly around the whole app (`_wrap_with_outer_middleware`) instead
   of via `add_middleware` — genuinely outside `ServerErrorMiddleware`'s boundary rather than
   nominally "added to the app." `SlowAPIMiddleware` stays on the inside; it depends on
   `request.app.state.limiter`, which is only set once a request has actually entered the FastAPI
   instance. A regression test (`test_unexpected_exception_response_still_carries_cors_and_tracing_headers`)
   forces the same failure and asserts all three header families survive it.

### Graceful degradation

The general principle threading through this section's error handling and rate limiting: a failure in
one dependency should degrade that one capability, not cascade into taking the whole service down.
Concretely, three instances of it: OpenAI or Qdrant being unreachable turns into a clean `503`
(above) rather than a crash; a Redis outage degrades rate limiting to a per-process in-memory count
(`in_memory_fallback_enabled=True`) rather than failing every request; and the reranker's `warm_up()`
(established during the hybrid-retrieval work) already meant a slow model load happens once at
startup, not silently inside a user's first real request.

## Evaluation methodology

The per-stage retrieval scores and the conversational RAG citations were both built with
evaluation in mind, but neither is itself an evaluation — asserting "retrieval returns
*something*" (the existing test suite) is a different claim from "retrieval returns the *right*
thing more often with fusion+reranking than without it." This closes that gap: `eval/` is a
self-contained harness, separate from `backend/tests/`, that runs the real retrieval pipeline and
generation building blocks against a hand-labeled dataset and reports standard IR + LLM-judge
metrics — not an assertion that a metric crosses some bar (that would just move the "trust me"
problem into a threshold nobody validated), but a report, read by a person, alongside an honest
account of where and why the system falls short (`eval/RESULTS.md`).

### Layout

```
eval/
  datasets/knowledge_base_eval.json   # queries + labeled relevant chunks + reference answers
  datasets/documents/                 # the 3 fixture source documents (2 md, 1 real multi-page PDF)
  metrics/retrieval_metrics.py        # Recall@K, MRR, NDCG — pure functions, no I/O
  metrics/generation_metrics.py       # LLM-as-judge faithfulness/relevance — prompts + parsing
  fakes.py                            # synthetic embedding/chat/judge/reranker fallbacks
  corpus.py                           # indexes the fixture docs through the real parsing/embedding pipeline
  run_eval.py                         # CLI: runs everything, writes a JSON report + prints a table
  tests/                              # unit tests for the metrics modules themselves
  results/                            # generated reports (gitignored; RESULTS.md documents figures)
```

It intentionally lives outside `backend/`'s package and its own `pytest` config (`testpaths =
["tests"]` scopes the main suite to `backend/tests/` so `eval/`'s tests never get pulled into that
run's coverage gate by accident) — this is deliberately a separate, optional tool, not a 22nd
service class the main suite is expected to exercise on every push.

### The labeled dataset and content-marker resolution

`knowledge_base_eval.json` hand-labels 21 queries against 3 fixture documents (an employee
handbook, an engineering-practices doc, and a real 4-page PDF generated with PyMuPDF so its page
numbers are genuine, not estimated — see the earlier page-estimation caveat). The query mix is
deliberate, not incidental: single-chunk lookups, two multi-chunk queries (the right answer spans
two sections), one cross-document discriminator (two documents both mention "PTO" for unrelated
reasons, testing whether retrieval finds the one that's actually relevant rather than matching on
the shared term), two PDF-page-specific queries, and one deliberately out-of-corpus question to
exercise the decline path from the conversational RAG work.

A chunk's id doesn't exist until after indexing, so the dataset can't reference chunk ids directly.
Instead each labeled "relevant chunk" is a short, unique substring of the source document
(`content_marker`) — `eval/corpus.py` resolves these to real chunk ids after indexing by
substring-matching (whitespace-normalized, so a marker isn't broken by where the source text
happens to wrap) against each chunk's actual persisted content. If a marker doesn't match anything
post-indexing, the harness aborts loudly rather than silently scoring against an empty or wrong
ground truth — a dataset/parser mismatch here would otherwise corrupt every downstream number.

### Retrieval evaluation: three variants, one fetch depth

For every query, `run_eval.py` runs three retrieval configurations at equal fetch depth (`top_k`,
default 10, overriding the production default so all three are directly comparable): dense-only
(`VectorStore.search` called directly), BM25-only (`ChunkRepository.search_by_keyword` called
directly), and the full production path (`RetrievalService.retrieve`, i.e. RRF fusion + rerank).
Each is scored with Recall@3, Recall@5, MRR (over the full fetched list, not truncated), and
NDCG@5 (`eval/metrics/retrieval_metrics.py` — pure functions, unit-tested in `eval/tests/`,
independent of any DB or LLM). Recall/MRR/NDCG are all defined as `None` for a query with no
labeled relevant chunks (the out-of-corpus query) rather than counted as 0 — averaging a
zero in for a query that has no correct answer would misrepresent an intentional non-answer as a
retrieval failure.

### Generation evaluation: LLM-as-judge, not NLI

Faithfulness (is the answer grounded in the retrieved context?) and answer relevance (does it
address the question?) are scored via LLM-as-judge rather than an off-the-shelf NLI model. The
reasoning (documented at length in `eval/metrics/generation_metrics.py`'s module docstring): this
system's answers are multi-sentence and often synthesize across more than one retrieved chunk, and
NLI models score single (premise, hypothesis) sentence pairs — reducing an answer to sentence pairs
and aggregating would lose exactly the cross-claim reasoning being evaluated, and adds a second
model's calibration problems on top. An LLM judge can be given the same plain-language rubric a
human reviewer would use and can explain *why* it scored what it scored, and this system already
depends on an LLM chat backend for generation itself — reusing that interface for judging adds no
new dependency. The known tradeoff, stated rather than glossed over: an LLM judge can share blind
spots with the generation model (especially when they're the same model, as here — cost reasons,
not a considered choice of a stronger separate judge), and its scores are noisier than a human's;
treat these numbers as a regression signal over time, not ground truth. Both rubrics are 1–5 Likert
scales (more reliable for an LLM to produce consistently than a raw continuous score),
`_normalize`d to `[0, 1]`; the relevance rubric explicitly instructs the judge not to penalize an
honest decline as irrelevant when the question genuinely can't be answered from the context.

### Environment-aware backend selection: real vs. synthetic

`run_eval.py::detect_mode` checks `settings.openai_api_key` against `None`/empty/the
`.env.example` placeholder (`sk-changeme`) and switches every OpenAI-backed component — embeddings,
answer generation, and the judge — to a deterministic, offline synthetic stand-in (`eval/fakes.py`)
rather than failing the whole harness for lack of a paid key: a hashing-trick bag-of-words
embedding, an extractive answer generator that stitches together the most lexically-overlapping
retrieved sentence(s) with citation markers, and a lexical-overlap heuristic judge that mimics the
real judge's JSON output shape. **The local cross-encoder reranker and Postgres FTS need no API key
and always run for real, in both modes** — only the OpenAI-backed legs fall back. Every report's
`meta.mode` field and the printed summary banner say plainly which mode produced a given run's
numbers, because they are not comparable; `eval/RESULTS.md` documents this explicitly rather than
letting a reader mistake a synthetic-mode number for a real one.

### A real finding, not a synthetic artifact: `rag_min_rerank_score` was uncalibrated — now fixed

Running the harness (in synthetic-embedding mode, but against the **real** local reranker) surfaced
a genuine issue independent of synthetic mode: one query retrieved the exactly correct chunk at
rank 1, with the real cross-encoder's rerank score comfortably ahead of every alternative
(`-1.64` vs. `-9.79` and lower) — but still below `rag_min_rerank_score`'s then-default of `0.0`, so
the system declined to answer a question it had actually retrieved the right context for. The
cross-encoder's raw output is an unbounded classifier logit, not a 0–1 relevance probability, so
"below zero" doesn't reliably mean "not relevant."

Rather than patch that one query, every query's rerank score was pulled to see the actual
distribution: 19 of 20 true positives scored `+2.54` to `+10.25`, the one outlier scored `-1.64`,
and the dataset's one labeled negative (the out-of-corpus query) scored `-9.85`. `rag_min_rerank_score`
was moved from `0.0` to **`-3.0`** — comfortably clearing the observed outlier with margin (~1.4)
without being pushed anywhere near the one observed negative (~6.8 of headroom left), since a
single labeled negative isn't enough evidence to trust the full gap as safe. Re-running the harness
after the change confirmed the fix (21/21 abstention-correct, up from 20/21) with retrieval metrics
unchanged (only the accept/decline cutoff moved, not the ranking) and the existing test suite still
green, including the one test whose real cross-encoder score this threshold change could plausibly
have affected (`test_ask_declines_when_no_relevant_context`, which depends on a real, unrelated
query scoring low against a real, unrelated corpus). Full score table and narrative in
`eval/RESULTS.md`. `app/core/config.py`'s field comment records the same reasoning next to the
value itself. This is exactly the calibration work a labeled eval dataset is for, and the
`content_marker` labeling makes it straightforward to grow the negative-example count and revisit
this threshold again with more evidence, rather than treating `-3.0` as any less a heuristic than
`0.0` was — it's a better-informed heuristic, not a proof.

### Running it

```bash
cd backend
uv run pytest ../eval/tests           # metrics module unit tests — fast, no infra needed
uv run python ../eval/run_eval.py     # full harness — needs a migrated Postgres + Qdrant
```

Wired into CI as a separate `eval` job on `.github/workflows/ci.yml`, gated to `workflow_dispatch`
only (not every push/PR) — a real-mode run makes on the order of 40 OpenAI calls across the
dataset (embeddings + generation + judge), which is real cost and latency for a signal that
doesn't change every commit, unlike the main `backend`/`frontend` jobs. An optional
`OPENAI_API_KEY` repository secret switches that job to real mode; left unset, it still completes
in synthetic mode and uploads its JSON report as a build artifact either way.

## Configurable LLM & embedding providers

Every phase up to this point assumed a funded `OPENAI_API_KEY` was available for the *running
application* (tests and the eval harness already had synthetic fallbacks — see § Evaluation
methodology — but the live app itself had no path that didn't call OpenAI). That assumption broke
in practice: a real key configured in this environment turned out to belong to an account with no
available quota (`insufficient_quota`, confirmed directly against the OpenAI API, not just this
app), which meant document processing and chat both failed outright, every time, with no way to
demonstrate the product working end to end without paying OpenAI first. This section is the fix —
not "add billing," but removing the hard dependency itself.

### Local embeddings by default

`EmbeddingBackend` (`app/core/embeddings.py`) gained a second implementation,
`LocalEmbeddingBackend`, running `BAAI/bge-small-en-v1.5` via `sentence-transformers` — the same
library already a hard dependency for the reranker, so this added no new Python package, just a
second model. `embedding_provider` (`local` | `openai`, default `local`) selects which one
`get_embedding_backend()` builds. Mirrors the reranker's pattern throughout: lazy load on first use
in a worker thread (`run_in_threadpool`, never blocks the event loop), a `warm_up()` hook so the
cost is paid once at process startup rather than inside a user's first request (called from both
`app/main.py`'s `lifespan` — this process also embeds query text directly, not just the Celery
worker embedding uploaded documents — and a new `worker_ready` Celery signal handler in
`app/core/celery_app.py`), and baked into the Docker image at build time
(`infra/docker/backend.Dockerfile`) so there's no runtime network dependency once built.

`qdrant_vector_size`'s default moved from `3072` (`text-embedding-3-large`'s dimensionality) to
`384` (`bge-small-en-v1.5`'s) to match. This is a genuinely breaking change for anyone with an
existing Qdrant collection built against the old default — Qdrant's collection dimensionality is
fixed at creation time, so switching `embedding_provider` (or upgrading into this default) against
an existing collection fails loudly on the first write with a dimension mismatch, not silently. Hit
exactly this directly during verification: this project's own long-lived local dev `.env` still had
the old `3072` explicitly set, and the first local-embedding test run correctly failed until it was
updated — the failure mode worked exactly as designed, just against this repo's own dev environment
first.

### Configurable chat: Ollama by default, OpenAI still available

`ChatBackend` gained `OllamaChatBackend` (`app/core/chat.py`), talking to a local Ollama server's
native `/api/chat` endpoint (not the OpenAI-compatible shim Ollama also exposes — the native API
reports prompt/completion token counts directly in the response body, which the compat shim
doesn't, and this app already has a token-usage metric to feed). `chat_provider` (`ollama` |
`openai`, default `ollama`) selects which `get_chat_backend()` builds; both implement the exact
same interface, so `ConversationService`, `QueryRewriter`, and everything else downstream of
`get_chat_backend()` needed zero changes; `httpx` (already a dev-only test dependency, for the ASGI
test transport) was promoted to a real one now that `OllamaChatBackend` uses it directly.

Unlike the reranker/embedding models (small, free, baked into the image), a real LLM isn't
something to bundle into the app's own Docker image — `infra/docker-compose.yml` and
`docker-compose.prod.yml` both gained an `ollama` service (the official `ollama/ollama` image) and
a one-shot `ollama-init` service that runs `ollama pull ${OLLAMA_CHAT_MODEL}` against it
(`OLLAMA_HOST=ollama:11434` pointed at the sibling container, the standard way to direct the Ollama
CLI at a non-default server) before exiting — the same `service_completed_successfully`
dependency-gating pattern `docker-compose.prod.yml`'s `migrate` service already established, so
`docker compose up` alone is still the whole story, never a separate manual pull step. The default
model (`llama3.2:3b`) is a real, deliberate tradeoff: small enough for reasonable CPU inference
latency in a self-hosted/portfolio context, at some cost to answer quality relative to a larger
model — swappable via `OLLAMA_CHAT_MODEL` with no code change. The one real cost this doesn't hide:
first boot now pulls a multi-GB model, changing this repo's "one command, fast" quickstart story —
cached in the `ollama_data` volume after, so every boot after the first is unaffected. `ollama` (and
its published port, in the dev compose file only) follows the same internal-services-publish-nothing
rule as Postgres/Redis/Qdrant in `docker-compose.prod.yml`.

### Actionable errors instead of one generic message

`app/core/llm_errors.py::classify_llm_error` sits between two extremes this project had already
committed to elsewhere: a single generic "temporarily unavailable" (harmless but useless for
actually fixing anything) and dumping `str(exc)` verbatim (which `error_handlers.py`'s unhandled-
exception path deliberately never does — see § Error handling — for good reason, since an arbitrary
exception's message can contain a stack frame, a DB error naming a column, a file path). The
resolution: the small, closed set of *known, expected* downstream-dependency failure modes (wrong
API key, no quota, a local service unreachable) are not sensitive internal detail — naming them
specifically is safe and actually helps — so they get their own actionable message; anything
unrecognized still falls back to the original fully generic one, preserving that guarantee for the
unknown case.

Two OpenAI failure categories needed distinguishing that look identical at the exception-class level
(`openai.RateLimitError` fires for both): verified directly against a real OpenAI account (not
assumed from documentation) that the exception carries a `.code` attribute directly —
`"insufficient_quota"` for a billing problem, some other value (e.g. `"rate_limit_exceeded"`) for
actual throttling — so the message can tell an operator "your account has no quota, check billing"
apart from "you're being rate-limited, try again shortly," which need genuinely different responses.
`openai.AuthenticationError` similarly carries `.code == "invalid_api_key"`. `httpx.ConnectError`/
`ConnectTimeout` (Ollama unreachable) and `ResponseHandlingException` (Qdrant unreachable) round out
the known set. Applied in both places a downstream failure can surface: the plain REST 503 path
(`error_handlers.py`) and the conversational SSE `error` event (`conversations.py`) — the latter
previously hardcoded the same generic string inline; now both go through the one classifier, so
there's a single place that knows about every provider's failure shapes.

### Verification

`docker compose -f infra/docker-compose.yml up` was rebuilt and re-run end to end against the new
defaults (`EMBEDDING_PROVIDER=local`, `CHAT_PROVIDER=ollama`, no `OPENAI_API_KEY` required at all)
following the exact pipeline stated as the acceptance target: upload → processing → chunking →
embeddings → Qdrant → question → retrieval → LLM generation → cited answer. See `docs/PROGRESS.md`
for the specific run and what it confirmed, including timing for the local reranker + local
embedding model + local LLM all running together on CPU.

## Infra

### Docker

Both `backend.Dockerfile` and `frontend.Dockerfile` are multi-stage:

- **Backend**: `uv sync` in a builder stage populates `/app/.venv`, then a slim runtime stage
  copies only the venv + app code, drops to a non-root user, and runs `uvicorn`.
- **Frontend**: dependencies install in a `deps` stage, `next build` (with `output: "standalone"`)
  runs in a `builder` stage, and the runtime stage copies only the standalone server output —
  no `node_modules`, no dev dependencies, no source maps in the final image.

Both images run as non-root users and declare `HEALTHCHECK`s.

The frontend runtime stage pins `ENV HOSTNAME=0.0.0.0`. Docker auto-injects a `HOSTNAME` env var
equal to the container ID; Next's standalone `server.js` binds to `process.env.HOSTNAME` if set,
so without this override the server bound to the container's internal IP instead of all
interfaces, and its own `localhost`-based healthcheck failed. This was caught during initial
verification (`docker compose ps` showed the container permanently `unhealthy`), not by
inspection — worth remembering for any future Next.js standalone image.

### docker-compose

`infra/docker-compose.yml` brings up the full local stack: `postgres`, `redis`, `qdrant`,
`backend`, `celery-worker` (a real consumer — `process_document` — alongside the original `ping`
proving-the-wiring task), and `frontend`. Service dependencies use `condition: service_healthy`
where a healthcheck exists, so `backend` won't start until Postgres/Redis/Qdrant actually accept
connections.

`backend` and `celery-worker` share a `uploads_data` named volume mounted at `/data/uploads`
(matching `settings.upload_dir`) — both need to see the same files: `backend` writes them on
upload, and `celery-worker` reads them back to actually parse and chunk.

`celery-worker` also `depends_on: qdrant (service_healthy)` — added once the worker
started actually writing to Qdrant, not just Postgres; `backend` already had this dependency
from early on (Qdrant was stood up early even though nothing used it until later).

`celery-worker` builds from the same image as `backend` (same Dockerfile, different `command`),
so it inherits the image's `HEALTHCHECK` unless overridden. The backend's `HEALTHCHECK` curls its
HTTP `/health` endpoint, which the worker doesn't serve — compose overrides it with
`celery -A app.core.celery_app inspect ping`, the Celery-native equivalent. Same lesson as above:
image-level `HEALTHCHECK` doesn't compose with reusing an image for a different process; override
it per-service.

### CI

`.github/workflows/ci.yml` runs two independent jobs on every push: `backend` and `frontend`, plus
a third, `eval`, gated to manual `workflow_dispatch` only — see § Evaluation methodology for why
that one isn't on every push. `frontend` is npm install → eslint → tsc --noEmit → vitest. `backend` runs against real
Postgres, Redis, **and Qdrant** service containers (not mocks — consistent with how
these are verified everywhere else in this project): uv sync → ruff lint → `alembic upgrade head`
→ pytest. Running migrations as an explicit CI step (rather than letting the test suite create
tables ad hoc) means CI is exercising the same migration path a real deploy would use, not a
shortcut that could hide a broken migration. The one thing CI never talks to for real is OpenAI —
every test that would otherwise call the embeddings or chat completions API injects a fake
`EmbeddingBackend`/`ChatBackend` instead (see `tests/test_document_processing_task.py
::FakeEmbeddingBackend`, `tests/test_conversation_service.py::FakeChatBackend`, and
`tests/test_embeddings.py`, which tests `OpenAIEmbeddingBackend`'s own logic against a mocked
OpenAI client rather than a fake backend) — no API key is available in CI, and there's no reason to
spend one even where it is. The local cross-encoder reranker, by contrast, **is** exercised for
real in CI (it's free, local, and needs no key) — `tests/test_reranker.py` and every retrieval/RAG
integration test run it as-is, downloading the model from Hugging Face over the runner's normal
internet access the same way `tests/test_tokenizer.py` does for `tiktoken`'s encoding file (see
the reranker section above for why this differs from the Docker image, which bakes both caches in
and runs offline).

## Production deployment

Every earlier piece of feature work was verified against `infra/docker-compose.yml` — a dev stack
with insecure-but-convenient defaults (a fixed JWT secret, no Redis/Qdrant auth, every service's
port published to the host) that was never meant to run on a real, internet-reachable host. This
section covers turning the finished system into something that actually could, without pretending
the gap didn't exist.

### `docker-compose.prod.yml`: what actually changed from dev

Deliberately kept at the **repo root**, not `infra/`, so Docker Compose's own `.env`
auto-discovery (same directory as the compose file being run) lines up with where an operator
creates their real secrets file (`cp .env.prod.example .env`). Differences from the dev stack,
each one a real production requirement rather than a stylistic preference:

- **Postgres/Redis/Qdrant publish no ports.** Only `backend`/`celery-worker`/`migrate`, all on the
  same compose network, ever need to reach them. In the dev stack, publishing them was a genuine
  convenience (connecting a local DB client, inspecting Qdrant's dashboard); on a real host, it's
  just an unnecessary attack surface.
- **Redis requires a password** (`--requirepass`, read into `REDIS_URL`/`CELERY_BROKER_URL`/
  `CELERY_RESULT_BACKEND` as `redis://:<password>@redis:6379/N` — standard URL-embedded auth,
  needing no code changes since `redis-py`/Celery both already parse that scheme) and **Qdrant
  requires an API key** (`QDRANT__SERVICE__API_KEY`, Qdrant's own nested-config env var
  convention, matching the same `QDRANT_API_KEY` the app's `AsyncQdrantClient` is already built to
  send — see the embeddings/indexing section above). Neither was enforced in dev.
- **Every service declares `deploy.resources.limits`** (cpus/memory) — modest, portfolio-scale
  defaults (e.g. 2 CPU/2GB for the API, 2 CPU/3GB for the Celery worker, which loads the same
  reranker model), not tuned against real load, and called out as such rather than presented as
  authoritative capacity planning.
- **A one-shot `migrate` service runs `alembic upgrade head` and exits**, with `backend`/
  `celery-worker` both declaring `depends_on: migrate: condition: service_completed_successfully`
  — so a deploy is `docker compose -f docker-compose.prod.yml up -d --build`, full stop, never a
  separate manual migration step. Building this surfaced a real gap, not a hypothetical one: the
  backend Docker image had never copied `alembic.ini`/`alembic/` into the image at all — every
  migration run to date (CI, local dev) had only ever happened from a host checkout, where those
  files exist on the filesystem outside any container. The `migrate` service's first real run
  failed with `"No 'script_location' key found in configuration"` — a live demonstration that
  "migrations run in CI" and "migrations can run *from the deployed artifact itself*" are different
  claims. Fixed in `infra/docker/backend.Dockerfile` by copying both in.
- **`ENVIRONMENT=production` in `.env.prod.example`** actually engages `app/core/startup_checks.py`'s
  fail-fast checks (added during the production-hardening work) — a real production deploy with
  the default JWT secret or a wildcard CORS origin now refuses to boot instead of running
  insecurely. `COOKIE_SECURE=true` is set
  alongside it, since cookies need HTTPS to actually be sent once real.
- **`backend`/`frontend` ports are still published directly** (`8000`, `3000`) — matching how this
  is smoke-tested (see below) and keeping the file usable standalone. A real internet-facing
  deployment should put a TLS-terminating reverse proxy (Caddy/nginx are both a single extra
  service away) in front and not expose these directly; deliberately not built here, see § What's
  deliberately deferred.

### Settings audit

`backend/.env.example` was missing three settings added across earlier work
(`RAG_HISTORY_MAX_TURNS`, `RAG_MIN_RERANK_SCORE`, `RAG_MAX_COMPLETION_TOKENS`) — found by diffing
every field in `app/core/config.py::Settings` against the file line by line, not by assuming it
was already complete. `.env.prod.example` (repo root) intentionally does **not** duplicate the
~40 non-secret tunables that file already documents: `docker-compose.prod.yml` loads
`backend/.env.example` first and the root `.env` second (`env_file` lists apply in order, later
files winning), so the production file only needs to contain what genuinely differs — secrets,
`ENVIRONMENT`, `COOKIE_SECURE`, `CORS_ORIGINS`, and the frontend's build-time API URL.

### CI: image build + push, deploy stays manual

`.github/workflows/ci.yml` gained a `build-and-push` job: after `backend` and `frontend` (lint,
full test suite, `pip-audit`/`npm audit`) both pass on a push to `main`, it builds and pushes both
Docker images to GHCR, tagged `latest` and by commit SHA. It does **not** then deploy anywhere —
there's no real target host in this repo to test an automated SSH/deploy step against, and a
CI job that can't actually be exercised is worse than a short, correct manual instruction (see
README § Deployment). One real gotcha documented there: `NEXT_PUBLIC_API_URL` is a Next.js
build-time constant baked into the client JS bundle, not a runtime env var, so the CI job needs it
available *at build time* (via a repo "Actions variable," `vars.NEXT_PUBLIC_API_URL`) — setting it
only on the deploy target would silently produce a frontend image that can never reach the right
backend URL no matter what's configured at runtime.

### Deployment target: one VM + Compose, not Kubernetes or a managed PaaS

Chosen deliberately, not by default. This project's engineering content worth demonstrating is the
RAG pipeline — chunking, hybrid retrieval, reranking, hallucination mitigation, eval methodology —
not infrastructure orchestration, and a single VM running `docker-compose.prod.yml` keeps the
entire deployment story inspectable in this repo with no platform-specific config to translate.
Kubernetes would be a legitimate choice at a scale this project isn't at (multiple regions,
autoscaling needs, a team operating it, not one person and one eval dataset); a managed PaaS
(Fly/Railway/Render) is a genuinely reasonable *alternative* — less ops burden — but was passed
over specifically so a reader can see every deployment decision made rather than "trust the
platform." See README.md § Deployment for the operator-facing version of this.

### Smoke test

`scripts/smoke_test.sh` (register → login → upload → poll processing → create a conversation → ask
a question → confirm a streamed, cited SSE answer) is the reusable version of this; run it against
`docker-compose.prod.yml` after `up -d --build`. It's written to distinguish "the pipeline is
broken" from "no real `OPENAI_API_KEY` is configured" — the latter is detected (the document lands
in `status: failed` with a clean, stored OpenAI-auth error rather than hanging or crashing) and
reported as an expected, documented gap, not a script failure, so the script stays useful without a
paid key too.

Run for real against the production compose stack in this environment (no `OPENAI_API_KEY`
configured here — see § Evaluation methodology for why every OpenAI-dependent path in this project
has to tolerate that): health check, register, login, and upload all passed against a freshly built
`docker-compose.prod.yml` stack with `ENVIRONMENT=production` confirmed live via `/health`, and the
`migrate` service applied all 5 migrations cleanly before `backend`/`celery-worker` started (the
dependency ordering — § above — doing exactly what it's for). Building the images for this run is
what caught the `alembic.ini`/`alembic/` Dockerfile gap (§ above) — a real bug this verification
step exists to catch, not a hypothetical one. Upload correctly dispatched to Celery, which
correctly attempted the real embedding pipeline and correctly stored a clean `failed` status with
the actual OpenAI 401 rather than hanging, crashing, or silently losing the task — the graceful-
degradation and task-retry/failure-state plumbing built earlier both doing their job under
a real (if here, unavoidable) failure condition, live, not simulated. Asking a question and getting
a generated, cited answer needs real embeddings to have been indexed first, so that step could not
be completed live in this environment; it's exercised instead by the conversational RAG test suite
and the eval harness's synthetic-mode fallback, and by
`scripts/smoke_test.sh` itself wherever a real key is available.

## What's deliberately deferred

Auth and multi-tenant isolation exist; document upload, storage, versioning, and the
async processing pipeline's plumbing exist; real parsing and structure-aware chunking
exist; embeddings, Qdrant indexing, and Postgres keyword search exist; hybrid
retrieval — RRF-fused dense + keyword search, cross-encoder reranking, and consistent filters —
exists; conversational RAG — query rewriting, grounded + cited + streamed answers, and a
chat UI — exists; production hardening — per-user rate limiting, a documented security
posture, request-id tracing across the sync/async boundary, Prometheus metrics, and graceful
degradation when a downstream dependency is unavailable — exists; a labeled retrieval +
generation evaluation harness, run against the real pipeline in three retrieval configurations and
reporting Recall@K/MRR/NDCG and LLM-as-judge faithfulness/relevance, with results documented
honestly including a real calibration finding it surfaced — exists (§ Evaluation
methodology); a production deployment configuration — hardened compose file, automatic migrations,
image build/push CI, and a justified single-VM deployment target — exists (§ Production
deployment). **This completes the project's originally planned scope.** Still deferred, honestly
rather than silently: a per-document, page-addressable viewer for citation chips to deep-link to
(they expand in place instead — see § Conversational RAG); conversation deletion (create/list/select
exist, no delete UI or endpoint yet); older-turn summarization instead of the current hard cutoff at
`rag_history_max_turns`; a second, subtler hallucination-mitigation layer beyond the rerank-score
threshold + prompt instruction (topically-relevant-but-insufficient context isn't caught
deterministically; the threshold itself was recalibrated from evidence, but still rests
on a single labeled negative example — see § Evaluation methodology); CSRF tokens beyond
`SameSite`; refresh-token-reuse detection/alerting; S3 storage (the abstraction is in place; no
second implementation exists yet); table/blockquote-aware Markdown parsing (folded into plain
paragraphs today); PDF outline/bookmark-based heading detection (font-size heuristic only today);
Qdrant collection recovery if a worker crashes mid-`replace_for_document` between the delete and
the upsert (the narrow window is documented, not eliminated); an actual Prometheus/Grafana stack
standing up the metrics already exposed (the `/metrics` endpoint and the PromQL this section
describes are ready for one, but none is deployed in this repo); a TLS-terminating reverse proxy in
front of the production compose stack (both app ports are published directly today — fine for the
smoke-tested single-VM target, not fine for real internet exposure without one); automated
CD (an image lands in GHCR on every merge to `main`; actually rolling it onto a running host is a
documented manual step, not a pipeline, since there's no real target host in this repo to test one
against); and Kubernetes/multi-region deployment (a deliberate scope choice, not a gap — see §
Production deployment for why). All of the above are intentional "down payments" or documented
simplifications, called out inline above and in `PROGRESS.md`, not oversights discovered by a
reader instead of by the people who built this.
