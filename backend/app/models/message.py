import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized (also reachable via conversation_id -> conversations.user_id)
    # per the multi-tenant isolation convention every resource table follows —
    # see chunks.user_id for the precedent.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Only populated on assistant messages — the standalone query Phase 5's
    # RetrievalService was actually called with for this turn (after query
    # rewriting), kept for debugging retrieval quality and for evaluation.
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Only populated on assistant messages, in the same rerank order the
    # answer's [n] citation markers were numbered against — reconstructing a
    # message's structured citations later means re-fetching these chunks and
    # re-scanning `content` for its markers, not storing a redundant second
    # copy of citation data that could drift from `content`.
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
