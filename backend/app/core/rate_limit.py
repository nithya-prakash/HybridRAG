from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import get_settings
from app.core.security import decode_access_token

settings = get_settings()


def get_rate_limit_key(request: Request) -> str:
    """Key authenticated requests by user_id, not by IP. Per-IP limiting
    would let every user behind a shared NAT/corporate proxy throttle each
    other, and let one abusive user dodge a limit just by rotating IPs — a
    per-user key doesn't have either problem. Reads the access-token cookie
    directly (a pure JWT decode, no DB round trip) rather than depending on
    `get_current_user`'s Depends result, since slowapi's key_func only
    receives the raw `Request`. Falls back to IP for requests with no valid
    session — e.g. `/auth/login` itself, before a token exists yet, or any
    request that will go on to get a 401 regardless."""
    token = request.cookies.get(settings.access_token_cookie_name)
    if token:
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            return f"user:{payload['sub']}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri=settings.redis_url,
    strategy="fixed-window",
    # Without this, slowapi never sends X-RateLimit-*/Retry-After headers at
    # all (it defaults to off) — a client hitting a 429 would have no
    # standard way to know how long to back off.
    headers_enabled=True,
    # If Redis itself is down, rate limiting should degrade to a per-process
    # in-memory limit rather than take every single request down with it —
    # worse rate-limit accuracy (each worker process counts independently)
    # beats an outage of an unrelated dependency turning into a site-wide
    # outage. See ARCHITECTURE.md § Graceful degradation.
    in_memory_fallback_enabled=True,
)
