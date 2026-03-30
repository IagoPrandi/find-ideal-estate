"""Stale-while-revalidate cache lookup for zone listings (M5.4)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from core.db import get_engine
from modules.listings.models import ZoneCacheStatus
from sqlalchemy import text


def compute_config_hash(
    search_type: str,
    usage_type: str,
    platforms: list[str],
) -> str:
    """Deterministic hash of the search configuration (excludes location)."""
    canonical = {
        "platforms": sorted(platforms),
        "search_type": search_type,
        "usage_type": usage_type,
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_search_location(search_location_normalized: str | None) -> str:
    return (search_location_normalized or "").strip().lower()


async def get_cache_record(
    search_location_normalized: str | None,
) -> dict[str, Any] | None:
    """Return the current zone_listing_cache row for a normalized address, or None."""
    normalized = normalize_search_location(search_location_normalized)
    if not normalized:
        return None

    engine = get_engine()
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                """
                SELECT id, zone_fingerprint, config_hash, search_location_normalized, status,
                       platforms_completed, platforms_failed,
                       coverage_ratio, preliminary_count,
                       scraped_at, expires_at, created_at
                FROM zone_listing_caches
                WHERE search_location_normalized = :normalized
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"normalized": normalized},
        )
        record = row.mappings().first()
        if record is None:
            return None
        return dict(record)


def cache_is_usable(record: dict[str, Any] | None) -> bool:
    """True when cache is complete/partial and not expired."""
    if record is None:
        return False
    if not ZoneCacheStatus.is_usable(record.get("status")):
        return False
    expires_at = record.get("expires_at")
    if expires_at is None:
        return True
    now = datetime.now(tz=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return now < expires_at


def cache_age_hours(record: dict[str, Any] | None) -> float | None:
    """Returns cache age in hours, or None if unavailable."""
    if record is None:
        return None
    scraped_at = record.get("scraped_at")
    if scraped_at is None:
        return None
    now = datetime.now(tz=timezone.utc)
    if scraped_at.tzinfo is None:
        scraped_at = scraped_at.replace(tzinfo=timezone.utc)
    return (now - scraped_at).total_seconds() / 3600


async def create_cache_record(
    search_location_normalized: str | None,
    *,
    zone_fingerprint: str,
    config_hash: str,
) -> UUID:
    """Create a new pending cache record. Return its id."""
    normalized = normalize_search_location(search_location_normalized)
    if not normalized:
        raise ValueError("search_location_normalized is required for listings cache")

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO zone_listing_caches (
                    zone_fingerprint, config_hash, search_location_normalized, status
                )
                VALUES (:zfp, :ch, :normalized, 'pending')
                ON CONFLICT (search_location_normalized) DO NOTHING
                RETURNING id
                """
            ),
            {"zfp": zone_fingerprint, "ch": config_hash, "normalized": normalized},
        )
        row = result.first()
        if row:
            return row[0]

        # Already existed — return existing id
        existing = await conn.execute(
            text(
                "SELECT id FROM zone_listing_caches "
                "WHERE search_location_normalized = :normalized"
            ),
            {"normalized": normalized},
        )
        return existing.scalar_one()


async def transition_cache_status(
    cache_id: UUID,
    current_status: str,
    new_status: str,
    *,
    platforms_completed: list[str] | None = None,
    platforms_failed: list[str] | None = None,
    coverage_ratio: float | None = None,
    preliminary_count: int | None = None,
    expires_at: datetime | None = None,
) -> None:
    """Validate and apply a status transition on a zone_listing_cache row."""
    ZoneCacheStatus.transition_to(current_status, new_status)

    engine = get_engine()
    sets = ["status = :new_status"]
    params: dict[str, Any] = {"cache_id": cache_id, "new_status": new_status}

    if new_status in {ZoneCacheStatus.COMPLETE, ZoneCacheStatus.PARTIAL}:
        sets.append("scraped_at = now()")

    if platforms_completed is not None:
        sets.append("platforms_completed = :platforms_completed")
        params["platforms_completed"] = platforms_completed

    if platforms_failed is not None:
        sets.append("platforms_failed = :platforms_failed")
        params["platforms_failed"] = platforms_failed

    if coverage_ratio is not None:
        sets.append("coverage_ratio = :coverage_ratio")
        params["coverage_ratio"] = coverage_ratio

    if preliminary_count is not None:
        sets.append("preliminary_count = :preliminary_count")
        params["preliminary_count"] = preliminary_count

    if expires_at is not None:
        sets.append("expires_at = :expires_at")
        params["expires_at"] = expires_at

    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE zone_listing_caches SET {', '.join(sets)} WHERE id = :cache_id"),
            params,
        )


async def find_partial_hit_from_overlapping_zone(
    zone_fingerprint: str,
    config_hash: str,
) -> dict[str, Any] | None:
    """
    M5.4: Look for a usable cache record from a different zone whose isochrone
    covers ≥ 70 % of the requested zone (ST_Within-based partial hit heuristic).
    """
    engine = get_engine()
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                """
                SELECT zlc.id, zlc.zone_fingerprint, zlc.config_hash,
                       zlc.status, zlc.platforms_completed, zlc.platforms_failed,
                       zlc.coverage_ratio, zlc.preliminary_count,
                       zlc.scraped_at, zlc.expires_at, zlc.created_at
                FROM zone_listing_caches zlc
                JOIN zones src ON src.fingerprint = :zone_fp
                JOIN zones alt ON alt.fingerprint = zlc.zone_fingerprint
                WHERE zlc.config_hash = :ch
                  AND zlc.status IN ('complete', 'partial')
                  AND (zlc.expires_at IS NULL OR zlc.expires_at > now())
                  AND alt.fingerprint != :zone_fp
                  AND ST_Area(ST_Intersection(src.isochrone_geom, alt.isochrone_geom))
                      / NULLIF(ST_Area(src.isochrone_geom), 0) >= 0.70
                ORDER BY zlc.scraped_at DESC
                LIMIT 1
                """
            ),
            {"zone_fp": zone_fingerprint, "ch": config_hash},
        )
        record = row.mappings().first()
        return dict(record) if record else None


async def find_usable_cache_for_search_location(
    search_location_normalized: str,
) -> dict[str, Any] | None:
    """
    Return the latest usable cache associated with a normalized search location.

    Cache for the same address is reused across zones and search configurations.
    """
    normalized = normalize_search_location(search_location_normalized)
    if not normalized:
        return None

    engine = get_engine()
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                """
                SELECT zlc.id, zlc.zone_fingerprint, zlc.config_hash,
                       zlc.search_location_normalized,
                       zlc.status, zlc.platforms_completed, zlc.platforms_failed,
                       zlc.coverage_ratio, zlc.preliminary_count,
                       zlc.scraped_at, zlc.expires_at, zlc.created_at
                FROM zone_listing_caches zlc
                WHERE zlc.search_location_normalized = :normalized
                  AND zlc.status IN ('complete', 'partial')
                  AND (zlc.expires_at IS NULL OR zlc.expires_at > now())
                ORDER BY zlc.scraped_at DESC NULLS LAST, zlc.created_at DESC
                LIMIT 1
                """
            ),
            {"normalized": normalized},
        )
        record = row.mappings().first()
        return dict(record) if record else None
