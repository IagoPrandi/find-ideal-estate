from __future__ import annotations

from uuid import UUID

from contracts import JobCancelAccepted, JobCreate, JobRead
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from modules.jobs.events import job_events_stream
from modules.jobs.service import create_job, get_job, request_job_cancellation

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job_endpoint(payload: JobCreate, response: Response) -> JobRead:
    result = await create_job(payload)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result.job


@router.get("/{job_id}", response_model=JobRead)
async def get_job_endpoint(job_id: UUID) -> JobRead:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobCancelAccepted, status_code=status.HTTP_202_ACCEPTED)
async def cancel_job_endpoint(job_id: UUID) -> JobCancelAccepted:
    cancellation = await request_job_cancellation(job_id)
    if cancellation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return cancellation


@router.get("/{job_id}/events")
async def job_events_endpoint(job_id: UUID, request: Request) -> StreamingResponse:
    job = await get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return StreamingResponse(
        job_events_stream(job_id, request, last_event_id=request.headers.get("last-event-id")),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )