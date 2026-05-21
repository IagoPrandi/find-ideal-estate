from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any
from uuid import UUID

import dramatiq
from contracts import JobType
from modules.jobs.events import publish_job_event
from modules.jobs.service import create_internal_job, get_job, update_job_execution_state
from modules.listings.cache import (
    compute_config_hash,
    create_cache_record,
    get_cache_record,
    mark_cache_prewarmed,
    normalize_search_location,
    transition_cache_status,
)
from modules.listings.models import ZoneCacheStatus
from modules.listings.platform_registry import get_platform_registry
from modules.listings.scrapers import ScraperDisallowedError, ScraperError
from modules.listings.scraping_lock import global_scraping_lock, scraping_lock
from modules.listings.search_requests import get_prewarm_targets
from workers.cancellation import check_cancellation
from .listings import (
    _persist_listings,
    _record_degradation_event,
    _record_success_rate_degradation_if_needed,
)
from workers.middleware import emit_stage_progress
from workers.queue import QUEUE_PREWARM
from workers.runtime import run_job_with_retry


DEFAULT_PLATFORM_BUDGET_SECONDS = 60.0


@dataclass(frozen=True)
class PrewarmTarget:
    search_location_normalized: str
    search_location_label: str
    search_location_type: str
    search_type: str
    usage_type: str
    zone_fingerprint: str | None
    platforms: tuple[str, ...]
    demand_count: int
    cache_age_hours: float


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _isoformat(value: datetime | None = None) -> str:
    return (value or _utcnow()).isoformat()


def _target_key(target: PrewarmTarget) -> str:
    return f"{target.search_type}:{target.usage_type}:{target.search_location_normalized}"


