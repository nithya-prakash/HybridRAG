from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """A handful of defensive response headers with no real downside for a
    JSON API: stop a browser from MIME-sniffing a response into something
    executable, refuse to ever be framed (no legitimate reason this API
    would be embedded in an iframe), and don't leak the full referring URL
    cross-origin. HSTS is added outside local/test only — it tells a
    browser "always use HTTPS for this host, from now on," which is
    actively wrong advice for a plain-http local dev/CI setup and would
    lock a developer's browser out of http://localhost until it expires."""

    def __init__(self, app) -> None:  # noqa: ANN001 - Starlette's own (untyped) app param
        super().__init__(app)
        self._enable_hsts = get_settings().environment not in ("local", "test")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if self._enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
