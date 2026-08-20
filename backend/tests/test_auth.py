import uuid
from datetime import timedelta

from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token
from app.repositories.user_repository import UserRepository

EMAIL = "alice@example.com"
PASSWORD = "correcthorsebattery"


async def _register(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD):
    return await client.post("/auth/register", json={"email": email, "password": password})


async def _login(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD):
    return await client.post("/auth/login", json={"email": email, "password": password})


async def test_register_creates_user(client: AsyncClient):
    response = await _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert body["is_active"] is True
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_duplicate_email_is_rejected(client: AsyncClient):
    first = await _register(client)
    assert first.status_code == 201

    second = await _register(client)

    assert second.status_code == 409


async def test_login_sets_cookies_and_returns_user(client: AsyncClient):
    await _register(client)

    response = await _login(client)

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies


async def test_login_wrong_password_is_rejected(client: AsyncClient):
    await _register(client)

    response = await _login(client, password="wrong-password")

    assert response.status_code == 401


async def test_login_nonexistent_user_is_rejected(client: AsyncClient):
    response = await _login(client, email="nobody@example.com")

    assert response.status_code == 401


async def test_me_returns_current_user_with_valid_cookie(client: AsyncClient):
    await _register(client)
    await _login(client)

    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


async def test_me_rejected_without_token(client: AsyncClient):
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_rejected_with_garbage_token(client: AsyncClient):
    client.cookies.set("access_token", "not-a-real-jwt")

    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_rejected_with_expired_token(client: AsyncClient):
    await _register(client)
    expired_token = create_access_token(uuid.uuid4(), expires_delta=timedelta(seconds=-1))
    client.cookies.set("access_token", expired_token)

    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_refresh_rotates_token_and_old_token_becomes_invalid(client: AsyncClient):
    await _register(client)
    await _login(client)
    old_refresh_token = client.cookies.get("refresh_token")

    first_refresh = await client.post("/auth/refresh")
    assert first_refresh.status_code == 200
    new_refresh_token = client.cookies.get("refresh_token")
    assert new_refresh_token != old_refresh_token

    client.cookies.set("refresh_token", old_refresh_token)
    reuse_attempt = await client.post("/auth/refresh")
    assert reuse_attempt.status_code == 401


async def test_refresh_without_cookie_is_rejected(client: AsyncClient):
    response = await client.post("/auth/refresh")

    assert response.status_code == 401


async def test_refresh_with_invalid_cookie_is_rejected(client: AsyncClient):
    client.cookies.set("refresh_token", "bogus-token")

    response = await client.post("/auth/refresh")

    assert response.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient):
    await _register(client)
    await _login(client)

    logout_response = await client.post("/auth/logout")
    assert logout_response.status_code == 204

    refresh_after_logout = await client.post("/auth/refresh")
    assert refresh_after_logout.status_code == 401


async def test_login_is_rate_limited(client: AsyncClient):
    await _register(client)

    responses = [await _login(client, password="wrong-password") for _ in range(6)]

    assert responses[-1].status_code == 429
    assert all(r.status_code == 401 for r in responses[:5])


async def test_me_rejected_for_deactivated_user(client: AsyncClient, db_session: AsyncSession):
    await _register(client)
    await _login(client)
    assert (await client.get("/auth/me")).status_code == 200

    user = await UserRepository(db_session).get_by_email(EMAIL)
    user.is_active = False
    await db_session.commit()

    response = await client.get("/auth/me")

    assert response.status_code == 401


def test_decode_access_token_rejects_non_access_token_type():
    # A validly-signed JWT that just isn't an access token (e.g. some other
    # token type this app might mint in the future) must still be rejected —
    # signature validity alone isn't sufficient authorization.
    settings = get_settings()
    payload = {"sub": str(uuid.uuid4()), "type": "not-an-access-token"}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    assert decode_access_token(token) is None
