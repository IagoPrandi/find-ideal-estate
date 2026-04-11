from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import dramatiq
from contracts import JobCancelAccepted, JobCreate, JobRead, JobState, JobType
from core.config import get_settings
from core.db import get_engine
from dramatiq.brokers.stub import StubBroker
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

_JOB_METRICS_KEY = "job_metrics"
_STAGE_METRICS_KEY = "stage_metrics"

_JOB_SELECT_COLUMNS = """
SELECT
    id,
    journey_id,
    job_type,
    state,
    progress_percent,
    current_stage,
    cancel_requested_at,
    started_at,
    finished_at,
    worker_id,
    result_ref,
    error_code,
    error_message,
    created_at
"""

_JOB_SELECT = f"""
{_JOB_SELECT_COLUMNS}
FROM jobs
WHERE id = :job_id
"""

_ACTIVE_JOB_SELECT = f"""
{_JOB_SELECT_COLUMNS}
FROM jobs
WHERE journey_id = :journey_id
  AND job_type = :job_type
  AND state IN ('pending', 'running', 'retrying')
ORDER BY created_at DESC, id DESC
LIMIT 1
"""

_GLOBAL_ACTIVE_JOB_SELECT = f"""
{_JOB_SELECT_COLUMNS}
FROM jobs
WHERE journey_id IS NULL
    AND job_type = :job_type
    AND state IN ('pending', 'running', 'retrying')
ORDER BY created_at DESC, id DESC
LIMIT 1
"""

_IDEMPOTENT_ACTIVE_JOB_TYPES = frozenset(
    {
        JobType.TRANSPORT_SEARCH.value,
        JobType.ZONE_GENERATION.value,
        JobType.ZONE_ENRICHMENT.value,
    }
)

_GLOBAL_IDEMPOTENT_ACTIVE_JOB_TYPES = frozenset(
    {
        JobType.LISTINGS_PREWARM.value,
    }
)

_DEFAULT_LOCAL_INLINE_JOB_TYPES = frozenset(
    {
        JobType.TRANSPORT_SEARCH.value,
        JobType.ZONE_GENERATION.value,
        JobType.ZONE_ENRICHMENT.value,
    }
)


@dataclass(frozen=True)
class CreateJobResult:
    job: JobRead
    created: bool


