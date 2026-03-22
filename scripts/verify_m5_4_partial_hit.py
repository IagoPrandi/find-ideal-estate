from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from core.db import close_db, get_engine, init_db  # noqa: E402
from modules.listings.cache import (  # noqa: E402
    compute_config_hash,
    find_partial_hit_from_overlapping_zone,
)
from modules.listings.dedup import (  # noqa: E402
    compute_property_fingerprint,
    fetch_listing_cards_for_zone,
    upsert_property_and_ad,
)
from modules.listings.models import ZoneCacheStatus  # noqa: E402
from sqlalchemy import text  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PRD M5.4 verification: zone B with >=70% overlap must reuse a "
            "partial cache hit from zone A."
        )
    )
    parser.add_argument(
        "--search-type",
        choices=["rent", "sale"],
        default="rent",
        help="Listing search type used for cache config hash.",
    )
    parser.add_argument(
        "--usage-type",
        default="residential",
        help="Usage type used for cache config hash.",
    )
    parser.add_argument(
        "--platforms",
        default="quintoandar,zapimoveis",
        help="Comma-separated platform names used in config hash.",
    )
    parser.add_argument(
        "--min-overlap",
        type=float,
        default=0.70,
        help="Minimum overlap ratio required for partial hit assertion.",
    )
    return parser.parse_args()


async def _ensure_required_tables() -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    to_regclass('public.zones') IS NOT NULL
                    AND to_regclass('public.zone_listing_caches') IS NOT NULL
                    AND to_regclass('public.properties') IS NOT NULL
                    AND to_regclass('public.listing_ads') IS NOT NULL
                    AND to_regclass('public.listing_snapshots') IS NOT NULL
                """
            )
        )
        ready = bool(result.scalar())
        if not ready:
            raise RuntimeError(
                "Required Phase 5 tables not found. Run alembic upgrade head before verification."
            )


def _square_polygon_wkt(*, min_lon: float, min_lat: float, side: float) -> str:
    max_lon = min_lon + side
    max_lat = min_lat + side
    return (
        f"POLYGON(({min_lon} {min_lat},"
        f"{max_lon} {min_lat},"
        f"{max_lon} {max_lat},"
        f"{min_lon} {max_lat},"
        f"{min_lon} {min_lat}))"
    )


async def _insert_zone(*, fingerprint: str, polygon_wkt: str) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO zones (
                    fingerprint,
                    modal,
                    max_time_minutes,
                    radius_meters,
                    state,
                    isochrone_geom,
                    created_at,
                    updated_at
                ) VALUES (
                    :fingerprint,
                    'walking',
                    30,
                    1500,
                    'complete',
                    ST_SetSRID(ST_GeomFromText(:wkt), 4326),
                    now(),
                    now()
                )
                """
            ),
            {"fingerprint": fingerprint, "wkt": polygon_wkt},
        )


async def _insert_cache_for_zone_a(
    *,
    zone_fingerprint: str,
    config_hash: str,
    platforms: list[str],
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO zone_listing_caches (
                    zone_fingerprint,
                    config_hash,
                    status,
                    platforms_completed,
                    platforms_failed,
                    coverage_ratio,
                    preliminary_count,
                    scraped_at,
                    expires_at,
                    created_at
                ) VALUES (
                    :zone_fingerprint,
                    :config_hash,
                    :status,
                    CAST(:platforms_completed AS text[]),
                    CAST(:platforms_failed AS text[]),
                    1.0,
                    1,
                    :scraped_at,
                    :expires_at,
                    now()
                )
                """
            ),
            {
                "zone_fingerprint": zone_fingerprint,
                "config_hash": config_hash,
                "status": ZoneCacheStatus.COMPLETE,
                "platforms_completed": platforms,
                "platforms_failed": [],
                "scraped_at": datetime.now(tz=timezone.utc),
                "expires_at": datetime.now(tz=timezone.utc) + timedelta(hours=12),
            },
        )


async def _insert_listing_inside_zone_a(*, platform: str, platform_listing_id: str) -> str:
    lat = -23.5500
    lon = -46.6320
    address = "Rua M5.4 Verificacao, 100 - Sao Paulo"
    fingerprint = compute_property_fingerprint(
        address_normalized=address,
        lat=lat,
        lon=lon,
        area_m2=70,
        bedrooms=2,
    )
    await upsert_property_and_ad(
        fingerprint=fingerprint,
        address_normalized=address,
        lat=lat,
        lon=lon,
        area_m2=70,
        bedrooms=2,
        bathrooms=1,
        parking=1,
        usage_type="residential",
        platform=platform,
        platform_listing_id=platform_listing_id,
        url="https://example.org/m54-partial-hit",
        advertised_usage_type="rent",
        price=Decimal("3500"),
        condo_fee=Decimal("500"),
        iptu=Decimal("120"),
        raw_payload={"m5_4_verification": True},
    )
    return fingerprint


async def _overlap_ratio(src_fp: str, alt_fp: str) -> float:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    ST_Area(ST_Intersection(src.isochrone_geom, alt.isochrone_geom))
                    / NULLIF(ST_Area(src.isochrone_geom), 0) AS overlap_ratio
                FROM zones src
                JOIN zones alt ON alt.fingerprint = :alt_fp
                WHERE src.fingerprint = :src_fp
                LIMIT 1
                """
            ),
            {"src_fp": src_fp, "alt_fp": alt_fp},
        )
        return float(result.scalar_one() or 0.0)


