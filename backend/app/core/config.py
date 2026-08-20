from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "rag-knowledge-assistant"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Postgres
    postgres_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "documents"
    # Must match the output dimensionality of whichever embedding model is
    # actually active (`local_embedding_model` or `openai_embedding_model`,
    # per `embedding_provider`) — an explicit setting rather than a
    # model-name lookup table, since collection creation needs this value up
    # front and the two are meant to be changed together deliberately, not
    # inferred. Default (384) matches `local_embedding_model`'s default
    # (bge-small-en-v1.5); switching `embedding_provider` to "openai" without
    # also setting this to 3072 (text-embedding-3-large's dimensionality)
    # will fail loudly at the first Qdrant write, not silently corrupt data.
    qdrant_vector_size: int = 384

    # Embeddings — provider selection. "local" (default) runs a
    # sentence-transformers model in-process, same pattern as the reranker
    # below: no API key, no per-call cost, no network dependency once the
    # model is baked into the image. "openai" uses the OpenAI embeddings API
    # instead, if a higher-quality hosted model is preferred and a key is
    # available.
    embedding_provider: Literal["local", "openai"] = "local"
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"

    # OpenAI
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-large"
    openai_chat_model: str = "gpt-4o-mini"
    embedding_batch_size: int = 100
    embedding_max_retries: int = 5

    # Chat / generation — provider selection. "ollama" (default) talks to a
    # local Ollama server (see infra/docker-compose.yml's `ollama` service)
    # — free, no API key, fully self-contained. "openai" uses the OpenAI
    # chat completions API instead. Both implement the same `ChatBackend`
    # interface (`app/core/chat.py`), so nothing downstream of
    # `get_chat_backend()` needs to know or care which one is active.
    chat_provider: Literal["ollama", "openai"] = "ollama"
    ollama_base_url: str = "http://ollama:11434"
    # A small instruction-tuned model, chosen for reasonable CPU inference
    # latency in a self-hosted/portfolio context — swap for a larger model
    # (env var, no code change) if better answer quality matters more than
    # speed and more RAM/CPU is available.
    ollama_chat_model: str = "llama3.2:3b"

    # Auth
    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    access_token_cookie_name: str = "access_token"
    refresh_token_cookie_name: str = "refresh_token"
    cookie_domain: str | None = None
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    auth_rate_limit: str = "5/minute"
    # Applied per-user (see app/core/rate_limit.py) to the endpoints that hit
    # paid, per-call-billed APIs (OpenAI) or otherwise do real work — a much
    # tighter budget than the plain per-IP auth limit above needs, since the
    # cost of abuse here is dollars, not just a login-brute-force annoyance.
    upload_rate_limit: str = "20/hour"
    retrieval_rate_limit: str = "30/minute"
    chat_rate_limit: str = "20/minute"

    # Uploads
    max_upload_size_mb: int = 50
    upload_dir: str = "/data/uploads"

    # Chunking
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 75

    # Reranker
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Search
    hybrid_search_rrf_k: int = 60
    retrieval_top_k: int = 20
    rerank_top_k: int = 5

    # RAG / conversational layer
    # How many prior turns (user+assistant messages, not counting the current
    # one) are included when rewriting a follow-up query and when generating
    # an answer — an unbounded history would grow every prompt's cost and
    # latency without bound over a long conversation.
    rag_history_max_turns: int = 10
    # Below this cross-encoder rerank score, retrieved context is treated as
    # not actually relevant and the assistant declines rather than guessing.
    # Calibrated against the Phase 8 eval dataset (eval/RESULTS.md), not
    # picked blind: the cross-encoder's raw output is an unbounded logit, not
    # a 0-1 probability, so 0.0 (the original guess) turned out to reject a
    # genuinely correct top-1 match that scored -1.64. Across the labeled
    # dataset, true positives ranged -1.64 to +10.25 and the one labeled
    # negative (an out-of-corpus query) scored -9.85 — -3.0 clears every
    # observed true positive with margin (~1.4) while staying well clear
    # (~6.8) of the one observed negative, deliberately not pushed as low as
    # that single negative example alone would allow: this is still a
    # heuristic threshold on an uncalibrated score, and n=1 negative example
    # isn't enough to trust the full gap down to -9.85 as safe. Re-tune as
    # the eval dataset grows with more labeled negatives.
    rag_min_rerank_score: float = -3.0
    rag_max_completion_tokens: int = 800

    # Observability
    # "local"/"test" get a human-readable console log; anything else gets
    # single-line JSON, meant for a log aggregator to parse (see
    # app/core/logging.py). request_id_header is the header a request's
    # trace id is read from (if an upstream proxy already set one) and
    # echoed back on, so a request can be correlated end to end across a
    # proxy, this API, and any Celery task it enqueues.
    request_id_header: str = "X-Request-ID"


@lru_cache
def get_settings() -> Settings:
    return Settings()
