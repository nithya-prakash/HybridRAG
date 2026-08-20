import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat import ChatBackend, get_chat_backend
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.services.rag.prompts import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    Citation,
    CitationSource,
    build_context_block,
    build_messages,
    extract_citations,
    from_chunk_models,
    from_retrieved_chunks,
)
from app.services.rag.query_rewriter import QueryRewriter
from app.services.retrieval import RetrievalService

logger = get_logger(__name__)


class ConversationNotFoundError(Exception):
    pass


@dataclass
class AnswerToken:
    delta: str


@dataclass
class AnswerComplete:
    message_id: uuid.UUID
    content: str
    rewritten_query: str
    retrieved_chunk_ids: list[uuid.UUID] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


AnswerEvent = AnswerToken | AnswerComplete


def _derive_title(content: str, max_len: int = 60) -> str:
    collapsed = " ".join(content.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 1].rstrip() + "…"


class ConversationService:
    """Orchestrates one grounded-answer turn: persist the user's message,
    rewrite it into a standalone query, retrieve (Phase 5's
    `RetrievalService`), decide whether the retrieved context is actually
    usable, generate a streamed, cited answer or a canned decline, and
    persist the result. See `ARCHITECTURE.md` § Conversational RAG for the
    full design and the two hallucination-mitigation layers."""

    def __init__(
        self,
        session: AsyncSession,
        retrieval_service: RetrievalService | None = None,
        query_rewriter: QueryRewriter | None = None,
        chat_backend: ChatBackend | None = None,
    ) -> None:
        settings = get_settings()
        self._session = session
        self._conversations = ConversationRepository(session)
        self._documents = DocumentRepository(session)
        self._chunks = ChunkRepository(session)
        self._retrieval = retrieval_service or RetrievalService(session)
        self._rewriter = query_rewriter or QueryRewriter(chat_backend)
        self._chat = chat_backend or get_chat_backend()
        self._min_rerank_score = settings.rag_min_rerank_score
        self._max_history_turns = settings.rag_history_max_turns

    async def create_conversation(self, user_id: uuid.UUID) -> Conversation:
        conversation = await self._conversations.create(user_id)
        await self._session.commit()
        return conversation

    async def list_conversations(self, user_id: uuid.UUID) -> list[Conversation]:
        return await self._conversations.list_for_user(user_id)

    async def require_conversation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation:
        conversation = await self._conversations.get_for_user(conversation_id, user_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation

    async def get_conversation_with_messages(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> tuple[Conversation, list[Message]]:
        conversation = await self.require_conversation(user_id, conversation_id)
        messages = await self._conversations.list_messages(conversation_id, user_id)
        return conversation, messages

    async def reconstruct_citations(self, user_id: uuid.UUID, message: Message) -> list[Citation]:
        """Re-derives a past assistant message's structured citations from
        its `retrieved_chunk_ids` and its own `content` — see `Message`'s
        docstring for why that's stored instead of a redundant citations
        copy. `retrieved_chunk_ids` preserves the rank order the message's
        `[n]` markers were originally numbered against, so results are
        re-ordered to match after the (order-losing) `IN` fetch."""
        if message.role != MessageRole.ASSISTANT.value or not message.retrieved_chunk_ids:
            return []
        chunk_ids = [uuid.UUID(cid) for cid in message.retrieved_chunk_ids]
        rows = await self._chunks.get_by_ids(user_id, chunk_ids)
        rows_by_id = {row.id: row for row in rows}
        ordered_rows = [rows_by_id[cid] for cid in chunk_ids if cid in rows_by_id]
        sources = from_chunk_models(ordered_rows)
        filenames = await self._filenames_for(user_id, sources)
        index_map = dict(enumerate(sources, start=1))
        return extract_citations(message.content, index_map, filenames)

    async def _filenames_for(
        self, user_id: uuid.UUID, sources: list[CitationSource]
    ) -> dict[uuid.UUID, str]:
        document_ids = list({s.document_id for s in sources})
        documents = await self._documents.get_many_for_user(user_id, document_ids)
        return {d.id: d.filename for d in documents}

    async def ask(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, raw_content: str
    ) -> AsyncIterator[AnswerEvent]:
        conversation = await self.require_conversation(user_id, conversation_id)

        prior_messages = await self._conversations.list_messages(conversation_id, user_id)
        history = [(m.role, m.content) for m in prior_messages][-self._max_history_turns :]

        # Committed immediately, in its own transaction: the user's own
        # message should survive on the page even if retrieval or generation
        # fails a moment later.
        await self._conversations.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.USER.value,
            content=raw_content,
        )
        await self._session.commit()

        rewritten = await self._rewriter.rewrite(history, raw_content)

        retrieval_result = await self._retrieval.retrieve(rewritten, user_id)
        results = retrieval_result.results
        best_score = max(
            (r.rerank_score for r in results if r.rerank_score is not None), default=None
        )

        if best_score is None or best_score < self._min_rerank_score:
            logger.info(
                "rag_insufficient_context",
                conversation_id=str(conversation_id),
                rewritten_query=rewritten,
                candidate_count=len(results),
                best_rerank_score=best_score,
            )
            content = INSUFFICIENT_CONTEXT_MESSAGE
            chunk_ids = [r.chunk_id for r in results]
            message = await self._conversations.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role=MessageRole.ASSISTANT.value,
                content=content,
                rewritten_query=rewritten,
                retrieved_chunk_ids=chunk_ids,
            )
            await self._conversations.touch(conversation)
            await self._session.commit()
            yield AnswerToken(delta=content)
            yield AnswerComplete(
                message_id=message.id,
                content=content,
                rewritten_query=rewritten,
                retrieved_chunk_ids=chunk_ids,
                citations=[],
            )
            return

        sources = from_retrieved_chunks(results)
        filenames = await self._filenames_for(user_id, sources)
        context_block, index_map = build_context_block(sources, filenames)
        messages = build_messages(history, context_block, rewritten)

        full_text_parts: list[str] = []
        async for delta in self._chat.stream_complete(messages):
            full_text_parts.append(delta)
            yield AnswerToken(delta=delta)
        full_text = "".join(full_text_parts)

        citations = extract_citations(full_text, index_map, filenames)
        chunk_ids = [r.chunk_id for r in results]
        message = await self._conversations.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=MessageRole.ASSISTANT.value,
            content=full_text,
            rewritten_query=rewritten,
            retrieved_chunk_ids=chunk_ids,
        )
        if conversation.title is None:
            await self._conversations.set_title(conversation, _derive_title(raw_content))
        await self._conversations.touch(conversation)
        await self._session.commit()

        logger.info(
            "rag_answer_complete",
            conversation_id=str(conversation_id),
            rewritten_query=rewritten,
            candidate_count=len(results),
            citation_count=len(citations),
            answer_length=len(full_text),
        )
        yield AnswerComplete(
            message_id=message.id,
            content=full_text,
            rewritten_query=rewritten,
            retrieved_chunk_ids=chunk_ids,
            citations=citations,
        )