async def _cleanup(
    *,
    zone_a_fp: str,
    zone_b_fp: str,
    config_hash: str,
    property_fp: str,
    platform_listing_id: str,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DELETE FROM listing_snapshots
                WHERE listing_ad_id IN (
                    SELECT id FROM listing_ads WHERE platform_listing_id = :platform_listing_id
                )
                """
            ),
            {"platform_listing_id": platform_listing_id},
        )
        await conn.execute(
            text("DELETE FROM listing_ads WHERE platform_listing_id = :platform_listing_id"),
            {"platform_listing_id": platform_listing_id},
        )
        await conn.execute(
            text("DELETE FROM properties WHERE fingerprint = :fingerprint"),
            {"fingerprint": property_fp},
        )
        await conn.execute(
            text(
                """
                DELETE FROM zone_listing_caches
                WHERE config_hash = :config_hash
                  AND zone_fingerprint = ANY(CAST(:zone_fingerprints AS text[]))
                """
            ),
            {"config_hash": config_hash, "zone_fingerprints": [zone_a_fp, zone_b_fp]},
        )
        await conn.execute(
            text("DELETE FROM zones WHERE fingerprint = ANY(CAST(:zone_fingerprints AS text[]))"),
            {"zone_fingerprints": [zone_a_fp, zone_b_fp]},
        )


async def main() -> int:
    args = parse_args()
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    init_db(database_url)

    platforms = [item.strip().lower() for item in args.platforms.split(",") if item.strip()]
    if not platforms:
        raise ValueError("--platforms must contain at least one platform")

    config_hash = compute_config_hash(args.search_type, args.usage_type, platforms)
    zone_a_fp = f"m54-zone-a-{uuid4().hex[:10]}"
    zone_b_fp = f"m54-zone-b-{uuid4().hex[:10]}"
    platform_listing_id = f"m54-{uuid4().hex[:10]}"
    property_fp = ""

    # Build deterministic 70% overlap between B (source) and A (cached zone).
    side = 0.02
    shift = side * 0.30
    base_lon = -46.64
    base_lat = -23.56
    polygon_a_wkt = _square_polygon_wkt(min_lon=base_lon, min_lat=base_lat, side=side)
    polygon_b_wkt = _square_polygon_wkt(min_lon=base_lon + shift, min_lat=base_lat, side=side)

    await _ensure_required_tables()

    try:
        await _insert_zone(fingerprint=zone_a_fp, polygon_wkt=polygon_a_wkt)
        await _insert_zone(fingerprint=zone_b_fp, polygon_wkt=polygon_b_wkt)
        await _insert_cache_for_zone_a(
            zone_fingerprint=zone_a_fp,
            config_hash=config_hash,
            platforms=platforms,
        )
        property_fp = await _insert_listing_inside_zone_a(
            platform=platforms[0],
            platform_listing_id=platform_listing_id,
        )

        ratio = await _overlap_ratio(zone_b_fp, zone_a_fp)
        partial = await find_partial_hit_from_overlapping_zone(zone_b_fp, config_hash)
        cards = await fetch_listing_cards_for_zone(
            zone_fingerprint=zone_a_fp,
            search_type=args.search_type,
            usage_type=args.usage_type,
            platforms=platforms,
        )

        print(f"zone_a={zone_a_fp}")
        print(f"zone_b={zone_b_fp}")
        print(f"config_hash={config_hash}")
        print(f"overlap_ratio={ratio:.4f}")
        print(f"partial_hit_zone={(partial or {}).get('zone_fingerprint')}")
        print(f"cards_from_zone_a={len(cards)}")

        if ratio < args.min_overlap:
            raise RuntimeError(
                f"PRD M5.4 verification failed: overlap ratio {ratio:.4f} < {args.min_overlap:.4f}"
            )
        if partial is None:
            raise RuntimeError(
                "PRD M5.4 verification failed: no partial cache hit found for zone B"
            )
        if partial.get("zone_fingerprint") != zone_a_fp:
            raise RuntimeError(
                "PRD M5.4 verification failed: partial hit did not reuse zone A cache"
            )
        if len(cards) == 0:
            raise RuntimeError(
                "PRD M5.4 verification failed: zone A cache has no listing cards to serve"
            )

        print("[OK] M5.4 verification passed")
        return 0
    finally:
        await _cleanup(
            zone_a_fp=zone_a_fp,
            zone_b_fp=zone_b_fp,
            config_hash=config_hash,
            property_fp=property_fp,
            platform_listing_id=platform_listing_id,
        )
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
