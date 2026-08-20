import io
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.vector_store import EmbeddedChunk, get_vector_store
from app.main import app

PASSWORD = "correcthorsebattery"

FILE_FIXTURES = {
    "pdf": ("report.pdf", b"%PDF-1.4\nfake pdf body"),
    "docx": ("letter.docx", b"PK\x03\x04fake docx zip body"),
    "txt": ("notes.txt", b"plain text content"),
    "md": ("readme.md", b"# Heading\n\nsome markdown"),
}


async def _register_and_login(client: AsyncClient, email: str) -> None:
    resp = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201
    resp = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200


async def _second_client(email: str) -> AsyncClient:
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await _register_and_login(c, email)
    return c


def _upload_files(filename: str, content: bytes, content_type: str = "application/octet-stream"):
    return {"file": (filename, io.BytesIO(content), content_type)}


@pytest.mark.parametrize("file_type", ["pdf", "docx", "txt", "md"])
async def test_upload_accepts_each_supported_type(client: AsyncClient, file_type: str):
    await _register_and_login(client, f"user-{file_type}@example.com")
    filename, content = FILE_FIXTURES[file_type]

    response = await client.post("/documents/upload", files=_upload_files(filename, content))

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == filename
    assert body["file_type"] == file_type
    assert body["status"] == "uploaded"
    assert body["version"] == 1
    assert body["error_message"] is None


async def test_upload_rejects_unsupported_extension(client: AsyncClient):
    await _register_and_login(client, "badtype@example.com")

    response = await client.post(
        "/documents/upload", files=_upload_files("virus.exe", b"MZ fake exe")
    )

    assert response.status_code == 415


async def test_upload_rejects_content_that_does_not_match_extension(client: AsyncClient):
    await _register_and_login(client, "mismatch@example.com")

    response = await client.post(
        "/documents/upload", files=_upload_files("fake.pdf", b"this is not a pdf")
    )

    assert response.status_code == 415


async def test_upload_rejects_oversized_file(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 0)
    await _register_and_login(client, "toobig@example.com")

    response = await client.post(
        "/documents/upload", files=_upload_files("notes.txt", b"some content")
    )

    assert response.status_code == 413


async def test_upload_requires_authentication(client: AsyncClient):
    response = await client.post(
        "/documents/upload", files=_upload_files("notes.txt", b"some content")
    )

    assert response.status_code == 401


async def test_list_returns_only_current_users_documents(client: AsyncClient):
    await _register_and_login(client, "usera@example.com")
    await client.post("/documents/upload", files=_upload_files("a.txt", b"a content"))
    await client.post("/documents/upload", files=_upload_files("a2.txt", b"a2 content"))

    other = await _second_client("userb@example.com")
    try:
        await other.post("/documents/upload", files=_upload_files("b.txt", b"b content"))

        a_docs = (await client.get("/documents")).json()
        b_docs = (await other.get("/documents")).json()

        assert {d["filename"] for d in a_docs} == {"a.txt", "a2.txt"}
        assert {d["filename"] for d in b_docs} == {"b.txt"}
    finally:
        await other.aclose()


async def test_user_cannot_get_or_delete_another_users_document(client: AsyncClient):
    await _register_and_login(client, "owner@example.com")
    upload = await client.post("/documents/upload", files=_upload_files("secret.txt", b"secret"))
    document_id = upload.json()["id"]

    intruder = await _second_client("intruder@example.com")
    try:
        get_resp = await intruder.get(f"/documents/{document_id}")
        delete_resp = await intruder.delete(f"/documents/{document_id}")
        status_resp = await intruder.get(f"/documents/{document_id}/status")

        assert get_resp.status_code == 404
        assert delete_resp.status_code == 404
        assert status_resp.status_code == 404

        still_there = await client.get(f"/documents/{document_id}")
        assert still_there.status_code == 200
    finally:
        await intruder.aclose()


async def test_get_nonexistent_document_returns_404(client: AsyncClient):
    await _register_and_login(client, "nodoc@example.com")

    response = await client.get("/documents/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_delete_removes_document(client: AsyncClient):
    await _register_and_login(client, "deleter@example.com")
    upload = await client.post("/documents/upload", files=_upload_files("bye.txt", b"bye"))
    document_id = upload.json()["id"]

    delete_resp = await client.delete(f"/documents/{document_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/documents/{document_id}")
    assert get_resp.status_code == 404


async def test_delete_removes_qdrant_vectors(client: AsyncClient):
    await _register_and_login(client, "vectordelete@example.com")
    upload = await client.post(
        "/documents/upload", files=_upload_files("v.txt", b"vector delete test")
    )
    document_id = uuid.UUID(upload.json()["id"])
    user_id = uuid.UUID((await client.get("/auth/me")).json()["id"])

    # Seed Qdrant directly rather than waiting on the async indexing pipeline
    # (covered separately in test_document_processing_task.py) — this test
    # targets the delete endpoint's cleanup specifically.
    store = get_vector_store()
    await store.replace_for_document(
        document_id,
        [
            EmbeddedChunk(
                chunk_id=uuid.uuid4(),
                vector=[0.1] * get_settings().qdrant_vector_size,
                document_id=document_id,
                user_id=user_id,
                document_version=1,
                page_number=1,
                section_path=[],
                chunk_index=0,
                file_type="txt",
                document_created_at=datetime(2024, 1, 1, tzinfo=UTC),
            )
        ],
    )
    assert await store.count_for_document(document_id) == 1

    delete_resp = await client.delete(f"/documents/{document_id}")

    assert delete_resp.status_code == 204
    assert await store.count_for_document(document_id) == 0


async def test_status_endpoint_returns_status_and_error_message(client: AsyncClient):
    await _register_and_login(client, "poller@example.com")
    upload = await client.post("/documents/upload", files=_upload_files("poll.txt", b"poll me"))
    document_id = upload.json()["id"]

    response = await client.get(f"/documents/{document_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == document_id
    assert body["status"] in ("uploaded", "processing", "ready")
    assert "error_message" in body


async def test_reupload_with_document_id_creates_new_version(client: AsyncClient):
    await _register_and_login(client, "versioner@example.com")
    first = await client.post(
        "/documents/upload", files=_upload_files("draft.txt", b"version one")
    )
    document_id = first.json()["id"]
    assert first.json()["version"] == 1

    second = await client.post(
        "/documents/upload",
        files=_upload_files("draft-v2.txt", b"version two"),
        data={"document_id": document_id},
    )

    assert second.status_code == 201
    body = second.json()
    assert body["id"] == document_id
    assert body["version"] == 2
    assert body["filename"] == "draft-v2.txt"

    listing = await client.get("/documents")
    assert len(listing.json()) == 1


async def test_reupload_to_another_users_document_id_is_rejected(client: AsyncClient):
    await _register_and_login(client, "victim@example.com")
    upload = await client.post("/documents/upload", files=_upload_files("mine.txt", b"mine"))
    document_id = upload.json()["id"]

    attacker = await _second_client("attacker@example.com")
    try:
        response = await attacker.post(
            "/documents/upload",
            files=_upload_files("hijack.txt", b"hijack attempt"),
            data={"document_id": document_id},
        )
        assert response.status_code == 404
    finally:
        await attacker.aclose()
