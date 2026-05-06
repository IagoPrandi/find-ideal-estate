from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from contracts import AuthGoogleLoginRequest, AuthLoginRequest, AuthRegisterRequest, AuthStatusRead
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from modules.auth.service import (
    AUTH_SESSION_COOKIE,
    build_auth_status,
    build_request_auth_context,
    login_google_user,
    login_user,
    register_user,
    revoke_session_by_token,
)
from modules.journeys.service import ANONYMOUS_SESSION_COOKIE

router = APIRouter(prefix="/auth", tags=["auth"])


async def get_optional_auth_context(
    auth_session: Annotated[str | None, Cookie(alias=AUTH_SESSION_COOKIE)] = None,
    anonymous_session_id: Annotated[str | None, Cookie(alias=ANONYMOUS_SESSION_COOKIE)] = None,
):
    return await build_request_auth_context(
        session_token=auth_session,
        anonymous_session_id=anonymous_session_id,
    )


def _set_auth_cookie(response: Response, session_token: str, *, max_age_seconds: int) -> None:
    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=session_token,
        max_age=max_age_seconds,
        httponly=True,
        samesite="lax",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_SESSION_COOKIE, httponly=True, samesite="lax")


def _session_max_age_seconds(expires_at: datetime) -> int:
    return max(0, int((expires_at - datetime.now(tz=timezone.utc)).total_seconds()))


@router.get("/me", response_model=AuthStatusRead)
async def get_current_auth_status(
    response: Response,
    auth_context=Depends(get_optional_auth_context),
) -> AuthStatusRead:
    status_payload = build_auth_status(auth_context)
    if not status_payload.is_authenticated and auth_context.session_token:
        _clear_auth_cookie(response)
    return status_payload


@router.post("/register", response_model=AuthStatusRead, status_code=status.HTTP_201_CREATED)
async def register_user_endpoint(
    payload: AuthRegisterRequest,
    response: Response,
    auth_context=Depends(get_optional_auth_context),
) -> AuthStatusRead:
    try:
        user, session_token, expires_at = await register_user(
            payload,
            anonymous_session_id=auth_context.anonymous_session_id,
        )
    except ValueError as exc:
        detail = str(exc)
        error_status = status.HTTP_409_CONFLICT if "Já existe" in detail else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=error_status, detail=detail) from exc

    max_age_seconds = _session_max_age_seconds(expires_at)
    _set_auth_cookie(response, session_token, max_age_seconds=max_age_seconds)
    return AuthStatusRead(
        is_authenticated=True,
        user=user,
        session_expires_at=expires_at,
    )


@router.post("/login", response_model=AuthStatusRead)
async def login_user_endpoint(
    payload: AuthLoginRequest,
    response: Response,
    auth_context=Depends(get_optional_auth_context),
) -> AuthStatusRead:
    try:
        user, session_token, expires_at = await login_user(
            payload,
            anonymous_session_id=auth_context.anonymous_session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    max_age_seconds = _session_max_age_seconds(expires_at)
    _set_auth_cookie(response, session_token, max_age_seconds=max_age_seconds)
    return AuthStatusRead(
        is_authenticated=True,
        user=user,
        session_expires_at=expires_at,
    )


@router.post("/google", response_model=AuthStatusRead)
async def login_google_user_endpoint(
    payload: AuthGoogleLoginRequest,
    response: Response,
    auth_context=Depends(get_optional_auth_context),
) -> AuthStatusRead:
    try:
        user, session_token, expires_at = await login_google_user(
            payload,
            anonymous_session_id=auth_context.anonymous_session_id,
        )
    except ValueError as exc:
        detail = str(exc)
        error_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if "não está configurado" in detail
            else status.HTTP_401_UNAUTHORIZED
        )
        raise HTTPException(status_code=error_status, detail=detail) from exc

    max_age_seconds = _session_max_age_seconds(expires_at)
    _set_auth_cookie(response, session_token, max_age_seconds=max_age_seconds)
    return AuthStatusRead(
        is_authenticated=True,
        user=user,
        session_expires_at=expires_at,
    )


@router.post("/logout", response_model=AuthStatusRead)
async def logout_user_endpoint(
    response: Response,
    auth_context=Depends(get_optional_auth_context),
) -> AuthStatusRead:
    await revoke_session_by_token(auth_context.session_token)
    _clear_auth_cookie(response)
    return AuthStatusRead(is_authenticated=False, user=None, session_expires_at=None)
