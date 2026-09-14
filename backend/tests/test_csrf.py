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


async def test_safe_method_also_echoes_csrf_token_as_response_header():
    # The only way a cross-origin frontend (e.g. Vercel calling a Render
    # backend — see docs/DEPLOY_FREE_TIER.md) can ever learn this value: it
    # can never read a cookie set by a different origin via document.cookie,
    # regardless of SameSite/Secure, so the token must also be readable from
    # the response itself.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

        header_token = resp.headers.get("x-csrf-token")
        assert header_token
        assert header_token == resp.cookies.get("csrf_token")


async def test_csrf_token_header_is_exposed_via_cors():
    # A browser's fetch() only exposes a browser-standard "safelisted" set
    # of response headers to cross-origin JS by default — X-CSRF-Token isn't
    # one of them, so without Access-Control-Expose-Headers (main.py) a
    # cross-origin frontend would see this same header on the wire but
    # res.headers.get("X-CSRF-Token") would return null anyway.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health", headers={"Origin": "http://localhost:3000"})

        exposed = resp.headers.get("access-control-expose-headers", "")
        assert "x-csrf-token" in exposed.lower()


async def test_csrf_token_header_is_resent_on_every_safe_request():
    # Deliberately the opposite of "only echo it once": document.cookie
    # persists across page loads for a same-origin frontend, but a
    # cross-origin frontend's in-memory copy of this value has nowhere else
    # to live and is wiped on every navigation. If the header were only
    # sent once (the request that issues the cookie), every page load after
    # the very first one, session-wide, would leave a cross-origin frontend
    # holding a browser cookie it has no way to learn the value of anymore.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        first = await ac.get("/health")
        first_token = first.headers.get("x-csrf-token")
        assert first_token

        second = await ac.get("/health")
        second_token = second.headers.get("x-csrf-token")
        assert second_token == first_token  # same cookie value, echoed again


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
