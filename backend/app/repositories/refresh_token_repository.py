import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        refresh_token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(refresh_token)
        await self._session.flush()
        return refresh_token

    async def get_valid_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        token = result.scalar_one_or_none()
        if token is None:
            return None
        if token.revoked_at is not None:
            return None
        if token.expires_at < datetime.now(UTC):
            return None
        return token

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_by_hash(self, token_hash: str) -> None:
        token = await self.get_valid_by_hash(token_hash)
        if token is not None:
            await self.revoke(token)
