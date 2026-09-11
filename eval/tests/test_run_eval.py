"""Tests for run_eval.py's generate_and_score, focused on the
guard_declined / declined / second_layer_catch distinction — a real bug
this harness had: `abstention_correct` used to be computed from the
pre-generation guard's decision alone, blind to whether the answer-
generation prompt's own constraint caught a case the guard's rerank-score
threshold missed. See eval/RESULTS.md for the real run that surfaced this.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.services.rag.prompts import INSUFFICIENT_CONTEXT_MESSAGE
from app.services.retrieval.models import RetrievedChunk
from eval.corpus import EvalQuery
from eval.run_eval import generate_and_score

# Explicit rather than relying on backend/pyproject.toml's asyncio_mode=auto —
# see eval/tests/test_generation_metrics.py's identical comment for why.
pytestmark = pytest.mark.asyncio


class _StubJudge:
    async def complete(self, messages: list[dict[str, str]]) -> str:
        import json

        return json.dumps({"score": 5, "rationale": "stub"})


class _StubChatBackend:
    def __init__(self, response: str) -> None:
        self._response = response

    async def complete(self, messages: list[dict[str, str]]) -> str:
        return self._response


def _make_chunk(rerank_score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="Some retrieved content that is topically related.",
        page_number=None,
        section_path=[],
        dense_score=0.5,
        bm25_score=0.5,
        rrf_score=0.5,
        rerank_score=rerank_score,
    )


def _make_query(answerable: bool) -> EvalQuery:
    return EvalQuery(
        id="q_test",
        query="Does the corpus cover this specific thing?",
        category="out_of_corpus" if not answerable else "single_chunk",
        relevant_chunk_ids=set(),
        reference_answer=None if not answerable else "Yes, per the handbook.",
        answerable=answerable,
    )


async def test_second_layer_catch_when_prompt_declines_despite_guard_not_declining():
    # rerank score well above threshold -> the guard does NOT decline...
    settings = get_settings()
    chunk = _make_chunk(rerank_score=settings.rag_min_rerank_score + 5.0)
    query = _make_query(answerable=False)
    # ...but the model's own answer is a decline anyway (the real observed
    # behavior on q089/q094 — see eval/RESULTS.md).
    chat_backend = _StubChatBackend(INSUFFICIENT_CONTEXT_MESSAGE)

    record = await generate_and_score(
        chat_backend, _StubJudge(), settings, {}, query, [chunk]
    )

    assert record["guard_declined"] is False
    assert record["declined"] is True
    assert record["second_layer_catch"] is True
    assert record["abstention_correct"] is True


async def test_no_second_layer_catch_when_model_answers_confidently_wrong():
    settings = get_settings()
    chunk = _make_chunk(rerank_score=settings.rag_min_rerank_score + 5.0)
    query = _make_query(answerable=False)
    chat_backend = _StubChatBackend("Yes, the company offers this. [1]")

    record = await generate_and_score(
        chat_backend, _StubJudge(), settings, {}, query, [chunk]
    )

    assert record["guard_declined"] is False
    assert record["declined"] is False
    assert record["second_layer_catch"] is False
    assert record["abstention_correct"] is False


async def test_guard_decline_is_not_counted_as_a_second_layer_catch():
    # Below threshold -> the guard itself declines, before any LLM call —
    # this is the guard doing its job, not the second layer doing anything.
    settings = get_settings()
    chunk = _make_chunk(rerank_score=settings.rag_min_rerank_score - 5.0)
    query = _make_query(answerable=False)

    record = await generate_and_score(None, _StubJudge(), settings, {}, query, [chunk])

    assert record["guard_declined"] is True
    assert record["declined"] is True
    assert record["second_layer_catch"] is False
    assert record["abstention_correct"] is True


async def test_answerable_query_declining_is_a_false_abstention_not_a_catch():
    settings = get_settings()
    chunk = _make_chunk(rerank_score=settings.rag_min_rerank_score + 5.0)
    query = _make_query(answerable=True)
    chat_backend = _StubChatBackend(INSUFFICIENT_CONTEXT_MESSAGE)

    record = await generate_and_score(
        chat_backend, _StubJudge(), settings, {}, query, [chunk]
    )

    assert record["declined"] is True
    assert record["second_layer_catch"] is False  # only defined for unanswerable queries
    assert record["abstention_correct"] is False  # a real false abstention
