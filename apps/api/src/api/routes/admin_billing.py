from __future__ import annotations

from typing import Annotated
from uuid import UUID

from contracts import AccountPlanRead, PaymentStatusRead
from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from modules.auth.service import AUTH_SESSION_COOKIE, RequestAuthContext, build_request_auth_context
from modules.billing.pix import (
    PaymentAlreadyProcessedError,
    PaymentExpiredError,
    PaymentNotFoundError,
    PixError,
    activate_plan_from_pix,
    get_payment_status,
)
from modules.journeys.service import ANONYMOUS_SESSION_COOKIE
from modules.plans.service import activate_plan_direct, get_active_plan_activation

router = APIRouter(prefix="/admin/billing", tags=["admin"])

_PROPRIETARIO_ROLE = "proprietario"


async def _require_proprietario(
    auth_session: Annotated[str | None, Cookie(alias=AUTH_SESSION_COOKIE)] = None,
    anonymous_session_id: Annotated[str | None, Cookie(alias=ANONYMOUS_SESSION_COOKIE)] = None,
) -> RequestAuthContext:
    ctx = await build_request_auth_context(
        session_token=auth_session,
        anonymous_session_id=anonymous_session_id,
    )
    if ctx.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária.")
    if ctx.user.role != _PROPRIETARIO_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a proprietários.")
    return ctx


@router.post("/pix/{payment_id}/confirm", response_model=PaymentStatusRead)
async def admin_confirm_pix(
    payment_id: UUID,
    ctx: RequestAuthContext = Depends(_require_proprietario),
) -> PaymentStatusRead:
    try:
        await activate_plan_from_pix(payment_id)
    except PaymentAlreadyProcessedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except (PaymentNotFoundError, PixError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        return await get_payment_status(payment_id)
    except PaymentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/plans/{plan_slug}/activate", response_model=AccountPlanRead, status_code=status.HTTP_200_OK)
async def proprietario_activate_plan(
    plan_slug: str,
    ctx: RequestAuthContext = Depends(_require_proprietario),
) -> AccountPlanRead:
    try:
        await activate_plan_direct(user_id=ctx.user.id, plan_slug=plan_slug)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    plan = await get_active_plan_activation(ctx.user.id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano não encontrado após ativação.")
    return plan
