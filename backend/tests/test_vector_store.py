import uuid
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.vector_store import EmbeddedChunk, get_vector_store


def _vector(seed: float) -> list[float]:
    size = get_settings().qdrant_vector_size
    return [seed] * size


def _embedded_chunk(document_id: uuid.UUID, user_id: uuid.UUID, seed: float, **overrides):
    defaults = {
        "chunk_id": uuid.uuid4(),
        "vector": _vector(seed),
        "document_id": document_id,
        "user_id": user_id,
        "document_version": 1,
        "page_number": 1,
        "section_path": ["Intro"],
        "chunk_index": 0,
        "file_type": "txt",
        "document_created_at": datetime(2024, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return EmbeddedChunk(**defaults)


async def test_replace_for_document_upserts_points_with_payload():
    store = get_vector_store()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    chunks = [
        _embedded_chunk(document_id, user_id, 0.1, chunk_index=0, page_number=1),
        _embedded_chunk(document_id, user_id, 0.2, chunk_index=1, page_number=2),
    ]

    await store.replace_for_document(document_id, chunks)

    assert await store.count_for_document(document_id) == 2


async def test_search_scopes_to_user_id():
    store = get_vector_store()
    document_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    await store.replace_for_document(
        document_id, [_embedded_chunk(document_id, owner_id, 0.5)]
    )

    owner_results = await store.search(user_id=owner_id, query_vector=_vector(0.5), top_k=5)
    other_results = await store.search(user_id=other_user_id, query_vector=_vector(0.5), top_k=5)

    assert len(owner_results) == 1
    assert other_results == []


async def test_search_filters_by_document_id():
    store = get_vector_store()
    user_id = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    await store.replace_for_document(doc_a, [_embedded_chunk(doc_a, user_id, 0.1)])
    await store.replace_for_document(doc_b, [_embedded_chunk(doc_b, user_id, 0.1)])

    results = await store.search(user_id=user_id, query_vector=_vector(0.1), top_k=10)
    scoped_results = await store.search(
        user_id=user_id, query_vector=_vector(0.1), top_k=10, document_id=doc_a
    )

    assert len(results) == 2
    assert len(scoped_results) == 1
    assert scoped_results[0].payload["document_id"] == str(doc_a)


async def test_search_result_payload_carries_expected_fields():
    store = get_vector_store()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    await store.replace_for_document(
        document_id,
        [
            _embedded_chunk(
                document_id,
                user_id,
                0.3,
                chunk_id=chunk_id,
                page_number=7,
                section_path=["A", "B"],
                chunk_index=2,
                document_version=3,
            )
        ],
    )

    results = await store.search(user_id=user_id, query_vector=_vector(0.3), top_k=1)

    assert len(results) == 1
    payload = results[0].payload
    assert payload["chunk_id"] == str(chunk_id)
    assert payload["document_id"] == str(document_id)
    assert payload["user_id"] == str(user_id)
    assert payload["page_number"] == 7
    assert payload["section_path"] == ["A", "B"]
    assert payload["chunk_index"] == 2
    assert payload["document_version"] == 3


async def test_replace_for_document_removes_previous_vectors():
    store = get_vector_store()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await store.replace_for_document(
        document_id,
        [
            _embedded_chunk(document_id, user_id, 0.1, chunk_index=0),
            _embedded_chunk(document_id, user_id, 0.2, chunk_index=1),
        ],
    )
    assert await store.count_for_document(document_id) == 2

    await store.replace_for_document(
        document_id, [_embedded_chunk(document_id, user_id, 0.9, chunk_index=0)]
    )

    assert await store.count_for_document(document_id) == 1


async def test_delete_for_document_removes_all_its_vectors():
    store = get_vector_store()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await store.replace_for_document(
        document_id,
        [
            _embedded_chunk(document_id, user_id, 0.1, chunk_index=0),
            _embedded_chunk(document_id, user_id, 0.2, chunk_index=1),
        ],
    )

    await store.delete_for_document(document_id)

    assert await store.count_for_document(document_id) == 0


async def test_delete_for_document_does_not_affect_other_documents():
    store = get_vector_store()
    user_id = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    await store.replace_for_document(doc_a, [_embedded_chunk(doc_a, user_id, 0.1)])
    await store.replace_for_document(doc_b, [_embedded_chunk(doc_b, user_id, 0.2)])

    await store.delete_for_document(doc_a)

    assert await store.count_for_document(doc_a) == 0
    assert await store.count_for_document(doc_b) == 1


async def test_replace_for_document_with_empty_chunks_only_deletes():
    store = get_vector_store()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await store.replace_for_document(document_id, [_embedded_chunk(document_id, user_id, 0.1)])

    await store.replace_for_document(document_id, [])

    assert await store.count_for_document(document_id) == 0
