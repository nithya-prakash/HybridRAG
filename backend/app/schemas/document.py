import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus
    version: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: DocumentStatus
    error_message: str | None
    updated_at: datetime