def _coerce_result_ref(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _merge_result_refs(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, patch_value in patch.items():
        current_value = merged.get(key)
        if isinstance(current_value, dict) and isinstance(patch_value, dict):
            merged[key] = _merge_result_refs(current_value, patch_value)
            continue
        merged[key] = patch_value
    return merged


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _isoformat_datetime(value: datetime) -> str:
    return _normalize_datetime(value).isoformat()


def _parse_result_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if not isinstance(value, str) or not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _normalize_datetime(parsed)


def _duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _stage_state_value(state: JobState | str | None) -> str | None:
    if state is None:
        return None
    return state.value if hasattr(state, "value") else str(state)


def _augment_result_ref_with_timing_metrics(
    base_result_ref: dict[str, Any],
    *,
    previous_stage: str | None,
    current_stage: str | None,
    state: JobState | str | None,
    progress_percent: int | None,
    job_started_at: datetime | None,
    mark_started: bool,
    mark_finished: bool,
    now: datetime,
) -> dict[str, Any]:
    result_ref = _coerce_result_ref(base_result_ref)
    effective_stage = current_stage or previous_stage
    normalized_state = _stage_state_value(state)

    job_metrics = result_ref.get(_JOB_METRICS_KEY)
    if not isinstance(job_metrics, dict):
        job_metrics = {}
    effective_job_started_at = job_started_at or _parse_result_datetime(job_metrics.get("started_at"))
    if effective_job_started_at is None and mark_started:
        effective_job_started_at = now
    if effective_job_started_at is not None:
        job_metrics["started_at"] = _isoformat_datetime(effective_job_started_at)
        job_metrics["last_updated_at"] = _isoformat_datetime(now)
        duration_ms = _duration_ms(effective_job_started_at, now)
        if duration_ms is not None:
            job_metrics["duration_ms"] = duration_ms
    if normalized_state is not None:
        job_metrics["state"] = normalized_state
    if mark_finished:
        job_metrics["completed_at"] = _isoformat_datetime(now)
    if job_metrics:
        result_ref[_JOB_METRICS_KEY] = job_metrics

    if effective_stage is not None:
        stage_metrics = result_ref.get(_STAGE_METRICS_KEY)
        if not isinstance(stage_metrics, dict):
            stage_metrics = {}

        stage_entry = stage_metrics.get(effective_stage)
        if not isinstance(stage_entry, dict):
            stage_entry = {}

        stage_started_at = (
            _parse_result_datetime(stage_entry.get("started_at"))
            or effective_job_started_at
            or now
        )
        stage_entry["started_at"] = _isoformat_datetime(stage_started_at)
        stage_entry["last_updated_at"] = _isoformat_datetime(now)
        duration_ms = _duration_ms(stage_started_at, now)
        if duration_ms is not None:
            stage_entry["duration_ms"] = duration_ms
        if progress_percent is not None:
            stage_entry["progress_percent"] = progress_percent
        if normalized_state is not None:
            stage_entry["state"] = normalized_state
        if mark_finished:
            stage_entry["completed_at"] = _isoformat_datetime(now)

        stage_metrics[effective_stage] = stage_entry
        result_ref[_STAGE_METRICS_KEY] = stage_metrics

    return result_ref


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


def _supports_active_job_idempotency(job_type: JobType | str) -> bool:
    value = job_type.value if hasattr(job_type, "value") else str(job_type)
    return value in _IDEMPOTENT_ACTIVE_JOB_TYPES


def _supports_global_job_idempotency(job_type: JobType | str) -> bool:
    value = job_type.value if hasattr(job_type, "value") else str(job_type)
    return value in _GLOBAL_IDEMPOTENT_ACTIVE_JOB_TYPES


async def get_job(job_id: UUID) -> JobRead | None:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(_JOB_SELECT), {"job_id": job_id})
        row = result.mappings().first()
    if row is None:
        return None
    return _row_to_job(row)


async def create_job(payload: JobCreate) -> CreateJobResult:
    engine = get_engine()
    job_type = payload.job_type.value
    created = False
    job_row: RowMapping | None = None

    async with engine.begin() as conn:
        if _supports_active_job_idempotency(job_type):
            existing = await conn.execute(
                text(_ACTIVE_JOB_SELECT),
                {"journey_id": payload.journey_id, "job_type": job_type},
            )
            job_row = existing.mappings().first()

        if job_row is None:
            try:
                async with conn.begin_nested():
                    result = await conn.execute(
                        text(
                            """
                            INSERT INTO jobs (journey_id, job_type, current_stage, result_ref)
                            VALUES (:journey_id, :job_type, :current_stage, CAST(:result_ref AS JSONB))
                            RETURNING id
                            """
                        ),
                        {
                            "journey_id": payload.journey_id,
                            "job_type": job_type,
                            "current_stage": payload.current_stage,
                            "result_ref": json.dumps({}),
                        },
                    )
                    job_id = result.scalar_one()
                created = True
            except IntegrityError:
                if not _supports_active_job_idempotency(job_type):
                    raise
                existing = await conn.execute(
                    text(_ACTIVE_JOB_SELECT),
                    {"journey_id": payload.journey_id, "job_type": job_type},
                )
                job_row = existing.mappings().first()
                if job_row is None:
                    raise

        if created:
            inserted = await conn.execute(text(_JOB_SELECT), {"job_id": job_id})
            job_row = inserted.mappings().first()

    if job_row is None:
        raise RuntimeError("Job creation did not persist")

    job = _row_to_job(job_row)
    if created:
        await enqueue_job(job)
    return CreateJobResult(job=job, created=created)


async def create_internal_job(
    *,
    job_type: JobType | str,
    current_stage: str | None = None,
    result_ref: dict[str, Any] | None = None,
) -> CreateJobResult:
    engine = get_engine()
    job_type_value = job_type.value if hasattr(job_type, "value") else str(job_type)
    created = False
    job_row: RowMapping | None = None

    async with engine.begin() as conn:
        if _supports_global_job_idempotency(job_type_value):
            existing = await conn.execute(
                text(_GLOBAL_ACTIVE_JOB_SELECT),
                {"job_type": job_type_value},
            )
            job_row = existing.mappings().first()

        if job_row is None:
            result = await conn.execute(
                text(
                    """
                    INSERT INTO jobs (journey_id, job_type, current_stage, result_ref)
                    VALUES (NULL, :job_type, :current_stage, CAST(:result_ref AS JSONB))
                    RETURNING id
                    """
                ),
                {
                    "job_type": job_type_value,
                    "current_stage": current_stage,
                    "result_ref": json.dumps(result_ref or {}),
                },
            )
            job_id = result.scalar_one()
            created = True

        if created:
            inserted = await conn.execute(text(_JOB_SELECT), {"job_id": job_id})
            job_row = inserted.mappings().first()

    if job_row is None:
        raise RuntimeError("Internal job creation did not persist")

    job = _row_to_job(job_row)
    if created:
        await enqueue_job(job)
    return CreateJobResult(job=job, created=created)


def _uses_stub_broker() -> bool:
    try:
        return isinstance(dramatiq.get_broker(), StubBroker)
    except RuntimeError:
        return False


def _local_inline_job_types() -> frozenset[str]:
    raw_value = get_settings().local_inline_job_types
    if raw_value is None:
        raw_value = os.getenv("LOCAL_INLINE_JOB_TYPES")
    if raw_value is None:
        return frozenset()

    normalized_items = [item.strip().lower() for item in raw_value.split(",") if item.strip()]
    if not normalized_items:
        return frozenset()
    if normalized_items == ["default"]:
        return _DEFAULT_LOCAL_INLINE_JOB_TYPES
    return frozenset(normalized_items)


def _should_run_inline_locally(job_type: JobType | str) -> bool:
    value = job_type.value if hasattr(job_type, "value") else str(job_type)
    return value in _local_inline_job_types()


async def _run_job_inline(job: JobRead) -> None:
    from workers.runtime import run_job_with_retry

    if job.job_type == JobType.TRANSPORT_SEARCH:
        from workers.handlers.transport import _transport_search_step

        await run_job_with_retry(
            job.id,
            JobType.TRANSPORT_SEARCH,
            stage="transport_search",
            execute_step=lambda: _transport_search_step(job.id),
        )
        return

    if job.job_type == JobType.ZONE_GENERATION:
        from workers.handlers.zones import _zone_generation_step

        await run_job_with_retry(
            job.id,
            JobType.ZONE_GENERATION,
            stage="zone_generation",
            execute_step=lambda: _zone_generation_step(job.id),
        )
        return

    if job.job_type == JobType.ZONE_ENRICHMENT:
        from workers.handlers.enrichment import _zone_enrichment_step

        await run_job_with_retry(
            job.id,
            JobType.ZONE_ENRICHMENT,
            stage="zone_enrichment",
            execute_step=lambda: _zone_enrichment_step(job.id),
        )
        return

    if job.job_type == JobType.LISTINGS_SCRAPE:
        from workers.handlers.listings import _listings_scrape_step

        await run_job_with_retry(
            job.id,
            JobType.LISTINGS_SCRAPE,
            stage="listings_scrape",
            execute_step=lambda: _listings_scrape_step(job.id),
        )
        return

    if job.job_type == JobType.LISTINGS_PREWARM:
        from workers.handlers.prewarm import _listings_prewarm_step

        await run_job_with_retry(
            job.id,
            JobType.LISTINGS_PREWARM,
            stage="listings_prewarm",
            execute_step=lambda: _listings_prewarm_step(job.id),
        )
        return


async def enqueue_job(job: JobRead) -> None:
    if _uses_stub_broker():
        asyncio.create_task(_run_job_inline(job))
        return

    if _should_run_inline_locally(job.job_type):
        asyncio.create_task(_run_job_inline(job))
        return

    if job.job_type == JobType.TRANSPORT_SEARCH:
        from workers.handlers.transport import transport_search_actor

        transport_search_actor.send(str(job.id))
    elif job.job_type == JobType.ZONE_GENERATION:
        from workers.handlers.zones import zone_generation_actor

        zone_generation_actor.send(str(job.id))
    elif job.job_type == JobType.ZONE_ENRICHMENT:
        from workers.handlers.enrichment import enrich_zones_actor
        enrich_zones_actor.send(str(job.id))
    elif job.job_type == JobType.LISTINGS_SCRAPE:
        from workers.handlers.listings import listings_scrape_actor

        listings_scrape_actor.send(str(job.id))
    elif job.job_type == JobType.LISTINGS_PREWARM:
        from workers.handlers.prewarm import listings_prewarm_actor

        listings_prewarm_actor.send(str(job.id))


async def update_job_execution_state(
    job_id: UUID,
    *,
    state: JobState | str | None = None,
    current_stage: str | None = None,
    progress_percent: int | None = None,
    error_message: str | None = None,
    mark_started: bool = False,
    mark_finished: bool = False,
    result_ref: dict[str, Any] | None = None,
) -> None:
    set_clauses: list[str] = []
    params: dict[str, Any] = {"job_id": job_id}
    should_update_result_ref = any(
        (
            result_ref is not None,
            current_stage is not None,
            progress_percent is not None,
            state is not None,
            mark_started,
            mark_finished,
        )
    )

    if state is not None:
        set_clauses.append("state = :state")
        params["state"] = state.value if hasattr(state, "value") else state

    if current_stage is not None:
        set_clauses.append("current_stage = :current_stage")
        params["current_stage"] = current_stage

    if progress_percent is not None:
        set_clauses.append("progress_percent = :progress_percent")
        params["progress_percent"] = progress_percent

    if error_message is not None:
        set_clauses.append("error_message = :error_message")
        params["error_message"] = error_message

    if mark_started:
        set_clauses.append("started_at = COALESCE(started_at, now())")

    if mark_finished:
        set_clauses.append("finished_at = now()")

    if not set_clauses and not should_update_result_ref:
        return

    engine = get_engine()
    async with engine.begin() as conn:
        if should_update_result_ref:
            current_result = await conn.execute(
                text(
                    """
                    SELECT result_ref, current_stage, started_at
                    FROM jobs
                    WHERE id = :job_id
                    FOR UPDATE
                    """
                ),
                {"job_id": job_id},
            )
            current_row = current_result.mappings().first()
            if current_row is None:
                return

            merged_result_ref = _coerce_result_ref(current_row["result_ref"])
            if result_ref is not None:
                merged_result_ref = _merge_result_refs(merged_result_ref, result_ref)
            merged_result_ref = _augment_result_ref_with_timing_metrics(
                merged_result_ref,
                previous_stage=current_row["current_stage"],
                current_stage=current_stage,
                state=state,
                progress_percent=progress_percent,
                job_started_at=current_row["started_at"],
                mark_started=mark_started,
                mark_finished=mark_finished,
                now=datetime.now(tz=timezone.utc),
            )
            set_clauses.append("result_ref = CAST(:result_ref AS JSONB)")
            params["result_ref"] = json.dumps(merged_result_ref)

        await conn.execute(
            text(f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = :job_id"),
            params,
        )


async def request_job_cancellation(job_id: UUID) -> JobCancelAccepted | None:
    cancel_requested_at = datetime.now(tz=timezone.utc)
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE jobs
                SET cancel_requested_at = COALESCE(cancel_requested_at, :cancel_requested_at)
                WHERE id = :job_id
                RETURNING cancel_requested_at
                """
            ),
            {"job_id": job_id, "cancel_requested_at": cancel_requested_at},
        )
        row = result.mappings().first()
    if row is None:
        return None
    return JobCancelAccepted(
        job_id=job_id,
        status="accepted",
        cancel_requested_at=row["cancel_requested_at"],
    )

