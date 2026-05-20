from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import UUID

from api.routes.admin_common import require_developer
from contracts import (
    AdminRunNowResponse,
    AdminScrapingBatchRead,
    AdminScrapingBatchesRead,
    AdminScrapingOverviewRead,
    AdminScrapingQueueAddRequest,
    AdminScrapingQueueItemRead,
    AdminScrapingQueueMutationRead,
    AdminScrapingQueueRead,
    JobCancelAccepted,
    JobRead,
    JobState,
    JobType,
)
from core.config import get_settings
from core.db import get_engine
from fastapi import APIRouter, Depends, HTTPException, Query, status
from modules.jobs.service import create_internal_job, get_job, request_job_cancellation
from modules.listings.cache import normalize_search_location
from modules.listings.search_requests import get_prewarm_targets
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

router = APIRouter(prefix="/admin/scraping", tags=["admin"])

_ACTIVE_JOB_STATES = (JobState.PENDING.value, JobState.RUNNING.value, JobState.RETRYING.value)
_MAX_ADMIN_QUEUE_ADDRESSES = 100


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _row_to_job(row: RowMapping) -> JobRead:
    return JobRead(
        id=row["id"],
        journey_id=row["journey_id"],
        job_type=row["job_type"],
        state=row["state"],
        progress_percent=row["progress_percent"],
        current_stage=row["current_stage"],
        cancel_requested_at=row["cancel_requested_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        worker_id=row["worker_id"],
        result_ref=row["result_ref"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        created_at=row["created_at"],
    )


def _batch_from_job(job: JobRead) -> AdminScrapingBatchRead:
    ref = job.result_ref if isinstance(job.result_ref, dict) else {}
    target_statuses = ref.get("target_statuses")
    if not isinstance(target_statuses, dict):
        target_statuses = {}

    job_metrics = ref.get("job_metrics") if isinstance(ref.get("job_metrics"), dict) else {}
    duration_ms = job_metrics.get("duration_ms")
    if not isinstance(duration_ms, int):
        duration_ms = None

    target_count = ref.get("target_count_24h")
    if not isinstance(target_count, int):
        target_count = ref.get("manual_target_count")
    if not isinstance(target_count, int):
        target_count = len(target_statuses)

    return AdminScrapingBatchRead(
        job=job,
        trigger=str(ref.get("trigger")) if ref.get("trigger") is not None else None,
        status=str(ref.get("status")) if ref.get("status") is not None else None,
        target_count=target_count,
        processed_count=int(ref.get("processed_count") or 0),
        skipped_count=int(ref.get("skipped_count") or 0),
        failed_count=int(ref.get("failed_count") or 0),
        duration_ms=duration_ms,
        target_statuses=target_statuses,
    )


async def _list_prewarm_jobs(*, active_only: bool = False, limit: int = 20, offset: int = 0) -> tuple[list[JobRead], int]:
    params: dict[str, Any] = {
        "job_type": JobType.LISTINGS_PREWARM.value,
        "limit": limit,
        "offset": offset,
    }
    where = ["job_type = :job_type", "journey_id IS NULL"]
    if active_only:
        where.append("state IN ('pending', 'running', 'retrying')")

    where_sql = " AND ".join(where)
    engine = get_engine()
    async with engine.connect() as conn:
        count_result = await conn.execute(text(f"SELECT count(*) FROM jobs WHERE {where_sql}"), params)
        rows = await conn.execute(
            text(
                f"""
                SELECT id, journey_id, job_type, state, progress_percent, current_stage,
                       cancel_requested_at, started_at, finished_at, worker_id,
                       result_ref, error_code, error_message, created_at
                FROM jobs
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        return [_row_to_job(row) for row in rows.mappings().all()], int(count_result.scalar_one())


async def _get_active_prewarm_job() -> JobRead | None:
    jobs, _ = await _list_prewarm_jobs(active_only=True, limit=1, offset=0)
    return jobs[0] if jobs else None


def _next_run(settings) -> tuple[datetime | None, int | None]:
    if not settings.enable_listings_prewarm_scheduler:
        return None, None
    now = _utc_now()
    next_run = now.replace(
        hour=settings.listings_prewarm_cron_hour,
        minute=settings.listings_prewarm_cron_minute,
        second=0,
        microsecond=0,
    )
    if next_run <= now:
        next_run = next_run + timedelta(days=1)
    return next_run, max(0, int((next_run - now).total_seconds()))


async def _queue_items(*, lookback_hours: int, limit: int) -> list[AdminScrapingQueueItemRead]:
    rows = await get_prewarm_targets(lookback_hours=lookback_hours, limit=limit)
    return [
        AdminScrapingQueueItemRead(
            search_location_normalized=str(row.get("search_location_normalized") or ""),
            search_location_label=str(row.get("search_location_label") or ""),
            search_location_type=str(row.get("search_location_type") or "address"),
            search_type=str(row.get("search_type") or "rent"),
            usage_type=str(row.get("usage_type") or "residential"),
            demand_count=int(row.get("demand_count") or 0),
            last_requested_at=row.get("last_requested_at"),
            zone_fingerprint=(str(row.get("zone_fingerprint")) if row.get("zone_fingerprint") else None),
            cache_status=(str(row.get("cache_status")) if row.get("cache_status") else None),
            cache_age_hours=(float(row.get("cache_age_hours")) if row.get("cache_age_hours") is not None else None),
            last_prewarmed_at=row.get("last_prewarmed_at"),
            scraped_at=row.get("scraped_at"),
        )
        for row in rows
    ]


@router.get("/overview", response_model=AdminScrapingOverviewRead)
async def get_scraping_overview(_ctx=Depends(require_developer)) -> AdminScrapingOverviewRead:
    settings = get_settings()
    next_run_at, seconds_until_next_run = _next_run(settings)
    active_job = await _get_active_prewarm_job()
    latest_jobs, _ = await _list_prewarm_jobs(limit=1)
    queue = await _queue_items(
        lookback_hours=settings.listings_prewarm_lookback_hours,
        limit=settings.listings_prewarm_limit,
    )
    return AdminScrapingOverviewRead(
        scheduler_enabled=settings.enable_listings_prewarm_scheduler,
        cron_hour=settings.listings_prewarm_cron_hour,
        cron_minute=settings.listings_prewarm_cron_minute,
        timezone="UTC",
        next_run_at=next_run_at,
        seconds_until_next_run=seconds_until_next_run,
        lookback_hours=settings.listings_prewarm_lookback_hours,
        limit=settings.listings_prewarm_limit,
        active_job=active_job,
        latest_job=latest_jobs[0] if latest_jobs else None,
        queue_count=len(queue),
    )


@router.get("/queue", response_model=AdminScrapingQueueRead)
async def get_scraping_queue(
    limit: int = Query(default=100, ge=1, le=100),
    lookback_hours: int | None = Query(default=None, ge=1, le=168),
    _ctx=Depends(require_developer),
) -> AdminScrapingQueueRead:
    settings = get_settings()
    effective_lookback = lookback_hours or settings.listings_prewarm_lookback_hours
    items = await _queue_items(lookback_hours=effective_lookback, limit=limit)
    return AdminScrapingQueueRead(
        items=items,
        total_count=len(items),
        limit=limit,
        lookback_hours=effective_lookback,
    )


@router.post("/queue", response_model=AdminScrapingQueueMutationRead, status_code=status.HTTP_201_CREATED)
async def add_scraping_queue_items(
    payload: AdminScrapingQueueAddRequest,
    _ctx=Depends(require_developer),
) -> AdminScrapingQueueMutationRead:
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for address in payload.addresses[:_MAX_ADMIN_QUEUE_ADDRESSES]:
        label = address.strip()
        normalized = normalize_search_location(label)
        if not label or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append({"label": label, "normalized": normalized})

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe ao menos um endereço válido.")

    engine = get_engine()
    async with engine.begin() as conn:
        for row in rows:
            await conn.execute(
                text(
                    """
                    INSERT INTO listing_search_requests (
                        journey_id, user_id, session_id, zone_fingerprint,
                        search_location_normalized, search_location_label,
                        search_location_type, search_type, usage_type,
                        platforms_hash, result_source, requested_at
                    ) VALUES (
                        NULL, NULL, NULL, :zone_fingerprint,
                        :normalized, :label,
                        :search_location_type, :search_type, :usage_type,
                        :platforms_hash, 'admin_manual', now()
                    )
                    """
                ),
                {
                    "zone_fingerprint": f"admin:{row['normalized']}"[:255],
                    "normalized": row["normalized"],
                    "label": row["label"],
                    "search_location_type": payload.search_location_type,
                    "search_type": payload.search_type,
                    "usage_type": payload.usage_type,
                    "platforms_hash": f"admin:{payload.search_type}:{payload.usage_type}",
                },
            )
    return AdminScrapingQueueMutationRead(status="added", affected_count=len(rows))


@router.delete("/queue/{normalized}", response_model=AdminScrapingQueueMutationRead)
async def remove_scraping_queue_item(
    normalized: str,
    lookback_hours: int | None = Query(default=None, ge=1, le=168),
    _ctx=Depends(require_developer),
) -> AdminScrapingQueueMutationRead:
    settings = get_settings()
    effective_lookback = lookback_hours or settings.listings_prewarm_lookback_hours
    normalized_value = normalize_search_location(normalized)
    if not normalized_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Endereço normalizado inválido.")
    since = _utc_now() - timedelta(hours=effective_lookback)
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                DELETE FROM listing_search_requests
                WHERE search_location_normalized = :normalized
                  AND requested_at >= :since
                """
            ),
            {"normalized": normalized_value, "since": since},
        )
    return AdminScrapingQueueMutationRead(status="removed", affected_count=int(result.rowcount or 0))


@router.get("/batches", response_model=AdminScrapingBatchesRead)
async def list_scraping_batches(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _ctx=Depends(require_developer),
) -> AdminScrapingBatchesRead:
    jobs, total = await _list_prewarm_jobs(limit=limit, offset=offset)
    return AdminScrapingBatchesRead(
        items=[_batch_from_job(job) for job in jobs],
        total_count=total,
        limit=limit,
        offset=offset,
    )


@router.get("/batches/{job_id}", response_model=AdminScrapingBatchRead)
async def get_scraping_batch(job_id: UUID, _ctx=Depends(require_developer)) -> AdminScrapingBatchRead:
    job = await get_job(job_id)
    if job is None or job.job_type != JobType.LISTINGS_PREWARM or job.journey_id is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batelada não encontrada.")
    return _batch_from_job(job)


@router.post("/batches/run-now", response_model=AdminRunNowResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_scraping_now(_ctx=Depends(require_developer)) -> AdminRunNowResponse:
    active_job = await _get_active_prewarm_job()
    if active_job is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma batelada em execução.")

    settings = get_settings()
    rows = await get_prewarm_targets(
        lookback_hours=settings.listings_prewarm_lookback_hours,
        limit=settings.listings_prewarm_limit,
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A fila atual não tem endereços elegíveis.")

    manual_targets = json.loads(json.dumps(rows, default=str))
    result = await create_internal_job(
        job_type=JobType.LISTINGS_PREWARM,
        current_stage="listings_prewarm",
        result_ref={
            "lookback_hours": settings.listings_prewarm_lookback_hours,
            "limit": min(len(manual_targets), settings.listings_prewarm_limit),
            "trigger": "admin_run_now",
            "manual_targets": manual_targets,
            "max_address_duration_seconds": settings.listings_prewarm_max_address_duration_seconds,
            "max_platform_duration_seconds": settings.listings_prewarm_max_address_duration_seconds,
        },
    )
    if not result.created:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma batelada em execução.")
    return AdminRunNowResponse(
        job=result.job,
        target_count=len(manual_targets),
        status="queued",
    )


@router.post("/batches/{job_id}/cancel", response_model=JobCancelAccepted, status_code=status.HTTP_202_ACCEPTED)
async def cancel_scraping_batch(job_id: UUID, _ctx=Depends(require_developer)) -> JobCancelAccepted:
    job = await get_job(job_id)
    if job is None or job.job_type != JobType.LISTINGS_PREWARM or job.journey_id is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batelada não encontrada.")
    if job.state not in _ACTIVE_JOB_STATES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A batelada não está ativa.")
    cancellation = await request_job_cancellation(job_id)
    if cancellation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batelada não encontrada.")
    return cancellation
