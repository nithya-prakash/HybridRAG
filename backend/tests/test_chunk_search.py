import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.parsing.models import Chunk as ParsedChunk


async def _make_document_with_chunks(session: AsyncSession, email: str, contents: list[str]):
    user = await UserRepository(session).create(email=email, hashed_password="x")
    document = await DocumentRepository(session).create(
        document_id=uuid.uuid4(),
        user_id=user.id,
        filename="a.txt",
        file_type="txt",
        file_size_bytes=1,
        storage_path="/tmp/does-not-matter.txt",
    )
    parsed_chunks = [
        _fake_parsed_chunk(index=i, content=content) for i, content in enumerate(contents)
    ]
    await ChunkRepository(session).replace_for_document(
        document_id=document.id, user_id=user.id, document_version=1, chunks=parsed_chunks
    )
    await session.commit()
    return user, document


def _fake_parsed_chunk(index: int, content: str) -> ParsedChunk:
    return ParsedChunk(
        content=content,
        chunk_index=index,
        page_number=1,
        section_path=[],
        char_start=0,
        char_end=len(content),
        token_count=len(content.split()),
        content_hash=str(index),
    )


async def test_search_by_keyword_ranks_relevant_chunk_first(db_session: AsyncSession):
    user, _document = await _make_document_with_chunks(
        db_session,
        "fts-basic@example.com",
        [
            "The quick brown fox jumps over the lazy dog",
            "Completely unrelated content about spreadsheets and budgets",
        ],
    )

    results = await ChunkRepository(db_session).search_by_keyword(user.id, "quick fox")

    assert len(results) == 1
    chunk, rank = results[0]
    assert "quick brown fox" in chunk.content
    assert rank > 0


async def test_search_by_keyword_no_match_returns_empty(db_session: AsyncSession):
    user, _document = await _make_document_with_chunks(
        db_session, "fts-nomatch@example.com", ["Some content about gardening"]
    )

    results = await ChunkRepository(db_session).search_by_keyword(user.id, "quantum physics")

    assert results == []


async def test_search_by_keyword_scoped_to_user(db_session: AsyncSession):
    owner, _doc_a = await _make_document_with_chunks(
        db_session, "fts-owner@example.com", ["Shared keyword pineapple appears here"]
    )
    other, _doc_b = await _make_document_with_chunks(
        db_session, "fts-other@example.com", ["Shared keyword pineapple appears here too"]
    )

    owner_results = await ChunkRepository(db_session).search_by_keyword(owner.id, "pineapple")
    other_results = await ChunkRepository(db_session).search_by_keyword(other.id, "pineapple")

    assert len(owner_results) == 1
    assert len(other_results) == 1
    assert owner_results[0][0].user_id == owner.id
    assert other_results[0][0].user_id == other.id


async def test_search_by_keyword_filters_by_document_id(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="fts-docfilter@example.com", hashed_password="x"
    )
    doc_a = await DocumentRepository(db_session).create(
        document_id=uuid.uuid4(),
        user_id=user.id,
        filename="a.txt",
        file_type="txt",
        file_size_bytes=1,
        storage_path="/tmp/a.txt",
    )
    doc_b = await DocumentRepository(db_session).create(
        document_id=uuid.uuid4(),
        user_id=user.id,
        filename="b.txt",
        file_type="txt",
        file_size_bytes=1,
        storage_path="/tmp/b.txt",
    )
    await ChunkRepository(db_session).replace_for_document(
        document_id=doc_a.id,
        user_id=user.id,
        document_version=1,
        chunks=[_fake_parsed_chunk(0, "Mango season starts in summer")],
    )
    await ChunkRepository(db_session).replace_for_document(
        document_id=doc_b.id,
        user_id=user.id,
        document_version=1,
        chunks=[_fake_parsed_chunk(0, "Mango imports rose this year")],
    )
    await db_session.commit()

    scoped_results = await ChunkRepository(db_session).search_by_keyword(
        user.id, "mango", document_id=doc_a.id
    )
    unscoped_results = await ChunkRepository(db_session).search_by_keyword(user.id, "mango")

    assert len(scoped_results) == 1
    assert scoped_results[0][0].document_id == doc_a.id
    assert len(unscoped_results) == 2


async def test_search_by_keyword_respects_top_k(db_session: AsyncSession):
    contents = [f"repeatedkeyword occurrence number {i}" for i in range(5)]
    user, _document = await _make_document_with_chunks(db_session, "fts-topk@example.com", contents)

    results = await ChunkRepository(db_session).search_by_keyword(
        user.id, "repeatedkeyword", top_k=2
    )

    assert len(results) == 2
