from __future__ import annotations

from zoneinfo import ZoneInfo

from contracts import JobType
from core.config import get_settings
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.db import get_engine
from core.redis import get_redis
from modules.jobs.events import publish_job_event
from modules.jobs.service import create_internal_job, update_job_execution_state
from sqlalchemy import text
from workers.middleware import JobHeartbeatMiddleware

WATCHDOG_INTERVAL_SECONDS = 60
WATCHDOG_STALE_SECONDS = 120
WATCHDOG_TIMEZONE = ZoneInfo("UTC")

_scheduler: AsyncIOScheduler | None = None


async def sweep_stale_running_jobs() -> None:
    engine = get_engine()
    redis = get_redis()

    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id,
                       result_ref->>'zone_fingerprint' AS zone_fingerprint,
                       result_ref->>'search_location_normalized' AS search_location_normalized
                FROM jobs
                WHERE state = 'running'
                """
            )
        )
        rows = result.mappings().all()

    for row in rows:
        job_id = row["id"]
        zone_fingerprint = row.get("zone_fingerprint")
        search_location_normalized = row.get("search_location_normalized")
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
            result_ref={
                "status": "cancelled_partial",
                "reason": "missing_heartbeat",
                "zone_fingerprint": zone_fingerprint,
            },
        )
        # Reset any zone_listing_caches that were left in 'scraping' state by the
        # cancelled job so that the next retry can start fresh.
        if search_location_normalized:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        UPDATE zone_listing_caches
                        SET status = 'cancelled_partial'
                        WHERE search_location_normalized = :search_location_normalized
                          AND status = 'scraping'
                        """
                    ),
                    {"search_location_normalized": search_location_normalized},
                )
        elif zone_fingerprint:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        UPDATE zone_listing_caches
                        SET status = 'cancelled_partial'
                        WHERE zone_fingerprint = :zone_fingerprint
                          AND status = 'scraping'
                        """
                    ),
                    {"zone_fingerprint": zone_fingerprint},
                )
        await publish_job_event(
            job_id,
            "job.failed",
            stage="watchdog",
            message="Watchdog cancelled stale running job",
            payload_json={"reason": "missing_heartbeat"},
        )


async def enqueue_nightly_listings_prewarm() -> None:
    settings = get_settings()
    await create_internal_job(
        job_type=JobType.LISTINGS_PREWARM,
        current_stage="listings_prewarm",
        result_ref={
            "lookback_hours": settings.listings_prewarm_lookback_hours,
            "limit": settings.listings_prewarm_limit,
            "trigger": "scheduler",
        },
    )


def start_watchdog() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=WATCHDOG_TIMEZONE)
    scheduler.add_job(
        sweep_stale_running_jobs,
        "interval",
        seconds=WATCHDOG_INTERVAL_SECONDS,
        max_instances=1,
        coalesce=True,
    )
    if settings.enable_listings_prewarm_scheduler:
        scheduler.add_job(
            enqueue_nightly_listings_prewarm,
            "cron",
            hour=settings.listings_prewarm_cron_hour,
            minute=settings.listings_prewarm_cron_minute,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800,
        )
    scheduler.start()
    _scheduler = scheduler


def stop_watchdog() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
