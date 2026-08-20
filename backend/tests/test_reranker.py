import uuid

from app.core.reranker import CrossEncoderReranker

# Real model, not mocked — it's local, free, and needs no API key (same
# reasoning as running real Postgres/Qdrant in other tests rather than
# stubbing them). The model is baked into the Docker image / synced venv,
# so no network access is needed at test time.


async def test_rerank_orders_relevant_candidate_first():
    reranker = CrossEncoderReranker()
    relevant_id, irrelevant_id = uuid.uuid4(), uuid.uuid4()
    candidates = [
        (irrelevant_id, "The Eiffel Tower is a famous landmark in Paris, France."),
        (relevant_id, "Python is a popular programming language for data science."),
    ]

    results = await reranker.rerank("What language is good for data science?", candidates)

    assert [chunk_id for chunk_id, _ in results] == [relevant_id, irrelevant_id]
    assert results[0][1] > results[1][1]


async def test_rerank_empty_candidates_returns_empty_without_loading_model():
    reranker = CrossEncoderReranker()

    results = await reranker.rerank("anything", [])

    assert results == []
    assert reranker._model is None


async def test_warm_up_forces_model_load():
    reranker = CrossEncoderReranker()
    assert reranker._model is None

    await reranker.warm_up()

    assert reranker._model is not None
