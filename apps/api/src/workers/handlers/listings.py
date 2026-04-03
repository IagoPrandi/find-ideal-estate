"""Dramatiq handler for LISTINGS_SCRAPE jobs (M5.3 / M5.4).

Flow per execution:
    1. Load job context (zone_fingerprint, platforms, search params).
    2. Acquire Redis scraping lock for the normalized address and bail out if another worker holds it.
    3. Transition zone_listing_cache: pending -> scraping.
    4. For each platform: run Playwright scraper, upsert properties+ads+snapshots.
    5. Transition to partial/complete; emit SSE events.
    6. Release lock (via context manager finally).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import dramatiq
from contracts import JobType
from core.db import get_engine
from modules.jobs.events import publish_job_event
from modules.jobs.service import update_job_execution_state
from modules.listings.cache import (
    cache_is_usable,
    compute_config_hash,
    create_cache_record,
    get_cache_record,
    normalize_search_location,
    transition_cache_status,
)
from modules.listings.classification import infer_listing_usage_type_from_url
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


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _isoformat(value: datetime | None = None) -> str:
    return (value or _utcnow()).isoformat()


def _scraper_platform_timeout_seconds() -> float:
    raw_value = os.getenv("LISTINGS_SCRAPER_PLATFORM_TIMEOUT_SECONDS", "240")
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        return 240.0
    return max(parsed, 30.0)


def _duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    return int((finished_at - started_at).total_seconds() * 1000)


def _ensure_scrape_diagnostics(
    ctx: dict[str, Any],
    *,
    zone_fingerprint: str,
    search_address: str,
    search_type: str,
    usage_type: str,
    platforms: list[str],
) -> dict[str, Any]:
    diagnostics = ctx.get("scrape_diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
        ctx["scrape_diagnostics"] = diagnostics

    diagnostics.setdefault("started_at", _isoformat())
    diagnostics["zone_fingerprint"] = zone_fingerprint
    diagnostics["search_address"] = search_address
    diagnostics["search_type"] = search_type
    diagnostics["usage_type"] = usage_type
    diagnostics["platform_order"] = list(platforms)
    diagnostics.setdefault("status", "pending")
    diagnostics.setdefault("active_platform", None)

    lock_info = diagnostics.get("lock")
    if not isinstance(lock_info, dict):
        lock_info = {}
        diagnostics["lock"] = lock_info

    summary = diagnostics.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        diagnostics["summary"] = summary
    summary.setdefault("total_scraped", 0)
    summary.setdefault("platforms_completed", [])
    summary.setdefault("platforms_failed", [])

    platform_details = diagnostics.get("platforms")
    if not isinstance(platform_details, dict):
        platform_details = {}
        diagnostics["platforms"] = platform_details

    for index, platform in enumerate(platforms, start=1):
        entry = platform_details.get(platform)
        if not isinstance(entry, dict):
            entry = {}
            platform_details[platform] = entry
        entry.setdefault("sequence", index)
        entry.setdefault("status", "pending")

    return diagnostics


async def _persist_scrape_diagnostics(job_id: UUID, ctx: dict[str, Any]) -> None:
    diagnostics = ctx.get("scrape_diagnostics")
    if isinstance(diagnostics, dict):
        diagnostics["updated_at"] = _isoformat()
    await update_job_execution_state(job_id, result_ref=ctx)


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


async def _run_scraper_for_platform_with_timeout(
    platform: str,
    search_address: str,
    search_type: str,
) -> list[dict[str, Any]]:
    timeout_seconds = _scraper_platform_timeout_seconds()
    try:
        return await asyncio.wait_for(
            _run_scraper_for_platform(platform, search_address, search_type),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise ScraperError(
            f"Scraper timeout for platform '{platform}' after {int(timeout_seconds)}s"
        ) from exc


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
        usage_type = infer_listing_usage_type_from_url(listing.get("url"), bedrooms)

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
            usage_type=usage_type,
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
    search_location_normalized: str = normalize_search_location(
        ctx.get("search_location_normalized") or search_address
    )
    search_type: str = ctx.get("search_type", "rent")
    usage_type: str = ctx.get("usage_type", "residential")
    registry = get_platform_registry()
    raw_platforms: list[str] = ctx.get("platforms") or registry.default_free_platforms()
    platforms = registry.resolve_names(raw_platforms)
    config_hash = compute_config_hash(search_type, usage_type, platforms)
    diagnostics = _ensure_scrape_diagnostics(
        ctx,
        zone_fingerprint=zone_fingerprint,
        search_address=search_address,
        search_type=search_type,
        usage_type=usage_type,
        platforms=platforms,
    )

    if not zone_fingerprint or not search_address:
        raise ValueError("Missing zone_fingerprint or search_address in job context")

    force_refresh: bool = bool(ctx.get("force_refresh", False))
    diagnostics["status"] = "waiting_for_lock"
    await _persist_scrape_diagnostics(job_id, ctx)
    await check_cancellation(job_id)
    await emit_stage_progress(
        job_id, stage=stage, progress_percent=5,
        message="Acquiring scraping lock",
    )

    async with scraping_lock(search_location_normalized) as acquired:
        if not acquired:
            diagnostics["status"] = "lock_contention"
            diagnostics["lock"] = {
                "acquired": False,
                "contention": True,
                "checked_at": _isoformat(),
            }
            # Another worker is already scraping; re-open cache before exiting.
            cache_after_wait = await get_cache_record(search_location_normalized)
            cache_status = (
                cache_after_wait["status"] if cache_after_wait else ZoneCacheStatus.PENDING
            )
            if cache_is_usable(cache_after_wait) and not force_refresh:
                diagnostics["status"] = "cache_reopen"
                diagnostics["cache_status"] = cache_status
                await _persist_scrape_diagnostics(job_id, ctx)
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

            await _persist_scrape_diagnostics(job_id, ctx)
            await emit_stage_progress(
                job_id,
                stage=stage,
                progress_percent=100,
                message="Scraping already in progress by another worker",
            )
            return

        # Create or retrieve cache record
        cache_id = await create_cache_record(
            search_location_normalized,
            zone_fingerprint=zone_fingerprint,
            config_hash=config_hash,
        )
        cache = await get_cache_record(search_location_normalized)
        current_status = cache["status"] if cache else ZoneCacheStatus.PENDING
        diagnostics["lock"] = {
            "acquired": True,
            "contention": False,
            "acquired_at": _isoformat(),
        }
        diagnostics["cache_status_before"] = current_status
        diagnostics["status"] = "cache_ready"
        await _persist_scrape_diagnostics(job_id, ctx)

        if cache_is_usable(cache) and not force_refresh:
            diagnostics["status"] = "cache_hit"
            diagnostics["finished_at"] = _isoformat()
            diagnostics["total_duration_ms"] = _duration_ms(
                datetime.fromisoformat(diagnostics["started_at"]),
                _utcnow(),
            )
            await _persist_scrape_diagnostics(job_id, ctx)
            await emit_stage_progress(
                job_id, stage=stage, progress_percent=100,
                message="Cache hit - listings already available",
            )
            await publish_job_event(
                job_id,
                "listings.preliminary.ready",
                stage=stage,
                message="Listings available from cache",
                payload_json={"source": "cache", "zone_fingerprint": zone_fingerprint},
            )
            return

        if current_status == ZoneCacheStatus.SCRAPING:
            diagnostics["status"] = "recovering_stale_scraping"
            diagnostics["cache_status"] = ZoneCacheStatus.CANCELLED_PARTIAL
            await _persist_scrape_diagnostics(job_id, ctx)
            await publish_job_event(
                job_id,
                "listings.cache.recovered",
                stage=stage,
                message="Recovered stale scraping cache before restart",
                payload_json={
                    "zone_fingerprint": zone_fingerprint,
                    "from_status": ZoneCacheStatus.SCRAPING,
                    "to_status": ZoneCacheStatus.CANCELLED_PARTIAL,
                },
            )
            await transition_cache_status(
                cache_id,
                ZoneCacheStatus.SCRAPING,
                ZoneCacheStatus.CANCELLED_PARTIAL,
            )
            current_status = ZoneCacheStatus.CANCELLED_PARTIAL

        await transition_cache_status(cache_id, current_status, ZoneCacheStatus.SCRAPING)
        diagnostics["status"] = "scraping"
        diagnostics["cache_status"] = ZoneCacheStatus.SCRAPING
        await _persist_scrape_diagnostics(job_id, ctx)
        if ZoneCacheStatus.is_usable(current_status) and force_refresh:
            await emit_stage_progress(
                job_id,
                stage=stage,
                progress_percent=8,
                message="Revalidating stale listings cache",
            )
        await emit_stage_progress(
            job_id, stage=stage, progress_percent=10,
            message="Scraping listings...",
        )

        platforms_completed: list[str] = []
        platforms_failed: list[str] = []
        total_scraped = 0

        for idx, platform in enumerate(platforms):
            await check_cancellation(job_id)

            platform_details = diagnostics.get("platforms", {})
            platform_entry = platform_details.get(platform, {}) if isinstance(platform_details, dict) else {}
            platform_started_at = _utcnow()
            platform_entry["status"] = "scraping"
            platform_entry["started_at"] = platform_entry.get("started_at") or _isoformat(platform_started_at)
            platform_entry["scrape_started_at"] = _isoformat(platform_started_at)
            diagnostics["active_platform"] = platform
            diagnostics["status"] = "scraping"
            await _persist_scrape_diagnostics(job_id, ctx)
            await publish_job_event(
                job_id,
                "listings.platform.started",
                stage=stage,
                message=f"Scraping started for {platform}",
                payload_json={
                    "platform": platform,
                    "sequence": idx + 1,
                    "total_platforms": len(platforms),
                    "started_at": platform_entry["scrape_started_at"],
                },
            )

            pct = 10 + int((idx / len(platforms)) * 80)
            await emit_stage_progress(
                job_id, stage=stage, progress_percent=pct,
                message=f"Scraping {platform}...",
            )

            try:
                listings = await _run_scraper_for_platform_with_timeout(
                    platform,
                    search_address,
                    search_type,
                )
            except ScraperDisallowedError as exc:
                platforms_failed.append(platform)
                platform_finished_at = _utcnow()
                platform_entry["status"] = "failed"
                platform_entry["finished_at"] = _isoformat(platform_finished_at)
                platform_entry["total_duration_ms"] = _duration_ms(platform_started_at, platform_finished_at)
                platform_entry["error_phase"] = "scrape"
                platform_entry["error_type"] = type(exc).__name__
                platform_entry["error_message"] = str(exc)
                diagnostics["summary"]["platforms_failed"] = list(platforms_failed)
                diagnostics["summary"]["last_error"] = {
                    "platform": platform,
                    "phase": "scrape",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "failed_at": platform_entry["finished_at"],
                }
                await _persist_scrape_diagnostics(job_id, ctx)
                await publish_job_event(
                    job_id,
                    "listings.platform.failed",
                    stage=stage,
                    message=f"{platform} failed during scrape",
                    payload_json={
                        "platform": platform,
                        "phase": "scrape",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "failed_at": platform_entry["finished_at"],
                    },
                )
                await _record_degradation_event(
                    platform, "degraded", "robots_disallowed", 1.0
                )
                continue
            except (ScraperError, Exception) as exc:  # noqa: BLE001
                platforms_failed.append(platform)
                platform_finished_at = _utcnow()
                platform_entry["status"] = "failed"
                platform_entry["finished_at"] = _isoformat(platform_finished_at)
                platform_entry["total_duration_ms"] = _duration_ms(platform_started_at, platform_finished_at)
                platform_entry["error_phase"] = "scrape"
                platform_entry["error_type"] = type(exc).__name__
                platform_entry["error_message"] = str(exc)
                diagnostics["summary"]["platforms_failed"] = list(platforms_failed)
                diagnostics["summary"]["last_error"] = {
                    "platform": platform,
                    "phase": "scrape",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "failed_at": platform_entry["finished_at"],
                }
                await _persist_scrape_diagnostics(job_id, ctx)
                await publish_job_event(
                    job_id,
                    "listings.platform.failed",
                    stage=stage,
                    message=f"{platform} failed during scrape",
                    payload_json={
                        "platform": platform,
                        "phase": "scrape",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "failed_at": platform_entry["finished_at"],
                    },
                )
                await _record_degradation_event(
                    platform, "degraded", "scraping_error", 1.0
                )
                continue

            scrape_finished_at = _utcnow()
            platform_entry["scrape_finished_at"] = _isoformat(scrape_finished_at)
            platform_entry["scraped_count"] = len(listings)
            platform_entry["scrape_duration_ms"] = _duration_ms(platform_started_at, scrape_finished_at)
            await publish_job_event(
                job_id,
                "listings.platform.scraped",
                stage=stage,
                message=f"{platform} scrape finished",
                payload_json={
                    "platform": platform,
                    "scraped_count": len(listings),
                    "scrape_duration_ms": platform_entry["scrape_duration_ms"],
                    "scrape_finished_at": platform_entry["scrape_finished_at"],
                },
            )

            persist_started_at = _utcnow()
            platform_entry["status"] = "persisting"
            platform_entry["persist_started_at"] = _isoformat(persist_started_at)
            diagnostics["status"] = "persisting"
            diagnostics["active_platform"] = platform
            await _persist_scrape_diagnostics(job_id, ctx)
            await emit_stage_progress(
                job_id,
                stage=stage,
                progress_percent=min(95, pct + max(1, int(40 / max(len(platforms), 1)))),
                message=f"Persisting {platform}...",
            )

            try:
                n = await _persist_listings(listings, platform, search_type)
            except Exception as exc:  # noqa: BLE001
                platforms_failed.append(platform)
                persist_finished_at = _utcnow()
                platform_entry["status"] = "failed"
                platform_entry["persist_finished_at"] = _isoformat(persist_finished_at)
                platform_entry["finished_at"] = platform_entry["persist_finished_at"]
                platform_entry["persist_duration_ms"] = _duration_ms(persist_started_at, persist_finished_at)
                platform_entry["total_duration_ms"] = _duration_ms(platform_started_at, persist_finished_at)
                platform_entry["error_phase"] = "persist"
                platform_entry["error_type"] = type(exc).__name__
                platform_entry["error_message"] = str(exc)
                diagnostics["summary"]["platforms_failed"] = list(platforms_failed)
                diagnostics["summary"]["last_error"] = {
                    "platform": platform,
                    "phase": "persist",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "failed_at": platform_entry["finished_at"],
                }
                await _persist_scrape_diagnostics(job_id, ctx)
                await publish_job_event(
                    job_id,
                    "listings.platform.failed",
                    stage=stage,
                    message=f"{platform} failed during persist",
                    payload_json={
                        "platform": platform,
                        "phase": "persist",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "failed_at": platform_entry["finished_at"],
                    },
                )
                await _record_degradation_event(
                    platform, "degraded", "persist_error", 1.0
                )
                continue

            persist_finished_at = _utcnow()
            total_scraped += n
            platforms_completed.append(platform)
            platform_entry["status"] = "completed"
            platform_entry["persist_finished_at"] = _isoformat(persist_finished_at)
            platform_entry["finished_at"] = platform_entry["persist_finished_at"]
            platform_entry["persisted_count"] = n
            platform_entry["persist_duration_ms"] = _duration_ms(persist_started_at, persist_finished_at)
            platform_entry["total_duration_ms"] = _duration_ms(platform_started_at, persist_finished_at)
            diagnostics["summary"]["total_scraped"] = total_scraped
            diagnostics["summary"]["platforms_completed"] = list(platforms_completed)
            diagnostics["summary"]["platforms_failed"] = list(platforms_failed)
            diagnostics["active_platform"] = None
            await _persist_scrape_diagnostics(job_id, ctx)
            await publish_job_event(
                job_id,
                "listings.platform.persisted",
                stage=stage,
                message=f"{platform} persist finished",
                payload_json={
                    "platform": platform,
                    "scraped_count": len(listings),
                    "persisted_count": n,
                    "persist_duration_ms": platform_entry["persist_duration_ms"],
                    "total_duration_ms": platform_entry["total_duration_ms"],
                    "finished_at": platform_entry["finished_at"],
                },
            )

        if platforms_failed and not platforms_completed:
            diagnostics["status"] = "failed"
            diagnostics["finished_at"] = _isoformat()
            diagnostics["active_platform"] = None
            diagnostics["cache_status"] = ZoneCacheStatus.FAILED
            diagnostics["summary"]["platforms_completed"] = list(platforms_completed)
            diagnostics["summary"]["platforms_failed"] = list(platforms_failed)
            diagnostics["total_duration_ms"] = _duration_ms(
                datetime.fromisoformat(diagnostics["started_at"]),
                _utcnow(),
            )
            await _persist_scrape_diagnostics(job_id, ctx)
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
        diagnostics["status"] = str(new_status)
        diagnostics["finished_at"] = _isoformat()
        diagnostics["active_platform"] = None
        diagnostics["cache_status"] = str(new_status)
        diagnostics["summary"]["platforms_completed"] = list(platforms_completed)
        diagnostics["summary"]["platforms_failed"] = list(platforms_failed)
        diagnostics["summary"]["total_scraped"] = total_scraped
        diagnostics["total_duration_ms"] = _duration_ms(
            datetime.fromisoformat(diagnostics["started_at"]),
            _utcnow(),
        )
        await _persist_scrape_diagnostics(job_id, ctx)
        await transition_cache_status(
            cache_id,
            ZoneCacheStatus.SCRAPING,
            new_status,
            platforms_completed=platforms_completed,
            platforms_failed=platforms_failed,
            preliminary_count=total_scraped,
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
