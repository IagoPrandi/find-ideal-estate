"""M6.1 – price rollup computation and retention for property_price_rollups.

Public API:
    compute_and_upsert_rollup(conn, zone_fingerprint, search_type, target_date)
    purge_old_rollups(conn)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# ---------------------------------------------------------------------------
# Helpers (pure Python, testable without DB)
# ---------------------------------------------------------------------------

RETENTION_DAYS = 365


def is_median_within_iqr(
    p25: Decimal | float | None,
    median: Decimal | float | None,
    p75: Decimal | float | None,
) -> bool:
    """Return True if median falls within [p25, p75] (inclusive)."""
    if p25 is None or median is None or p75 is None:
        return False
    return float(p25) <= float(median) <= float(p75)


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------


async def compute_and_upsert_rollup(
    conn: AsyncConnection,
    zone_fingerprint: str,
    search_type: str,
    target_date: date | None = None,
) -> dict[str, Any]:
    """Compute price percentiles for *zone_fingerprint/search_type* on *target_date*
    (defaults to today UTC) and upsert into ``property_price_rollups``.

    Returns the upserted row as a dict with keys:
    ``date, zone_fingerprint, search_type, median_price, p25_price, p75_price, sample_count``
    """
    if target_date is None:
        target_date = datetime.now(tz=timezone.utc).date()

    stats_row = await conn.execute(
        text(
            """
            WITH zone_props AS (
                SELECT p.id AS property_id
                FROM   properties p
                JOIN   zones z ON z.fingerprint = :zone_fp
                WHERE  ST_Within(p.location, z.isochrone_geom)
            ),
            active_prices AS (
                SELECT ls.price
                FROM   listing_snapshots  ls
                JOIN   listing_ads        la ON la.id = ls.listing_ad_id
                WHERE  la.property_id = ANY(
                           SELECT property_id FROM zone_props
                       )
                  AND  la.advertised_usage_type = :search_type
                  AND  la.is_active = true
                  AND  ls.price IS NOT NULL
                  AND  (ls.availability_state = 'active' OR ls.availability_state IS NULL)
            )
            SELECT
                percentile_cont(0.25) WITHIN GROUP (ORDER BY price) AS p25,
                percentile_cont(0.50) WITHIN GROUP (ORDER BY price) AS median,
                percentile_cont(0.75) WITHIN GROUP (ORDER BY price) AS p75,
                COUNT(*)                                             AS sample_count
            FROM active_prices
            """
        ),
        {"zone_fp": zone_fingerprint, "search_type": search_type},
    )

    stats = stats_row.mappings().first() or {}
    p25 = stats.get("p25")
    median = stats.get("median")
    p75 = stats.get("p75")
    sample_count = int(stats.get("sample_count") or 0)

    upsert_row = await conn.execute(
        text(
            """
            INSERT INTO property_price_rollups
                (date, zone_fingerprint, search_type,
                 median_price, p25_price, p75_price, sample_count, computed_at)
            VALUES
                (:date, :zone_fp, :search_type,
                 :median, :p25, :p75, :sample_count, now())
            ON CONFLICT (date, zone_fingerprint, search_type) DO UPDATE
                SET median_price  = EXCLUDED.median_price,
                    p25_price     = EXCLUDED.p25_price,
                    p75_price     = EXCLUDED.p75_price,
                    sample_count  = EXCLUDED.sample_count,
                    computed_at   = EXCLUDED.computed_at
            RETURNING id, date, zone_fingerprint, search_type,
                      median_price, p25_price, p75_price, sample_count, computed_at
            """
        ),
        {
            "date": target_date,
            "zone_fp": zone_fingerprint,
            "search_type": search_type,
            "median": median,
            "p25": p25,
            "p75": p75,
            "sample_count": sample_count,
        },
    )

    return dict(upsert_row.mappings().first() or {})


async def purge_old_rollups(conn: AsyncConnection) -> int:
    """Delete rollup rows older than RETENTION_DAYS days.  Returns deleted row count."""
    result = await conn.execute(
        text(
            "DELETE FROM property_price_rollups "
            "WHERE date < CURRENT_DATE - :days * INTERVAL '1 day' "
            "RETURNING id"
        ),
        {"days": RETENTION_DAYS},
    )
    return result.rowcount


async def fetch_rollups_for_zone(
    conn: AsyncConnection,
    zone_fingerprint: str,
    search_type: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Return up to *days* most recent rollup rows for a zone, newest first."""
    rows = await conn.execute(
        text(
            """
            SELECT id, date, zone_fingerprint, search_type,
                   median_price, p25_price, p75_price, sample_count, computed_at
            FROM   property_price_rollups
            WHERE  zone_fingerprint = :zone_fp
              AND  search_type      = :search_type
              AND  date >= CURRENT_DATE - :days * INTERVAL '1 day'
            ORDER  BY date DESC
            LIMIT  :days
            """
        ),
        {"zone_fp": zone_fingerprint, "search_type": search_type, "days": days},
    )
    return [dict(r) for r in rows.mappings()]
