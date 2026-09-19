from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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

    @field_validator("postgres_url")
    @classmethod
    def _require_asyncpg_driver(cls, v: str) -> str:
        # Every managed Postgres provider (Render, Railway, Heroku, ...)
        # hands out a plain postgres:// or postgresql:// connection string —
        # never the +asyncpg driver suffix SQLAlchemy's async engine
        # requires. Rewriting it here means POSTGRES_URL can be wired
        # straight from a provider's connection-string env var without a
        # manual edit, instead of failing at engine creation with a cryptic
        # "no such driver" error the first time this app runs somewhere
        # other than the docker-compose stack that always set it correctly.
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    # False (default) is the real async setup: .delay() enqueues to the
    # broker, a separate celery worker process consumes it. True runs the
    # task synchronously in whichever process called .delay() instead — no
    # worker process at all. Exists for deployments too small to run API
    # and worker as separate processes (see docs/DEPLOY_FREE_TIER.md): a
    # free Render web service has no free worker instance type, and running
    # both in one container each load their own copy of the embedding
    # model, which reliably exceeds the free tier's 512MB and gets
    # OOM-killed on the first real upload — verified, not theoretical (see
    # commit history). Eager mode avoids the second process (and its second
    # model copy) entirely, at the cost of the upload request blocking
    # until processing finishes rather than returning immediately.
    celery_task_always_eager: bool = False

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
    # chat completions API instead. "groq" talks to Groq's hosted API, which
    # is OpenAI-compatible (same request/response shape, different base_url)
    # — used for deployments where running Ollama isn't an option (its 4GB+
    # RAM footprint doesn't fit a free hosting tier) but a real API key with
    # per-token cost isn't wanted either. All three implement the same
    # `ChatBackend` interface (`app/core/chat.py`), so nothing downstream of
    # `get_chat_backend()` needs to know or care which one is active.
    chat_provider: Literal["ollama", "openai", "groq"] = "ollama"
    ollama_base_url: str = "http://ollama:11434"
    # A small instruction-tuned model, chosen for reasonable CPU inference
    # latency in a self-hosted/portfolio context — swap for a larger model
    # (env var, no code change) if better answer quality matters more than
    # speed and more RAM/CPU is available.
    ollama_chat_model: str = "llama3.2:3b"

    # Groq
    groq_api_key: str | None = None
    groq_chat_model: str = "openai/gpt-oss-120b"

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
    # A plain HF model id/local path is always accepted directly (the
    # historical, still-default behavior). RERANKER_MODEL also accepts the
    # literals "baseline"/"finetuned" as a convenience alias — resolved in
    # app/core/reranker.py (not here: Settings stays a plain data holder,
    # and resolving a literal that depends on reranker_finetuned_path below
    # is simpler as an ordinary function than as a pydantic cross-field
    # validator, which would have to fight field declaration order to see
    # that value).
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Where CrossEncoderReranker looks when RERANKER_MODEL=finetuned. Not
    # baked into the production Docker image (see infra/docker/
    # backend.Dockerfile — only the baseline model is warmed up at build
    # time, and HF_HUB_OFFLINE=1 at runtime means a missing local path here
    # fails loudly rather than silently falling back to a network fetch).
    # Real, disclosed limitation: RERANKER_MODEL=finetuned is for local/eval
    # use with a checkpoint produced by eval/reranker_training/
    # train_reranker.py, not (yet) a supported production deployment target
    # — see README.md's reranker fine-tuning section.
    reranker_finetuned_path: str = "../eval/reranker_training/models/finetuned"

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
    # Recalibrated against the full 110-query/11-negative hallucination-guard
    # eval (eval/evaluate_hallucination.py, eval/RESULTS.md) — a proper
    # threshold sweep over every observed score (not a guess) found -3.3 sits
    # in a genuine gap in the real distribution: q034 (an answerable query,
    # incorrectly declined at the prior -3.0 threshold) scored -3.1147, while
    # the nearest true negative (q096, unanswerable) scored -3.475 — -3.3
    # sits roughly at the midpoint, clearing q034 with margin (~0.19) while
    # staying clear of q096 (~0.17). This improves accuracy 95.5%->96.4%,
    # precision 80.0%->88.9%, F1 0.762->0.800 versus the prior -3.0, with NO
    # threshold able to improve recall (72.7%) without a worse F1 trade-off:
    # the sweep confirmed two of the three false negatives (q089 +3.27,
    # q094 +4.81) score *higher* than many genuinely answerable queries, so
    # no cutoff on this score alone separates them — those are a real,
    # different failure mode (topically-similar-but-not-specific content
    # scored confidently), addressed instead by the second-layer prompt
    # constraint in app/services/rag/prompts.py rather than by this
    # threshold. Re-tune as the eval dataset grows further.
    rag_min_rerank_score: float = -0.6
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
