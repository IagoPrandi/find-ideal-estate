from __future__ import annotations

import json
from uuid import UUID

from contracts import JobState
from core.redis import get_redis
from modules.jobs.events import publish_job_event
from modules.jobs.service import update_job_execution_state


class JobStateMiddleware:
    async def mark_running(self, job_id: UUID, *, stage: str | None = None) -> None:
        await update_job_execution_state(
            job_id,
            state=JobState.RUNNING,
            current_stage=stage,
            mark_started=True,
        )
        await publish_job_event(job_id, "job.started", stage=stage, message="Job started")

    async def mark_retrying(
        self,
        job_id: UUID,
        *,
        stage: str | None = None,
        retry_in_seconds: int = 0,
    ) -> None:
        await update_job_execution_state(job_id, state=JobState.RETRYING, current_stage=stage)
        await publish_job_event(
            job_id,
            "job.retrying",
            stage=stage,
            message=f"Retrying in {retry_in_seconds}s",
            payload_json={"retry_in_seconds": retry_in_seconds},
        )

    async def mark_pending(self, job_id: UUID, *, stage: str | None = None) -> None:
        await update_job_execution_state(job_id, state=JobState.PENDING, current_stage=stage)
        await publish_job_event(job_id, "job.pending", stage=stage, message="Job moved to pending")

    async def mark_completed(self, job_id: UUID, *, stage: str | None = None) -> None:
        await update_job_execution_state(
            job_id,
            state=JobState.COMPLETED,
            current_stage=stage,
            progress_percent=100,
            mark_finished=True,
        )
        await publish_job_event(job_id, "job.completed", stage=stage, message="Job completed")

    async def mark_failed(
        self,
        job_id: UUID,
        *,
        stage: str | None = None,
        error_message: str | None = None,
    ) -> None:
        await update_job_execution_state(
            job_id,
            state=JobState.FAILED,
            current_stage=stage,
            error_message=error_message,
            mark_finished=True,
        )
        await publish_job_event(
            job_id,
            "job.failed",
            stage=stage,
            message=error_message or "Job failed",
        )

    async def mark_cancelled_partial(self, job_id: UUID, *, stage: str | None = None) -> None:
        await update_job_execution_state(
            job_id,
            state=JobState.CANCELLED_PARTIAL,
            current_stage=stage,
            mark_finished=True,
            result_ref={"status": "cancelled_partial"},
        )
        await publish_job_event(
            job_id,
            "job.cancelled",
            stage=stage,
            message="Job cancelled by request",
        )


class JobHeartbeatMiddleware:
    def __init__(self, ttl_seconds: int = 120):
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def heartbeat_key(job_id: UUID) -> str:
        return f"job_heartbeat:{job_id}"

    async def beat(self, job_id: UUID) -> None:
        redis = get_redis()
        await redis.set(self.heartbeat_key(job_id), "1", ex=self._ttl_seconds)

    async def clear(self, job_id: UUID) -> None:
        redis = get_redis()
        await redis.delete(self.heartbeat_key(job_id))


async def emit_stage_progress(
    job_id: UUID,
    *,
    stage: str,
    progress_percent: int,
    message: str | None = None,
) -> None:
    await update_job_execution_state(job_id, current_stage=stage, progress_percent=progress_percent)
    payload = {"progress_percent": progress_percent}
    await publish_job_event(
        job_id,
        "job.stage.progress",
        stage=stage,
        message=message,
        payload_json=payload,
    )


def serialize_error(exc: Exception) -> str:
    return json.dumps({"error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=True)
