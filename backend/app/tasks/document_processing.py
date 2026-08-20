import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.embeddings import get_embedding_backend
from app.core.logging import get_logger
from app.core.storage import get_storage_backend
from app.core.vector_store import EmbeddedChunk, get_vector_store
from app.models.document import DocumentStatus
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.parsing import chunk_document, parse_document

# structlog's own get_logger, not Celery's get_task_logger — this worker
# process now runs the same configure_logging() the API does (see
# app/core/celery_app.py's setup_logging signal handler), so every log line
# here goes through the same structured-kwargs, contextvars-aware pipeline
# as the rest of the app, not Celery's plain %-style default formatting.
logger = get_logger(__name__)


async def _with_session(coro_fn: Callable[[AsyncSession], Awaitable[None]]) -> None:
    """Create an engine/session scoped to a single task invocation and dispose it
    before returning. Celery tasks here run via `asyncio.run()`, which opens a new
    event loop per call — a module-level engine's connection pool would end up
    bound to a stale, closed loop on the second invocation in the same worker
    process (the same failure mode hit with pytest-asyncio in Phase 1)."""
    settings = get_settings()
    # No pool_pre_ping here: this engine is freshly created and disposed within a
    # single task invocation, so its connection can never have gone stale between
    # uses — pre-ping exists to protect long-lived pools, not one-shot ones.
    engine = create_async_engine(settings.postgres_url)
    try:
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            await coro_fn(session)
    finally:
        await engine.dispose()


async def _process(session: AsyncSession, document_id: uuid.UUID, version: int) -> None:
    start = time.perf_counter()
    repo = DocumentRepository(session)

    document = await repo.get_by_id(document_id)
    if document is None or document.version != version:
        logger.info(
            "document_processing_skipped_stale",
            document_id=str(document_id),
            version=version,
            reason="missing" if document is None else "stale",
        )
        return

    await repo.update_status(document, DocumentStatus.PROCESSING)
    await session.commit()

    # Parsing/chunking/embedding is pure computation against the stored file —
    # no DB or Qdrant writes happen until it's fully done, so a ParsingError
    # (or an embedding-API error, or anything else) raised here leaves the
    # previous version's chunks, vectors, and status completely untouched. It
    # propagates out of this function; the task's autoretry_for + on_failure
    # handle turning it into a `failed` row with the error message.
    content = await get_storage_backend().read(document.storage_path)
    parsed = parse_document(document.file_type, content)
    chunks = chunk_document(parsed)
    vectors = await get_embedding_backend().embed_batch([chunk.content for chunk in chunks])

    # Re-fetch: a re-upload may have superseded this version while we were
    # parsing/embedding — if so, this run's result is stale and must not win.
    document = await repo.get_by_id(document_id)
    if document is None or document.version != version:
        logger.info(
            "document_processing_discarded_superseded",
            document_id=str(document_id),
            version=version,
        )
        return

    # Postgres chunk replacement, Qdrant vector replacement, and the status
    # flip happen as one logical unit before the single commit below — if
    # anything raises partway (including the Qdrant call), nothing here has
    # been committed to Postgres, so the previous version's chunks are left
    # exactly as they were. Qdrant itself isn't transactional with Postgres
    # (no distributed transaction spans both), so on a retry after a partial
    # Qdrant failure, the vector replacement simply runs again — its
    # delete-then-upsert shape makes that safe to repeat. See
    # ARCHITECTURE.md for the full reasoning and the narrow inconsistency
    # window this design accepts.
    chunk_rows = await ChunkRepository(session).replace_for_document(
        document_id=document.id,
        user_id=document.user_id,
        document_version=document.version,
        chunks=chunks,
    )
    embedded_chunks = [
        EmbeddedChunk(
            chunk_id=row.id,
            vector=vector,
            document_id=document.id,
            user_id=document.user_id,
            document_version=document.version,
            page_number=chunk.page_number,
            section_path=chunk.section_path,
            chunk_index=chunk.chunk_index,
            file_type=document.file_type,
            document_created_at=document.created_at,
        )
        for row, chunk, vector in zip(chunk_rows, chunks, vectors, strict=True)
    ]
    await get_vector_store().replace_for_document(document.id, embedded_chunks)

    await repo.update_status(document, DocumentStatus.READY)
    await session.commit()

    logger.info(
        "document_processing_complete",
        document_id=str(document_id),
        version=version,
        chunk_count=len(chunks),
        elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
    )


async def _mark_failed(document_id: uuid.UUID, version: int, error_message: str) -> None:
    async def _do(session: AsyncSession) -> None:
        repo = DocumentRepository(session)
        document = await repo.get_by_id(document_id)
        if document is None or document.version != version:
            return
        await repo.update_status(
            document, DocumentStatus.FAILED, error_message=error_message[:2000]
        )
        await session.commit()

    await _with_session(_do)


class DocumentProcessingTask(celery_app.Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        document_id_raw = kwargs.get("document_id", args[0] if args else None)
        version_raw = kwargs.get("version", args[1] if len(args) > 1 else None)
        if document_id_raw is None or version_raw is None:
            return
        asyncio.run(_mark_failed(uuid.UUID(str(document_id_raw)), int(version_raw), str(exc)))


@celery_app.task(
    bind=True,
    base=DocumentProcessingTask,
    name="process_document",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def process_document(self, document_id: str, version: int, request_id: str | None = None) -> None:
    # Binds the id of the HTTP request that enqueued this task (see
    # DocumentService.upload) into structlog's contextvars for the task's
    # duration — every log line this run emits, including ones deep inside
    # the parsing/embedding pipeline, then carries the same `request_id` a
    # user's upload request logged, so the two can be correlated across the
    # sync-request / async-task boundary. Also binds Celery's own task_id,
    # which is unique per attempt (distinct across retries) where
    # request_id stays the same for every retry of one logical upload.
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=self.request.id, request_id=request_id)

    async def _do(session: AsyncSession) -> None:
        await _process(session, uuid.UUID(document_id), version)

    asyncio.run(_with_session(_do))
