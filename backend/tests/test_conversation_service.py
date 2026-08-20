import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.vector_store import EmbeddedChunk, get_vector_store
from app.models.message import MessageRole
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.parsing.models import Chunk as ParsedChunk
from app.services.rag import (
    AnswerComplete,
    AnswerToken,
    ConversationNotFoundError,
    ConversationService,
)
from app.services.rag.prompts import INSUFFICIENT_CONTEXT_MESSAGE
from app.services.retrieval import RetrievalService
from tests.helpers import FakeEmbeddingBackend, fake_embed

CORPUS = [
    "Employees may book economy class flights for trips under six hours.",
    "Hotel bookings should not exceed 200 dollars per night without manager approval.",
    "Meal reimbursement is capped at 75 dollars per day while traveling for business.",
]


class FakeChatBackend:
    """Deterministic stand-in for both the query-rewriter's `complete()` call
    and the answer generator's `stream_complete()` call — no real OpenAI call
    in this file, per the task's "mock the OpenAI chat API" instruction."""

    def __init__(
        self,
        answer: str = "Meals are capped at 75 dollars per day [1].",
        rewrite: str | None = None,
    ):
        self.answer = answer
        self.rewrite = rewrite
        self.complete_calls: list[list[dict]] = []
        self.stream_calls: list[list[dict]] = []

    async def complete(self, messages):
        self.complete_calls.append(messages)
        return self.rewrite if self.rewrite is not None else messages[-1]["content"]

    async def stream_complete(self, messages):
        self.stream_calls.append(messages)
        for word in self.answer.split(" "):
            yield word + " "


async def _index_document(
    session: AsyncSession, user_id: uuid.UUID, contents: list[str], filename: str = "policy.txt"
):
    document = await DocumentRepository(session).create(
        document_id=uuid.uuid4(),
        user_id=user_id,
        filename=filename,
        file_type="txt",
        file_size_bytes=1,
        storage_path=f"/tmp/{filename}",
    )
    parsed_chunks = [
        ParsedChunk(
            content=text,
            chunk_index=i,
            page_number=1,
            section_path=[],
            char_start=0,
            char_end=len(text),
            token_count=len(text.split()),
            content_hash=str(i),
        )
        for i, text in enumerate(contents)
    ]
    rows = await ChunkRepository(session).replace_for_document(
        document_id=document.id, user_id=user_id, document_version=1, chunks=parsed_chunks
    )
    await session.commit()

    embedded = [
        EmbeddedChunk(
            chunk_id=row.id,
            vector=fake_embed(chunk.content),
            document_id=document.id,
            user_id=user_id,
            document_version=1,
            page_number=1,
            section_path=[],
            chunk_index=chunk.chunk_index,
            file_type="txt",
            document_created_at=document.created_at,
        )
        for row, chunk in zip(rows, parsed_chunks, strict=True)
    ]
    await get_vector_store().replace_for_document(document.id, embedded)
    return document


def _service(session: AsyncSession, chat_backend=None) -> ConversationService:
    return ConversationService(
        session,
        retrieval_service=RetrievalService(session, embedding_backend=FakeEmbeddingBackend()),
        chat_backend=chat_backend or FakeChatBackend(),
    )


