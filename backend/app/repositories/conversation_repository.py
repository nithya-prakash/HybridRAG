import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message


class ConversationRepository:
    """Conversations and their messages together — messages are never
    accessed except through a conversation, the same "one repo covers the
    parent + its owned child rows" shape `DocumentRepository` uses for
    `DocumentVersion`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: uuid.UUID) -> Conversation:
        conversation = Conversation(id=uuid.uuid4(), user_id=user_id)
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def list_for_user(self, user_id: uuid.UUID) -> list[Conversation]:
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_messages(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.user_id == user_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        content: str,
        rewritten_query: str | None = None,
        retrieved_chunk_ids: list[uuid.UUID] | None = None,
    ) -> Message:
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            rewritten_query=rewritten_query,
            retrieved_chunk_ids=[str(cid) for cid in (retrieved_chunk_ids or [])],
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def set_title(self, conversation: Conversation, title: str) -> None:
        conversation.title = title
        await self._session.flush()

    async def touch(self, conversation: Conversation) -> None:
        """Bump `updated_at` explicitly — adding a child `Message` row doesn't
        by itself mark the parent `Conversation` row dirty, so its `onupdate`
        never fires unless something on the row itself actually changes.
        Called every turn so `list_for_user`'s "most recently active first"
        ordering reflects real activity, not just conversation creation time."""
        conversation.updated_at = datetime.now(UTC)
        await self._session.flush()
