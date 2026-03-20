from __future__ import annotations

import asyncio
from uuid import UUID

import dramatiq
from contracts import JobType
from workers.cancellation import check_cancellation
from workers.middleware import emit_stage_progress
from workers.queue import QUEUE_TRANSPORT
from workers.runtime import run_job_with_retry


async def _transport_search_step(job_id: UUID) -> None:
    stage = "transport_search"
    ticks = 6
    for idx in range(ticks):
        await check_cancellation(job_id)
        progress = int(((idx + 1) / ticks) * 100)
        await emit_stage_progress(
            job_id,
            stage=stage,
            progress_percent=progress,
            message=f"Transport search progress {progress}%",
        )
        await asyncio.sleep(0.5)


@dramatiq.actor(queue_name=QUEUE_TRANSPORT)
def transport_search_actor(job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    asyncio.run(
        run_job_with_retry(
            parsed_job_id,
            JobType.TRANSPORT_SEARCH,
            stage="transport_search",
            execute_step=lambda: _transport_search_step(parsed_job_id),
        )
    )
