"""Dramatiq handler for LISTINGS_SCRAPE jobs (M5.3 / M5.4).

Flow per execution:
    1. Load job context (zone_fingerprint, config_hash, platforms, search params).
    2. Acquire Redis scraping lock — bail out (re-read cache) if another worker holds it.
    3. Transition zone_listing_cache: pending → scraping.
    4. For each platform: run Playwright scraper, upsert properties+ads+snapshots.
    5. Transition to partial/complete; emit SSE events.
    6. Release lock (via context manager finally).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import dramatiq
from contracts import JobType
from core.db import get_engine
from modules.jobs.events import publish_job_event
from modules.listings.cache import (
    compute_config_hash,
    create_cache_record,
    get_cache_record,
    transition_cache_status,
)
from modules.listings.dedup import compute_property_fingerprint, upsert_property_and_ad
from modules.listings.models import (
    PreliminaryResultThresholds,
    ZoneCacheStatus,
)
from modules.listings.platform_registry import get_platform_registry
from modules.listings.price_rollups import compute_and_upsert_rollup, purge_old_rollups
from modules.listings.scrapers import ScraperDisallowedError, ScraperError
from modules.listings.scraping_lock import scraping_lock
from sqlalchemy import text
from workers.cancellation import check_cancellation
from workers.middleware import emit_stage_progress
from workers.queue import QUEUE_SCRAPE_BROWSER
from workers.runtime import run_job_with_retry


async def _load_job_context(job_id: UUID) -> dict[str, Any]:
    """Fetch job details and the associated journey+zone context."""
    engine = get_engine()
    async with engine.connect() as conn:
        job_row = await conn.execute(
            text(
                """
                SELECT j.id, j.journey_id, j.result_ref
                FROM jobs j
                WHERE j.id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        job = job_row.mappings().first()
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        result_ref: dict[str, Any] = job["result_ref"] or {}
        return result_ref


