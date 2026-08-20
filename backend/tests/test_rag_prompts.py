import uuid

from app.models.chunk import Chunk as ChunkModel
from app.services.rag.prompts import (
    CitationSource,
    build_context_block,
    build_messages,
    extract_citations,
    from_chunk_models,
    from_retrieved_chunks,
)
from app.services.retrieval.models import RetrievedChunk


def _source(content: str = "chunk text", page: int | None = 1, doc_id=None, chunk_id=None):
    return CitationSource(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=doc_id or uuid.uuid4(),
        content=content,
        page_number=page,
    )


def test_build_context_block_numbers_sources_in_order_with_filename_and_page():
    doc_id = uuid.uuid4()
    sources = [
        _source(content="First chunk", page=3, doc_id=doc_id),
        _source(content="Second chunk", page=None, doc_id=doc_id),
    ]
    filenames = {doc_id: "handbook.pdf"}

    block, index_map = build_context_block(sources, filenames)

    assert '[1] (from "handbook.pdf", page 3)' in block
    assert "First chunk" in block
    assert '[2] (from "handbook.pdf")' in block
    assert "Second chunk" in block
    assert index_map[1] is sources[0]
    assert index_map[2] is sources[1]


def test_build_context_block_unknown_document_falls_back_to_placeholder_name():
    block, _ = build_context_block([_source()], {})

    assert "unknown document" in block


def test_build_messages_includes_system_prompt_history_context_and_question():
    history = [("user", "hi"), ("assistant", "hello")]

    messages = build_messages(history, "some context block", "what is X?")

    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "hi"}
    assert messages[2] == {"role": "assistant", "content": "hello"}
    assert messages[3]["role"] == "system"
    assert "some context block" in messages[3]["content"]
    assert messages[4] == {"role": "user", "content": "what is X?"}


def test_extract_citations_returns_only_cited_markers_in_ascending_order():
    doc_id = uuid.uuid4()
    s1, s2, s3 = _source("A", 1, doc_id), _source("B", 2, doc_id), _source("C", 3, doc_id)
    index_map = {1: s1, 2: s2, 3: s3}
    filenames = {doc_id: "doc.pdf"}

    citations = extract_citations("The answer cites [2] and also [1].", index_map, filenames)

    assert [c.marker for c in citations] == [1, 2]
    assert citations[0].chunk_id == s1.chunk_id
    assert citations[0].filename == "doc.pdf"


def test_extract_citations_ignores_unknown_marker_numbers():
    index_map = {1: _source("A")}

    citations = extract_citations("cites [1] and [9]", index_map, {})

    assert [c.marker for c in citations] == [1]


def test_extract_citations_deduplicates_repeated_markers():
    index_map = {1: _source("A")}

    citations = extract_citations("[1] repeated again [1]", index_map, {})

    assert len(citations) == 1


def test_extract_citations_no_markers_returns_empty():
    assert extract_citations("plain answer, no citations", {1: _source()}, {}) == []


def test_extract_citations_excerpt_is_truncated():
    index_map = {1: _source("x" * 500)}

    citations = extract_citations("[1]", index_map, {})

    assert len(citations[0].excerpt) == 280


def test_from_retrieved_chunks_maps_fields():
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="text",
        page_number=2,
        section_path=[],
        dense_score=0.5,
        bm25_score=None,
        rrf_score=0.1,
        rerank_score=1.0,
    )

    [source] = from_retrieved_chunks([chunk])

    assert source.chunk_id == chunk.chunk_id
    assert source.document_id == chunk.document_id
    assert source.content == "text"
    assert source.page_number == 2


def test_from_chunk_models_maps_fields():
    row = ChunkModel(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content="chunk body",
        chunk_metadata={"page_number": 4},
    )

    [source] = from_chunk_models([row])

    assert source.chunk_id == row.id
    assert source.document_id == row.document_id
    assert source.content == "chunk body"
    assert source.page_number == 4


def test_from_chunk_models_missing_page_number_is_none():
    row = ChunkModel(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content="x",
        chunk_metadata={},
    )

    [source] = from_chunk_models([row])

    assert source.page_number is None
