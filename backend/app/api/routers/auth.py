from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import UserCreate, UserLogin, UserRead
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    TokenPair,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _set_auth_cookies(response: Response, tokens: TokenPair) -> None:
    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=tokens.access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
    )
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=tokens.refresh_token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        settings.access_token_cookie_name, path="/", domain=settings.cookie_domain
    )
    response.delete_cookie(
        settings.refresh_token_cookie_name, path="/auth", domain=settings.cookie_domain
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().auth_rate_limit)
async def register(
    request: Request,
    response: Response,
    payload: UserCreate,
    session: AsyncSession = Depends(get_db),
) -> User:
    service = AuthService(session)
    try:
        return await service.register(payload.email, payload.password)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc


@router.post("/login", response_model=UserRead)
@limiter.limit(lambda: get_settings().auth_rate_limit)
async def login(
    request: Request,
    response: Response,
    payload: UserLogin,
    session: AsyncSession = Depends(get_db),
) -> User:
    service = AuthService(session)
    try:
        user = await service.authenticate(payload.email, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        ) from exc

    tokens = await service.issue_tokens(user.id)
    _set_auth_cookies(response, tokens)
    return user


@router.post("/refresh", response_model=UserRead)
async def refresh(
    response: Response,
    session: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> User:
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )

    service = AuthService(session)
    try:
        user, tokens = await service.rotate_refresh_token(refresh_token)
    except InvalidRefreshTokenError as exc:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        ) from exc

    _set_auth_cookies(response, tokens)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> None:
    if refresh_token is not None:
        await AuthService(session).revoke_refresh_token(refresh_token)
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
