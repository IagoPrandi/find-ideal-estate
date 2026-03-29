from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import dramatiq
from contracts import JobCancelAccepted, JobCreate, JobRead, JobState, JobType
from core.db import get_engine
from dramatiq.brokers.stub import StubBroker
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError

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

_IDEMPOTENT_ACTIVE_JOB_TYPES = frozenset(
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


def _uses_stub_broker() -> bool:
    try:
        return isinstance(dramatiq.get_broker(), StubBroker)
    except RuntimeError:
        return False


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


async def enqueue_job(job: JobRead) -> None:
    if _uses_stub_broker():
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

    if result_ref is not None:
        set_clauses.append("result_ref = CAST(:result_ref AS JSONB)")
        params["result_ref"] = json.dumps(result_ref)

    if mark_started:
        set_clauses.append("started_at = COALESCE(started_at, now())")

    if mark_finished:
        set_clauses.append("finished_at = now()")

    if not set_clauses:
        return

    engine = get_engine()
    async with engine.begin() as conn:
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

