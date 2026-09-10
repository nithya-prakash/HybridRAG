from httpx import ASGITransport, AsyncClient

from app.main import app

PASSWORD = "correcthorsebattery"


async def test_safe_method_issues_a_csrf_cookie():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

        assert resp.status_code == 200
        assert "csrf_token" in resp.cookies
        assert ac.cookies.get("csrf_token")


async def test_unsafe_method_without_csrf_header_is_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/health")  # establishes the csrf_token cookie, no header sent back

        resp = await ac.post(
            "/auth/register", json={"email": "csrf-missing@example.com", "password": PASSWORD}
        )

        assert resp.status_code == 403
        assert "csrf" in resp.json()["detail"].lower()


async def test_unsafe_method_with_mismatched_csrf_header_is_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/health")

        resp = await ac.post(
            "/auth/register",
            json={"email": "csrf-mismatch@example.com", "password": PASSWORD},
            headers={"X-CSRF-Token": "not-the-real-token"},
        )

        assert resp.status_code == 403


async def test_unsafe_method_with_matching_csrf_header_succeeds():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/health")
        token = ac.cookies.get("csrf_token")

        resp = await ac.post(
            "/auth/register",
            json={"email": "csrf-match@example.com", "password": PASSWORD},
            headers={"X-CSRF-Token": token},
        )

        assert resp.status_code == 201


async def test_csrf_rejection_still_carries_cors_headers():
    # A browser's fetch() treats a response with no CORS headers as an
    # opaque network failure, not a readable 403 — see main.py's
    # _wrap_with_outer_middleware docstring for the same concern applied to
    # unhandled exceptions. CsrfMiddleware must sit inside that CORS wrap
    # for a rejected request to actually be visible to client-side code.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/health")

        resp = await ac.post(
            "/auth/register",
            json={"email": "csrf-cors@example.com", "password": PASSWORD},
            headers={"Origin": "http://localhost:3000"},
        )

        assert resp.status_code == 403
        assert resp.headers.get("access-control-allow-origin")


async def test_csrf_cookie_is_not_httponly():
    # The whole double-submit pattern depends on same-origin JS being able
    # to read this cookie back — see csrf.py's module docstring.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

        set_cookie = resp.headers.get("set-cookie", "")
        assert "csrf_token=" in set_cookie
        assert "httponly" not in set_cookie.lower()
