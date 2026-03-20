from __future__ import annotations

from uuid import UUID

from modules.jobs.service import get_job


class JobCancelledException(Exception):
    """Raised when a job has a cancel request and should stop cooperatively."""


async def check_cancellation(job_id: UUID) -> None:
    job = await get_job(job_id)
    if job is None:
        raise RuntimeError(f"Job {job_id} not found")
    if job.cancel_requested_at is not None:
        raise JobCancelledException(f"Job {job_id} cancellation requested")
