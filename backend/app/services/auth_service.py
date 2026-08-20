import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository

settings = get_settings()


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_token_expires_at: datetime


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    async def register(self, email: str, password: str) -> User:
        existing = await self._users.get_by_email(email)
        if existing is not None:
            raise EmailAlreadyRegisteredError(email)
        user = await self._users.create(email=email, hashed_password=hash_password(password))
        await self._session.commit()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            raise InvalidCredentialsError(email)
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError(email)
        return user

    async def issue_tokens(self, user_id: uuid.UUID) -> TokenPair:
        access_token = create_access_token(user_id)

        raw_refresh_token = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
        await self._refresh_tokens.create(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=expires_at,
        )
        await self._session.commit()

        return TokenPair(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            refresh_token_expires_at=expires_at,
        )

    async def rotate_refresh_token(self, raw_refresh_token: str) -> tuple[User, TokenPair]:
        token_hash = hash_refresh_token(raw_refresh_token)
        token = await self._refresh_tokens.get_valid_by_hash(token_hash)
        if token is None:
            raise InvalidRefreshTokenError

        user = await self._users.get_by_id(token.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError

        await self._refresh_tokens.revoke(token)
        new_tokens = await self.issue_tokens(user.id)
        return user, new_tokens

    async def revoke_refresh_token(self, raw_refresh_token: str) -> None:
        await self._refresh_tokens.revoke_by_hash(hash_refresh_token(raw_refresh_token))
        await self._session.commit()
