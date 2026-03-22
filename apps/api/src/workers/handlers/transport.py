from __future__ import annotations

import asyncio
from uuid import UUID

import dramatiq
from contracts import JobType
from core.container import get_container
from workers.cancellation import check_cancellation
from workers.middleware import emit_stage_progress
from workers.queue import QUEUE_TRANSPORT
from workers.runtime import run_job_with_retry


async def run_transport_search_for_job(job_id: UUID) -> int:
    transport_service = get_container().transport_service()
    return await transport_service.run_transport_search_for_job(job_id)


async def _transport_search_step(job_id: UUID) -> None:
    stage = "transport_search"
    await check_cancellation(job_id)
    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=10,
        message="Loading journey context",
    )

    await check_cancellation(job_id)
    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=40,
        message="Querying transport points near reference",
    )
    await asyncio.sleep(0.5)
    await run_transport_search_for_job(job_id)

    await check_cancellation(job_id)
    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=100,
        message="Transport points persisted",
    )


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
