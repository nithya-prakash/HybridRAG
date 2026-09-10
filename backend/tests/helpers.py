from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings


async def new_client(raise_app_exceptions: bool = True) -> AsyncClient:
    """A fresh `AsyncClient` against the real app, CSRF-primed the same way
    the `client` fixture in conftest.py is (see that fixture's comment) —
    needed anywhere a test spins up a second client by hand (a "second
    user"/"intruder", or one needing `raise_app_exceptions=False` to inspect
    an unhandled-exception response instead of letting httpx re-raise it)
    instead of using the fixture, since `CsrfMiddleware` requires a matching
    `X-CSRF-Token` header on every unsafe-method request — including the
    `_register_and_login` helpers' own POSTs — and httpx has no browser-JS
    equivalent that reads the cookie back automatically."""
    from app.main import app  # local import: avoids a circular import at module load

    transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    c = AsyncClient(transport=transport, base_url="http://test")
    await c.get("/health")
    token = c.cookies.get("csrf_token")
    if token:
        c.headers["X-CSRF-Token"] = token
    return c


def fake_embed(text: str) -> list[float]:
    """Deterministic bag-of-words hash embedding — no OpenAI calls needed.
    Distinct texts get distinct (L2-normalized) vectors, and texts sharing
    words end up with non-zero cosine similarity, which is enough for dense
    search to produce a meaningful, testable ranking without a real model."""
    size = get_settings().qdrant_vector_size
    vec = [0.0] * size
    for word in text.lower().split():
        vec[hash(word) % size] += 1.0
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class FakeEmbeddingBackend:
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [fake_embed(t) for t in texts]
