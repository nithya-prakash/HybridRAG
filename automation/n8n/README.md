# n8n workflow: document intake

`document_intake.json` — import via n8n → Workflows → Import from file.

`POST /webhook/rag-ingest {"file_url": "https://…/handbook.pdf"}` →
logs in to the API (cookie auth + double-submit CSRF) → downloads the file →
`POST /documents/upload` → polls `/documents/{id}/status` every 5 s (max 3 min)
→ responds `200` when `ready`, `502` with the error when `failed` or timed out.

Set these environment variables on the n8n instance: `RAG_API_URL`,
`RAG_EMAIL`, `RAG_PASSWORD`, and `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
(n8n blocks `$env` in nodes by default).

Status: executed end to end on 2026-10-08 in n8n 2.42.5 (Docker) against a local API:
login, download, upload, poll, `200 {"outcome":"ready"}`. The 3-minute timeout path
also fired once (`502 {"outcome":"timeout"}`) when the Celery worker crashed. Not tested:
the `failed` document outcome, and n8n 1.x. Extra env used in the test:
`NODE_FUNCTION_ALLOW_BUILTIN=crypto`. Import via the UI (the CLI `import:workflow`
needs an `id` field this file does not have). Also structure-checked by
`tests/test_n8n_workflow.py`.
