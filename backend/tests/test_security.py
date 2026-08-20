import httpx
import openai
import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client.http.exceptions import ResponseHandlingException

from app.core.config import Settings
from app.core.startup_checks import InsecureConfigurationError, validate_production_settings
from app.core.vector_store import VectorStore
from app.main import app
from tests.helpers import FakeEmbeddingBackend

PASSWORD = "correcthorsebattery"


async def _register_and_login(client, email: str) -> None:
    resp = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201
    resp = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200


# --- security headers + request id -------------------------------------------


async def test_security_headers_present_on_every_response(client):
    resp = await client.get("/health")

    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # settings.environment == "test" in this suite — HSTS must stay off, or a
    # developer's browser would get told "only ever use HTTPS for
    # localhost," which would break plain-http local dev afterward.
    assert "Strict-Transport-Security" not in resp.headers


async def test_request_id_present_and_echoed_back(client):
    resp = await client.get("/health")
    assert "X-Request-ID" in resp.headers

    my_id = "test-request-id-12345"
    resp2 = await client.get("/health", headers={"X-Request-ID": my_id})
    assert resp2.headers["X-Request-ID"] == my_id


# --- startup configuration validation -----------------------------------------


def test_validate_production_settings_rejects_default_jwt_secret():
    settings = Settings(environment="staging", jwt_secret_key="change-me-in-env")

    with pytest.raises(InsecureConfigurationError):
        validate_production_settings(settings)


def test_validate_production_settings_rejects_wildcard_cors():
    settings = Settings(
        environment="staging", jwt_secret_key="a-real-random-secret", cors_origins=["*"]
    )

    with pytest.raises(InsecureConfigurationError):
        validate_production_settings(settings)


def test_validate_production_settings_passes_with_safe_config():
    settings = Settings(
        environment="staging",
        jwt_secret_key="a-real-random-secret",
        cors_origins=["https://app.example.com"],
    )

    validate_production_settings(settings)  # must not raise


def test_validate_production_settings_skips_check_outside_production_environments():
    settings = Settings(environment="local", jwt_secret_key="change-me-in-env")

    validate_production_settings(settings)  # must not raise despite the insecure default


# --- server-side input validation, independent of the client ------------------


async def test_upload_strips_path_traversal_from_filename(client):
    await _register_and_login(client, "security-traversal@example.com")

    resp = await client.post(
        "/documents/upload",
        files={"file": ("../../../etc/passwd.txt", b"not actually /etc/passwd", "text/plain")},
    )

    assert resp.status_code == 201
    filename = resp.json()["filename"]
    assert filename == "passwd.txt"
    assert "/" not in filename
    assert ".." not in filename


# --- graceful degradation when a downstream dependency is unavailable ---------


async def test_retrieval_returns_503_not_500_when_qdrant_unreachable(client, monkeypatch):
    async def _boom(self, *args, **kwargs):
        raise ResponseHandlingException("simulated Qdrant outage")

    monkeypatch.setattr(VectorStore, "search", _boom)
    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend", lambda: FakeEmbeddingBackend()
    )
    await _register_and_login(client, "security-qdrant-down@example.com")

    resp = await client.post("/retrieval/search", json={"query": "anything at all"})

    assert resp.status_code == 503
    body = resp.json()
    assert "detail" in body
    # classify_llm_error (app/core/llm_errors.py) names the specific known
    # dependency rather than a one-size-fits-all message — see its tests
    # (tests/test_llm_errors.py) for the full mapping.
    assert "qdrant" in body["detail"].lower()
    # The real exception's message/type must never reach the client.
    assert "ResponseHandlingException" not in resp.text
    assert "simulated Qdrant outage" not in resp.text


async def test_retrieval_returns_503_not_500_when_openai_unreachable(client, monkeypatch):
    async def _boom(self, texts):
        raise openai.APIConnectionError(
            message="simulated OpenAI outage",
            request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
        )

    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend",
        lambda: type("Boom", (), {"embed_batch": _boom})(),
    )
    await _register_and_login(client, "security-openai-down@example.com")

    resp = await client.post("/retrieval/search", json={"query": "anything at all"})

    assert resp.status_code == 503
    detail = resp.json()["detail"].lower()
    assert "openai" in detail or "network" in detail
    assert "simulated OpenAI outage" not in resp.text


async def test_unexpected_exception_returns_500_with_generic_message(monkeypatch):
    async def _boom(self, texts):
        raise RuntimeError(
            "some unexpected internal bug, with sensitive detail: db_password=hunter2"
        )

    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend",
        lambda: type("Boom", (), {"embed_batch": _boom})(),
    )

    # Starlette's ServerErrorMiddleware sends the client its proper error
    # response, then *also* re-raises the original exception afterward — by
    # design, so a real ASGI server can still log/see it even though the
    # client already got a clean response. httpx's ASGITransport surfaces
    # that re-raise to the caller by default; raise_app_exceptions=False
    # is httpx's own documented way to instead just hand back the response
    # the client actually received, which is what this test wants to
    # inspect. Only this one test opts out — every other test in this suite
    # keeps the default, so a genuinely-unexpected exception elsewhere still
    # fails loudly instead of being silently downgraded to a response.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as isolated_client:
        await _register_and_login(isolated_client, "security-unexpected-error@example.com")

        resp = await isolated_client.post("/retrieval/search", json={"query": "anything at all"})

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error."}
    assert "hunter2" not in resp.text
    assert "RuntimeError" not in resp.text


async def test_unexpected_exception_response_still_carries_cors_and_tracing_headers(
    monkeypatch,
):
    # Regression test for a real bug found during Phase 7: Starlette always
    # inserts ServerErrorMiddleware as the true outermost layer around
    # anything added via app.add_middleware(), so the bare-Exception handler
    # (registered in register_error_handlers) used to produce a response
    # with no CORS/security/request-id headers at all. A browser's
    # `fetch()` with credentials: "include" (used throughout this frontend)
    # treats a cross-origin response missing CORS headers as a network
    # failure, not a readable error — hiding every real crash from both the
    # user and any client-side error tracking. Fixed by constructing
    # CORSMiddleware/RequestContextMiddleware/SecurityHeadersMiddleware
    # directly around the whole app in app/main.py, genuinely outside
    # ServerErrorMiddleware's boundary, not just via add_middleware().
    async def _boom(self, texts):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend",
        lambda: type("Boom", (), {"embed_batch": _boom})(),
    )

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as isolated_client:
        await _register_and_login(isolated_client, "security-500-headers@example.com")

        resp = await isolated_client.post(
            "/retrieval/search",
            json={"query": "anything at all"},
            headers={"Origin": "http://localhost:3000"},
        )

    assert resp.status_code == 500
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert "X-Request-ID" in resp.headers