async def test_ask_persists_user_and_assistant_messages(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="rag-persist@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, CORPUS)
    conversation = await ConversationRepository(db_session).create(user.id)
    await db_session.commit()

    async for _ in _service(db_session).ask(user.id, conversation.id, "What is the meal cap?"):
        pass

    messages = await ConversationRepository(db_session).list_messages(conversation.id, user.id)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER.value
    assert messages[0].content == "What is the meal cap?"
    assert messages[1].role == MessageRole.ASSISTANT.value


async def test_ask_grounded_answer_includes_citations_matching_stream(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="rag-grounded@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, CORPUS)
    conversation = await ConversationRepository(db_session).create(user.id)
    await db_session.commit()

    chat = FakeChatBackend(answer="Meals are capped at 75 dollars per day [1].")
    events = [
        e
        async for e in _service(db_session, chat).ask(
            user.id, conversation.id, "What is the meal reimbursement cap?"
        )
    ]

    tokens = [e for e in events if isinstance(e, AnswerToken)]
    complete = next(e for e in events if isinstance(e, AnswerComplete))

    assert tokens
    assert "".join(t.delta for t in tokens).strip() == complete.content.strip()
    assert complete.citations
    assert complete.citations[0].marker == 1
    assert complete.retrieved_chunk_ids

    messages = await ConversationRepository(db_session).list_messages(conversation.id, user.id)
    assistant_message = messages[-1]
    assert assistant_message.content == complete.content
    assert assistant_message.rewritten_query == "What is the meal reimbursement cap?"
    assert [
        uuid.UUID(cid) for cid in assistant_message.retrieved_chunk_ids
    ] == complete.retrieved_chunk_ids


async def test_ask_sets_conversation_title_from_first_message(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="rag-title@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, CORPUS)
    conversation = await ConversationRepository(db_session).create(user.id)
    await db_session.commit()

    async for _ in _service(db_session).ask(
        user.id, conversation.id, "What is the meal reimbursement cap per day?"
    ):
        pass

    updated = await ConversationRepository(db_session).get_for_user(conversation.id, user.id)
    assert updated.title == "What is the meal reimbursement cap per day?"


async def test_ask_declines_when_no_relevant_context(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="rag-decline@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, CORPUS)
    conversation = await ConversationRepository(db_session).create(user.id)
    await db_session.commit()

    chat = FakeChatBackend()
    events = [
        e
        async for e in _service(db_session, chat).ask(
            user.id, conversation.id, "What is the boiling point of mercury?"
        )
    ]

    complete = next(e for e in events if isinstance(e, AnswerComplete))
    assert complete.content == INSUFFICIENT_CONTEXT_MESSAGE
    assert complete.citations == []
    assert chat.stream_calls == []  # never called the LLM for a doomed answer

    messages = await ConversationRepository(db_session).list_messages(conversation.id, user.id)
    assert messages[-1].content == INSUFFICIENT_CONTEXT_MESSAGE


async def test_ask_raises_for_missing_conversation(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="rag-missing@example.com", hashed_password="x"
    )

    with pytest.raises(ConversationNotFoundError):
        async for _ in _service(db_session).ask(user.id, uuid.uuid4(), "hello"):
            pass


async def test_ask_rejects_another_users_conversation(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(
        email="rag-owner@example.com", hashed_password="x"
    )
    other = await UserRepository(db_session).create(
        email="rag-other@example.com", hashed_password="x"
    )
    await _index_document(db_session, owner.id, CORPUS)
    conversation = await ConversationRepository(db_session).create(owner.id)
    await db_session.commit()

    with pytest.raises(ConversationNotFoundError):
        async for _ in _service(db_session).ask(other.id, conversation.id, "hi"):
            pass


async def test_ask_grounds_only_in_askers_own_documents(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(
        email="rag-grounded-owner@example.com", hashed_password="x"
    )
    other = await UserRepository(db_session).create(
        email="rag-grounded-other@example.com", hashed_password="x"
    )
    owner_doc = await _index_document(db_session, owner.id, CORPUS, filename="owner.txt")
    other_doc = await _index_document(db_session, other.id, CORPUS, filename="other.txt")
    conversation = await ConversationRepository(db_session).create(owner.id)
    await db_session.commit()

    events = [
        e
        async for e in _service(db_session).ask(
            owner.id, conversation.id, "What is the meal reimbursement cap?"
        )
    ]
    complete = next(e for e in events if isinstance(e, AnswerComplete))

    assert complete.citations
    assert all(c.document_id == owner_doc.id for c in complete.citations)
    assert all(c.document_id != other_doc.id for c in complete.citations)


async def test_query_rewriting_used_on_followup_turn(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="rag-followup@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, CORPUS)
    conversation = await ConversationRepository(db_session).create(user.id)
    await db_session.commit()

    chat = FakeChatBackend(
        answer="Economy class is fine under six hours [1].",
        rewrite="What is the flight class policy for short trips?",
    )
    service = _service(db_session, chat)

    async for _ in service.ask(user.id, conversation.id, "What is the flight policy?"):
        pass
    assert chat.complete_calls == []  # first turn: no history yet, rewrite skipped

    events = [e async for e in service.ask(user.id, conversation.id, "what about short trips?")]

    assert len(chat.complete_calls) == 1  # follow-up turn: history exists, rewrite called
    complete = next(e for e in events if isinstance(e, AnswerComplete))
    assert complete.rewritten_query == "What is the flight class policy for short trips?"


async def test_reconstruct_citations_matches_original_after_generation(db_session: AsyncSession):
    user = await UserRepository(db_session).create(
        email="rag-reconstruct@example.com", hashed_password="x"
    )
    await _index_document(db_session, user.id, CORPUS)
    conversation = await ConversationRepository(db_session).create(user.id)
    await db_session.commit()

    chat = FakeChatBackend(answer="Meals are capped at 75 dollars per day [1].")
    service = _service(db_session, chat)
    events = [
        e
        async for e in service.ask(
            user.id, conversation.id, "What is the meal reimbursement cap?"
        )
    ]
    complete = next(e for e in events if isinstance(e, AnswerComplete))

    messages = await ConversationRepository(db_session).list_messages(conversation.id, user.id)
    reconstructed = await service.reconstruct_citations(user.id, messages[-1])

    assert len(reconstructed) == len(complete.citations)
    assert reconstructed[0].chunk_id == complete.citations[0].chunk_id
    assert reconstructed[0].filename == complete.citations[0].filename


async def test_reconstruct_citations_empty_for_user_message(db_session: AsyncSession):
    service = _service(db_session)
    fake_user_message = type(
        "FakeMessage",
        (),
        {"role": MessageRole.USER.value, "retrieved_chunk_ids": [], "content": "[1] hi"},
    )()

    result = await service.reconstruct_citations(uuid.uuid4(), fake_user_message)

    assert result == []
