"""Optional Langfuse tracing for the RAG pipeline.

Active only when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set (plus LANGFUSE_HOST for a
self-hosted server); otherwise every call is a no-op and langfuse is never imported. One trace per
question: a root span, a child span for query rewrite + retrieval (with per-stage timings), and a
"generation" for the LLM call. Question text, retrieved context and answers are recorded only when
LANGFUSE_CAPTURE_CONTENT=true, because they are user data; by default only names, timings, counts
and scores leave the process.

Spans are started and ended explicitly (not as context managers) so they stay correct across the
`yield`s of the streaming answer generator. Tracing problems are logged and never reach the caller.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def capture_content() -> bool:
    return os.getenv("LANGFUSE_CAPTURE_CONTENT", "false").lower() == "true"


class Span:
    """Thin wrapper over a Langfuse observation; a no-op when `_obs` is None."""

    def __init__(self, obs: Any = None) -> None:
        self._obs = obs

    def child(self, name: str, *, as_type: str = "span", **kwargs: Any) -> "Span":
        if self._obs is None:
            return Span()
        try:
            obs = self._obs.start_observation(name=name, as_type=as_type, **self._clean(kwargs))
            return Span(obs)
        except Exception:  # noqa: BLE001 - tracing must not break a request
            logger.warning("langfuse child span failed", exc_info=True)
            return Span()

    def update(self, **kwargs: Any) -> None:
        if self._obs is None:
            return
        try:
            self._obs.update(**self._clean(kwargs))
        except Exception:  # noqa: BLE001
            logger.warning("langfuse update failed", exc_info=True)

    def end(self) -> None:
        if self._obs is None:
            return
        try:
            self._obs.end()
        except Exception:  # noqa: BLE001
            logger.warning("langfuse end failed", exc_info=True)

    @staticmethod
    def _clean(kwargs: dict[str, Any]) -> dict[str, Any]:
        if not capture_content():
            kwargs = {k: v for k, v in kwargs.items() if k not in ("input", "output")}
        return kwargs


def start_trace(name: str, **kwargs: Any) -> Span:
    """Root span for one request; a no-op Span when tracing is not configured."""
    if not enabled():
        return Span()
    try:
        from langfuse import get_client

        client = get_client()
        return Span(client.start_observation(name=name, as_type="span", **Span._clean(kwargs)))
    except Exception:  # noqa: BLE001
        logger.warning("langfuse tracing unavailable", exc_info=True)
        return Span()

