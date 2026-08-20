import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client.http.exceptions import ResponseHandlingException

from app.core.vector_store import EmbeddedChunk, get_vector_store
from app.main import app
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.parsing.models import Chunk as ParsedChunk
from app.services.rag.prompts import INSUFFICIENT_CONTEXT_MESSAGE
from tests.helpers import FakeEmbeddingBackend, fake_embed
from tests.test_conversation_service import FakeChatBackend

PASSWORD = "correcthorsebattery"

CORPUS = [
    "Employees may book economy class flights for trips under six hours.",
    "Meal reimbursement is capped at 75 dollars per day while traveling for business.",
]


@pytest.fixture(autouse=True)
def _fake_backends(monkeypatch):
    # Three call sites, each importing its own reference to these factories —
    # "patch where it's used," not where it's defined (see
    # app/services/retrieval/service.py, app/services/rag/conversation_service.py,
    # app/services/rag/query_rewriter.py).
    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend", lambda: FakeEmbeddingBackend()
    )
    monkeypatch.setattr(
        "app.services.rag.conversation_service.get_chat_backend", lambda: FakeChatBackend()
    )
    monkeypatch.setattr(
        "app.services.rag.query_rewriter.get_chat_backend", lambda: FakeChatBackend()
    )


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for record in text.split("\n\n"):
        if not record.strip():
            continue
        event = "message"
        data = None
        for line in record.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if data is not None:
            events.append((event, data))
    return events


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


async def test_conversations_endpoints_require_authentication(client: AsyncClient):
    assert (await client.post("/conversations")).status_code == 401
    assert (await client.get("/conversations")).status_code == 401
    assert (await client.get(f"/conversations/{uuid.uuid4()}")).status_code == 401
    assert (
        await client.post(f"/conversations/{uuid.uuid4()}/messages", json={"content": "hi"})
    ).status_code == 401


async def test_create_and_list_conversations(client: AsyncClient):
    await _register_and_login(client, "conv-basic@example.com")

    create_resp = await client.post("/conversations")
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["title"] is None

    list_resp = await client.get("/conversations")
    assert list_resp.status_code == 200
    assert [c["id"] for c in list_resp.json()] == [body["id"]]


async def test_get_nonexistent_conversation_returns_404(client: AsyncClient):
    await _register_and_login(client, "conv-404@example.com")

    resp = await client.get(f"/conversations/{uuid.uuid4()}")

    assert resp.status_code == 404


async def test_get_another_users_conversation_returns_404(client: AsyncClient):
    await _register_and_login(client, "conv-owner@example.com")
    conversation_id = (await client.post("/conversations")).json()["id"]

    intruder = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        await _register_and_login(intruder, "conv-intruder@example.com")
        resp = await intruder.get(f"/conversations/{conversation_id}")
        assert resp.status_code == 404
    finally:
        await intruder.aclose()


async def test_post_message_to_nonexistent_conversation_returns_404_before_streaming(
    client: AsyncClient,
):
    await _register_and_login(client, "conv-post404@example.com")

    resp = await client.post(f"/conversations/{uuid.uuid4()}/messages", json={"content": "hi"})

    assert resp.status_code == 404


async def test_post_message_rejects_empty_content(client: AsyncClient):
    await _register_and_login(client, "conv-empty@example.com")
    conversation_id = (await client.post("/conversations")).json()["id"]

    resp = await client.post(f"/conversations/{conversation_id}/messages", json={"content": ""})

    assert resp.status_code == 422


async def test_post_message_streams_grounded_answer_with_citations(
    client: AsyncClient, db_session
):
    user_id = await _register_and_login(client, "conv-stream@example.com")
    await _index_for_user(db_session, user_id, CORPUS, "policy.txt")
    conversation_id = (await client.post("/conversations")).json()["id"]

    resp = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is the meal reimbursement cap?"},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    token_events = [d for e, d in events if e == "token"]
    citation_events = [d for e, d in events if e == "citations"]

    assert token_events
    assert citation_events
    assert citation_events[0]["citations"]
    assert citation_events[0]["citations"][0]["filename"] == "policy.txt"
    assert "done" in [e for e, _ in events]


async def test_post_message_declines_for_out_of_corpus_question(client: AsyncClient, db_session):
    user_id = await _register_and_login(client, "conv-decline@example.com")
    await _index_for_user(db_session, user_id, CORPUS, "policy.txt")
    conversation_id = (await client.post("/conversations")).json()["id"]

    resp = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is the boiling point of mercury?"},
    )

    events = _parse_sse(resp.text)
    token_events = [d for e, d in events if e == "token"]
    citation_events = [d for e, d in events if e == "citations"]
    full_text = "".join(t["delta"] for t in token_events)

    assert INSUFFICIENT_CONTEXT_MESSAGE in full_text
    assert citation_events[0]["citations"] == []


async def test_get_conversation_returns_history_with_reconstructed_citations(
    client: AsyncClient, db_session
):
    user_id = await _register_and_login(client, "conv-history@example.com")
    await _index_for_user(db_session, user_id, CORPUS, "policy.txt")
    conversation_id = (await client.post("/conversations")).json()["id"]
    await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is the meal reimbursement cap?"},
    )

    detail = await client.get(f"/conversations/{conversation_id}")

    assert detail.status_code == 200
    body = detail.json()
    assert body["conversation"]["id"] == conversation_id
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"
    assert body["messages"][1]["citations"]


async def test_post_message_streams_error_event_when_downstream_unavailable(
    client: AsyncClient, monkeypatch
):
    # Unlike /retrieval/search's equivalent test (a plain 503 — see
    # test_security.py), a streaming response has already committed to 200
    # before generation starts, so a downstream outage here has to surface
    # as a labeled SSE `error` event instead — see the router's own comment
    # on this. This test covers that except branch directly.
    await _register_and_login(client, "conv-downstream-down@example.com")
    conversation_id = (await client.post("/conversations")).json()["id"]

    async def _boom(self, texts):
        raise ResponseHandlingException("simulated Qdrant outage")

    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend",
        lambda: type("Boom", (), {"embed_batch": _boom})(),
    )

    resp = await client.post(
        f"/conversations/{conversation_id}/messages", json={"content": "hello"}
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    error_events = [d for e, d in events if e == "error"]
    assert error_events
    # classify_llm_error (app/core/llm_errors.py) names the specific known
    # dependency rather than a one-size-fits-all message.
    assert "qdrant" in error_events[0]["detail"].lower()
    assert "ResponseHandlingException" not in resp.text
    assert "simulated Qdrant outage" not in resp.text
    assert "done" not in [e for e, _ in events]


async def test_post_message_streams_error_event_on_unexpected_exception(
    client: AsyncClient, monkeypatch
):
    await _register_and_login(client, "conv-unexpected-error@example.com")
    conversation_id = (await client.post("/conversations")).json()["id"]

    async def _boom(self, texts):
        raise RuntimeError("simulated bug, sensitive detail: db_password=hunter2")

    monkeypatch.setattr(
        "app.services.retrieval.service.get_embedding_backend",
        lambda: type("Boom", (), {"embed_batch": _boom})(),
    )

    resp = await client.post(
        f"/conversations/{conversation_id}/messages", json={"content": "hello"}
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [d for e, d in events if e == "error"] == [{"detail": "Answer generation failed."}]
    assert "hunter2" not in resp.text
    assert "RuntimeError" not in resp.text
