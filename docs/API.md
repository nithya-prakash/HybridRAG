# API Design Notes

This documents the actual current API surface. See `docs/ARCHITECTURE.md` for the design
rationale behind any of this; this file is the quick reference.

## Endpoints

| Method | Path | Auth | Rate limit | Description |
|---|---|---|---|---|
| GET | `/health` | none | — | Liveness check, returns app metadata |
| GET | `/metrics` | none | — | Prometheus scrape endpoint |
| POST | `/auth/register` | none | `auth_rate_limit` (5/min, per IP) | Create an account, sets auth cookies |
| POST | `/auth/login` | none | `auth_rate_limit` (5/min, per IP) | Authenticate, sets auth cookies |
| POST | `/auth/refresh` | refresh cookie | — | Rotates the refresh token, issues a new access token |
| POST | `/auth/logout` | refresh cookie | — | Revokes the refresh token, clears cookies |
| GET | `/auth/me` | cookie | — | Returns the current user |
| POST | `/documents/upload` | cookie | `upload_rate_limit` (20/hour, per user) | Upload a PDF/DOCX/TXT/MD file; re-upload via optional `document_id` form field |
| GET | `/documents` | cookie | — | List the current user's documents |
| GET | `/documents/{document_id}` | cookie | — | Get one document |
| GET | `/documents/{document_id}/status` | cookie | — | Lightweight status-only read, for polling |
| DELETE | `/documents/{document_id}` | cookie | — | Delete a document, its stored file(s), and its Qdrant vectors |
| POST | `/retrieval/search` | cookie | `retrieval_rate_limit` (30/min, per user) | Hybrid (dense + BM25, RRF-fused, reranked) search over the user's documents |
| POST | `/conversations` | cookie | — | Create a conversation |
| GET | `/conversations` | cookie | — | List the current user's conversations |
| GET | `/conversations/{conversation_id}` | cookie | — | Get a conversation with its full message history and reconstructed citations |
| POST | `/conversations/{conversation_id}/messages` | cookie | `chat_rate_limit` (20/min, per user) | Ask a question; streams the answer back as Server-Sent Events |

"cookie" auth means the `access_token` `httpOnly` cookie set by `/auth/register`/`/auth/login`,
validated by the `get_current_user` FastAPI dependency (`app/api/deps.py`) — see
`docs/ARCHITECTURE.md` § Authentication & multi-tenancy. Every cookie-authenticated route is
additionally scoped to `current_user.id`; there is no endpoint that returns another user's data.

## Conventions

- No path versioning today — every router mounts unprefixed (`/auth/...`, `/documents/...`, etc.).
  `Settings.api_v1_prefix` (`/api/v1`) exists in config but is currently unused by any router;
  don't assume it's actually applied anywhere until it is.
- Request/response bodies are Pydantic models living in `app/schemas/`, one module per resource
  (`auth.py`, `document.py`, `retrieval.py`, `conversation.py`, `health.py`).
- Auth-protected routes depend on `get_current_user` (`app/api/deps.py`), which reads the
  `access_token` cookie — not an `Authorization: Bearer` header. The frontend never sees or
  handles a raw token; see `docs/ARCHITECTURE.md` § Cookie storage, not localStorage for why.
- Errors return a consistent JSON shape: `{"detail": str | list[...]}`, following FastAPI's default
  `HTTPException`/validation-error behavior — no custom error envelope. Unexpected server errors
  return a generic `500` with a fixed message, never the real exception detail (see
  `docs/ARCHITECTURE.md` § Error handling).
- Rate-limited endpoints return `429` with `Retry-After` and `X-RateLimit-*` headers on trip,
  keyed per-user (from the access-token cookie) rather than per-IP wherever the caller is
  authenticated.

## Selected request/response shapes

- **`POST /documents/upload`**: `multipart/form-data`, fields `file` (required) and `document_id`
  (optional UUID — supplying it creates a new version of an existing document instead of a new
  one). Returns a `DocumentRead` (`id`, `filename`, `file_type`, `file_size_bytes`, `status` —
  `uploaded`/`processing`/`ready`/`failed`, `version`, `error_message`, `created_at`,
  `updated_at`). Processing happens asynchronously; poll `GET /documents/{id}/status` for
  `status`/`error_message` until it leaves `processing`.
- **`POST /retrieval/search`**: `{query, filters?, top_k?}` where `filters` is
  `{document_ids?, file_types?, created_after?, created_before?}`. Returns
  `{query, results, timings_ms}`; each result carries `dense_score`/`bm25_score`/`rrf_score`/
  `rerank_score` (each `null`, not `0.0`, if that stage didn't produce one) alongside `content`,
  `page_number`, and `section_path`.
- **`POST /conversations/{conversation_id}/messages`**: `{content}` in, a
  `text/event-stream` response out (not JSON) — the endpoint 404s synchronously up front for a
  missing/foreign conversation, then streams named SSE events:
  - `event: token` — `{delta}`, one per generated token
  - `event: citations` — `{message_id, rewritten_query, citations}`, sent once after generation
    completes, where each citation is `{marker, chunk_id, document_id, filename, page_number,
    excerpt}`
  - `event: done` — `{}`, marks the end of a successful stream
  - `event: error` — `{detail}`, sent instead of `done` if a downstream dependency was unavailable
    or generation otherwise failed (a "not enough context to answer" case is not an error — it's a
    normal answer via `token`/`citations`/`done` whose content is the canned decline message)
