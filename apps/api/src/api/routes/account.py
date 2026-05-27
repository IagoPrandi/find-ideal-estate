from __future__ import annotations

from typing import Annotated
from uuid import UUID

from contracts import AccountCreditsRead, AccountPlanRead
from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from modules.auth.service import AUTH_SESSION_COOKIE, RequestAuthContext, build_request_auth_context
from modules.credits.service import get_user_credits
from modules.journeys.service import ANONYMOUS_SESSION_COOKIE
from modules.plans.service import get_active_plan_activation, resolve_entitlements

router = APIRouter(prefix="/account", tags=["account"])


async def _require_auth(
    auth_session: Annotated[str | None, Cookie(alias=AUTH_SESSION_COOKIE)] = None,
    anonymous_session_id: Annotated[str | None, Cookie(alias=ANONYMOUS_SESSION_COOKIE)] = None,
) -> RequestAuthContext:
    ctx = await build_request_auth_context(
        session_token=auth_session,
        anonymous_session_id=anonymous_session_id,
    )
    if ctx.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária.")
    return ctx


@router.get("/plan", response_model=AccountPlanRead)
async def get_my_plan(ctx: RequestAuthContext = Depends(_require_auth)) -> AccountPlanRead:
    resolved = await resolve_entitlements(ctx.user.id)
    if resolved.plan.slug == "proprietario":
        return AccountPlanRead(
            plan=resolved.plan,
            status="active",
            started_at=None,
            ends_at=None,
            entitlements=resolved.entitlements,
        )

    plan = await get_active_plan_activation(ctx.user.id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhum plano ativo encontrado.")
    return plan


@router.get("/credits", response_model=AccountCreditsRead)
async def get_my_credits(ctx: RequestAuthContext = Depends(_require_auth)) -> AccountCreditsRead:
    return await get_user_credits(ctx.user.id)
