import asyncio
import time
import uuid

from qdrant_client import models as qdrant_models
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.embeddings import EmbeddingBackend, get_embedding_backend
from app.core.logging import get_logger
from app.core.metrics import RETRIEVAL_STAGE_DURATION_SECONDS
from app.core.reranker import Reranker, get_reranker
from app.core.vector_store import VectorStore, get_vector_store
from app.models.chunk import Chunk as ChunkModel
from app.repositories.chunk_repository import ChunkRepository
from app.services.retrieval.fusion import reciprocal_rank_fusion
from app.services.retrieval.models import RetrievalFilters, RetrievalResult, RetrievedChunk

logger = get_logger(__name__)


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


class RetrievalService:
    """The hybrid search pipeline, end to end: embed the query, run dense
    (Qdrant) and keyword (Postgres full-text) search concurrently, fuse with
    Reciprocal Rank Fusion, fetch full text for the fused candidates, rerank
    with a cross-encoder, return the final top-K with every stage's score
    attached. See ARCHITECTURE.md for the full pipeline diagram and the
    reasoning behind each step.

    Every call requires `user_id` and scopes both retrieval legs to it —
    there is no unscoped `retrieve`, the same isolation shape as
    `VectorStore.search` and `ChunkRepository.search_by_keyword`, which this
    service is a thin, testable orchestration layer on top of.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_backend: EmbeddingBackend | None = None,
        vector_store: VectorStore | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        settings = get_settings()
        self._chunks = ChunkRepository(session)
        self._embeddings = embedding_backend or get_embedding_backend()
        self._vector_store = vector_store or get_vector_store()
        self._reranker = reranker or get_reranker()
        self._retrieval_top_k = settings.retrieval_top_k
        self._rrf_k = settings.hybrid_search_rrf_k
        self._default_top_k = settings.rerank_top_k

    async def retrieve(
        self,
        query: str,
        user_id: uuid.UUID,
        filters: RetrievalFilters | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        filters = filters or RetrievalFilters()
        final_top_k = top_k or self._default_top_k
        timings: dict[str, float] = {}
        overall_start = time.perf_counter()

        t0 = time.perf_counter()
        query_vector = (await self._embeddings.embed_batch([query]))[0]
        timings["embed_query_ms"] = _elapsed_ms(t0)

        # Dense (Qdrant) and keyword (Postgres) search are independent I/O
        # against two different systems — run them concurrently rather than
        # paying both latencies sequentially. Each times itself internally so
        # per-leg timings survive running side by side.
        #
        # return_exceptions=True is deliberate, not an oversight: plain
        # asyncio.gather cancels every other pending task the instant one
        # raises. Cancelling the bm25 leg mid-flight cancels an in-progress
        # query on this request's single shared AsyncSession — and asyncpg
        # connections do not tolerate a query being abandoned mid-flight;
        # the connection is left in a broken protocol state ("another
        # operation is in progress") that then blows up on the *next* thing
        # that touches the session, including its own cleanup on the way
        # out. Verified directly: a Qdrant-down chaos test reproduced this
        # exact asyncpg.InterfaceError. Letting both legs actually finish
        # (or fail on their own terms) and re-raising afterward avoids ever
        # cancelling a live Postgres query.
        retrieval_start = time.perf_counter()
        dense_result, bm25_result = await asyncio.gather(
            self._dense_search(user_id, query_vector, filters),
            self._bm25_search(user_id, query, filters),
            return_exceptions=True,
        )
        for result in (dense_result, bm25_result):
            if isinstance(result, BaseException):
                raise result
        (dense_points, dense_ms), (bm25_rows, bm25_ms) = dense_result, bm25_result
        timings["dense_search_ms"] = dense_ms
        timings["bm25_search_ms"] = bm25_ms
        timings["retrieval_wall_ms"] = _elapsed_ms(retrieval_start)

        dense_ids = [uuid.UUID(p.payload["chunk_id"]) for p in dense_points]
        dense_scores = {uuid.UUID(p.payload["chunk_id"]): p.score for p in dense_points}
        bm25_ids = [chunk.id for chunk, _ in bm25_rows]
        bm25_scores = {chunk.id: score for chunk, score in bm25_rows}

        t0 = time.perf_counter()
        fused = reciprocal_rank_fusion([dense_ids, bm25_ids], k=self._rrf_k)
        timings["fusion_ms"] = _elapsed_ms(t0)
        rrf_scores = dict(fused)
        fused_ids = [chunk_id for chunk_id, _ in fused]

        if not fused_ids:
            timings["rerank_ms"] = 0.0
            timings["total_ms"] = _elapsed_ms(overall_start)
            self._log_complete(query, filters, 0, dense_ids, bm25_ids, fused_ids, timings)
            return RetrievalResult(query=query, results=[], timings_ms=timings)

        # Qdrant's payload deliberately doesn't carry chunk text (see
        # ARCHITECTURE.md § Phase 4) — fetch it from Postgres for the whole
        # fused set in one batch query, not per-chunk.
        chunk_rows = await self._chunks.get_by_ids(user_id, fused_ids)
        content_by_id = {c.id: c for c in chunk_rows}
        # A fused id might not resolve (e.g. deleted between search and here,
        # or a stray reference) — skip it rather than failing the request.
        candidates = [
            (chunk_id, content_by_id[chunk_id].content)
            for chunk_id in fused_ids
            if chunk_id in content_by_id
        ]

        t0 = time.perf_counter()
        reranked = await self._reranker.rerank(query, candidates)
        timings["rerank_ms"] = _elapsed_ms(t0)
        timings["total_ms"] = _elapsed_ms(overall_start)

        results = [
            _to_retrieved_chunk(
                content_by_id[chunk_id], rerank_score, dense_scores, bm25_scores, rrf_scores
            )
            for chunk_id, rerank_score in reranked[:final_top_k]
        ]

        self._log_complete(query, filters, len(results), dense_ids, bm25_ids, fused_ids, timings)
        return RetrievalResult(query=query, results=results, timings_ms=timings)

    async def _dense_search(
        self, user_id: uuid.UUID, query_vector: list[float], filters: RetrievalFilters
    ) -> tuple[list[qdrant_models.ScoredPoint], float]:
        t0 = time.perf_counter()
        points = await self._vector_store.search(
            user_id=user_id,
            query_vector=query_vector,
            top_k=self._retrieval_top_k,
            document_ids=filters.document_ids,
            file_types=filters.file_types,
            created_after=filters.created_after,
            created_before=filters.created_before,
        )
        return points, _elapsed_ms(t0)

    async def _bm25_search(
        self, user_id: uuid.UUID, query: str, filters: RetrievalFilters
    ) -> tuple[list[tuple[ChunkModel, float]], float]:
        t0 = time.perf_counter()
        rows = await self._chunks.search_by_keyword(
            user_id=user_id,
            query=query,
            top_k=self._retrieval_top_k,
            document_ids=filters.document_ids,
            file_types=filters.file_types,
            created_after=filters.created_after,
            created_before=filters.created_before,
        )
        return rows, _elapsed_ms(t0)

    def _log_complete(
        self,
        query: str,
        filters: RetrievalFilters,
        result_count: int,
        dense_ids: list[uuid.UUID],
        bm25_ids: list[uuid.UUID],
        fused_ids: list[uuid.UUID],
        timings: dict[str, float],
    ) -> None:
        logger.info(
            "retrieval_complete",
            query=query,
            result_count=result_count,
            dense_candidates=len(dense_ids),
            bm25_candidates=len(bm25_ids),
            fused_candidates=len(fused_ids),
            filtered=bool(
                filters.document_ids
                or filters.file_types
                or filters.created_after
                or filters.created_before
            ),
            **timings,
        )
        # A second, queryable-as-a-distribution view of the same per-stage
        # numbers the log line above carries — not a replacement for it.
        for key, ms in timings.items():
            stage = key.removesuffix("_ms")
            RETRIEVAL_STAGE_DURATION_SECONDS.labels(stage=stage).observe(ms / 1000)


def _to_retrieved_chunk(
    chunk: ChunkModel,
    rerank_score: float,
    dense_scores: dict[uuid.UUID, float],
    bm25_scores: dict[uuid.UUID, float],
    rrf_scores: dict[uuid.UUID, float],
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        content=chunk.content,
        page_number=chunk.chunk_metadata.get("page_number"),
        section_path=chunk.chunk_metadata.get("section_path", []),
        dense_score=dense_scores.get(chunk.id),
        bm25_score=bm25_scores.get(chunk.id),
        rrf_score=rrf_scores.get(chunk.id),
        rerank_score=rerank_score,
    )
