from __future__ import annotations

from uuid import UUID

from api.routes.auth import get_optional_auth_context
from contracts import JobCancelAccepted, JobCreate, JobRead, JobType
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from modules.auth.service import get_accessible_journey
from modules.credits.service import InsufficientCreditsError, check_and_consume, consume_anonymous_credits
from modules.jobs.events import job_events_stream
from modules.jobs.service import create_job, get_job, request_job_cancellation
from modules.usage_restrictions.service import get_global_usage_restrictions_disabled

router = APIRouter(prefix="/jobs", tags=["jobs"])

_CREDIT_JOB_TYPES = {JobType.ZONE_GENERATION, JobType.ZONE_ENRICHMENT}


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job_endpoint(payload: JobCreate, response: Response, auth_context=Depends(get_optional_auth_context)) -> JobRead:
    journey = await get_accessible_journey(payload.journey_id, auth_context)
    if journey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found")
    if payload.job_type == JobType.LISTINGS_SCRAPE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nenhum plano libera scraping sob demanda.",
        )
    if payload.job_type in _CREDIT_JOB_TYPES:
        try:
            global_bypass = await get_global_usage_restrictions_disabled()
            if auth_context.user is None:
                if not global_bypass:
                    session_id = auth_context.anonymous_session_id or ""
                    await consume_anonymous_credits(session_id, 20)
            else:
                bypass = (
                    global_bypass
                    or auth_context.user.role == "proprietario"
                    or getattr(auth_context.user, "usage_restrictions_disabled", False)
                )
                await check_and_consume(auth_context.user.id, payload.job_type.value, bypass=bypass)
        except InsufficientCreditsError as exc:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Créditos insuficientes para executar esta etapa (necessário={exc.required}, saldo={exc.balance}).",
            ) from exc
    result = await create_job(payload)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result.job


@router.get("/{job_id}", response_model=JobRead)
async def get_job_endpoint(job_id: UUID, auth_context=Depends(get_optional_auth_context)) -> JobRead:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.journey_id is None or await get_accessible_journey(job.journey_id, auth_context) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobCancelAccepted, status_code=status.HTTP_202_ACCEPTED)
async def cancel_job_endpoint(job_id: UUID, auth_context=Depends(get_optional_auth_context)) -> JobCancelAccepted:
    job = await get_job(job_id)
    if job is None or job.journey_id is None or await get_accessible_journey(job.journey_id, auth_context) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    cancellation = await request_job_cancellation(job_id)
    if cancellation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return cancellation


@router.get("/{job_id}/events")
async def job_events_endpoint(job_id: UUID, request: Request, auth_context=Depends(get_optional_auth_context)) -> StreamingResponse:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.journey_id is None or await get_accessible_journey(job.journey_id, auth_context) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return StreamingResponse(
        job_events_stream(job_id, request, last_event_id=request.headers.get("last-event-id")),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
