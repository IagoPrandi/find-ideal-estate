from __future__ import annotations

import secrets
from typing import Annotated, Literal

from contracts import JobRead
from core.config import get_settings
from fastapi import APIRouter, Depends, Header, HTTPException, status
from modules.jobs.service import get_job
from pydantic import BaseModel, Field

router = APIRouter(prefix="/internal", tags=["internal"])


class ManualListingsPrewarmRequest(BaseModel):
    addresses: list[str] = Field(min_length=1)
    search_type: Literal["rent", "sale"] = "rent"
    usage_type: str = "residential"
    search_location_type: str = "address"
    max_address_duration_seconds: int = Field(default=60, gt=0, le=60)


def _extract_internal_token(
    authorization: str | None,
    x_internal_token: str | None,
) -> str | None:
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    if x_internal_token and x_internal_token.strip():
        return x_internal_token.strip()
    return None


async def require_internal_api_token(
    authorization: Annotated[str | None, Header()] = None,
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    expected_token = get_settings().internal_api_token
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_API_TOKEN nao configurado",
        )

    provided_token = _extract_internal_token(authorization, x_internal_token)
    if not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token interno ausente ou invalido",
        )


async def enqueue_manual_listings_prewarm(*args, **kwargs):
    from workers.handlers.prewarm import enqueue_manual_listings_prewarm as _enqueue_manual

    return await _enqueue_manual(*args, **kwargs)


@router.post(
    "/listings/prewarm/manual",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_token)],
)
async def trigger_manual_listings_prewarm(
    body: ManualListingsPrewarmRequest,
) -> JobRead:
    try:
        job_id = await enqueue_manual_listings_prewarm(
            body.addresses,
            search_type=body.search_type,
            usage_type=body.usage_type,
            search_location_type=body.search_location_type,
            max_address_duration_seconds=body.max_address_duration_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job = await get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Job interno nao foi persistido",
        )
    return job
