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
from core.config import get_settings
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
from modules.listings.address_suggestions import get_zone_address_suggestions
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
    try:
        registry = get_platform_registry()
    except PlatformRegistryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
        q: str = Query(default=""),
) -> list[SearchAddressSuggestion]:
    """
        M5.7: Combobox suggestions for streets inside the selected zone.

        Current pipeline:
            - sample points inside zone geometry
            - query Mapbox Tilequery for nearby roads
            - reverse geocode representative points
            - return scraper-ready labels in the form:
                "Rua, Bairro, Cidade-UF"
    """
    engine = _get_engine()
    async with engine.connect() as conn:
        zone_result = await conn.execute(
            text(
                """
                SELECT
                    z.fingerprint,
                    ST_AsGeoJSON(z.isochrone_geom) AS isochrone_geom,
                    ST_X(ST_Centroid(z.isochrone_geom)) AS centroid_lon,
                    ST_Y(ST_Centroid(z.isochrone_geom)) AS centroid_lat,
                    ST_XMin(z.isochrone_geom)::DOUBLE PRECISION AS xmin,
                    ST_YMin(z.isochrone_geom)::DOUBLE PRECISION AS ymin,
                    ST_XMax(z.isochrone_geom)::DOUBLE PRECISION AS xmax,
                    ST_YMax(z.isochrone_geom)::DOUBLE PRECISION AS ymax
                FROM journey_zones jz
                JOIN zones z ON z.id = jz.zone_id
                WHERE jz.journey_id = :journey_id
                  AND z.fingerprint = :fp
                LIMIT 1
                """
            ),
            {"journey_id": journey_id, "fp": zone_fingerprint},
        )
        zone = zone_result.mappings().first()

    if zone is None or not zone["isochrone_geom"]:
        raise HTTPException(status_code=404, detail="Zona nao encontrada para sugestao de enderecos")

    settings = get_settings()
    raw_suggestions = await get_zone_address_suggestions(
        access_token=settings.mapbox_access_token,
        zone_fingerprint=str(zone["fingerprint"]),
        geometry=json.loads(zone["isochrone_geom"]),
        bbox=(
            float(zone["xmin"]),
            float(zone["ymin"]),
            float(zone["xmax"]),
            float(zone["ymax"]),
        ),
        centroid=(float(zone["centroid_lon"]), float(zone["centroid_lat"])),
        q=q,
    )

    return [
        SearchAddressSuggestion(
            label=item["label"],
            normalized=item["normalized"],
            location_type=item["location_type"],
            lat=float(item["lat"]),
            lon=float(item["lon"]),
        )
        for item in raw_suggestions
    ]


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
    try:
        registry = get_platform_registry()
    except PlatformRegistryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
