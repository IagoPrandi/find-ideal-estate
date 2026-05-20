from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, HTTPException, status
from modules.auth.service import AUTH_SESSION_COOKIE, RequestAuthContext, build_request_auth_context
from modules.journeys.service import ANONYMOUS_SESSION_COOKIE


async def require_developer(
    auth_session: Annotated[str | None, Cookie(alias=AUTH_SESSION_COOKIE)] = None,
    anonymous_session_id: Annotated[str | None, Cookie(alias=ANONYMOUS_SESSION_COOKIE)] = None,
) -> RequestAuthContext:
    ctx = await build_request_auth_context(
        session_token=auth_session,
        anonymous_session_id=anonymous_session_id,
    )
    if ctx.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária.")
    if not ctx.user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito ao desenvolvedor.")
    return ctx
