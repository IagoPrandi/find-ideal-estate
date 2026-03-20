from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from contracts import JobType
from workers.cancellation import JobCancelledException
from workers.middleware import JobHeartbeatMiddleware, JobStateMiddleware, serialize_error
from workers.retry_policy import JobRetryPolicy

HEARTBEAT_INTERVAL_SECONDS = 30


async def _heartbeat_loop(
    heartbeat: JobHeartbeatMiddleware,
    job_id: UUID,
    stop_signal: asyncio.Event,
) -> None:
    while not stop_signal.is_set():
        await heartbeat.beat(job_id)
        try:
            await asyncio.wait_for(stop_signal.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
        except TimeoutError:
            continue


async def run_job_with_retry(
    job_id: UUID,
    job_type: JobType,
    *,
    stage: str,
    execute_step: Callable[[], Awaitable[None]],
) -> None:
    state = JobStateMiddleware()
    heartbeat = JobHeartbeatMiddleware(ttl_seconds=120)
    retry_rule = JobRetryPolicy.for_job_type(job_type)
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat_loop(heartbeat, job_id, heartbeat_stop))

    await state.mark_running(job_id, stage=stage)

    try:
        for attempt in range(retry_rule.max_retries + 1):
            try:
                await execute_step()
                await state.mark_completed(job_id, stage=stage)
                return
            except JobCancelledException:
                await state.mark_cancelled_partial(job_id, stage=stage)
                return
            except Exception as exc:
                if attempt >= retry_rule.max_retries:
                    await state.mark_failed(job_id, stage=stage, error_message=serialize_error(exc))
                    return

                backoff_seconds = retry_rule.backoff_seconds[attempt]
                await state.mark_retrying(job_id, stage=stage, retry_in_seconds=backoff_seconds)
                await asyncio.sleep(backoff_seconds)
                await state.mark_pending(job_id, stage=stage)
                await state.mark_running(job_id, stage=stage)
    finally:
        heartbeat_stop.set()
        await heartbeat_task
        await heartbeat.clear(job_id)
