import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import HTTP_REQUEST_DURATION_SECONDS

logger = get_logger(__name__)


def _route_path(request: Request) -> str:
    """The matched route's *template* path (e.g. "/documents/{document_id}"),
    not the raw resolved URL — using the raw URL as a metric label would
    mint an unbounded number of Prometheus time series, one per distinct id
    ever requested. Route matching happens inside `call_next`'s inner ASGI
    stack, which mutates the same `scope` dict `request` wraps, so this is
    only meaningful *after* `call_next` returns — a request that matched no
    route at all (a genuine 404) is labeled "unmatched" instead."""
    route = request.scope.get("route")
    return route.path if route is not None else "unmatched"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds a per-request id into structlog's contextvars for the life of
    the request, so every log line emitted anywhere during it — this
    middleware, a router, a service, a repository, deep inside
    RetrievalService's per-stage logging — automatically carries the same
    `request_id`, with no changes needed at any of those call sites (see
    `structlog.contextvars.merge_contextvars` in app/core/logging.py). Also
    records total request latency, both as a structured log line and a
    Prometheus histogram."""

    def __init__(self, app) -> None:  # noqa: ANN001 - Starlette's own (untyped) app param
        super().__init__(app)
        self._header_name = get_settings().request_id_header

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Trust an upstream proxy's request id if it supplied one (so a
        # trace started at a load balancer/API gateway carries through),
        # otherwise mint a fresh one.
        request_id = request.headers.get(self._header_name) or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "http_request_failed",
                method=request.method,
                path=_route_path(request),
                elapsed_ms=elapsed_ms,
            )
            raise

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        path = _route_path(request)
        response.headers[self._header_name] = request_id
        logger.info(
            "http_request_complete",
            method=request.method,
            path=path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method, path=path, status=str(response.status_code)
        ).observe(elapsed_ms / 1000)
        return response
