"""Authentication & account routes (FR-501..FR-508).

Two independent ways to create and use an account: Google (``/auth/google``)
and manual email/password (``/auth/register``, ``/auth/login``). Neither is
required — Google works with no manual account ever created, and manual
sign-in works whether or not Google is configured — and both end in the same
place: a :class:`TokenResponse` from the same issuer, usable against every
protected route exactly the same way.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from tender_intel.api.dependencies.auth import get_current_user
from tender_intel.api.dependencies.services import get_auth_service
from tender_intel.api.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from tender_intel.application.dto.auth import TokenPair
from tender_intel.application.services.auth_service import AuthService
from tender_intel.domain.entities import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _to_token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@router.post("/google", response_model=TokenResponse)
async def google_login(
    body: GoogleLoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    pair = await service.google_login(
        id_token=body.id_token,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _to_token_response(pair)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    pair = await service.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _to_token_response(pair)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    pair = await service.login(
        email=body.email,
        password=body.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _to_token_response(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    pair = await service.refresh(
        refresh_token=body.refresh_token,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _to_token_response(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    service: AuthService = Depends(get_auth_service),
) -> Response:
    await service.logout(refresh_token=body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_entity(user)
