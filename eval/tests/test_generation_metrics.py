import json

import pytest

from eval.metrics.generation_metrics import (
    build_faithfulness_messages,
    build_relevance_messages,
    score_faithfulness,
    score_relevance,
)

# Explicit rather than relying on backend/pyproject.toml's asyncio_mode=auto:
# these tests live outside backend/'s directory tree, and pytest's ini-file
# discovery follows the invoked test paths, not the CWD — running `pytest
# ../eval/tests` from backend/ never finds backend/pyproject.toml, so the
# auto mode setting there doesn't apply here. Verified directly: without
# this, every async test failed with "async def functions are not natively
# supported."
pytestmark = pytest.mark.asyncio


class _StubJudge:
    def __init__(self, response: str) -> None:
        self._response = response
        self.received_messages: list[dict[str, str]] | None = None

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.received_messages = messages
        return self._response


async def test_score_faithfulness_parses_score_and_normalizes_to_unit_interval():
    judge = _StubJudge(json.dumps({"score": 4, "rationale": "mostly grounded"}))

    result = await score_faithfulness(judge, "q?", "context text", "answer text")

    assert result.parse_ok is True
    assert result.raw_score == 4
    assert result.score == 0.75  # (4-1)/4
    assert result.rationale == "mostly grounded"


async def test_score_relevance_handles_lowest_score():
    judge = _StubJudge(json.dumps({"score": 1, "rationale": "off topic"}))

    result = await score_relevance(judge, "q?", "unrelated answer")

    assert result.score == 0.0
    assert result.raw_score == 1


async def test_score_extracts_json_even_with_surrounding_prose():
    judge = _StubJudge('Here is my answer: {"score": 5, "rationale": "fully grounded"} Thanks!')

    result = await score_faithfulness(judge, "q?", "ctx", "ans")

    assert result.parse_ok is True
    assert result.score == 1.0


async def test_score_falls_back_gracefully_on_unparseable_output():
    judge = _StubJudge("I refuse to answer in JSON.")

    result = await score_relevance(judge, "q?", "ans")

    assert result.parse_ok is False
    assert result.score == 0.0
    assert result.raw_score is None


async def test_score_clamps_out_of_range_scores():
    judge = _StubJudge(json.dumps({"score": 9, "rationale": "too high"}))

    result = await score_relevance(judge, "q?", "ans")

    assert result.raw_score == 9
    assert result.score == 1.0  # clamped to 5 -> normalized to 1.0


async def test_faithfulness_prompt_includes_question_context_and_answer():
    messages = build_faithfulness_messages("What is X?", "X is defined here.", "X is Y.")

    user_message = messages[-1]["content"]
    assert "What is X?" in user_message
    assert "X is defined here." in user_message
    assert "X is Y." in user_message
    assert messages[0]["role"] == "system"


async def test_relevance_prompt_excludes_context_and_includes_question_and_answer():
    messages = build_relevance_messages("What is X?", "X is Y.")

    user_message = messages[-1]["content"]
    assert "What is X?" in user_message
    assert "X is Y." in user_message
    assert "Context" not in user_message
