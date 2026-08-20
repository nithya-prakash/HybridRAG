"""Turns a caught downstream-dependency exception into a message that's
actually actionable, without leaking anything sensitive (a stack frame, an
API key, an account id). This sits between two extremes this app has already
committed to elsewhere: a completely generic "temporarily unavailable"
(Phase 7's original choice, safe but useless for anyone trying to fix it —
see git history) and dumping `str(exc)` verbatim (which is exactly what
`app/core/error_handlers.py`'s unhandled-exception path deliberately never
does, for good reason). The failure modes classified here are all *known*,
*expected* categories (wrong key, no quota, service unreachable) — not
internal implementation detail — so naming them specifically is safe. Any
exception that doesn't match a known case falls back to the original fully
generic message, preserving that guarantee for the unknown case.

Verified empirically against a live OpenAI account (see docs/ARCHITECTURE.md
§ Configurable LLM/embedding providers): `openai.RateLimitError` carries a
`.code` attribute directly on the exception (not nested under `.body`) —
`"insufficient_quota"` for a billing/quota problem, distinct from actual
rate-limiting — and `openai.AuthenticationError` carries `.code ==
"invalid_api_key"`. Both confirmed directly against the real API rather than
assumed from documentation.
"""

import httpx
import openai
from qdrant_client.http.exceptions import ResponseHandlingException

GENERIC_MESSAGE = "A downstream service is temporarily unavailable. Please try again shortly."


def classify_llm_error(exc: Exception) -> str:
    if isinstance(exc, openai.AuthenticationError):
        return (
            "The configured OPENAI_API_KEY was rejected by OpenAI. If you're "
            "self-hosting this, check the key in your .env file."
        )
    if isinstance(exc, openai.RateLimitError):
        code = getattr(exc, "code", None)
        if code == "insufficient_quota":
            return (
                "The OpenAI account behind the configured API key has no "
                "available quota. Check billing at "
                "platform.openai.com/settings/organization/billing, or switch "
                "CHAT_PROVIDER/EMBEDDING_PROVIDER to a local model — see README.md."
            )
        return "The LLM provider is rate-limiting requests. Please try again in a moment."
    if isinstance(exc, openai.APIConnectionError | openai.APITimeoutError):
        return "Could not reach the OpenAI API — check network connectivity from this environment."
    if isinstance(exc, openai.InternalServerError):
        return "The OpenAI API returned a server error. Please try again shortly."
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return (
            "Could not reach the local Ollama service. If you're self-hosting "
            "this, check that the `ollama` container is running and healthy "
            "(`docker compose ps ollama`) and that the model has finished "
            "downloading (first boot only — see README.md)."
        )
    if isinstance(exc, httpx.ReadTimeout):
        return (
            "The local Ollama service didn't respond in time — it may still be "
            "loading the model or generating a long response. Please try again."
        )
    if isinstance(exc, ResponseHandlingException):
        return (
            "Could not reach Qdrant (the vector database). Check that the "
            "`qdrant` service is running."
        )
    return GENERIC_MESSAGE