async def _record_degradation_event(
    platform: str,
    event_type: str,
    trigger_metric: str,
    metric_value: float,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO scraping_degradation_events
                    (platform, event_type, trigger_metric, metric_value)
                VALUES (:platform, :event_type, :trigger_metric, :metric_value)
                """
            ),
            {
                "platform": platform,
                "event_type": event_type,
                "trigger_metric": trigger_metric,
                "metric_value": metric_value,
            },
        )


async def _platform_success_rate_24h(platform: str) -> tuple[int, int, float | None]:
    """
    Compute 24h scraper success rate for a platform using cache outcomes.

    A cache row counts as:
    - success when platform appears in `platforms_completed`
    - failure when platform appears in `platforms_failed`
    """
    engine = get_engine()
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                """
                SELECT
                    SUM(CASE WHEN :platform = ANY(COALESCE(platforms_completed, '{}'::text[]))
                             THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN :platform = ANY(COALESCE(platforms_failed, '{}'::text[]))
                             THEN 1 ELSE 0 END) AS failed_count
                FROM zone_listing_caches
                WHERE created_at >= (now() - interval '24 hours')
                  AND (
                    :platform = ANY(COALESCE(platforms_completed, '{}'::text[]))
                    OR :platform = ANY(COALESCE(platforms_failed, '{}'::text[]))
                  )
                """
            ),
            {"platform": platform},
        )
        stats = row.mappings().first() or {}

    success_count = int(stats.get("success_count") or 0)
    failed_count = int(stats.get("failed_count") or 0)
    total = success_count + failed_count
    if total == 0:
        return success_count, failed_count, None
    return success_count, failed_count, (success_count / total)


async def _record_success_rate_degradation_if_needed(platform: str) -> None:
    """Create degradation event when platform success_rate(24h) drops below 85%."""
    _, _, success_rate = await _platform_success_rate_24h(platform)
    if success_rate is None:
        return
    if success_rate < 0.85:
        await _record_degradation_event(
            platform=platform,
            event_type="degraded",
            trigger_metric="success_rate_24h",
            metric_value=success_rate,
        )


async def _run_scraper_for_platform(
    platform: str,
    search_address: str,
    search_type: str,
) -> list[dict[str, Any]]:
    registry = get_platform_registry()
    canonical = registry.resolve_name(platform)
    scraper_cls = registry.scraper_class_for(canonical)
    scraper = scraper_cls(
        search_address=search_address,
        search_type=search_type,
        platform_config=registry.scraper_config_for(canonical),
    )
    return await scraper.scrape()


async def _persist_listings(
    listings: list[dict[str, Any]],
    platform: str,
    search_type: str,
) -> int:
    """Upsert all listings. Returns count persisted."""
    count = 0
    for listing in listings:
        address = listing.get("address")
        lat = listing.get("lat")
        lon = listing.get("lon")
        area_m2 = listing.get("area_m2")
        bedrooms = listing.get("bedrooms")

        fingerprint = compute_property_fingerprint(
            address_normalized=address,
            lat=lat,
            lon=lon,
            area_m2=area_m2,
            bedrooms=bedrooms,
        )

        price_raw = listing.get("price_brl")
        price = Decimal(str(price_raw)) if price_raw is not None else None
        condo_raw = listing.get("condo_fee_brl")
        condo_fee = Decimal(str(condo_raw)) if condo_raw is not None else None
        iptu_raw = listing.get("iptu_brl")
        iptu = Decimal(str(iptu_raw)) if iptu_raw is not None else None

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address,
            lat=lat,
            lon=lon,
            area_m2=area_m2,
            bedrooms=bedrooms,
            bathrooms=listing.get("bathrooms"),
            parking=listing.get("parking"),
            usage_type="residential",
            platform=platform,
            platform_listing_id=listing["platform_listing_id"],
            url=listing.get("url"),
            advertised_usage_type=search_type,
            price=price,
            condo_fee=condo_fee,
            iptu=iptu,
            raw_payload=listing,
        )
        count += 1
    return count


async def _listings_scrape_step(job_id: UUID) -> None:
    stage = "listings_scrape"

    # -- Load job context from result_ref stored by the API ------------------
    ctx = await _load_job_context(job_id)
    zone_fingerprint: str = ctx.get("zone_fingerprint", "")
    search_address: str = ctx.get("search_address", "")
    search_type: str = ctx.get("search_type", "rent")
    usage_type: str = ctx.get("usage_type", "residential")
    registry = get_platform_registry()
    raw_platforms: list[str] = ctx.get("platforms") or registry.default_free_platforms()
    platforms = registry.resolve_names(raw_platforms)
    config_hash = compute_config_hash(search_type, usage_type, platforms)

    if not zone_fingerprint or not search_address:
        raise ValueError("Missing zone_fingerprint or search_address in job context")

    await check_cancellation(job_id)
    await emit_stage_progress(
        job_id, stage=stage, progress_percent=5,
        message="Acquiring scraping lock",
    )

    async with scraping_lock(zone_fingerprint, config_hash) as acquired:
        if not acquired:
            # Another worker is already scraping; re-open cache before exiting.
            cache_after_wait = await get_cache_record(zone_fingerprint, config_hash)
            cache_status = (
                cache_after_wait["status"] if cache_after_wait else ZoneCacheStatus.PENDING
            )
            if ZoneCacheStatus.is_usable(cache_status):
                await publish_job_event(
                    job_id,
                    "listings.preliminary.ready",
                    stage=stage,
                    message="Listings became available while waiting for scraping lock",
                    payload_json={
                        "source": "cache_reopen",
                        "zone_fingerprint": zone_fingerprint,
                        "status": cache_status,
                    },
                )
                await emit_stage_progress(
                    job_id,
                    stage=stage,
                    progress_percent=100,
                    message="Listings available after waiting for lock",
                )
                return

            await emit_stage_progress(
                job_id,
                stage=stage,
                progress_percent=100,
                message="Scraping already in progress by another worker",
            )
            return

        # Create or retrieve cache record
        cache_id = await create_cache_record(zone_fingerprint, config_hash)
        cache = await get_cache_record(zone_fingerprint, config_hash)
        current_status = cache["status"] if cache else ZoneCacheStatus.PENDING

        if ZoneCacheStatus.is_usable(current_status):
            await emit_stage_progress(
                job_id, stage=stage, progress_percent=100,
                message="Cache hit \u2014 listings already available",
            )
            await publish_job_event(
                job_id,
                "listings.preliminary.ready",
                stage=stage,
                message="Listings available from cache",
                payload_json={"source": "cache", "zone_fingerprint": zone_fingerprint},
            )
            return

        await transition_cache_status(cache_id, current_status, ZoneCacheStatus.SCRAPING)
        await emit_stage_progress(
            job_id, stage=stage, progress_percent=10,
            message="Scraping listings\u2026",
        )

        platforms_completed: list[str] = []
        platforms_failed: list[str] = []
        total_scraped = 0

        for idx, platform in enumerate(platforms):
            await check_cancellation(job_id)

            pct = 10 + int((idx / len(platforms)) * 80)
            await emit_stage_progress(
                job_id, stage=stage, progress_percent=pct,
                message=f"Scraping {platform}…",
            )

            try:
                listings = await _run_scraper_for_platform(platform, search_address, search_type)
                n = await _persist_listings(listings, platform, search_type)
                total_scraped += n
                platforms_completed.append(platform)

            except ScraperDisallowedError:
                platforms_failed.append(platform)
                await _record_degradation_event(
                    platform, "degraded", "robots_disallowed", 1.0
                )
            except (ScraperError, Exception):  # noqa: BLE001
                platforms_failed.append(platform)
                await _record_degradation_event(
                    platform, "degraded", "scraping_error", 1.0
                )

        # Determine TTL for cache
        ttl_hours = (
            PreliminaryResultThresholds.MAX_CACHE_AGE_RENTAL
            if search_type == "rent"
            else PreliminaryResultThresholds.MAX_CACHE_AGE_SALE
        )
        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=ttl_hours)

        if platforms_failed and not platforms_completed:
            await transition_cache_status(
                cache_id,
                ZoneCacheStatus.SCRAPING,
                ZoneCacheStatus.FAILED,
                platforms_completed=platforms_completed,
                platforms_failed=platforms_failed,
            )
            raise ScraperError(f"All platforms failed for zone {zone_fingerprint}")

        new_status = (
            ZoneCacheStatus.COMPLETE if not platforms_failed else ZoneCacheStatus.PARTIAL
        )
        await transition_cache_status(
            cache_id,
            ZoneCacheStatus.SCRAPING,
            new_status,
            platforms_completed=platforms_completed,
            platforms_failed=platforms_failed,
            preliminary_count=total_scraped,
            expires_at=expires_at,
        )

        for platform in set(platforms_completed + platforms_failed):
            await _record_success_rate_degradation_if_needed(platform)

        meets_threshold = (
            total_scraped >= PreliminaryResultThresholds.MIN_PROPERTIES_RENTAL
            if search_type == "rent"
            else total_scraped >= PreliminaryResultThresholds.MIN_PROPERTIES_SALE
        )

        if meets_threshold:
            await publish_job_event(
                job_id,
                "listings.preliminary.ready",
                stage=stage,
                message=f"{total_scraped} listings scraped and cached",
                payload_json={
                    "source": "fresh_scrape",
                    "total_count": total_scraped,
                    "platforms_completed": platforms_completed,
                    "platforms_failed": platforms_failed,
                    "zone_fingerprint": zone_fingerprint,
                    "expires_at": expires_at.isoformat(),
                },
            )

        await emit_stage_progress(
            job_id, stage=stage, progress_percent=100,
            message=(
                f"Completed: {total_scraped} listings "
                f"from {len(platforms_completed)} platforms"
            ),
        )

        # M6.1: trigger rollup on ingest (non-blocking; errors are logged, not re-raised)
        if platforms_completed:
            try:
                engine = get_engine()
                async with engine.begin() as _conn:
                    await compute_and_upsert_rollup(_conn, zone_fingerprint, search_type)
                    await purge_old_rollups(_conn)
            except Exception:  # noqa: BLE001
                pass  # rollup failure must not break scraping job


@dramatiq.actor(queue_name=QUEUE_SCRAPE_BROWSER)
def listings_scrape_actor(job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    asyncio.run(
        run_job_with_retry(
            parsed_job_id,
            JobType.LISTINGS_SCRAPE,
            stage="listings_scrape",
            execute_step=lambda: _listings_scrape_step(parsed_job_id),
        )
    )
