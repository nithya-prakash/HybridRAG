import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RetrievalFilters:
    """Passed through to both the dense (Qdrant) and keyword (Postgres FTS)
    legs identically, so a filtered search is consistent across both before
    fusion — see VectorStore.search / ChunkRepository.search_by_keyword,
    which accept the same fields. Adding a new filterable field means adding
    it here plus one branch in each of those two methods."""

    document_ids: list[uuid.UUID] | None = None
    file_types: list[str] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    page_number: int | None
    section_path: list[str]
    # None for a given stage means the chunk didn't reach/pass that stage —
    # e.g. a keyword-only hit has dense_score=None, never 0.0 (0.0 would
    # wrongly imply "dense search considered and scored it low").
    dense_score: float | None
    bm25_score: float | None
    rrf_score: float | None
    rerank_score: float | None


@dataclass
class RetrievalResult:
    query: str
    results: list[RetrievedChunk] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
