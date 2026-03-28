from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.db import get_engine
from core.redis import get_redis
from modules.jobs.events import publish_job_event
from modules.jobs.service import update_job_execution_state
from sqlalchemy import text
from workers.middleware import JobHeartbeatMiddleware

WATCHDOG_INTERVAL_SECONDS = 60
WATCHDOG_STALE_SECONDS = 120

_scheduler: AsyncIOScheduler | None = None


async def sweep_stale_running_jobs() -> None:
    engine = get_engine()
    redis = get_redis()

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id
                FROM jobs
                WHERE state = 'running'
                """
            )
        )
        rows = result.mappings().all()

    for row in rows:
        job_id = row["id"]
        heartbeat_key = JobHeartbeatMiddleware.heartbeat_key(job_id)
        heartbeat_exists = await redis.exists(heartbeat_key)
        if heartbeat_exists:
            continue

        await update_job_execution_state(
            job_id,
            state="cancelled_partial",
            current_stage="watchdog",
            error_message="missing_heartbeat",
            mark_finished=True,
            result_ref={"status": "cancelled_partial", "reason": "missing_heartbeat"},
        )
        # Reset any zone_listing_caches that were left in 'scraping' state by the
        # cancelled job so that the next retry can start fresh.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE zone_listing_caches
                    SET status = 'cancelled_partial'
                    WHERE zone_fingerprint = (
                        SELECT result_ref->>'zone_fingerprint'
                        FROM jobs WHERE id = :job_id
                    )
                    AND status = 'scraping'
                    """
                ),
                {"job_id": job_id},
            )
        await publish_job_event(
            job_id,
            "job.failed",
            stage="watchdog",
            message="Watchdog cancelled stale running job",
            payload_json={"reason": "missing_heartbeat"},
        )


def start_watchdog() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        sweep_stale_running_jobs,
        "interval",
        seconds=WATCHDOG_INTERVAL_SECONDS,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler


def stop_watchdog() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