def _duration_ms(started_at_iso: object, finished_at_iso: str) -> int | None:
    if not isinstance(started_at_iso, str):
        return None
    try:
        started_at = datetime.fromisoformat(started_at_iso.replace("Z", "+00:00"))
        finished_at = datetime.fromisoformat(finished_at_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _ensure_target_statuses(ctx: dict[str, object]) -> dict[str, Any]:
    statuses = ctx.get("target_statuses")
    if not isinstance(statuses, dict):
        statuses = {}
        ctx["target_statuses"] = statuses
    return statuses


async def _set_target_status(
    job_id: UUID,
    ctx: dict[str, object],
    target: PrewarmTarget,
    status: str,
    **extra: Any,
) -> None:
    statuses = _ensure_target_statuses(ctx)
    key = _target_key(target)
    current = statuses.get(key) if isinstance(statuses.get(key), dict) else {}
    now = _isoformat()
    next_status = {
        **current,
        "status": status,
        "search_location_normalized": target.search_location_normalized,
        "search_location_label": target.search_location_label,
        "search_type": target.search_type,
        "usage_type": target.usage_type,
        "demand_count": target.demand_count,
        "platforms": list(target.platforms),
        "updated_at": now,
        **extra,
    }
    if status == "running" and "started_at" not in next_status:
        next_status["started_at"] = now
    if status in {"completed", "partial", "failed", "skipped"}:
        next_status["finished_at"] = now
        duration = _duration_ms(next_status.get("started_at"), now)
        if duration is not None:
            next_status["duration_ms"] = duration
    statuses[key] = next_status
    await _persist_job_context(job_id, ctx)


def _prewarm_zone_fingerprint(target: PrewarmTarget) -> str:
    if target.zone_fingerprint:
        return target.zone_fingerprint
    return f"prewarm:{target.search_type}:{target.search_location_normalized}"[:255]


def _platform_budget_seconds(ctx: dict[str, object]) -> float:
    raw_value = ctx.get("max_platform_duration_seconds")
    if raw_value is None:
        raw_value = ctx.get("max_address_duration_seconds")
    if raw_value is None:
        raw_value = os.getenv(
            "LISTINGS_PREWARM_MAX_ADDRESS_DURATION_SECONDS",
            str(int(DEFAULT_PLATFORM_BUDGET_SECONDS)),
        )
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        parsed = DEFAULT_PLATFORM_BUDGET_SECONDS
    return min(max(parsed, 0.01), DEFAULT_PLATFORM_BUDGET_SECONDS)


async def _load_job_context(job_id: UUID) -> dict[str, object]:
    job = await get_job(job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")
    return dict(job.result_ref or {})


async def _persist_job_context(job_id: UUID, ctx: dict[str, object]) -> None:
    await update_job_execution_state(job_id, result_ref=ctx)


async def _build_prewarm_targets(
    *,
    lookback_hours: int,
    limit: int,
    manual_targets: list[dict[str, Any]] | None = None,
) -> list[PrewarmTarget]:
    raw_targets = manual_targets or await get_prewarm_targets(
        lookback_hours=lookback_hours,
        limit=limit,
    )
    if not raw_targets:
        return []

    registry = get_platform_registry()
    platforms = tuple(registry.default_free_platforms())
    targets: list[PrewarmTarget] = []
    seen: set[tuple[str, str, str]] = set()
    for row in raw_targets:
        normalized = normalize_search_location(str(row.get("search_location_normalized") or ""))
        label = str(row.get("search_location_label") or "").strip()
        if not normalized or not label:
            continue
        key = (
            normalized,
            str(row.get("search_type") or "rent"),
            str(row.get("usage_type") or "residential"),
        )
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            PrewarmTarget(
                search_location_normalized=normalized,
                search_location_label=label,
                search_location_type=str(row.get("search_location_type") or "street"),
                search_type=str(row.get("search_type") or "rent"),
                usage_type=str(row.get("usage_type") or "residential"),
                zone_fingerprint=(
                    str(row.get("zone_fingerprint")) if row.get("zone_fingerprint") else None
                ),
                platforms=platforms,
                demand_count=int(row.get("demand_count") or 0),
                cache_age_hours=float(row.get("cache_age_hours") or 0.0),
            )
        )
    return targets


def build_manual_target_payloads(
    addresses: list[str],
    *,
    search_type: str = "rent",
    usage_type: str = "residential",
    search_location_type: str = "address",
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for address in addresses:
        label = str(address or "").strip()
        normalized = normalize_search_location(label)
        if not label or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        payloads.append(
            {
                "search_location_normalized": normalized,
                "search_location_label": label,
                "search_location_type": search_location_type,
                "search_type": search_type,
                "usage_type": usage_type,
                "zone_fingerprint": None,
                "demand_count": 1,
                "cache_age_hours": 1000000000.0,
                "manual": True,
            }
        )
    return payloads


async def enqueue_manual_listings_prewarm(
    addresses: list[str],
    *,
    search_type: str = "rent",
    usage_type: str = "residential",
    search_location_type: str = "address",
    max_address_duration_seconds: int | float | None = None,
) -> UUID:
    manual_targets = build_manual_target_payloads(
        addresses,
        search_type=search_type,
        usage_type=usage_type,
        search_location_type=search_location_type,
    )
    if not manual_targets:
        raise ValueError("At least one non-empty unique address is required")

    result = await create_internal_job(
        job_type=JobType.LISTINGS_PREWARM,
        current_stage="listings_prewarm",
        result_ref={
            "lookback_hours": 0,
            "limit": len(manual_targets),
            "trigger": "manual",
            "manual_targets": manual_targets,
            "max_address_duration_seconds": max_address_duration_seconds,
            "max_platform_duration_seconds": max_address_duration_seconds,
        },
    )
    return result.job.id


async def _open_platform_sessions(targets: list[PrewarmTarget]):
    registry = get_platform_registry()
    sessions: dict[tuple[str, str], object] = {}
    for target in targets:
        for platform in target.platforms:
            key = (platform, target.search_type)
            if key in sessions:
                continue
            scraper_cls = registry.scraper_class_for(platform)
            scraper = scraper_cls(
                search_address=target.search_location_label,
                search_type=target.search_type,
                platform_config=registry.scraper_config_for(platform),
            )
            await scraper.start_session()
            sessions[key] = scraper
    return sessions


async def _close_platform_sessions(sessions: dict[tuple[str, str], object]) -> None:
    for scraper in sessions.values():
        await scraper.close_session()


async def _process_target(
    *,
    job_id: UUID,
    ctx: dict[str, object],
    target: PrewarmTarget,
    platform_sessions: dict[tuple[str, str], object],
) -> bool:
    stage = "listings_prewarm"
    search_location_normalized = target.search_location_normalized
    ctx["search_location_normalized"] = search_location_normalized
    ctx["search_location_label"] = target.search_location_label
    ctx["zone_fingerprint"] = _prewarm_zone_fingerprint(target)
    ctx["active_target"] = {
        "search_location_normalized": search_location_normalized,
        "search_location_label": target.search_location_label,
        "search_type": target.search_type,
        "usage_type": target.usage_type,
        "demand_count": target.demand_count,
        "cache_age_hours": target.cache_age_hours,
        "max_platform_duration_seconds": _platform_budget_seconds(ctx),
    }
    await _persist_job_context(job_id, ctx)
    await _set_target_status(job_id, ctx, target, "running")

    async with global_scraping_lock(timeout_seconds=0) as global_acquired:
        if not global_acquired:
            await _set_target_status(
                job_id,
                ctx,
                target,
                "skipped",
                reason="global_scraping_lock_not_acquired",
            )
            return False

        async with scraping_lock(search_location_normalized, timeout_seconds=0) as acquired:
            if not acquired:
                await _set_target_status(
                    job_id,
                    ctx,
                    target,
                    "skipped",
                    reason="scraping_lock_not_acquired",
                )
                return False

            return await _process_target_with_locks(
                job_id=job_id,
                ctx=ctx,
                target=target,
                platform_sessions=platform_sessions,
                search_location_normalized=search_location_normalized,
                stage=stage,
            )


async def _process_target_with_locks(
    *,
    job_id: UUID,
    ctx: dict[str, object],
    target: PrewarmTarget,
    platform_sessions: dict[tuple[str, str], object],
    search_location_normalized: str,
    stage: str,
) -> bool:
        config_hash = compute_config_hash(
            target.search_type,
            target.usage_type,
            list(target.platforms),
        )
        cache_id = await create_cache_record(
            search_location_normalized,
            zone_fingerprint=_prewarm_zone_fingerprint(target),
            config_hash=config_hash,
        )
        cache = await get_cache_record(search_location_normalized)
        current_status = cache["status"] if cache else ZoneCacheStatus.PENDING
        if current_status == ZoneCacheStatus.SCRAPING:
            await transition_cache_status(
                cache_id,
                ZoneCacheStatus.SCRAPING,
                ZoneCacheStatus.CANCELLED_PARTIAL,
            )
            current_status = ZoneCacheStatus.CANCELLED_PARTIAL

        await transition_cache_status(cache_id, current_status, ZoneCacheStatus.SCRAPING)
        entered_scraping = True

        platforms_completed: list[str] = []
        platforms_failed: list[str] = []
        total_scraped = 0
        budget_seconds = _platform_budget_seconds(ctx)
        budget_exhausted = False
        try:
            for platform in target.platforms:
                await check_cancellation(job_id)
                scraper = platform_sessions[(platform, target.search_type)]
                try:
                    listings = await asyncio.wait_for(
                        scraper.scrape_in_session(target.search_location_label),
                        timeout=budget_seconds,
                    )
                    total_scraped += await _persist_listings(
                        listings,
                        platform,
                        target.search_type,
                        search_location_normalized,
                    )
                    platforms_completed.append(platform)
                except asyncio.TimeoutError:
                    budget_exhausted = True
                    platforms_failed.append(platform)
                    await publish_job_event(
                        job_id,
                        "prewarm.address.timeout",
                        stage=stage,
                        message=f"Prewarm platform budget exhausted while scraping {platform}",
                        payload_json={
                            "platform": platform,
                            "search_location_normalized": search_location_normalized,
                            "budget_seconds": budget_seconds,
                            "budget_scope": "platform",
                        },
                    )
                    continue
                except ScraperDisallowedError as exc:
                    platforms_failed.append(platform)
                    await _record_degradation_event(platform, "degraded", "robots_disallowed", 1.0)
                    await publish_job_event(
                        job_id,
                        "prewarm.platform.failed",
                        stage=stage,
                        message=f"{platform} blocked by robots during prewarm",
                        payload_json={
                            "platform": platform,
                            "search_location_normalized": search_location_normalized,
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        },
                    )
                except (ScraperError, Exception) as exc:  # noqa: BLE001
                    platforms_failed.append(platform)
                    await _record_degradation_event(platform, "degraded", "scraping_error", 1.0)
                    await publish_job_event(
                        job_id,
                        "prewarm.platform.failed",
                        stage=stage,
                        message=f"{platform} failed during prewarm",
                        payload_json={
                            "platform": platform,
                            "search_location_normalized": search_location_normalized,
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        },
                    )

            if platforms_failed and not platforms_completed:
                await transition_cache_status(
                    cache_id,
                    ZoneCacheStatus.SCRAPING,
                    ZoneCacheStatus.FAILED,
                    platforms_completed=platforms_completed,
                    platforms_failed=platforms_failed,
                    preliminary_count=total_scraped,
                )
                await _set_target_status(
                    job_id,
                    ctx,
                    target,
                    "failed",
                    platforms_completed=platforms_completed,
                    platforms_failed=platforms_failed,
                    total_count=total_scraped,
                    budget_exhausted=budget_exhausted,
                )
                return False

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
            )
            await mark_cache_prewarmed(cache_id)

            for platform in set(platforms_completed + platforms_failed):
                await _record_success_rate_degradation_if_needed(platform)

            await publish_job_event(
                job_id,
                "prewarm.target.completed",
                stage=stage,
                message=f"Prewarm completed for {target.search_location_label}",
                payload_json={
                    "search_location_normalized": search_location_normalized,
                    "search_location_label": target.search_location_label,
                    "platforms_completed": platforms_completed,
                    "platforms_failed": platforms_failed,
                    "total_count": total_scraped,
                    "status": new_status,
                    "budget_exhausted": budget_exhausted,
                },
            )
            await _set_target_status(
                job_id,
                ctx,
                target,
                "completed" if new_status == ZoneCacheStatus.COMPLETE else "partial",
                platforms_completed=platforms_completed,
                platforms_failed=platforms_failed,
                total_count=total_scraped,
                cache_status=new_status,
                budget_exhausted=budget_exhausted,
            )
            return True
        except asyncio.CancelledError:
            if entered_scraping:
                with suppress(Exception):
                    await transition_cache_status(
                        cache_id,
                        ZoneCacheStatus.SCRAPING,
                        ZoneCacheStatus.CANCELLED_PARTIAL,
                        platforms_completed=platforms_completed,
                        platforms_failed=platforms_failed,
                        preliminary_count=total_scraped,
                    )
            await _set_target_status(
                job_id,
                ctx,
                target,
                "failed",
                platforms_completed=platforms_completed,
                platforms_failed=platforms_failed,
                total_count=total_scraped,
                error_type="CancelledError",
            )
            raise
        except Exception as exc:
            if entered_scraping:
                with suppress(Exception):
                    await transition_cache_status(
                        cache_id,
                        ZoneCacheStatus.SCRAPING,
                        ZoneCacheStatus.CANCELLED_PARTIAL,
                        platforms_completed=platforms_completed,
                        platforms_failed=platforms_failed,
                        preliminary_count=total_scraped,
                    )
            await _set_target_status(
                job_id,
                ctx,
                target,
                "failed",
                platforms_completed=platforms_completed,
                platforms_failed=platforms_failed,
                total_count=total_scraped,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise


async def _listings_prewarm_step(job_id: UUID) -> None:
    stage = "listings_prewarm"
    ctx = await _load_job_context(job_id)
    lookback_hours = int(ctx.get("lookback_hours") or 24)
    limit = int(ctx.get("limit") or 100)
    manual_targets_raw = ctx.get("manual_targets")
    manual_targets = (
        manual_targets_raw if isinstance(manual_targets_raw, list) else None
    )
    targets = await _build_prewarm_targets(
        lookback_hours=lookback_hours,
        limit=limit,
        manual_targets=manual_targets,
    )

    ctx["started_at"] = ctx.get("started_at") or _isoformat()
    ctx["lookback_hours"] = lookback_hours
    ctx["limit"] = limit
    ctx["target_count_24h"] = len(targets)
    ctx["manual_target_count"] = len(manual_targets or [])
    ctx["status"] = "running"
    ctx["target_statuses"] = {
        _target_key(target): {
            "status": "queued",
            "search_location_normalized": target.search_location_normalized,
            "search_location_label": target.search_location_label,
            "search_type": target.search_type,
            "usage_type": target.usage_type,
            "demand_count": target.demand_count,
            "platforms": list(target.platforms),
            "updated_at": _isoformat(),
        }
        for target in targets
    }
    await _persist_job_context(job_id, ctx)

    if not targets:
        ctx["status"] = "success_empty"
        ctx["finished_at"] = _isoformat()
        ctx["coverage_rate"] = 1.0
        await _persist_job_context(job_id, ctx)
        await emit_stage_progress(
            job_id,
            stage=stage,
            progress_percent=100,
            message="Prewarm completed with no eligible addresses",
        )
        return

    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=5,
        message=f"Prewarming {len(targets)} searched addresses",
    )

    platform_sessions = await _open_platform_sessions(targets)
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        for index, target in enumerate(targets, start=1):
            await check_cancellation(job_id)
            progress_percent = 5 + int((index - 1) / max(len(targets), 1) * 90)
            await emit_stage_progress(
                job_id,
                stage=stage,
                progress_percent=progress_percent,
                message=f"Prewarming {target.search_location_label}",
            )
            try:
                processed = await _process_target(
                    job_id=job_id,
                    ctx=ctx,
                    target=target,
                    platform_sessions=platform_sessions,
                )
            except Exception as exc:
                failed_count += 1
                await _set_target_status(
                    job_id,
                    ctx,
                    target,
                    "failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                continue
            if processed:
                processed_count += 1
            else:
                skipped_count += 1
    finally:
        await _close_platform_sessions(platform_sessions)

    coverage_rate = processed_count / len(targets) if targets else 1.0
    if processed_count == 0 and failed_count:
        status = "failed"
    elif skipped_count or failed_count:
        status = "partial"
    else:
        status = "success"

    ctx["status"] = status
    ctx["processed_count"] = processed_count
    ctx["skipped_count"] = skipped_count
    ctx["failed_count"] = failed_count
    ctx["coverage_rate"] = coverage_rate
    ctx["finished_at"] = _isoformat()
    ctx["active_target"] = None
    await _persist_job_context(job_id, ctx)

    await publish_job_event(
        job_id,
        "prewarm.completed",
        stage=stage,
        message="Nightly listings prewarm finished",
        payload_json={
            "status": status,
            "processed_count": processed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "coverage_rate": coverage_rate,
            "target_count_24h": len(targets),
        },
    )
    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=100,
        message=f"Prewarm finished: {processed_count}/{len(targets)} addresses updated",
    )


@dramatiq.actor(queue_name=QUEUE_PREWARM, priority=5)
def listings_prewarm_actor(job_id: str) -> None:
    from workers.runner import init_worker_runtime, shutdown_worker_runtime

    parsed_job_id = UUID(job_id)
    async def _run() -> None:
        container = init_worker_runtime()
        try:
            await run_job_with_retry(
                parsed_job_id,
                JobType.LISTINGS_PREWARM,
                stage="listings_prewarm",
                execute_step=lambda: _listings_prewarm_step(parsed_job_id),
            )
        finally:
            await shutdown_worker_runtime(container)

    asyncio.run(_run())
