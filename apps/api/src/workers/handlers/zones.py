from __future__ import annotations

import asyncio
from uuid import UUID

import dramatiq
from contracts import JobType
from core.container import get_container
from modules.jobs.events import publish_job_event
from workers.cancellation import check_cancellation
from workers.middleware import emit_stage_progress
from workers.queue import QUEUE_ZONES
from workers.runtime import run_job_with_retry


async def run_zone_generation_for_job(job_id: UUID):
    zone_service = get_container().zone_service()
    return await zone_service.ensure_zones_for_job(job_id)


async def _zone_generation_step(job_id: UUID) -> None:
    stage = "zone_generation"
    await check_cancellation(job_id)
    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=10,
        message="Loading zone generation context",
    )

    await check_cancellation(job_id)
    outcome = await run_zone_generation_for_job(job_id)

    zones = outcome["zones"]
    total_zones = outcome["total"]

    # Emit partial_result.ready for each zone
    for idx, zone in enumerate(zones, 1):
        event_type = "zone.reused" if zone.reused else "zone.generated"
        await publish_job_event(
            job_id,
            event_type,
            stage=stage,
            message=(
                "Zone reused from fingerprint cache"
                if zone.reused
                else "Zone generated from Valhalla isochrone"
            ),
            payload_json={
                "zone_id": str(zone.zone_id),
                "fingerprint": zone.fingerprint,
                "reused": zone.reused,
                "sequence": idx,
                "total": total_zones,
            },
        )

        # Emit partial_result.ready to trigger progressive display
        await publish_job_event(
            job_id,
            "job.partial_result.ready",
            stage=stage,
            message=f"Zone {idx}/{total_zones} generation completed",
            payload_json={
                "zone_id": str(zone.zone_id),
                "fingerprint": zone.fingerprint,
                "sequence": idx,
                "total": total_zones,
                "reused": zone.reused,
            },
        )

        await emit_stage_progress(
            job_id,
            stage=stage,
            progress_percent=10 + int((idx / total_zones) * 90),
            message=f"Generated {idx}/{total_zones} zones",
        )

        await check_cancellation(job_id)

    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=100,
        message="Zone generation step completed",
    )


@dramatiq.actor(queue_name=QUEUE_ZONES)
def zone_generation_actor(job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    asyncio.run(
        run_job_with_retry(
            parsed_job_id,
            JobType.ZONE_GENERATION,
            stage="zone_generation",
            execute_step=lambda: _zone_generation_step(parsed_job_id),
        )
    )
