"""Listings API routes.

POST /journeys/{journey_id}/listings/search
    Step 5: confirm address search, record demand, return cache or enqueue scraping.

GET  /journeys/{journey_id}/listings/address-suggest
    Step 5: autocomplete filtered to zone polygon.

GET  /journeys/{journey_id}/zones/{zone_fingerprint}/listings
    Step 6: return listing cards for display.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from contracts import ListingsRequestResult, SearchAddressSuggestion
from core.db import get_engine as _get_engine
from fastapi import APIRouter, Cookie, HTTPException, Query
from modules.listings.cache import (
    cache_age_hours,
    cache_is_usable,
    compute_config_hash,
    create_cache_record,
    find_partial_hit_from_overlapping_zone,
    get_cache_record,
)
from modules.listings.dedup import fetch_listing_cards_for_zone
from modules.listings.platform_registry import PlatformRegistryError, get_platform_registry
from modules.listings.search_requests import record_search_request
from pydantic import BaseModel
from sqlalchemy import text
from modules.jobs.service import enqueue_job, get_job

router = APIRouter(prefix="/journeys", tags=["listings"])


class ListingsSearchRequest(BaseModel):
    zone_fingerprint: str
    search_location_normalized: str
    search_location_label: str
    search_location_type: str  # 'neighborhood' | 'street' | 'address' | 'landmark'
    search_type: str           # 'rent' | 'sale'
    usage_type: str = "residential"
    # PRO plan future: pass platform list; for now always FREE
    platforms: list[str] | None = None


async def _enqueue_listings_scrape_job(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    search_address: str,
    search_type: str,
    usage_type: str,
    platforms: list[str],
) -> UUID:
    """Create and dispatch a listings_scrape job, returning the created job id."""
    engine = _get_engine()
    async with engine.begin() as conn:
        job_result = await conn.execute(
            text(
                """
                INSERT INTO jobs (journey_id, job_type, state, result_ref)
                VALUES (:journey_id, 'listings_scrape', 'pending', CAST(:result_ref AS JSONB))
                RETURNING id
                """
            ),
            {
                "journey_id": journey_id,
                "result_ref": json.dumps(
                    {
                        "zone_fingerprint": zone_fingerprint,
                        "search_address": search_address,
                        "search_type": search_type,
                        "usage_type": usage_type,
                        "platforms": platforms,
                    }
                ),
            },
        )
        job_id = job_result.scalar_one()

    job = await get_job(job_id)
    if job is None:
        raise RuntimeError(f"Failed to fetch listings job after insert: {job_id}")

    await enqueue_job(job)
    return job_id


@router.post(
    "/{journey_id}/listings/search",
    response_model=ListingsRequestResult,
)
async def listings_search(
    journey_id: UUID,
    body: ListingsSearchRequest,
    anonymous_session_id: str | None = Cookie(default=None),
) -> ListingsRequestResult:
    """
    M5.6: Record confirmed listing search and determine result source.

    FREE plan (current phase):
      - cache hit -> return immediately.
      - partial hit from overlapping zone -> return with partial badge.
      - cache miss -> return queued result ; search is still recorded for prewarm.
    """
    registry = get_platform_registry()
    raw_platforms = body.platforms or registry.default_free_platforms()
    try:
        platforms = registry.resolve_names(raw_platforms)
    except PlatformRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config_hash = compute_config_hash(body.search_type, body.usage_type, platforms)
    platforms_hash = hashlib.sha256(
        json.dumps(sorted(platforms), separators=(",", ":")).encode()
    ).hexdigest()[:16]

    # Determine result source
    cache = await get_cache_record(body.zone_fingerprint, config_hash)

    if cache_is_usable(cache):
        result_source = "cache_hit"
    else:
        partial = await find_partial_hit_from_overlapping_zone(
            body.zone_fingerprint, config_hash
        )
        if partial and cache_is_usable(partial):
            result_source = "cache_partial"
            cache = partial
        else:
            result_source = "cache_miss"

    # Always record demand (including misses -- drives prewarm)
    await record_search_request(
        journey_id=journey_id,
        session_id=anonymous_session_id,
        zone_fingerprint=body.zone_fingerprint,
        search_location_normalized=body.search_location_normalized,
        search_location_label=body.search_location_label,
        search_location_type=body.search_location_type,
        search_type=body.search_type,
        usage_type=body.usage_type,
        platforms_hash=platforms_hash,
        result_source=result_source,
    )

    if result_source == "cache_miss":
        # Ensure cache row exists (for lock coordination) and enqueue scrape job
        await create_cache_record(body.zone_fingerprint, config_hash)

        await _enqueue_listings_scrape_job(
            journey_id=journey_id,
            zone_fingerprint=body.zone_fingerprint,
            search_address=body.search_location_label,
            search_type=body.search_type,
            usage_type=body.usage_type,
            platforms=platforms,
        )

        return ListingsRequestResult(
            source="none",
            freshness_status="queued_for_next_prewarm",
            upgrade_reason="fresh_listings",
            next_refresh_window="03:00-05:30",
            listings=[],
            total_count=0,
        )

    # Cache hit or partial hit -- return listings
    listing_cards_raw = await fetch_listing_cards_for_zone(
        zone_fingerprint=cache["zone_fingerprint"],
        search_type=body.search_type,
        usage_type=body.usage_type,
        platforms=platforms,
    )

    age_hours = cache_age_hours(cache)
    freshness = "fresh" if (age_hours is not None and age_hours < 2) else "stale"

    # M5.4 stale-while-revalidate: serve immediately and refresh in background.
    should_revalidate = result_source == "cache_partial" or (
        result_source == "cache_hit" and freshness == "stale"
    )
    if should_revalidate:
        await create_cache_record(body.zone_fingerprint, config_hash)
        await _enqueue_listings_scrape_job(
            journey_id=journey_id,
            zone_fingerprint=body.zone_fingerprint,
            search_address=body.search_location_label,
            search_type=body.search_type,
            usage_type=body.usage_type,
            platforms=platforms,
        )

    return ListingsRequestResult(
        source="cache",
        freshness_status=freshness,
        listings=listing_cards_raw,  # type: ignore[arg-type]
        total_count=len(listing_cards_raw),
        cache_age_hours=age_hours,
    )


@router.get(
    "/{journey_id}/listings/address-suggest",
    response_model=list[SearchAddressSuggestion],
)
async def address_suggest(
    journey_id: UUID,
    zone_fingerprint: str = Query(...),
    q: str = Query(..., min_length=2),
) -> list[SearchAddressSuggestion]:
    """
    M5.7: Autocomplete addresses filtered by ST_Contains(zone, address_point).
    """
    engine = _get_engine()
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                WITH zone_geom AS (
                    SELECT isochrone_geom FROM zones WHERE fingerprint = :fp LIMIT 1
                )
                SELECT
                    COALESCE(street_name, stop_name)  AS label,
                    LOWER(COALESCE(street_name, stop_name)) AS normalized,
                    'street'                           AS location_type,
                    ST_Y(location::geometry)           AS lat,
                    ST_X(location::geometry)           AS lon
                FROM gtfs_stops, zone_geom
                WHERE ST_Within(location::geometry, zone_geom.isochrone_geom)
                  AND (
                    stop_name ILIKE :q
                    OR street_name ILIKE :q
                  )
                LIMIT 20
                """
            ),
            {"fp": zone_fingerprint, "q": f"%{q}%"},
        )
        suggestions = []
        for row in rows.mappings():
            suggestions.append(
                SearchAddressSuggestion(
                    label=row["label"] or "",
                    normalized=row["normalized"] or "",
                    location_type=row["location_type"],
                    lat=float(row["lat"]) if row["lat"] else 0.0,
                    lon=float(row["lon"]) if row["lon"] else 0.0,
                )
            )
        return suggestions


