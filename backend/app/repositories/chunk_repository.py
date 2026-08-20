import uuid
from datetime import datetime

from sqlalchemy import Text, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk as ChunkModel
from app.models.document import Document
from app.services.parsing.models import Chunk as ParsedChunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        document_version: int,
        chunks: list[ParsedChunk],
    ) -> list[ChunkModel]:
        """Delete any existing chunks for this document and insert the given
        ones, as one unit of work — a re-upload's chunks must fully replace the
        previous version's, never mix with them. Returns the newly created
        rows in the same order as `chunks`, so callers can pair each row's
        real `id` (needed as the Qdrant point id) with its source chunk."""
        await self._session.execute(delete(ChunkModel).where(ChunkModel.document_id == document_id))

        rows = []
        for chunk in chunks:
            row = ChunkModel(
                document_id=document_id,
                user_id=user_id,
                content=chunk.content,
                chunk_metadata={
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "section_path": chunk.section_path,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "token_count": chunk.token_count,
                    "content_hash": chunk.content_hash,
                    "document_version": document_version,
                },
            )
            self._session.add(row)
            rows.append(row)
        await self._session.flush()
        return rows

    async def list_for_document(
        self, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[ChunkModel]:
        result = await self._session.execute(
            select(ChunkModel).where(
                ChunkModel.document_id == document_id, ChunkModel.user_id == user_id
            )
        )
        chunks = list(result.scalars().all())
        chunks.sort(key=lambda c: c.chunk_metadata["chunk_index"])
        return chunks

    async def search_by_keyword(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int = 10,
        document_id: uuid.UUID | None = None,
        document_ids: list[uuid.UUID] | None = None,
        file_types: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[tuple[ChunkModel, float]]:
        """Postgres full-text search over `search_vector` (see the Chunk model
        — a GENERATED tsvector column derived from `content`), ranked by
        `ts_rank_cd`. Returns (chunk, rank) pairs, highest rank first. Every
        caller must supply user_id — there is no unscoped search, mirroring
        VectorStore.search. `file_types`/`created_after`/`created_before` are
        the same filters `VectorStore.search` accepts, applied consistently
        here via a join to `documents` (chunks don't carry file_type/created_at
        themselves — no need to denormalize them onto every chunk row the way
        Qdrant's payload has to, since Postgres can just join).

        The query's terms are OR'd together, not AND'd: `plainto_tsquery`
        alone ANDs every term, so a natural multi-word question loses *all*
        results the moment a single word (e.g. a filler word like "good" in
        "what programming language is good for data science") doesn't
        appear anywhere in the corpus — verified hitting exactly this with
        zero results during Phase 5 development. Real BM25 doesn't work that
        way: it scores by term overlap and gives partial credit, it doesn't
        require every query term to be present. `plainto_tsquery` already
        does the stopword-removal/stemming this needs (so "what"/"is"/"for"
        drop out and "programming"/"languag" get stemmed consistently with
        how `content` was indexed) — its rendered text form only ever joins
        terms with `&`, so swapping that for `|` turns the same normalized
        term set into an OR query without reimplementing tokenization."""
        and_query = func.plainto_tsquery("english", query)
        tsquery = func.to_tsquery("english", func.replace(func.cast(and_query, Text), " & ", " | "))
        rank = func.ts_rank_cd(ChunkModel.search_vector, tsquery).label("rank")

        conditions = [ChunkModel.user_id == user_id, ChunkModel.search_vector.op("@@")(tsquery)]
        if document_id is not None:
            conditions.append(ChunkModel.document_id == document_id)
        if document_ids:
            conditions.append(ChunkModel.document_id.in_(document_ids))

        stmt = select(ChunkModel, rank)
        needs_document_join = (
            bool(file_types) or created_after is not None or created_before is not None
        )
        if needs_document_join:
            stmt = stmt.join(Document, Document.id == ChunkModel.document_id)
            if file_types:
                conditions.append(Document.file_type.in_(file_types))
            if created_after is not None:
                conditions.append(Document.created_at >= created_after)
            if created_before is not None:
                conditions.append(Document.created_at <= created_before)

        stmt = stmt.where(*conditions).order_by(rank.desc()).limit(top_k)
        result = await self._session.execute(stmt)
        return [(chunk, rank_value) for chunk, rank_value in result.all()]

    async def get_by_ids(
        self, user_id: uuid.UUID, chunk_ids: list[uuid.UUID]
    ) -> list[ChunkModel]:
        """Batch fetch by id, scoped to user_id — used by RetrievalService to
        pull full chunk content (Qdrant's payload deliberately doesn't carry
        it) for the fused candidate set before reranking."""
        if not chunk_ids:
            return []
        result = await self._session.execute(
            select(ChunkModel).where(
                ChunkModel.user_id == user_id, ChunkModel.id.in_(chunk_ids)
            )
        )
        return list(result.scalars().all())
