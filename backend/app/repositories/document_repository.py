import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        file_type: str,
        file_size_bytes: int,
        storage_path: str,
    ) -> Document:
        document = Document(
            id=document_id,
            user_id=user_id,
            filename=filename,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            storage_path=storage_path,
            status=DocumentStatus.UPLOADED.value,
            version=1,
        )
        self._session.add(document)
        await self._session.flush()

        self._session.add(
            DocumentVersion(
                document_id=document.id,
                version=1,
                filename=filename,
                file_type=file_type,
                file_size_bytes=file_size_bytes,
                storage_path=storage_path,
            )
        )
        await self._session.flush()
        return document

    async def add_version(
        self,
        document: Document,
        filename: str,
        file_type: str,
        file_size_bytes: int,
        storage_path: str,
    ) -> DocumentVersion:
        document.version += 1
        document.filename = filename
        document.file_type = file_type
        document.file_size_bytes = file_size_bytes
        document.storage_path = storage_path
        document.status = DocumentStatus.UPLOADED.value
        document.error_message = None

        version = DocumentVersion(
            document_id=document.id,
            version=document.version,
            filename=filename,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            storage_path=storage_path,
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def list_for_user(self, user_id: uuid.UUID) -> list[Document]:
        result = await self._session.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, document_id: uuid.UUID, user_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_many_for_user(
        self, user_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> list[Document]:
        """Batch fetch by id, scoped to user_id — used to resolve filenames
        for citations built from a small set of retrieved chunks' document_ids."""
        if not document_ids:
            return []
        result = await self._session.execute(
            select(Document).where(
                Document.user_id == user_id, Document.id.in_(document_ids)
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        """Unscoped by user — only for the background processing task, which
        operates by document_id after the enqueueing request already checked
        ownership. Never call this from a user-facing route; use `get_for_user`."""
        return await self._session.get(Document, document_id)

    async def list_versions(self, document_id: uuid.UUID) -> list[DocumentVersion]:
        result = await self._session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version)
        )
        return list(result.scalars().all())

    async def update_status(
        self, document: Document, status: DocumentStatus, error_message: str | None = None
    ) -> None:
        document.status = status.value
        document.error_message = error_message
        await self._session.flush()

    async def delete(self, document: Document) -> None:
        await self._session.delete(document)
