import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.file_validation import (
    safe_filename,
    validate_and_normalize_file_type,
    validate_file_size,
)
from app.core.storage import StorageBackend, get_storage_backend
from app.core.vector_store import VectorStore, get_vector_store
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository

settings = get_settings()


class DocumentNotFoundError(Exception):
    pass


class DocumentService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageBackend | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._session = session
        self._documents = DocumentRepository(session)
        self._storage = storage or get_storage_backend()
        self._vector_store = vector_store or get_vector_store()

    async def upload(
        self,
        user_id: uuid.UUID,
        filename: str,
        content: bytes,
        existing_document_id: uuid.UUID | None = None,
    ) -> Document:
        validate_file_size(len(content), settings.max_upload_size_mb)
        clean_filename = safe_filename(filename)
        file_type = validate_and_normalize_file_type(clean_filename, content)

        document: Document | None = None
        if existing_document_id is not None:
            document = await self._documents.get_for_user(existing_document_id, user_id)
            if document is None:
                raise DocumentNotFoundError(existing_document_id)

        next_version = (document.version + 1) if document is not None else 1
        document_id = document.id if document is not None else uuid.uuid4()
        key = f"{user_id}/{document_id}/v{next_version}/{clean_filename}"
        storage_path = await self._storage.save(key, content)

        if document is None:
            document = await self._documents.create(
                document_id=document_id,
                user_id=user_id,
                filename=clean_filename,
                file_type=file_type,
                file_size_bytes=len(content),
                storage_path=storage_path,
            )
        else:
            await self._documents.add_version(
                document,
                filename=clean_filename,
                file_type=file_type,
                file_size_bytes=len(content),
                storage_path=storage_path,
            )

        await self._session.commit()
        await self._session.refresh(document)

        from app.tasks.document_processing import process_document

        # Threads this HTTP request's id through to the task, so a single
        # upload's logs — the request that enqueued it, and every log line
        # emitted while actually processing it — share one `request_id` and
        # can be traced together. See RequestContextMiddleware and
        # app/tasks/document_processing.py.
        request_id = structlog.contextvars.get_contextvars().get("request_id")

        if settings.celery_task_always_eager:
            # No separate worker process in this deployment (see
            # celery_task_always_eager's docstring in app/core/config.py) —
            # run the task function directly instead of enqueueing it.
            # Calling it inline on this coroutine would still break: the
            # task bridges into async code via asyncio.run() (see
            # app/tasks/document_processing.py::_with_session), which
            # cannot be called from within a loop that's already running —
            # exactly the loop this request handler is running on. Running
            # it in a threadpool thread instead gives it a thread with no
            # event loop of its own, so its own asyncio.run() works exactly
            # as it does in a real worker process.
            await run_in_threadpool(
                process_document, str(document.id), document.version, request_id=request_id
            )
            # process_document runs its whole body inside its own throwaway
            # asyncio.run() loop (see app/core/celery_app.py's docstring on
            # this exact failure mode, and tests/test_document_processing_
            # task.py's, which documents hitting it directly). get_vector_
            # store()'s AsyncQdrantClient is a process-wide @lru_cache
            # singleton — the first real call through it binds its httpx
            # transport to whichever loop made that call. Called from here,
            # that's the task's own throwaway loop, which is closed by the
            # time run_in_threadpool returns above: the *next* caller on
            # this request's actual (main) loop — e.g. this same request's
            # eventual retrieval — would hit "RuntimeError: Event loop is
            # closed" reusing that now-dead connection. Clearing the cache
            # forces the next real caller, on whichever loop it's actually
            # running on, to construct a fresh client instead.
            get_vector_store.cache_clear()
            await self._session.refresh(document)
        else:
            process_document.delay(str(document.id), document.version, request_id=request_id)

        return document

    async def list_for_user(self, user_id: uuid.UUID) -> list[Document]:
        return await self._documents.list_for_user(user_id)

    async def get_for_user(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self._documents.get_for_user(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    async def delete(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        document = await self._documents.get_for_user(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError(document_id)

        versions = await self._documents.list_versions(document_id)
        for version in versions:
            await self._storage.delete(version.storage_path)

        # chunks rows (and their Postgres full-text index) cascade-delete at
        # the DB level (chunks.document_id has ON DELETE CASCADE). Qdrant
        # isn't Postgres — there's no FK cascade to lean on there, so it needs
        # an explicit delete. Done before the DB row goes away so a failure
        # here surfaces as a normal exception rather than leaving orphaned
        # vectors silently behind after the document already looks deleted.
        await self._vector_store.delete_for_document(document_id)

        await self._documents.delete(document)
        await self._session.commit()
