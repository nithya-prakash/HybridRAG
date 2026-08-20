from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.types import ASGIApp

from app.api.routers import auth, conversations, documents, health, metrics, retrieval
from app.core.config import get_settings
from app.core.embeddings import get_embedding_backend
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import limiter
from app.core.request_context import RequestContextMiddleware
from app.core.reranker import get_reranker
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.startup_checks import validate_production_settings

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Fail fast on an insecure configuration rather than serve on one — see
    # ARCHITECTURE.md § Security posture.
    validate_production_settings(settings)
    logger.info("app_startup", environment=settings.environment)
    # Loads the reranker model now (blocking startup briefly) instead of on
    # the first real search request — see Reranker.warm_up's docstring for
    # the latency numbers that make this worth doing.
    await get_reranker().warm_up()
    logger.info("reranker_warmed_up")
    # No-op for the OpenAI embedding backend; loads the local
    # sentence-transformers model now, same reasoning as the reranker above
    # — this process also embeds query text directly (RetrievalService),
    # not just the Celery worker embedding uploaded documents.
    await get_embedding_backend().warm_up()
    logger.info("embedding_backend_warmed_up")
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=get_settings().app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    # SlowAPI has to live *inside* Starlette's own middleware stack — its
    # per-route checks read `request.app.state.limiter`, which is only set
    # once a request has actually entered this FastAPI instance, and its
    # RateLimitExceeded handler is registered the normal FastAPI way (see
    # register_error_handlers below for why that matters).
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(retrieval.router)
    app.include_router(conversations.router)

    return app


def _wrap_with_outer_middleware(inner_app: FastAPI) -> ASGIApp:
    """CORS, security headers, and request-id binding all need to apply to
    *every* response this service ever sends — including one path a plain
    `app.add_middleware()` call can never reach: a genuinely unhandled
    exception. FastAPI/Starlette unconditionally wraps anything added via
    `add_middleware` inside `ServerErrorMiddleware` (the catch-all-Exception
    handler registered in register_error_handlers becomes *its* handler,
    not a normal one `ExceptionMiddleware` dispatches to) — so
    `ServerErrorMiddleware` is the true outermost layer around the whole
    app regardless of add_middleware() call order, and anything added that
    way never sees a response that came from the bare-Exception path.
    Verified empirically during Phase 7: without this wrapping, a real
    unhandled-exception response had no CORS headers on it at all — which a
    browser's `fetch()` (this frontend always calls with
    `credentials: "include"`) treats as an opaque network failure rather
    than a readable response, hiding the real 500 from both the user and
    any client-side error tracking. Constructing these three directly here
    (rather than via `add_middleware`) is what puts them genuinely outside
    that boundary. SlowAPIMiddleware is deliberately not part of this list —
    see create_app's docstring-comment above it."""
    settings = get_settings()
    wrapped: ASGIApp = inner_app
    wrapped = SecurityHeadersMiddleware(wrapped)
    wrapped = RequestContextMiddleware(wrapped)
    wrapped = CORSMiddleware(
        wrapped,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return wrapped


app = _wrap_with_outer_middleware(create_app())
