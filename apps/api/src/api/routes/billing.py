from __future__ import annotations

from typing import Annotated
from uuid import UUID

from contracts import PaymentStatusRead, PixCheckoutRequest, PixCheckoutResponse
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from modules.auth.service import AUTH_SESSION_COOKIE, RequestAuthContext, build_request_auth_context
from modules.billing.pix import (
    PaymentAlreadyProcessedError,
    PaymentExpiredError,
    PaymentNotFoundError,
    PixError,
    activate_plan_from_pix,
    cancel_payment,
    create_pix_checkout,
    get_payment_status,
    verify_pix_callback_signature,
)
from modules.journeys.service import ANONYMOUS_SESSION_COOKIE
from modules.plans.service import list_plans
from contracts import PlanRead

router = APIRouter(prefix="/billing", tags=["billing"])


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


@router.get("/plans", response_model=list[PlanRead])
async def get_plans() -> list[PlanRead]:
    return await list_plans()


@router.post("/pix/checkout", response_model=PixCheckoutResponse, status_code=status.HTTP_201_CREATED)
async def pix_checkout(
    payload: PixCheckoutRequest,
    ctx: RequestAuthContext = Depends(_require_auth),
) -> PixCheckoutResponse:
    try:
        return await create_pix_checkout(
            user_id=ctx.user.id,
            plan_slug=payload.plan_slug,
            payment_type=payload.payment_type,
        )
    except PixError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/payments/{payment_id}", response_model=PaymentStatusRead)
async def get_payment(
    payment_id: UUID,
    ctx: RequestAuthContext = Depends(_require_auth),
) -> PaymentStatusRead:
    try:
        return await get_payment_status(payment_id, user_id=ctx.user.id)
    except PaymentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/payments/{payment_id}/cancel", response_model=PaymentStatusRead)
async def cancel_payment_endpoint(
    payment_id: UUID,
    ctx: RequestAuthContext = Depends(_require_auth),
) -> PaymentStatusRead:
    try:
        return await cancel_payment(payment_id, user_id=ctx.user.id)
    except PaymentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/pix/callback")
async def pix_callback(request: Request) -> dict:
    body = await request.body()
    signature = request.headers.get("X-Pix-Signature", "")
    if not verify_pix_callback_signature(body, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Assinatura inválida.")

    import json
    try:
        data = json.loads(body)
        payment_id = UUID(data["payment_id"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido.") from exc

    try:
        await activate_plan_from_pix(payment_id)
    except PaymentAlreadyProcessedError:
        pass
    except (PaymentNotFoundError, PaymentExpiredError, PixError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"ok": True}