@router.get(
    "/{journey_id}/zones/{zone_fingerprint}/listings",
    response_model=ListingsRequestResult,
)
async def get_zone_listings(
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str = Query(default="rent"),
    usage_type: str = Query(default="residential"),
    platforms: list[str] | None = Query(default=None),
) -> ListingsRequestResult:
    """
    M5.7 Step 6: Return cached listing cards for a zone, plus freshness info.
    """
    registry = get_platform_registry()
    raw_platforms = platforms or registry.default_free_platforms()
    try:
        canonical_platforms = registry.resolve_names(raw_platforms)
    except PlatformRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config_hash = compute_config_hash(search_type, usage_type, canonical_platforms)
    cache = await get_cache_record(zone_fingerprint, config_hash)

    if not cache or not cache_is_usable(cache):
        return ListingsRequestResult(
            source="none",
            freshness_status="no_cache",
            listings=[],
            total_count=0,
        )

    listing_cards_raw = await fetch_listing_cards_for_zone(
        zone_fingerprint=zone_fingerprint,
        search_type=search_type,
        usage_type=usage_type,
        platforms=canonical_platforms,
    )
    age_hours = cache_age_hours(cache)
    freshness = "fresh" if (age_hours is not None and age_hours < 2) else "stale"

    return ListingsRequestResult(
        source="cache",
        freshness_status=freshness,
        listings=listing_cards_raw,  # type: ignore[arg-type]
        total_count=len(listing_cards_raw),
        cache_age_hours=age_hours,
    )


__all__ = ["router"]
