import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.storage import StorageBackend, get_storage_backend
from app.core.vector_store import get_vector_store
from app.models.document import DocumentStatus
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.parsing import ParsingError
from app.tasks.document_processing import (
    DocumentProcessingTask,
    _mark_failed,
    _process,
    process_document,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeEmbeddingBackend:
    """Deterministic fake — no real OpenAI calls in this test file. Every
    embed_batch call returns one fixed-size vector per input text."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        size = get_settings().qdrant_vector_size
        return [[0.1] * size for _ in texts]


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    monkeypatch.setattr(
        "app.tasks.document_processing.get_embedding_backend", lambda: FakeEmbeddingBackend()
    )


def test_process_document_is_configured_with_retry_policy():
    assert process_document.max_retries == 3
    assert process_document.autoretry_for == (Exception,)
    assert process_document.retry_backoff is True


# Every test below calls `_process`/`_mark_failed` directly rather than the
# real `process_document(...)` task entrypoint. That's deliberate, not an
# oversight: `process_document` wraps its body in its own `asyncio.run(...)`
# call, and this suite's `AsyncSessionLocal` engine and `get_vector_store()`
# client are both `@lru_cache`d singletons bound to whichever event loop
# first touches them — pytest-asyncio's *session-scoped* loop, shared by
# every other async test here. Calling the real sync entrypoint from a
# throwaway `asyncio.run()` loop (the only way to test a function that
# itself calls `asyncio.run()`, since that can't nest inside an
# already-running loop) breaks both of those singletons with a "bound to a
# different event loop" error — verified directly by hitting exactly that
# failure while attempting it. `_process` is the entire functional body of
# the task and has full coverage below; the ~2 lines unique to
# `process_document` itself (binding request_id/task_id into structlog's
# contextvars) were verified instead against the real, running Celery
# worker in Phase 7's live end-to-end check — see docs/PROGRESS.md.


async def _make_document(
    session: AsyncSession,
    email: str,
    fixture_name: str = "sample.txt",
    file_type: str = "txt",
):
    user = await UserRepository(session).create(email=email, hashed_password="x")
    content = (FIXTURES_DIR / fixture_name).read_bytes()
    document_id = uuid.uuid4()
    storage_path = await get_storage_backend().save(
        f"test-fixtures/{document_id}/v1/{fixture_name}", content
    )
    document = await DocumentRepository(session).create(
        document_id=document_id,
        user_id=user.id,
        filename=fixture_name,
        file_type=file_type,
        file_size_bytes=len(content),
        storage_path=storage_path,
    )
    await session.commit()
    return document


async def test_process_pdf_creates_chunks_with_correct_page_and_section_metadata(
    db_session: AsyncSession,
):
    document = await _make_document(db_session, "task-pdf@example.com", "sample.pdf", "pdf")

    await _process(db_session, document.id, document.version)

    refreshed = await DocumentRepository(db_session).get_by_id(document.id)
    assert refreshed.status == DocumentStatus.READY.value
    assert refreshed.error_message is None

    chunks = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    assert len(chunks) > 0
    pages = {c.chunk_metadata["page_number"] for c in chunks}
    assert pages == {1, 2}
    sections = {tuple(c.chunk_metadata["section_path"]) for c in chunks}
    assert ("Introduction",) in sections
    assert ("Background",) in sections
    assert all(c.chunk_metadata["document_version"] == document.version for c in chunks)

    # Every persisted chunk must have a matching Qdrant vector, keyed by the
    # same chunk_id — this is the actual "embedding + indexing" wiring, not
    # just the pre-existing chunking pipeline from Phase 3.
    vector_count = await get_vector_store().count_for_document(document.id)
    assert vector_count == len(chunks)

    search_results = await get_vector_store().search(
        user_id=document.user_id,
        query_vector=[0.1] * get_settings().qdrant_vector_size,
        top_k=10,
        document_id=document.id,
    )
    assert len(search_results) == len(chunks)
    result_chunk_ids = {r.payload["chunk_id"] for r in search_results}
    assert result_chunk_ids == {str(c.id) for c in chunks}


async def test_process_docx_creates_chunks_with_nested_section_paths(db_session: AsyncSession):
    document = await _make_document(db_session, "task-docx@example.com", "sample.docx", "docx")

    await _process(db_session, document.id, document.version)

    refreshed = await DocumentRepository(db_session).get_by_id(document.id)
    assert refreshed.status == DocumentStatus.READY.value

    chunks = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    sections = {tuple(c.chunk_metadata["section_path"]) for c in chunks}
    assert ("Project Overview", "Goals") in sections


async def test_process_markdown_creates_chunks(db_session: AsyncSession):
    document = await _make_document(db_session, "task-md@example.com", "sample.md", "md")

    await _process(db_session, document.id, document.version)

    refreshed = await DocumentRepository(db_session).get_by_id(document.id)
    assert refreshed.status == DocumentStatus.READY.value

    chunks = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    assert any("hello world" in c.content for c in chunks)


async def test_process_chunk_no_chunk_exceeds_configured_token_limit(db_session: AsyncSession):
    document = await _make_document(db_session, "task-limit@example.com", "sample.md", "md")

    await _process(db_session, document.id, document.version)

    chunks = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    max_tokens = get_settings().chunk_max_tokens
    assert all(c.chunk_metadata["token_count"] <= max_tokens for c in chunks)


async def test_process_corrupt_pdf_raises_and_leaves_status_processing(db_session: AsyncSession):
    document = await _make_document(db_session, "task-corrupt@example.com", "corrupt.pdf", "pdf")

    with pytest.raises(ParsingError):
        await _process(db_session, document.id, document.version)

    # _process itself doesn't catch — status is whatever was last committed
    # (PROCESSING, set before the parse attempt). Turning this into `failed`
    # is the on_failure hook's job, tested separately below via _mark_failed.
    refreshed = await DocumentRepository(db_session).get_by_id(document.id)
    assert refreshed.status == DocumentStatus.PROCESSING.value

    chunks = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    assert chunks == []


async def test_corrupt_file_failure_end_to_end_via_mark_failed(db_session: AsyncSession):
    document = await _make_document(db_session, "task-corrupt2@example.com", "corrupt.docx", "docx")

    try:
        await _process(db_session, document.id, document.version)
    except ParsingError as exc:
        await _mark_failed(document.id, document.version, str(exc))

    await db_session.refresh(document)
    assert document.status == DocumentStatus.FAILED.value
    assert document.error_message
    assert "docx" in document.error_message.lower() or "zip" in document.error_message.lower()


async def test_reprocessing_replaces_old_chunks_rather_than_accumulating(
    db_session: AsyncSession,
):
    document = await _make_document(db_session, "task-reprocess@example.com")
    await _process(db_session, document.id, document.version)

    chunks_v1 = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    assert len(chunks_v1) > 0
    v1_marker = chunks_v1[0].content[:15]
    v1_chunk_ids = {c.id for c in chunks_v1}
    assert await get_vector_store().count_for_document(document.id) == len(chunks_v1)

    new_content = b"Totally new content for version two.\n\nA second paragraph follows."
    document = await DocumentRepository(db_session).get_by_id(document.id)
    new_storage_path = await get_storage_backend().save(
        f"test-fixtures/{document.id}/v2/new.txt", new_content
    )
    await DocumentRepository(db_session).add_version(
        document,
        filename="new.txt",
        file_type="txt",
        file_size_bytes=len(new_content),
        storage_path=new_storage_path,
    )
    await db_session.commit()

    await _process(db_session, document.id, document.version)

    chunks_v2 = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    assert len(chunks_v2) > 0
    joined = " ".join(c.content for c in chunks_v2)
    assert "Totally new content" in joined
    assert not any(v1_marker in c.content for c in chunks_v2)
    assert all(c.chunk_metadata["document_version"] == 2 for c in chunks_v2)

    # Qdrant must reflect only the new version too — old vectors replaced,
    # not left alongside the new ones (a stale-version search leak).
    assert await get_vector_store().count_for_document(document.id) == len(chunks_v2)
    v2_chunk_ids = {c.id for c in chunks_v2}
    assert v1_chunk_ids.isdisjoint(v2_chunk_ids)
    search_results = await get_vector_store().search(
        user_id=document.user_id,
        query_vector=[0.1] * get_settings().qdrant_vector_size,
        top_k=10,
        document_id=document.id,
    )
    result_chunk_ids = {r.payload["chunk_id"] for r in search_results}
    assert result_chunk_ids == {str(cid) for cid in v2_chunk_ids}
    assert result_chunk_ids.isdisjoint({str(cid) for cid in v1_chunk_ids})


async def test_process_skips_document_with_stale_version(db_session: AsyncSession):
    document = await _make_document(db_session, "task-stale@example.com")

    await _process(db_session, document.id, version=document.version + 1)

    refreshed = await DocumentRepository(db_session).get_by_id(document.id)
    assert refreshed.status == DocumentStatus.UPLOADED.value


class _RacyStorage(StorageBackend):
    """Wraps the real storage backend, bumping the target document's version
    right after the file is read — simulating a re-upload landing while this
    run is mid-parse, to exercise the post-processing staleness check."""

    def __init__(self, real: StorageBackend, session: AsyncSession, document_id: uuid.UUID):
        self._real = real
        self._session = session
        self._document_id = document_id

    async def save(self, key: str, content: bytes) -> str:
        return await self._real.save(key, content)

    async def read(self, storage_path: str) -> bytes:
        content = await self._real.read(storage_path)
        doc = await DocumentRepository(self._session).get_by_id(self._document_id)
        doc.version += 1
        await self._session.commit()
        return content

    async def delete(self, storage_path: str) -> None:
        await self._real.delete(storage_path)


async def test_process_discards_result_if_superseded_during_processing(
    db_session: AsyncSession, monkeypatch
):
    document = await _make_document(db_session, "task-race@example.com")
    original_version = document.version

    racy_storage = _RacyStorage(get_storage_backend(), db_session, document.id)
    monkeypatch.setattr(
        "app.tasks.document_processing.get_storage_backend", lambda: racy_storage
    )

    await _process(db_session, document.id, original_version)

    refreshed = await DocumentRepository(db_session).get_by_id(document.id)
    # The newer version's row must not be stomped back to READY by the stale run,
    # and the stale run's chunks must not have been persisted either.
    assert refreshed.status != DocumentStatus.READY.value
    chunks = await ChunkRepository(db_session).list_for_document(document.id, document.user_id)
    assert chunks == []
    assert await get_vector_store().count_for_document(document.id) == 0


class _FailingVectorStore:
    async def replace_for_document(self, document_id: uuid.UUID, chunks: list) -> None:
        raise RuntimeError("simulated Qdrant outage")


async def test_process_leaves_document_non_ready_if_indexing_fails(
    db_session: AsyncSession, monkeypatch
):
    document = await _make_document(db_session, "task-indexfail@example.com")

    monkeypatch.setattr(
        "app.tasks.document_processing.get_vector_store", lambda: _FailingVectorStore()
    )

    with pytest.raises(RuntimeError, match="simulated Qdrant outage"):
        await _process(db_session, document.id, document.version)

    # Verify via a fresh session, not db_session itself — db_session still
    # has the failed call's uncommitted chunk insert pending in its identity
    # map/transaction, which a real caller would never see: in production,
    # _with_session's `async with session_factory() as session:` closes the
    # session without committing when an exception propagates, discarding
    # that work entirely (see app/tasks/document_processing.py).
    async with AsyncSessionLocal() as verify_session:
        refreshed = await DocumentRepository(verify_session).get_by_id(document.id)
        assert refreshed.status == DocumentStatus.PROCESSING.value

        chunks = await ChunkRepository(verify_session).list_for_document(
            document.id, document.user_id
        )
        assert chunks == []


async def test_mark_failed_sets_failed_status_with_error_message(db_session: AsyncSession):
    document = await _make_document(db_session, "task-failed@example.com")

    # _mark_failed opens its own session (mirroring the real on_failure hook, which
    # has no request-scoped session to reuse) — refresh this session's copy of the
    # row so the assertion below sees that session's committed write, not a stale
    # in-memory value from before it ran.
    await _mark_failed(document.id, document.version, "boom: processing exploded")
    await db_session.refresh(document)

    assert document.status == DocumentStatus.FAILED.value
    assert document.error_message == "boom: processing exploded"


async def test_mark_failed_skips_stale_version(db_session: AsyncSession):
    document = await _make_document(db_session, "task-failed-stale@example.com")

    await _mark_failed(document.id, document.version + 1, "should not apply")
    await db_session.refresh(document)

    assert document.status == DocumentStatus.UPLOADED.value
    assert document.error_message is None


def test_on_failure_does_nothing_when_document_id_and_version_missing():
    # Defensive guard for a malformed/unexpected task invocation — must not
    # attempt asyncio.run(...) (which would raise, called from here with no
    # running loop issue, but is still the wrong thing to attempt) when
    # there's nothing identifiable to mark failed.
    task = DocumentProcessingTask()

    task.on_failure(RuntimeError("boom"), "fake-task-id", (), {}, einfo=None)
