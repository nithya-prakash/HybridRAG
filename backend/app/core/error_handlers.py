import httpx
import openai
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import ResponseHandlingException

from app.core.llm_errors import classify_llm_error
from app.core.logging import get_logger

logger = get_logger(__name__)

# Exception types that mean "a downstream dependency (OpenAI, Ollama, Qdrant)
# is misconfigured, temporarily unreachable, or overloaded," as opposed to a
# bug in this codebase. Verified empirically: pointing an AsyncQdrantClient at
# an unreachable host raises exactly ResponseHandlingException (it wraps the
# underlying httpx connection error) — not some Qdrant-specific
# connection-error subtype; Ollama's client (also httpx-based) raises the
# same httpx connection/timeout errors directly when the `ollama` service
# isn't reachable. Distinguishing this bucket from "unexpected exception"
# lets the client see an actionable message (via `classify_llm_error`)
# instead of a bare 500, and lets an operator's alerting tell "a provider is
# down or misconfigured" apart from "we have a bug" at a glance.
DOWNSTREAM_UNAVAILABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
    openai.AuthenticationError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    ResponseHandlingException,
)


async def downstream_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "downstream_service_unavailable", path=request.url.path, exc_type=type(exc).__name__
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": classify_llm_error(exc)},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # The one place in the app allowed to catch bare Exception: this is the
    # last line of defense, not a substitute for handling specific errors
    # closer to where they happen. Logs the real exception (with traceback,
    # via logger.exception) server-side, including the request id already
    # bound into structlog's contextvars by RequestIDMiddleware — but the
    # client only ever sees a generic message. Never the exception's own
    # str(), which could leak internal details (a stack frame, a DB error
    # message naming a column or table, a file path).
    logger.exception("unhandled_exception", path=request.url.path, exc_type=type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


def register_error_handlers(app: FastAPI) -> None:
    for exc_type in DOWNSTREAM_UNAVAILABLE_EXCEPTIONS:
        app.add_exception_handler(exc_type, downstream_unavailable_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
