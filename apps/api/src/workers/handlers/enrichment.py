"""Zone enrichment worker handlers for zone_enrichment jobs."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import dramatiq
from contracts import JobType
from core.db import get_engine
from modules.jobs.events import publish_job_event
from modules.zones.badges import compute_zone_badges, update_zone_badges
from modules.zones.enrichment import (
    enrich_zone_flood,
    enrich_zone_green,
    enrich_zone_pois,
    enrich_zone_safety,
)
from sqlalchemy import text
from workers.cancellation import check_cancellation
from workers.middleware import emit_stage_progress
from workers.queue import QUEUE_ENRICHMENT
from workers.runtime import run_job_with_retry


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _extract_enrichment_flags(input_snapshot: Any) -> dict[str, bool]:
    defaults = {
        "green": True,
        "flood": True,
        "safety": True,
        "pois": True,
    }
    if not isinstance(input_snapshot, dict):
        return defaults

    enrichments = input_snapshot.get("enrichments")
    if isinstance(enrichments, dict):
        return {
            "green": _parse_bool(enrichments.get("green"), True),
            "flood": _parse_bool(enrichments.get("flood"), True),
            "safety": _parse_bool(enrichments.get("safety"), True),
            "pois": _parse_bool(enrichments.get("pois"), True),
        }

    return {
        "green": _parse_bool(input_snapshot.get("zone_detail_include_green"), True),
        "flood": _parse_bool(input_snapshot.get("zone_detail_include_flood"), True),
        "safety": _parse_bool(input_snapshot.get("zone_detail_include_public_safety"), True),
        "pois": _parse_bool(input_snapshot.get("zone_detail_include_pois"), True),
    }


async def _load_job_enrichment_flags(job_id: UUID) -> dict[str, bool]:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT j.input_snapshot
                FROM jobs jb
                JOIN journeys j ON j.id = jb.journey_id
                WHERE jb.id = :job_id
                """
            ),
            {"job_id": job_id},
        )
        row = result.mappings().first()

    snapshot = row["input_snapshot"] if row else None
    return _extract_enrichment_flags(snapshot)


async def dispatch_enrichment_subjobs(zone_id: UUID, enrichments: dict[str, bool]) -> dict[str, Any]:
    """Start enabled enrichment subjobs concurrently for one zone."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE zones
                SET state = 'enriching', updated_at = now()
                WHERE id = :zone_id
                """
            ),
            {"zone_id": zone_id},
        )

    tasks: dict[str, asyncio.Future] = {}
    if enrichments.get("green", True):
        tasks["green"] = asyncio.create_task(enrich_zone_green(zone_id))
    if enrichments.get("flood", True):
        tasks["flood"] = asyncio.create_task(enrich_zone_flood(zone_id))
    if enrichments.get("safety", True):
        tasks["safety"] = asyncio.create_task(enrich_zone_safety(zone_id))
    if enrichments.get("pois", True):
        tasks["pois"] = asyncio.create_task(enrich_zone_pois(zone_id))

    if tasks:
        await asyncio.gather(*tasks.values())

    green = tasks["green"].result() if "green" in tasks else {}
    flood = tasks["flood"].result() if "flood" in tasks else {}
    safety = tasks["safety"].result() if "safety" in tasks else {}
    pois = tasks["pois"].result() if "pois" in tasks else {}

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE zones
                SET state = 'complete', updated_at = now()
                WHERE id = :zone_id
                """
            ),
            {"zone_id": zone_id},
        )

    return {
        "green_area_m2": green.get("green_area_m2"),
        "flood_area_m2": flood.get("flood_area_m2"),
        "safety_incidents_count": safety.get("safety_incidents_count"),
        "poi_counts": pois.get("poi_counts"),
    }


async def _zone_enrichment_step(job_id: UUID) -> None:
    stage = "zone_enrichment"
    await check_cancellation(job_id)
    enrichment_flags = await _load_job_enrichment_flags(job_id)
    await emit_stage_progress(
        job_id,
        stage=stage,
        progress_percent=10,
        message="Loading zones for enrichment",
    )

    engine = get_engine()
    async with engine.begin() as conn:
        zones_result = await conn.execute(
            text(
                """
                SELECT z.id
                FROM journey_zones jz
                JOIN jobs jb ON jb.journey_id = jz.journey_id
                JOIN zones z ON z.id = jz.zone_id
                WHERE jb.id = :job_id
                ORDER BY jz.created_at ASC, z.created_at ASC
                """
            ),
            {"job_id": job_id},
        )
        zones = [row[0] for row in zones_result.fetchall()]

    total = len(zones)
    if total == 0:
        await emit_stage_progress(
            job_id,
            stage=stage,
            progress_percent=100,
            message="No zones to enrich",
        )
        return

    for idx, zone_id in enumerate(zones, 1):
        await check_cancellation(job_id)
        results = await dispatch_enrichment_subjobs(zone_id, enrichment_flags)

        # Compute provisional badges after enrichment (based on zones completed so far)
        provisional_badges = await compute_zone_badges(
            zone_id, provisional=True, based_on_count=idx
        )
        await update_zone_badges(zone_id, provisional_badges, provisional=True)

        await publish_job_event(
            job_id,
            "zone.enriched",
            stage=stage,
            message=f"Zone {idx}/{total} enriched",
            payload_json={
                "zone_id": str(zone_id),
                "sequence": idx,
                "total": total,
                "results": results,
            },
        )

        # Emit provisional badges event
        await publish_job_event(
            job_id,
            "zone.badges.updated",
            stage=stage,
            message=f"Badges computed (provisional, {idx}/{total} zones)",
            payload_json={
                "zone_id": str(zone_id),
                "sequence": idx,
                "total": total,
                "badges": provisional_badges,
            },
        )

        progress = 10 + int((idx / total) * 90)
        await emit_stage_progress(
            job_id,
            stage=stage,
            progress_percent=progress,
            message=f"Enriched {idx}/{total} zones",
        )

    # After all zones complete, compute and emit final badges
    async with engine.begin() as conn:
        zones_result = await conn.execute(
            text(
                """
                SELECT z.id
                FROM journey_zones jz
                JOIN jobs jb ON jb.journey_id = jz.journey_id
                JOIN zones z ON z.id = jz.zone_id
                WHERE jb.id = :job_id
                ORDER BY jz.created_at ASC, z.created_at ASC
                """
            ),
            {"job_id": job_id},
        )
        final_zones = [row[0] for row in zones_result.fetchall()]

    for zone_id in final_zones:
        final_badges = await compute_zone_badges(zone_id, provisional=False)
        await update_zone_badges(zone_id, final_badges, provisional=False)

    # Emit finalized badges event (once for the entire journey)
    await publish_job_event(
        job_id,
        "zones.badges.finalized",
        stage=stage,
        message="All zone badges finalized",
        payload_json={
            "total_zones": len(final_zones),
            "zones_finalized": [str(z) for z in final_zones],
        },
    )


@dramatiq.actor(queue_name=QUEUE_ENRICHMENT)
def enrich_zones_actor(job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    asyncio.run(
        run_job_with_retry(
            parsed_job_id,
            JobType.ZONE_ENRICHMENT,
            stage="zone_enrichment",
            execute_step=lambda: _zone_enrichment_step(parsed_job_id),
        )
    )
