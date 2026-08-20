import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    marker: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int | None
    excerpt: str


class MessageRead(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    rewritten_query: str | None
    citations: list[CitationRead]
    created_at: datetime


class ConversationDetailRead(BaseModel):
    conversation: ConversationRead
    messages: list[MessageRead]


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)
