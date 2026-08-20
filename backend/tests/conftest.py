import os
import tempfile
from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Must run before any `app.*` import below triggers a Settings() construction
# (get_settings() is cached on first call, wherever that happens to be). The
# real UPLOAD_DIR default (/data/uploads) only exists because the Docker
# image's build step creates and chowns it — running the suite anywhere else
# (a bare CI runner, a developer's host outside Docker) hits a real
# PermissionError/FileNotFoundError trying to mkdir it. A session-scoped temp
# directory works identically everywhere, with no environment-specific setup
# needed.
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="rag-test-uploads-"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import AsyncSessionLocal, engine  # noqa: E402
from app.core.vector_store import get_vector_store  # noqa: E402
from app.main import app  # noqa: E402

settings = get_settings()


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE refresh_tokens, chunks, document_versions, documents, users"
                " CASCADE"
            )
        )

    redis_client = aioredis.from_url(settings.redis_url)
    await redis_client.flushdb()
    await redis_client.aclose()

    # Drop and let the next ensure_collection() recreate it — mirrors the
    # Postgres TRUNCATE above: every test starts against a genuinely empty
    # Qdrant collection, not one carrying leftover points from a previous
    # test. Reaching into VectorStore's "private" client/flag here is
    # test-only cleanup, not a pattern to follow in application code.
    vector_store = get_vector_store()
    try:
        await vector_store._client.delete_collection(settings.qdrant_collection)
    except Exception:
        pass
    vector_store._ensured = False

    yield


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
