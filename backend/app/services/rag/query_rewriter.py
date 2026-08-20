from app.core.chat import ChatBackend, get_chat_backend
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "You rewrite a user's follow-up question into a standalone question, using the "
    "conversation history to resolve pronouns and implicit references (e.g. \"what about "
    "page 3?\" -> \"what does page 3 say about <topic from history>?\"). Preserve the "
    "original question's intent exactly: do not answer it, do not add information the "
    "conversation doesn't imply, and do not change what's being asked. If the follow-up "
    "question is already standalone, return it unchanged. Output ONLY the rewritten "
    "question and nothing else — no preamble, no quotes, no explanation."
)


class QueryRewriter:
    """Turns the latest user turn into a standalone retrieval query. Skips
    the LLM call entirely when there's no prior history to resolve against —
    a first message in a conversation has nothing to rewrite, and calling
    an LLM to echo its input back unchanged would just add latency and cost
    for a guaranteed no-op."""

    def __init__(self, chat_backend: ChatBackend | None = None) -> None:
        self._chat = chat_backend or get_chat_backend()
        self._max_history_turns = get_settings().rag_history_max_turns

    async def rewrite(self, history: list[tuple[str, str]], latest_query: str) -> str:
        if not history:
            logger.info(
                "query_rewrite_skipped", reason="no_history", raw_query=latest_query
            )
            return latest_query

        recent_history = history[-self._max_history_turns :]
        messages = [{"role": "system", "content": REWRITE_SYSTEM_PROMPT}]
        messages.extend({"role": role, "content": content} for role, content in recent_history)
        messages.append(
            {
                "role": "user",
                "content": f"Follow-up question: {latest_query}\n\nStandalone question:",
            }
        )

        try:
            rewritten = (await self._chat.complete(messages)).strip()
        except Exception:
            # Rewriting is a retrieval-quality optimization, not a correctness
            # requirement — retrieval still works on the raw query, just
            # possibly worse for a pronoun-heavy follow-up. Falling back
            # rather than failing the whole request keeps one LLM call's
            # outage from taking down the entire turn.
            logger.exception("query_rewrite_failed", raw_query=latest_query)
            return latest_query

        if not rewritten:
            logger.warning("query_rewrite_empty_completion", raw_query=latest_query)
            return latest_query

        logger.info(
            "query_rewrite_complete", raw_query=latest_query, rewritten_query=rewritten
        )
        return rewritten
