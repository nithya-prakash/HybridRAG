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

    The token is issued as a *non-httpOnly* cookie deliberately — frontend
    JS must be able to get its value somehow to echo it back as a request
    header. For a same-origin frontend that's `document.cookie`. But this
    app can also be deployed with the frontend and API on two different
    origins entirely (e.g. Vercel + Render — see docs/DEPLOY_FREE_TIER.md),
    and a page can never read a cookie set by a *different* origin,
    regardless of its SameSite/Secure attributes — that's not a CSRF
    property, it's a basic same-origin-policy fact about `document.cookie`
    itself. So the value is *also* echoed back as an `X-CSRF-Token`
    *response* header the first time it's issued (see below), which CORS
    can expose cross-origin (`Access-Control-Expose-Headers` —
    app/main.py) even though the cookie itself stays unreadable there. A
    same-origin frontend can use either source; a cross-origin one only has
    the header. Either way, what actually defeats a cross-site attacker is
    unchanged: only a legitimate request — one the real frontend, same- or
    cross-origin, made and read the response of — can end up knowing a
    value that matches the cookie. The JWT auth cookies remain httpOnly
    throughout — this token carries no authentication value on its own, it
    only proves the request came from a page that could read this specific
    response.

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
            new_token = secrets.token_urlsafe(32)
            # Also exposed as a response header (see the class docstring) —
            # the only way a cross-origin frontend can ever learn this
            # value, since it can't read the cookie itself.
            response.headers[CSRF_HEADER_NAME] = new_token
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=new_token,
                httponly=False,
                secure=self._secure,
                samesite=self._samesite,
                domain=self._domain,
                path="/",
            )

        return response
