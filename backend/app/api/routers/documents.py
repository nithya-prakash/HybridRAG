import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.file_validation import FileTooLargeError, UnsupportedFileTypeError
from app.core.rate_limit import limiter
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentRead, DocumentStatusRead
from app.services.document_service import DocumentNotFoundError, DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().upload_rate_limit)
async def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    document_id: uuid.UUID | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Document:
    content = await file.read()
    service = DocumentService(session)
    try:
        return await service.upload(
            user_id=current_user.id,
            filename=file.filename or "upload",
            content=content,
            existing_document_id=document_id,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Document]:
    return await DocumentService(session).list_for_user(current_user.id)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Document:
    try:
        return await DocumentService(session).get_for_user(current_user.id, document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc


@router.get("/{document_id}/status", response_model=DocumentStatusRead)
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Document:
    try:
        return await DocumentService(session).get_for_user(current_user.id, document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    try:
        await DocumentService(session).delete(current_user.id, document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc
