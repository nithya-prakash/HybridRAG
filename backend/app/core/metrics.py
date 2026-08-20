from prometheus_client import Counter, Histogram

# Every request, regardless of route — the `path` label is the route's
# *template* (e.g. "/documents/{document_id}"), never the raw resolved URL,
# to keep cardinality bounded (a raw path label would mint a new time series
# per distinct UUID ever requested). See RequestContextMiddleware.
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path", "status"],
)

# One observation per stage per retrieve() call — mirrors the structured
# `retrieval_complete` log event from Phase 5 (that event stays; this is a
# second, queryable-as-a-distribution view of the same numbers, not a
# replacement for it).
RETRIEVAL_STAGE_DURATION_SECONDS = Histogram(
    "retrieval_stage_duration_seconds",
    "Per-stage latency of the hybrid retrieval pipeline, in seconds",
    ["stage"],
)

LLM_CALL_DURATION_SECONDS = Histogram(
    "llm_call_duration_seconds",
    "Latency of an outbound LLM API call, in seconds",
    ["provider", "call_type"],
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total tokens consumed by outbound LLM API calls",
    ["provider", "call_type", "token_type"],
)
