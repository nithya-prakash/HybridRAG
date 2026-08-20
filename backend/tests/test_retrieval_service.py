import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.vector_store import EmbeddedChunk, get_vector_store
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.parsing.models import Chunk as ParsedChunk
from app.services.retrieval import RetrievalFilters, RetrievalService
from tests.helpers import FakeEmbeddingBackend, fake_embed

CORPUS = [
    "Python is a popular programming language for data science and web development.",
    "The Eiffel Tower is a famous landmark in Paris, France.",
    "Machine learning models require large amounts of training data.",
    "French cuisine is known for its pastries, cheese, and wine.",
    "Space exploration has advanced with reusable rockets like SpaceX Falcon 9.",
]


async def _index_document(
    session: AsyncSession,
    user_id: uuid.UUID,
    contents: list[str],
    filename: str = "corpus.txt",
    file_type: str = "txt",
    created_at: datetime | None = None,
):
    document = await DocumentRepository(session).create(
        document_id=uuid.uuid4(),
        user_id=user_id,
        filename=filename,
        file_type=file_type,
        file_size_bytes=1,
        storage_path=f"/tmp/{filename}",
    )
    if created_at is not None:
        document.created_at = created_at
        await session.flush()

    parsed_chunks = [
        ParsedChunk(
            content=text,
            chunk_index=i,
            page_number=1,
            section_path=[],
            char_start=0,
            char_end=len(text),
            token_count=len(text.split()),
            content_hash=str(i),
        )
        for i, text in enumerate(contents)
    ]
    rows = await ChunkRepository(session).replace_for_document(
        document_id=document.id, user_id=user_id, document_version=1, chunks=parsed_chunks
    )
    await session.commit()

    embedded = [
        EmbeddedChunk(
            chunk_id=row.id,
            vector=fake_embed(chunk.content),
            document_id=document.id,
            user_id=user_id,
            document_version=1,
            page_number=1,
            section_path=[],
            chunk_index=chunk.chunk_index,
            file_type=file_type,
            document_created_at=document.created_at,
        )
        for row, chunk in zip(rows, parsed_chunks, strict=True)
    ]
    await get_vector_store().replace_for_document(document.id, embedded)

    return document, rows


def _service(session: AsyncSession) -> RetrievalService:
    return RetrievalService(session, embedding_backend=FakeEmbeddingBackend())


async def test_retrieve_ranks_relevant_chunk_highly(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="ret-basic@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, CORPUS)

    result = await _service(db_session).retrieve(
        "what programming language is good for data science", user.id
    )

    assert result.results
    top = result.results[0]
    assert "Python" in top.content
    # The top hit is expected to have surfaced via both retrieval legs and
    # survived fusion + rerank, so every stage's score should be populated.
    assert top.dense_score is not None
    assert top.bm25_score is not None
    assert top.rrf_score is not None
    assert top.rerank_score is not None


async def test_retrieve_returns_empty_for_no_indexed_content(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="ret-empty@example.com", hashed_password="x"
    )

    result = await _service(db_session).retrieve("anything at all", user.id)

    assert result.results == []
    assert result.timings_ms["total_ms"] >= 0


async def test_retrieve_filters_by_document_id(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="ret-docfilter@example.com", hashed_password="x"
    )
    doc_a, _ = await _index_document(db_session, user.id, [CORPUS[0]], filename="a.txt")
    doc_b, _ = await _index_document(db_session, user.id, [CORPUS[1]], filename="b.txt")

    filtered = await _service(db_session).retrieve(
        "landmark France Paris", user.id, filters=RetrievalFilters(document_ids=[doc_b.id])
    )

    assert filtered.results
    assert all(r.document_id == doc_b.id for r in filtered.results)
    assert doc_a.id not in {r.document_id for r in filtered.results}


async def test_retrieve_filters_by_file_type(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="ret-typefilter@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, [CORPUS[0]], filename="a.pdf", file_type="pdf")
    await _index_document(db_session, user.id, [CORPUS[0]], filename="a.txt", file_type="txt")

    filtered = await _service(db_session).retrieve(
        "programming language data science",
        user.id,
        filters=RetrievalFilters(file_types=["pdf"]),
    )

    assert filtered.results
    doc_ids = {r.document_id for r in filtered.results}
    docs = await DocumentRepository(db_session).list_for_user(user.id)
    pdf_doc_ids = {d.id for d in docs if d.file_type == "pdf"}
    assert doc_ids <= pdf_doc_ids


async def test_retrieve_filters_by_date_range(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="ret-datefilter@example.com", hashed_password="x"
    )
    old_doc, _ = await _index_document(
        db_session, user.id, [CORPUS[0]], filename="old.txt",
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    new_doc, _ = await _index_document(
        db_session, user.id, [CORPUS[0]], filename="new.txt",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    filtered = await _service(db_session).retrieve(
        "programming language data science",
        user.id,
        filters=RetrievalFilters(created_after=datetime(2025, 1, 1, tzinfo=UTC)),
    )

    doc_ids = {r.document_id for r in filtered.results}
    assert new_doc.id in doc_ids
    assert old_doc.id not in doc_ids


async def test_retrieve_user_isolation(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(
        email="ret-owner@example.com", hashed_password="x"
    )
    other = await UserRepository(db_session).create(
        email="ret-other@example.com", hashed_password="x"
    )
    owner_doc, _ = await _index_document(db_session, owner.id, CORPUS, filename="owner.txt")
    # Same content indexed for a different user — proves isolation isn't an
    # accident of the content simply not matching, but an explicit scope.
    other_doc, _ = await _index_document(db_session, other.id, CORPUS, filename="other.txt")

    owner_result = await _service(db_session).retrieve(
        "what programming language is good for data science", owner.id
    )
    other_result = await _service(db_session).retrieve(
        "what programming language is good for data science", other.id
    )

    assert owner_result.results
    assert other_result.results
    assert all(r.document_id == owner_doc.id for r in owner_result.results)
    assert all(r.document_id == other_doc.id for r in other_result.results)


async def test_retrieve_user_isolation_empty_for_user_with_no_documents(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(
        email="ret-hasdocs@example.com", hashed_password="x"
    )
    bystander = await UserRepository(db_session).create(
        email="ret-nodocs@example.com", hashed_password="x"
    )
    await _index_document(db_session, owner.id, CORPUS)

    result = await _service(db_session).retrieve(
        "what programming language is good for data science", bystander.id
    )

    assert result.results == []
