import uuid

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

settings = get_settings()


async def get_current_user(
    session: AsyncSession = Depends(get_db),
    access_token: str | None = Cookie(default=None, alias="access_token"),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if access_token is None:
        raise credentials_error

    payload = decode_access_token(access_token)
    if payload is None:
        raise credentials_error

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise credentials_error from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        raise credentials_error

    return user
