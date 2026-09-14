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
    *response* header on every safe-method response (see below), which CORS
    can expose cross-origin (`Access-Control-Expose-Headers` —
    app/main.py) even though the cookie itself stays unreadable there. A
    same-origin frontend can use either source; a cross-origin one only has
    the header — and needs it on *every* safe-method response, not only the
    one that first sets the cookie: `document.cookie` persists across page
    loads, but a cross-origin frontend's in-memory copy of this value has
    nowhere else to live and is wiped on every navigation, so each fresh
    page load needs its own chance to re-learn a value the browser's cookie
    jar has actually held onto the whole time. Either way, what actually
    defeats a cross-site attacker is unchanged: only a legitimate request —
    one the real frontend, same- or cross-origin, made and read the
    response of — can end up knowing a value that matches the cookie. The
    JWT auth cookies remain httpOnly throughout — this token carries no
    authentication value on its own, it only proves the request came from a
    page that could read this specific response.

    Every safe-method (GET/HEAD/OPTIONS) response both issues the cookie
    (if the request didn't already carry one — so the very first page load,
    before any login, establishes it) and echoes its value as the
    `X-CSRF-Token` header, new or pre-existing either way. Unsafe methods
    (POST/PUT/PATCH/DELETE) require the header to be present and to match
    the cookie; a missing or mismatched pair is rejected before the request
    reaches any route handler.
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
            cookie_token = secrets.token_urlsafe(32)
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=cookie_token,
                httponly=False,
                secure=self._secure,
                samesite=self._samesite,
                domain=self._domain,
                path="/",
            )

        # Echoed as a response header on *every* safe-method response, not
        # only the one that first issues the cookie (see the class
        # docstring) — a same-origin frontend only ever needs this once,
        # since document.cookie persists across page loads, but a
        # cross-origin one's in-memory copy (there's nowhere else it could
        # live — it can't read this cookie) is wiped on every navigation.
        # Without re-sending it every time, only the very first request a
        # cross-origin frontend ever makes, session-wide, would work — every
        # page load after that would carry a browser cookie the frontend
        # itself has no way to learn the value of anymore.
        if request.method in _SAFE_METHODS:
            response.headers[CSRF_HEADER_NAME] = cookie_token

        return response
