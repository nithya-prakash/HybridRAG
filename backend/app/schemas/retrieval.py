import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.retrieval.models import RetrievalFilters


class RetrievalFiltersRequest(BaseModel):
    document_ids: list[uuid.UUID] | None = None
    file_types: list[str] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None

    def to_domain(self) -> RetrievalFilters:
        return RetrievalFilters(
            document_ids=self.document_ids,
            file_types=self.file_types,
            created_after=self.created_after,
            created_before=self.created_before,
        )


class RetrievalSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    filters: RetrievalFiltersRequest | None = None
    top_k: int | None = Field(default=None, gt=0)


class RetrievedChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    page_number: int | None
    section_path: list[str]
    dense_score: float | None
    bm25_score: float | None
    rrf_score: float | None
    rerank_score: float | None


class RetrievalSearchResponse(BaseModel):
    query: str
    results: list[RetrievedChunkRead]
    timings_ms: dict[str, float]
