"""Generation-quality metrics: faithfulness (is the answer grounded in the
retrieved context?) and answer relevance (does the answer address the
question asked?).

Both are implemented as LLM-as-judge scoring rather than an NLI (natural
language inference) model, deliberately:

- The answers this system produces are multi-sentence, multi-claim, and
  often synthesize across more than one retrieved chunk. Off-the-shelf NLI
  models score a single (premise, hypothesis) sentence pair for entailment;
  reducing an answer to sentence pairs and aggregating loses exactly the
  cross-claim, cross-chunk reasoning this system is meant to do, and adds a
  second model (and its own calibration problems) to maintain.
- An LLM judge can be given the *same* rubric a human reviewer would use,
  in plain language, and can explain *why* it scored what it scored — which
  is what makes a low score in eval/RESULTS.md actionable rather than just a
  number.
- This system already depends on an LLM chat backend for generation itself
  (`app.core.chat.ChatBackend`) — reusing that same interface for judging
  adds no new runtime dependency.

The known tradeoff, documented honestly rather than glossed over: an LLM
judge is itself an imperfect, somewhat expensive, and non-deterministic
grader — it can share blind spots with the generation model (especially
when judge and generator are the same underlying model family), and its
absolute scores are noisier than a human's. Treat these numbers as a
consistent, automatable signal for tracking regressions over time, not as
ground truth.

The judge is injected as any object implementing the same `complete(messages)
-> str` shape as `app.core.chat.ChatBackend` — in real-backend mode that's
the actual `OpenAIChatBackend`; in synthetic mode (no OpenAI key configured)
it's a deterministic heuristic stand-in (see eval/fakes.py) that returns the
same JSON shape from a lexical-overlap heuristic. This module never checks
which one it was given — the fallback story lives entirely in which judge
object the caller constructs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

FAITHFULNESS_RUBRIC = """You are grading whether an AI-generated answer stays grounded in a \
provided context, on a 1-5 scale:

5 - Every factual claim in the answer is directly supported by the context. No invented details.
4 - Nearly all claims are supported; at most one minor, non-critical detail is unsupported or
    imprecise.
3 - Most claims are supported, but the answer includes at least one moderately significant
    unsupported claim.
2 - Multiple claims are unsupported, or the answer meaningfully overstates what the context says.
1 - The answer is substantially fabricated or contradicts the context.

Judge ONLY whether the answer's claims are supported by the context — not whether the answer is \
well-written, complete, or actually useful for the question."""

RELEVANCE_RUBRIC = """You are grading whether an AI-generated answer actually addresses the \
question that was asked, on a 1-5 scale:

5 - Directly and completely answers the question asked.
4 - Answers the question but omits a minor relevant detail, or includes some tangential content.
3 - Partially answers the question; a meaningfully important part of it is missing or off-target.
2 - Only tangentially related to the question; the core of what was asked is not addressed.
1 - Does not address the question at all.

A clear, honest statement that the system doesn't have enough information to answer should be \
scored a 5 if the question truly can't be answered from the given context, since declining is the \
correct response in that case — do not penalize an honest "I don't know" as irrelevant.

Judge ONLY relevance to the question — not factual accuracy of the content."""

_JUDGE_INSTRUCTIONS = (
    'Respond with ONLY a JSON object of the form {{"score": <integer 1-5>, "rationale": '
    '"<one sentence explaining the score>"}}. No other text.'
)


class Judge(Protocol):
    async def complete(self, messages: list[dict[str, str]]) -> str: ...


@dataclass
class JudgeScore:
    score: float  # normalized to [0.0, 1.0]
    raw_score: int | None  # the 1-5 Likert value the judge returned, if parsed
    rationale: str
    parse_ok: bool


def _normalize(raw_score: int) -> float:
    clamped = max(1, min(5, raw_score))
    return (clamped - 1) / 4


def _unparseable(raw: str) -> JudgeScore:
    return JudgeScore(
        score=0.0, raw_score=None, rationale=f"unparseable judge output: {raw!r}", parse_ok=False
    )


def _extract_first_json_object(raw: str) -> str | None:
    """Finds the first balanced `{...}` substring by bracket-depth counting
    (string- and escape-aware), rather than a single greedy regex spanning
    the first `{` to the *last* `}` in the whole response. That distinction
    is not theoretical: a smaller local judge model (llama3.2:3b, used in
    "local" mode — see run_eval.py) was observed emitting a stray extra
    closing brace after an otherwise well-formed object, e.g.
    `{"score": 5, "rationale": "..."}}"` — a greedy regex swallows that
    trailing `}` into the match, producing invalid JSON and silently
    mis-scoring a genuinely well-formed 5/5 judgment as unparseable (score
    0.0). Stopping at the first balanced close is correct for that case and
    for the more common one (leading prose before the object) alike."""
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
    return None


def _parse_judge_response(raw: str) -> JudgeScore:
    candidate = _extract_first_json_object(raw)
    if candidate is None:
        return _unparseable(raw)
    try:
        payload = json.loads(candidate)
        raw_score = int(payload["score"])
        rationale = str(payload.get("rationale", ""))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _unparseable(raw)
    return JudgeScore(
        score=_normalize(raw_score), raw_score=raw_score, rationale=rationale, parse_ok=True
    )


def build_faithfulness_messages(question: str, context: str, answer: str) -> list[dict[str, str]]:
    user_content = (
        f"Question: {question}\n\n"
        f"Context the answer was supposed to be grounded in:\n{context}\n\n"
        f"Answer to grade:\n{answer}\n\n{_JUDGE_INSTRUCTIONS}"
    )
    return [
        {"role": "system", "content": FAITHFULNESS_RUBRIC},
        {"role": "user", "content": user_content},
    ]


def build_relevance_messages(question: str, answer: str) -> list[dict[str, str]]:
    user_content = f"Question: {question}\n\nAnswer to grade:\n{answer}\n\n{_JUDGE_INSTRUCTIONS}"
    return [
        {"role": "system", "content": RELEVANCE_RUBRIC},
        {"role": "user", "content": user_content},
    ]


async def score_faithfulness(judge: Judge, question: str, context: str, answer: str) -> JudgeScore:
    raw = await judge.complete(build_faithfulness_messages(question, context, answer))
    return _parse_judge_response(raw)


async def score_relevance(judge: Judge, question: str, answer: str) -> JudgeScore:
    raw = await judge.complete(build_relevance_messages(question, answer))
    return _parse_judge_response(raw)
