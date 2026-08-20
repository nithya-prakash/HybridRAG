from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.retrieval import RetrievalSearchRequest, RetrievalSearchResponse
from app.services.retrieval import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchResponse)
@limiter.limit(lambda: get_settings().retrieval_rate_limit)
async def search(
    request: Request,
    response: Response,
    body: RetrievalSearchRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RetrievalSearchResponse:
    filters = body.filters.to_domain() if body.filters else None
    result = await RetrievalService(session).retrieve(
        query=body.query,
        user_id=current_user.id,
        filters=filters,
        top_k=body.top_k,
    )
    return RetrievalSearchResponse(
        query=result.query,
        results=result.results,
        timings_ms=result.timings_ms,
    )
