import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings

# Payload fields that get their own index for fast filtering. user_id is the
# one every query MUST filter by (see VectorStore.search); the rest back the
# retrieval filters from Phase 5 (document_id(s), file type, date range).
_INDEXED_PAYLOAD_FIELDS: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("user_id", models.PayloadSchemaType.KEYWORD),
    ("document_id", models.PayloadSchemaType.KEYWORD),
    ("file_type", models.PayloadSchemaType.KEYWORD),
    ("document_created_at", models.PayloadSchemaType.DATETIME),
)


@dataclass
class EmbeddedChunk:
    chunk_id: uuid.UUID
    vector: list[float]
    document_id: uuid.UUID
    user_id: uuid.UUID
    document_version: int
    page_number: int | None
    section_path: list[str]
    chunk_index: int
    file_type: str
    document_created_at: datetime


def _document_id_filter(document_id: uuid.UUID) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="document_id", match=models.MatchValue(value=str(document_id))
            )
        ]
    )


def _build_search_filter(
    user_id: uuid.UUID,
    document_id: uuid.UUID | None,
    document_ids: list[uuid.UUID] | None,
    file_types: list[str] | None,
    created_after: datetime | None,
    created_before: datetime | None,
) -> models.Filter:
    must: list[models.FieldCondition] = [
        models.FieldCondition(key="user_id", match=models.MatchValue(value=str(user_id)))
    ]
    if document_id is not None:
        must.append(
            models.FieldCondition(
                key="document_id", match=models.MatchValue(value=str(document_id))
            )
        )
    if document_ids:
        must.append(
            models.FieldCondition(
                key="document_id", match=models.MatchAny(any=[str(d) for d in document_ids])
            )
        )
    if file_types:
        must.append(
            models.FieldCondition(key="file_type", match=models.MatchAny(any=file_types))
        )
    if created_after is not None or created_before is not None:
        must.append(
            models.FieldCondition(
                key="document_created_at",
                range=models.DatetimeRange(gte=created_after, lte=created_before),
            )
        )
    return models.Filter(must=must)


class VectorStore:
    """Thin wrapper around Qdrant — the only place in the codebase that talks
    to the qdrant_client library directly. See ARCHITECTURE.md for why this
    is one shared collection (not one per user) and how isolation is enforced
    here instead: every read method requires a user_id and filters on it —
    there is no "search everything" method to misuse.
    """

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        settings = get_settings()
        self._collection = settings.qdrant_collection
        self._vector_size = settings.qdrant_vector_size
        self._client = client or AsyncQdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key
        )
        self._ensured = False

    async def ensure_collection(self) -> None:
        """Idempotent collection + payload index setup. Cheap to call
        repeatedly (skips after the first success within this process)."""
        if self._ensured:
            return

        if not await self._client.collection_exists(self._collection):
            try:
                await self._client.create_collection(
                    self._collection,
                    vectors_config=models.VectorParams(
                        size=self._vector_size, distance=models.Distance.COSINE
                    ),
                )
            except Exception:
                # A concurrent worker may have created it between our existence
                # check and this call — the desired end state (collection
                # exists) holds either way, so only re-raise if it genuinely
                # doesn't exist now.
                if not await self._client.collection_exists(self._collection):
                    raise
            for field_name, schema_type in _INDEXED_PAYLOAD_FIELDS:
                await self._client.create_payload_index(
                    self._collection,
                    field_name=field_name,
                    field_schema=schema_type,
                )

        self._ensured = True

    async def replace_for_document(
        self, document_id: uuid.UUID, chunks: list[EmbeddedChunk]
    ) -> None:
        """Delete any existing vectors for this document, then upsert the
        given ones — mirrors ChunkRepository.replace_for_document's delete-
        then-insert shape, so a re-upload's vectors fully replace the
        previous version's rather than accumulating alongside them. There is
        a brief window with zero vectors for this document between the two
        calls; a search landing in that window returns nothing for it rather
        than stale content, which is the failure mode we want (see
        ARCHITECTURE.md)."""
        await self.ensure_collection()
        await self.delete_for_document(document_id)
        if not chunks:
            return

        points = [
            models.PointStruct(
                id=str(chunk.chunk_id),
                vector=chunk.vector,
                payload={
                    "chunk_id": str(chunk.chunk_id),
                    "document_id": str(chunk.document_id),
                    "user_id": str(chunk.user_id),
                    "document_version": chunk.document_version,
                    "page_number": chunk.page_number,
                    "section_path": chunk.section_path,
                    "chunk_index": chunk.chunk_index,
                    "file_type": chunk.file_type,
                    "document_created_at": chunk.document_created_at.isoformat(),
                },
            )
            for chunk in chunks
        ]
        await self._client.upsert(self._collection, points=points)

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        await self.ensure_collection()
        await self._client.delete(
            self._collection,
            points_selector=models.FilterSelector(filter=_document_id_filter(document_id)),
        )

    async def search(
        self,
        user_id: uuid.UUID,
        query_vector: list[float],
        top_k: int,
        document_id: uuid.UUID | None = None,
        document_ids: list[uuid.UUID] | None = None,
        file_types: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[models.ScoredPoint]:
        """Every caller must supply user_id — there is no unscoped search.
        `document_id` (single) and `document_ids` (list) may be combined with
        the other filters freely; adding a new filterable field means adding
        one field to the payload at index time (see `replace_for_document`)
        and one branch in `_build_search_filter` — nothing else changes."""
        await self.ensure_collection()
        query_filter = _build_search_filter(
            user_id, document_id, document_ids, file_types, created_after, created_before
        )
        response = await self._client.query_points(
            self._collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
        )
        return response.points

    async def count_for_document(self, document_id: uuid.UUID) -> int:
        """Verification/test helper — not used by the indexing pipeline."""
        await self.ensure_collection()
        result = await self._client.count(
            self._collection, count_filter=_document_id_filter(document_id)
        )
        return result.count


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()
