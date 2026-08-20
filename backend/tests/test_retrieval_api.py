import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.vector_store import EmbeddedChunk, get_vector_store
from app.main import app
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.parsing.models import Chunk as ParsedChunk
from tests.helpers import FakeEmbeddingBackend, fake_embed

PASSWORD = "correcthorsebattery"

CORPUS = [
    "Python is a popular programming language for data science and web development.",
    "The Eiffel Tower is a famous landmark in Paris, France.",
]


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend", lambda: FakeEmbeddingBackend()
    )


async def _register_and_login(client: AsyncClient, email: str) -> uuid.UUID:
    resp = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201
    resp = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    me = await client.get("/auth/me")
    return uuid.UUID(me.json()["id"])


async def _index_for_user(
    db_session, user_id: uuid.UUID, contents: list[str], filename: str
) -> None:
    document = await DocumentRepository(db_session).create(
        document_id=uuid.uuid4(),
        user_id=user_id,
        filename=filename,
        file_type="txt",
        file_size_bytes=1,
        storage_path=f"/tmp/{filename}",
    )
    parsed_chunks = [
        ParsedChunk(
            content=text, chunk_index=i, page_number=1, section_path=[],
            char_start=0, char_end=len(text), token_count=len(text.split()), content_hash=str(i),
        )
        for i, text in enumerate(contents)
    ]
    rows = await ChunkRepository(db_session).replace_for_document(
        document_id=document.id, user_id=user_id, document_version=1, chunks=parsed_chunks
    )
    await db_session.commit()

    embedded = [
        EmbeddedChunk(
            chunk_id=row.id, vector=fake_embed(chunk.content), document_id=document.id,
            user_id=user_id, document_version=1, page_number=1, section_path=[],
            chunk_index=chunk.chunk_index, file_type="txt", document_created_at=document.created_at,
        )
        for row, chunk in zip(rows, parsed_chunks, strict=True)
    ]
    await get_vector_store().replace_for_document(document.id, embedded)


async def test_search_requires_authentication(client: AsyncClient):
    response = await client.post("/retrieval/search", json={"query": "anything"})

    assert response.status_code == 401


async def test_search_returns_ranked_results_with_all_scores(client: AsyncClient, db_session):
    user_id = await _register_and_login(client, "api-search@example.com")
    await _index_for_user(db_session, user_id, CORPUS, "corpus.txt")

    response = await client.post(
        "/retrieval/search",
        json={"query": "what programming language is good for data science"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "what programming language is good for data science"
    assert body["results"]
    top = body["results"][0]
    assert "Python" in top["content"]
    for field in ("dense_score", "bm25_score", "rrf_score", "rerank_score"):
        assert field in top
    assert set(body["timings_ms"]) >= {
        "embed_query_ms", "dense_search_ms", "bm25_search_ms", "fusion_ms", "rerank_ms", "total_ms",
    }


async def test_search_scopes_results_to_authenticated_user(client: AsyncClient, db_session):
    owner_id = await _register_and_login(client, "api-owner@example.com")
    await _index_for_user(db_session, owner_id, CORPUS, "owner.txt")

    intruder = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        await _register_and_login(intruder, "api-intruder@example.com")

        response = await intruder.post(
            "/retrieval/search",
            json={"query": "what programming language is good for data science"},
        )

        assert response.status_code == 200
        assert response.json()["results"] == []
    finally:
        await intruder.aclose()


async def test_search_respects_top_k(client: AsyncClient, db_session):
    user_id = await _register_and_login(client, "api-topk@example.com")
    await _index_for_user(db_session, user_id, CORPUS, "corpus.txt")

    response = await client.post(
        "/retrieval/search",
        json={"query": "Paris France Python data science", "top_k": 1},
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1


async def test_search_applies_document_id_filter(client: AsyncClient, db_session):
    user_id = await _register_and_login(client, "api-filter@example.com")
    await _index_for_user(db_session, user_id, [CORPUS[0]], "python.txt")
    await _index_for_user(db_session, user_id, [CORPUS[1]], "paris.txt")
    docs = await DocumentRepository(db_session).list_for_user(user_id)
    paris_doc = next(d for d in docs if d.filename == "paris.txt")

    response = await client.post(
        "/retrieval/search",
        json={
            "query": "Python programming",
            "filters": {"document_ids": [str(paris_doc.id)]},
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert all(r["document_id"] == str(paris_doc.id) for r in results)
