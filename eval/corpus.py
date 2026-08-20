"""Builds the eval harness's throwaway corpus: a fresh eval-only user, the
three fixture documents under eval/datasets/documents/ parsed and chunked
through the real Phase 3 pipeline, and their chunks persisted to Postgres and
indexed into Qdrant through the real repository/vector-store classes — the
same components `app/tasks/document_processing.py` uses, just called
directly instead of through Celery (see that module's tests for why: calling
the real Celery task from a standalone script fights its internal
`asyncio.run()` and the app's loop-bound singleton clients).

Content markers in the eval dataset are resolved to real chunk ids here,
post-indexing, by substring search over each chunk's actual persisted
content — see knowledge_base_eval.json's top-level "description" for why
markers rather than precomputed ids (chunk ids don't exist until indexing
has actually happened).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import EmbeddingBackend
from app.core.vector_store import EmbeddedChunk, VectorStore
from app.models.document import DocumentStatus
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.parsing import chunk_document, parse_document

DATASET_DIR = Path(__file__).parent / "datasets"
DATASET_PATH = DATASET_DIR / "knowledge_base_eval.json"

_WS_RE = re.compile(r"\s+")


def _normalize_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


@dataclass
class IndexedDocument:
    dataset_id: str
    document_id: uuid.UUID
    filename: str
    chunk_ids: list[uuid.UUID] = field(default_factory=list)
    chunk_contents: list[str] = field(default_factory=list)


@dataclass
class EvalQuery:
    id: str
    query: str
    category: str
    relevant_chunk_ids: set[uuid.UUID]
    reference_answer: str | None
    notes: str | None = None


@dataclass
class Corpus:
    user_id: uuid.UUID
    documents: dict[str, IndexedDocument]
    queries: list[EvalQuery]
    unresolved_markers: list[str]


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text())


async def build_corpus(
    session: AsyncSession,
    vector_store: VectorStore,
    embedding_backend: EmbeddingBackend,
) -> Corpus:
    dataset = load_dataset()

    user = await UserRepository(session).create(
        email=f"eval-{uuid.uuid4().hex[:12]}@eval.local", hashed_password="not-a-real-login"
    )

    documents: dict[str, IndexedDocument] = {}
    doc_repo = DocumentRepository(session)
    chunk_repo = ChunkRepository(session)

    for doc_spec in dataset["documents"]:
        file_path = DATASET_DIR / doc_spec["path"]
        content = file_path.read_bytes()
        parsed = parse_document(doc_spec["file_type"], content)
        chunks = chunk_document(parsed)

        document = await doc_repo.create(
            document_id=uuid.uuid4(),
            user_id=user.id,
            filename=file_path.name,
            file_type=doc_spec["file_type"],
            file_size_bytes=len(content),
            storage_path=str(file_path),
        )
        rows = await chunk_repo.replace_for_document(
            document_id=document.id, user_id=user.id, document_version=1, chunks=chunks
        )
        await doc_repo.update_status(document, DocumentStatus.READY)
        await session.commit()

        vectors = await embedding_backend.embed_batch([c.content for c in chunks])
        embedded = [
            EmbeddedChunk(
                chunk_id=row.id,
                vector=vector,
                document_id=document.id,
                user_id=user.id,
                document_version=1,
                page_number=chunk.page_number,
                section_path=chunk.section_path,
                chunk_index=chunk.chunk_index,
                file_type=doc_spec["file_type"],
                document_created_at=document.created_at,
            )
            for row, chunk, vector in zip(rows, chunks, vectors, strict=True)
        ]
        await vector_store.replace_for_document(document.id, embedded)

        documents[doc_spec["id"]] = IndexedDocument(
            dataset_id=doc_spec["id"],
            document_id=document.id,
            filename=file_path.name,
            chunk_ids=[row.id for row in rows],
            chunk_contents=[row.content for row in rows],
        )

    queries: list[EvalQuery] = []
    unresolved_markers: list[str] = []
    for q in dataset["queries"]:
        relevant_ids: set[uuid.UUID] = set()
        for rc in q["relevant_chunks"]:
            indexed_doc = documents[rc["document_id"]]
            marker = _normalize_ws(rc["content_marker"])
            matches = [
                chunk_id
                for chunk_id, content in zip(
                    indexed_doc.chunk_ids, indexed_doc.chunk_contents, strict=True
                )
                if marker in _normalize_ws(content)
            ]
            if not matches:
                unresolved_markers.append(f"{q['id']} / {rc['document_id']}: {marker!r}")
            relevant_ids.update(matches)

        queries.append(
            EvalQuery(
                id=q["id"],
                query=q["query"],
                category=q["category"],
                relevant_chunk_ids=relevant_ids,
                reference_answer=q.get("reference_answer"),
                notes=q.get("notes"),
            )
        )

    return Corpus(
        user_id=user.id, documents=documents, queries=queries, unresolved_markers=unresolved_markers
    )


async def teardown_corpus(session: AsyncSession, vector_store: VectorStore, corpus: Corpus) -> None:
    """Removes everything build_corpus created, from both Postgres and
    Qdrant, so repeated eval runs (locally, or against a shared CI/dev
    instance) don't accumulate throwaway users and documents indefinitely.
    """
    for indexed_doc in corpus.documents.values():
        await vector_store.delete_for_document(indexed_doc.document_id)

    user = await UserRepository(session).get_by_id(corpus.user_id)
    if user is not None:
        await session.delete(user)  # cascades to documents/document_versions/chunks
        await session.commit()
