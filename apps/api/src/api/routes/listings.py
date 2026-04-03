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
    find_usable_cache_for_search_location,
    get_cache_record,
    normalize_search_location,
)
from modules.listings.dedup import fetch_listing_cards_for_zone
from modules.listings.platform_registry import PlatformRegistryError, get_platform_registry
from modules.listings.address_suggestions import get_zone_address_suggestions
from modules.listings.search_requests import (
    get_latest_search_request_for_zone,
    record_search_request,
)
from modules.zones.isochrone_proxy import build_isochrone_proxy_circle
from pydantic import BaseModel
from sqlalchemy import text
from modules.jobs.service import enqueue_job, get_job

router = APIRouter(prefix="/journeys", tags=["listings"])


def _cache_display_platforms(
    cache: dict[str, object] | None,
    requested_platforms: list[str],
) -> list[str]:
    if not cache:
        return requested_platforms

    raw_completed = cache.get("platforms_completed")
    if not isinstance(raw_completed, list) or not raw_completed:
        return requested_platforms

    completed = {str(name) for name in raw_completed if str(name).strip()}
    filtered = [platform for platform in requested_platforms if platform in completed]
    return filtered or requested_platforms


class ListingsSearchRequest(BaseModel):
    zone_fingerprint: str
    search_location_normalized: str
    search_location_label: str
    search_location_type: str  # 'neighborhood' | 'street' | 'address' | 'landmark'
    search_type: str           # 'rent' | 'sale'
    usage_type: str = "residential"
    # PRO plan future: pass platform list; for now always FREE
    platforms: list[str] | None = None


class ListingsScrapePlanPlatform(BaseModel):
    platform: str
    max_pages: int


class ListingsScrapePlanResponse(BaseModel):
    search_type: str
    usage_type: str
    total_pages: int
    platforms: list[ListingsScrapePlanPlatform]


async def _enqueue_listings_scrape_job(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    search_location_normalized: str,
    search_address: str,
    search_type: str,
    usage_type: str,
    platforms: list[str],
    force_refresh: bool = False,
) -> UUID:
    """Create and dispatch a listings_scrape job, returning the created job id."""
    normalized_search_location = normalize_search_location(search_location_normalized)

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
                        "search_location_normalized": normalized_search_location,
                        "search_address": search_address,
                        "search_type": search_type,
                        "usage_type": usage_type,
                        "platforms": platforms,
                        "force_refresh": force_refresh,
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


