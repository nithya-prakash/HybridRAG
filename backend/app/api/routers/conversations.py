import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.error_handlers import DOWNSTREAM_UNAVAILABLE_EXCEPTIONS
from app.core.llm_errors import classify_llm_error
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.conversation import (
    CitationRead,
    ConversationDetailRead,
    ConversationRead,
    MessageCreateRequest,
    MessageRead,
)
from app.services.rag import (
    AnswerComplete,
    AnswerToken,
    Citation,
    ConversationNotFoundError,
    ConversationService,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _citation_payload(citations: list[Citation]) -> list[dict]:
    return [CitationRead.model_validate(c).model_dump(mode="json") for c in citations]


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await ConversationService(session).create_conversation(current_user.id)


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await ConversationService(session).list_conversations(current_user.id)


@router.get("/{conversation_id}", response_model=ConversationDetailRead)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationDetailRead:
    service = ConversationService(session)
    try:
        conversation, messages = await service.get_conversation_with_messages(
            current_user.id, conversation_id
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from exc

    message_reads = []
    for message in messages:
        citations = await service.reconstruct_citations(current_user.id, message)
        message_reads.append(
            MessageRead(
                id=message.id,
                role=message.role,
                content=message.content,
                rewritten_query=message.rewritten_query,
                citations=[CitationRead.model_validate(c) for c in citations],
                created_at=message.created_at,
            )
        )
    return ConversationDetailRead(
        conversation=ConversationRead.model_validate(conversation), messages=message_reads
    )


@router.post("/{conversation_id}/messages")
@limiter.limit(lambda: get_settings().chat_rate_limit)
async def post_message(
    request: Request,
    conversation_id: uuid.UUID,
    body: MessageCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = ConversationService(session)
    # Validated eagerly, before the streaming response starts — once
    # StreamingResponse begins, the 200 status line is already sent and the
    # HTTP status can no longer change, so a missing/foreign conversation
    # must 404 here rather than surface as an in-stream SSE error event.
    try:
        await service.require_conversation(current_user.id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from exc

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.ask(current_user.id, conversation_id, body.content):
                if isinstance(event, AnswerToken):
                    yield _sse("token", {"delta": event.delta})
                elif isinstance(event, AnswerComplete):
                    yield _sse(
                        "citations",
                        {
                            "message_id": str(event.message_id),
                            "rewritten_query": event.rewritten_query,
                            "citations": _citation_payload(event.citations),
                        },
                    )
            yield _sse("done", {})
        except DOWNSTREAM_UNAVAILABLE_EXCEPTIONS as exc:
            # Same "can't change the HTTP status mid-stream" constraint as
            # the 404 check above — a downstream outage becomes a clearly-
            # labeled SSE error event here rather than a generic 500/503,
            # since the response has already committed to 200 by this point.
            # classify_llm_error turns a known failure (wrong key, no quota,
            # Ollama/Qdrant unreachable) into something the person running
            # this can actually act on, instead of a one-size-fits-all
            # "try again shortly" that's equally unhelpful for all of them.
            logger.exception(
                "rag_answer_stream_downstream_unavailable", conversation_id=str(conversation_id)
            )
            yield _sse("error", {"detail": classify_llm_error(exc)})
        except Exception:
            logger.exception("rag_answer_stream_failed", conversation_id=str(conversation_id))
            yield _sse("error", {"detail": "Answer generation failed."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
