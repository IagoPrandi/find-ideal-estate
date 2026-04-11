"""Records confirmed listing search requests for prewarm demand tracking (M5.6).

Every click on "Buscar imóveis" in Step 5 calls record_search_request().
The prewarm scheduler queries this table to find high-demand addresses.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from core.db import get_engine
from modules.listings.cache import normalize_search_location
from sqlalchemy import text


async def record_search_request(
    *,
    zone_fingerprint: str,
    search_location_normalized: str,
    search_location_label: str,
    search_location_type: str,
    search_type: str,
    usage_type: str,
    platforms_hash: str,
    result_source: str,
    journey_id: UUID | None = None,
    user_id: UUID | None = None,
    session_id: str | None = None,
) -> UUID:
    """
    Persist a confirmed search request. Returns the new row id.

    result_source must be one of:
        'cache_hit' | 'cache_partial' | 'cache_miss' | 'fresh_scrape'
    """
    normalized_search_location = normalize_search_location(search_location_normalized)

    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO listing_search_requests (
                    journey_id, user_id, session_id,
                    zone_fingerprint,
                    search_location_normalized,
                    search_location_label,
                    search_location_type,
                    search_type,
                    usage_type,
                    platforms_hash,
                    result_source
                ) VALUES (
                    :journey_id, :user_id, :session_id,
                    :zone_fingerprint,
                    :search_location_normalized,
                    :search_location_label,
                    :search_location_type,
                    :search_type,
                    :usage_type,
                    :platforms_hash,
                    :result_source
                )
                RETURNING id
                """
            ),
            {
                "journey_id": journey_id,
                "user_id": user_id,
                "session_id": session_id,
                "zone_fingerprint": zone_fingerprint,
                "search_location_normalized": normalized_search_location,
                "search_location_label": search_location_label,
                "search_location_type": search_location_type,
                "search_type": search_type,
                "usage_type": usage_type,
                "platforms_hash": platforms_hash,
                "result_source": result_source,
            },
        )
        return result.scalar_one()


async def get_prewarm_targets(
    lookback_hours: int = 24,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Return the top search locations requested in the last `lookback_hours`,
    ordered by demand count DESC, then most-recent first.

    Used by the Phase-7 prewarm scheduler.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
    engine = get_engine()
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                WITH demand AS (
                    SELECT
                        search_location_normalized,
                        search_location_label,
                        search_location_type,
                        search_type,
                        usage_type,
                        platforms_hash,
                        COUNT(*)          AS demand_count,
                        MAX(requested_at) AS last_requested_at
                    FROM listing_search_requests
                    WHERE requested_at >= :since
                    GROUP BY
                        search_location_normalized,
                        search_location_label,
                        search_location_type,
                        search_type,
                        usage_type,
                        platforms_hash
                )
                SELECT
                    d.search_location_normalized,
                    d.search_location_label,
                    d.search_location_type,
                    d.search_type,
                    d.usage_type,
                    d.platforms_hash,
                    d.demand_count,
                    d.last_requested_at,
                    recent.zone_fingerprint,
                    zlc.status AS cache_status,
                    COALESCE(
                        EXTRACT(EPOCH FROM (
                            now() - COALESCE(
                                zlc.last_prewarmed_at,
                                zlc.scraped_at,
                                zlc.created_at
                            )
                        )) / 3600.0,
                        1000000000.0
                    ) AS cache_age_hours,
                    zlc.last_prewarmed_at,
                    zlc.scraped_at
                FROM demand d
                JOIN LATERAL (
                    SELECT lsr.zone_fingerprint
                    FROM listing_search_requests lsr
                    WHERE lsr.search_location_normalized = d.search_location_normalized
                      AND lsr.search_location_label = d.search_location_label
                      AND lsr.search_location_type = d.search_location_type
                      AND lsr.search_type = d.search_type
                      AND lsr.usage_type = d.usage_type
                      AND lsr.platforms_hash = d.platforms_hash
                    ORDER BY lsr.requested_at DESC
                    LIMIT 1
                ) recent ON TRUE
                LEFT JOIN zone_listing_caches zlc
                  ON zlc.search_location_normalized = d.search_location_normalized
                ORDER BY demand_count DESC, last_requested_at DESC, cache_age_hours DESC
                LIMIT :limit
                """
            ),
            {"since": since, "limit": limit},
        )
        return [dict(row) for row in rows.mappings()]


async def get_latest_search_request_for_zone(
    journey_id: UUID,
    zone_fingerprint: str,
) -> dict[str, Any] | None:
    """Return the most recent confirmed Step 5 search for a journey zone."""
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    search_location_normalized,
                    search_location_label,
                    search_location_type,
                    search_type,
                    usage_type,
                    platforms_hash,
                    result_source,
                    requested_at
                FROM listing_search_requests
                WHERE journey_id = :journey_id
                  AND zone_fingerprint = :zone_fingerprint
                ORDER BY requested_at DESC
                LIMIT 1
                """
            ),
            {"journey_id": journey_id, "zone_fingerprint": zone_fingerprint},
        )
        row = result.mappings().first()
        return dict(row) if row else None
