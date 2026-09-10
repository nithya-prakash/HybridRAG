import secrets
from collections.abc import Awaitable, Callable
from hmac import compare_digest

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit-cookie CSRF protection — real defense-in-depth beyond
    `SameSite`, not a replacement for it. `SameSite=Lax` (the default —
    see `settings.cookie_samesite`) already blocks the classic cross-site
    form-POST and fetch/XHR CSRF attacks in current browsers; this covers
    the gap `SameSite` alone doesn't: browsers/webviews that don't honor it
    correctly, and any future misconfiguration that weakens it (e.g. an
    operator setting `cookie_samesite=none` for a legitimate cross-subdomain
    need).

    The token is issued as a *non-httpOnly* cookie deliberately — same-origin
    JS must be able to read it (via `document.cookie`) to echo it back as a
    request header, which is exactly the property that defeats a cross-site
    attacker: same-origin policy stops attacker-controlled JS from reading a
    victim's cookies, so only a legitimate same-origin request can construct
    a header that matches the cookie. The JWT auth cookies remain httpOnly
    throughout — this token carries no authentication value on its own, it
    only proves the request came from the same origin that received the
    cookie.

    Every safe-method (GET/HEAD/OPTIONS) response issues a token if the
    request didn't already carry one, so the very first page load —
    happening before any login — establishes it. Unsafe methods (POST/PUT/
    PATCH/DELETE) require the header to be present and to match the cookie;
    a missing or mismatched pair is rejected before the request reaches any
    route handler.
    """

    def __init__(self, app) -> None:  # noqa: ANN001 - Starlette's own (untyped) app param
        super().__init__(app)
        settings = get_settings()
        self._secure = settings.cookie_secure
        self._samesite = settings.cookie_samesite
        self._domain = settings.cookie_domain

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)

        if request.method not in _SAFE_METHODS:
            header_token = request.headers.get(CSRF_HEADER_NAME)
            if (
                not cookie_token
                or not header_token
                or not compare_digest(cookie_token, header_token)
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Missing or invalid CSRF token"},
                )

        response = await call_next(request)

        if cookie_token is None:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=secrets.token_urlsafe(32),
                httponly=False,
                secure=self._secure,
                samesite=self._samesite,
                domain=self._domain,
                path="/",
            )

        return response
