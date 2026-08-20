import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Computed, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized (also reachable via document_id -> documents.user_id) per the
    # multi-tenant isolation convention: every resource table carries its own
    # user_id FK so ownership can be checked/filtered without a join.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Python attribute can't be named `metadata` — that shadows
    # Base.metadata (SQLAlchemy's schema registry). The DB column is still
    # named `metadata`, per the schema this table was specified with.
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    # Postgres-native full-text search index — GENERATED ALWAYS AS ... STORED,
    # so it's derived from `content` by Postgres itself on every insert/update
    # and can never drift out of sync with it (no app-code responsibility to
    # remember to update it). See ARCHITECTURE.md for why this instead of an
    # in-memory rank_bm25 index.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