async def _find_active_listings_job_id(
    journey_id: UUID,
    zone_fingerprint: str | None = None,
    search_location_normalized: str | None = None,
) -> UUID | None:
    normalized_search_location = normalize_search_location(search_location_normalized)

    engine = _get_engine()
    async with engine.connect() as conn:
        if normalized_search_location:
            result = await conn.execute(
                text(
                    """
                    SELECT id
                    FROM jobs
                    WHERE journey_id = :journey_id
                      AND job_type = 'listings_scrape'
                      AND state IN ('pending', 'running', 'retrying')
                      AND result_ref->>'search_location_normalized' = :search_location_normalized
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "journey_id": journey_id,
                    "search_location_normalized": normalized_search_location,
                },
            )
            return result.scalar_one_or_none()

        if zone_fingerprint is None:
            return None

        result = await conn.execute(
            text(
                """
                SELECT id
                FROM jobs
                WHERE journey_id = :journey_id
                  AND job_type = 'listings_scrape'
                  AND state IN ('pending', 'running', 'retrying')
                  AND result_ref->>'zone_fingerprint' = :zone_fingerprint
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
                        {
                                "journey_id": journey_id,
                                "zone_fingerprint": zone_fingerprint,
                        },
        )
        return result.scalar_one_or_none()


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
    normalized_search_location = normalize_search_location(body.search_location_normalized)

    if not normalized_search_location:
        raise HTTPException(status_code=400, detail="search_location_normalized nao pode ser vazio")

    # Determine result source.
    # Cache hits for listings/search must be address-scoped to avoid reusing
    # results scraped with a different search address in the same zone.
    cache = await find_usable_cache_for_search_location(normalized_search_location)

    if cache and cache_is_usable(cache):
        result_source = "cache_hit"
    else:
        result_source = "cache_miss"

    # Always record demand (including misses -- drives prewarm)
    await record_search_request(
        journey_id=journey_id,
        session_id=anonymous_session_id,
        zone_fingerprint=body.zone_fingerprint,
        search_location_normalized=normalized_search_location,
        search_location_label=body.search_location_label,
        search_location_type=body.search_location_type,
        search_type=body.search_type,
        usage_type=body.usage_type,
        platforms_hash=platforms_hash,
        result_source=result_source,
    )

    if result_source == "cache_miss":
        active_job_id = await _find_active_listings_job_id(
            journey_id,
            search_location_normalized=normalized_search_location,
        )
        if active_job_id is not None:
            return ListingsRequestResult(
                source="none",
                job_id=active_job_id,
                freshness_status="queued_for_next_prewarm",
                upgrade_reason="fresh_listings",
                next_refresh_window="03:00-05:30",
                listings=[],
                total_count=0,
            )

        # Ensure cache row exists (for lock coordination) and enqueue scrape job
        await create_cache_record(
            normalized_search_location,
            zone_fingerprint=body.zone_fingerprint,
            config_hash=config_hash,
        )

        job_id = await _enqueue_listings_scrape_job(
            journey_id=journey_id,
            zone_fingerprint=body.zone_fingerprint,
            search_location_normalized=normalized_search_location,
            search_address=body.search_location_label,
            search_type=body.search_type,
            usage_type=body.usage_type,
            platforms=platforms,
            force_refresh=False,
        )

        return ListingsRequestResult(
            source="none",
            job_id=job_id,
            freshness_status="queued_for_next_prewarm",
            upgrade_reason="fresh_listings",
            next_refresh_window="03:00-05:30",
            listings=[],
            total_count=0,
        )

    # Cache hit or partial hit -- return listings
    display_platforms = _cache_display_platforms(cache, platforms)
    listing_cards_raw = await fetch_listing_cards_for_zone(
        zone_fingerprint=body.zone_fingerprint,
        search_type=body.search_type,
        usage_type=body.usage_type,
        platforms=display_platforms,
        observed_since=cache.get("created_at"),
    )

    age_hours = cache_age_hours(cache)
    freshness = "fresh"

    # Listings cache remains valid by default; background refresh only happens
    # for explicit partial-hit flows.
    should_revalidate = result_source == "cache_partial"
    if should_revalidate:
        active_job_id = await _find_active_listings_job_id(
            journey_id,
            search_location_normalized=normalized_search_location,
        )
        if active_job_id is None:
            await create_cache_record(
                normalized_search_location,
                zone_fingerprint=body.zone_fingerprint,
                config_hash=config_hash,
            )
            await _enqueue_listings_scrape_job(
                journey_id=journey_id,
                zone_fingerprint=body.zone_fingerprint,
                search_location_normalized=normalized_search_location,
                search_address=body.search_location_label,
                search_type=body.search_type,
                usage_type=body.usage_type,
                platforms=platforms,
                force_refresh=True,
            )

    return ListingsRequestResult(
        source="cache",
        freshness_status=freshness,
        listings=listing_cards_raw,  # type: ignore[arg-type]
        total_count=len(listing_cards_raw),
        cache_age_hours=age_hours,
    )


@router.get(
    "/{journey_id}/listings/scrape-plan",
    response_model=ListingsScrapePlanResponse,
)
async def get_listings_scrape_plan(
    journey_id: UUID,
    search_type: str = Query(default="rent"),
    usage_type: str = Query(default="residential"),
    platforms: list[str] | None = Query(default=None),
) -> ListingsScrapePlanResponse:
    del journey_id
    try:
        registry = get_platform_registry()
    except PlatformRegistryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    raw_platforms = platforms or registry.default_free_platforms()
    try:
        canonical_platforms = registry.resolve_names(raw_platforms)
    except PlatformRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    platform_plan = [
        ListingsScrapePlanPlatform(
            platform=platform,
            max_pages=int(registry.scraper_config_for(platform).get("max_pages", 1) or 1),
        )
        for platform in canonical_platforms
    ]

    return ListingsScrapePlanResponse(
        search_type=search_type,
        usage_type=usage_type,
        total_pages=sum(item.max_pages for item in platform_plan),
        platforms=platform_plan,
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
            - `walking`/`car`: single radial Tilequery + reverse geocode on zone centroid
            - `transit`: sample points inside zone geometry, then Tilequery + reverse geocode
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
                    z.modal,
                    ST_AsGeoJSON(z.isochrone_geom) AS isochrone_geom,
                    ST_X(ST_Centroid(z.isochrone_geom)) AS centroid_lon,
                    ST_Y(ST_Centroid(z.isochrone_geom)) AS centroid_lat,
                    ST_Area(z.isochrone_geom::geography) AS area_m2,
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

    try:
        proxy_circle = build_isochrone_proxy_circle(
            lon=float(zone["centroid_lon"]),
            lat=float(zone["centroid_lat"]),
            area_m2=float(zone["area_m2"]),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Zona invalida para proxy circular de enderecos",
        ) from exc

    settings = get_settings()
    raw_suggestions = await get_zone_address_suggestions(
        access_token=settings.mapbox_access_token,
        zone_fingerprint=str(zone["fingerprint"]),
        geometry=proxy_circle["geometry"],
        bbox=proxy_circle["bbox"],
        centroid=(float(zone["centroid_lon"]), float(zone["centroid_lat"])),
        modal=str(zone["modal"] or ""),
        search_radius_m=float(proxy_circle["radius_m"]),
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
    spatial_scope: str = Query(default="inside_zone"),
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

    if spatial_scope not in {"inside_zone", "all"}:
        raise HTTPException(status_code=400, detail="spatial_scope deve ser 'inside_zone' ou 'all'")

    latest_search = await get_latest_search_request_for_zone(journey_id, zone_fingerprint)
    cache = await get_cache_record(
        latest_search["search_location_normalized"] if latest_search else None
    )

    if not cache or not cache_is_usable(cache):
        active_job_id = await _find_active_listings_job_id(
            journey_id,
            zone_fingerprint=zone_fingerprint,
            search_location_normalized=(
                str(latest_search["search_location_normalized"]) if latest_search else None
            ),
        )
        return ListingsRequestResult(
            source="none",
            job_id=active_job_id,
            freshness_status="no_cache",
            listings=[],
            total_count=0,
        )

    display_platforms = _cache_display_platforms(cache, canonical_platforms)
    listing_cards_raw = await fetch_listing_cards_for_zone(
        zone_fingerprint=zone_fingerprint,
        search_type=search_type,
        usage_type=usage_type,
        platforms=display_platforms,
        observed_since=cache.get("created_at"),
        spatial_scope=spatial_scope,
    )
    age_hours = cache_age_hours(cache)
    freshness = "fresh"

    return ListingsRequestResult(
        source="cache",
        freshness_status=freshness,
        listings=listing_cards_raw,  # type: ignore[arg-type]
        total_count=len(listing_cards_raw),
        cache_age_hours=age_hours,
    )


__all__ = ["router"]
