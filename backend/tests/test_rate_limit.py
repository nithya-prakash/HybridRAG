from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.config import get_settings
from app.core.rate_limit import get_rate_limit_key
from app.core.security import create_access_token
from app.main import app

PASSWORD = "correcthorsebattery"


async def _register_and_login(client: AsyncClient, email: str) -> None:
    resp = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201
    resp = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200


def _upload_files(name: str = "a.txt", content: bytes = b"hello"):
    return {"file": (name, content, "text/plain")}


# --- get_rate_limit_key unit tests -----------------------------------------


def test_rate_limit_key_uses_user_id_from_valid_cookie():
    import uuid

    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    scope = {
        "type": "http",
        "headers": [(b"cookie", f"access_token={token}".encode())],
        "client": ("203.0.113.5", 12345),
    }
    request = Request(scope)

    assert get_rate_limit_key(request) == f"user:{user_id}"


def test_rate_limit_key_falls_back_to_ip_with_no_cookie():
    scope = {"type": "http", "headers": [], "client": ("203.0.113.5", 12345)}
    request = Request(scope)

    key = get_rate_limit_key(request)

    assert key == "ip:203.0.113.5"


def test_rate_limit_key_falls_back_to_ip_with_garbage_cookie():
    scope = {
        "type": "http",
        "headers": [(b"cookie", b"access_token=not-a-real-jwt")],
        "client": ("203.0.113.5", 12345),
    }
    request = Request(scope)

    key = get_rate_limit_key(request)

    assert key == "ip:203.0.113.5"


# --- end-to-end enforcement --------------------------------------------------
# upload_rate_limit is read dynamically per request (see
# @limiter.limit(lambda: get_settings().upload_rate_limit) in
# app/api/routers/documents.py), so monkeypatching the Settings singleton's
# attribute here takes effect on the very next request — no need to actually
# exhaust the real (deliberately generous) 20/hour production limit.


async def test_upload_rate_limit_exceeded_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_rate_limit", "2/minute")
    await _register_and_login(client, "ratelimit-basic@example.com")

    for i in range(2):
        resp = await client.post("/documents/upload", files=_upload_files(f"a{i}.txt"))
        assert resp.status_code == 201

    resp = await client.post("/documents/upload", files=_upload_files("one-too-many.txt"))

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 0
    assert "X-RateLimit-Limit" in resp.headers
    assert "error" in resp.json()


async def test_rate_limit_is_scoped_per_user_not_shared(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_rate_limit", "1/minute")
    await _register_and_login(client, "ratelimit-userA@example.com")

    first = await client.post("/documents/upload", files=_upload_files("a.txt"))
    assert first.status_code == 201
    second = await client.post("/documents/upload", files=_upload_files("b.txt"))
    assert second.status_code == 429  # user A has now used their one request

    other = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        await _register_and_login(other, "ratelimit-userB@example.com")
        # Same test-transport "IP" as user A, but a distinct user_id — this
        # only passes if the key function is actually per-user, not per-IP.
        resp = await other.post("/documents/upload", files=_upload_files("c.txt"))
        assert resp.status_code == 201
    finally:
        await other.aclose()
