"""Property fingerprint computation and deduplication upsert logic."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from typing import Any
from uuid import UUID

from core.db import get_engine
from sqlalchemy import text


def _normalize_address(address: str | None) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    if not address:
        return ""
    nfkd = unicodedata.normalize("NFKD", address)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    lower = ascii_only.lower()
    return re.sub(r"\s+", " ", lower).strip()


def compute_property_fingerprint(
    address_normalized: str | None,
    lat: float | None,
    lon: float | None,
    area_m2: float | None,
    bedrooms: int | None,
) -> str:
    """
    SHA-256 fingerprint over canonical property identity fields.

    lat/lon rounded to 4 decimal digits (~10m), area rounded to nearest int.
    Returns a 64-char hex string.
    """
    canonical: dict[str, Any] = {
        "address": _normalize_address(address_normalized),
        "area_m2": round(float(area_m2)) if area_m2 is not None else None,
        "bedrooms": int(bedrooms) if bedrooms is not None else None,
        "lat": round(float(lat), 4) if lat is not None else None,
        "lon": round(float(lon), 4) if lon is not None else None,
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def upsert_property_and_ad(
    *,
    fingerprint: str,
    address_normalized: str | None,
    lat: float | None,
    lon: float | None,
    area_m2: float | None,
    bedrooms: int | None,
    bathrooms: int | None,
    parking: int | None,
    usage_type: str | None,
    platform: str,
    platform_listing_id: str,
    url: str | None,
    advertised_usage_type: str | None,
    price: Decimal | None,
    condo_fee: Decimal | None,
    iptu: Decimal | None,
    raw_payload: dict[str, Any] | None,
) -> tuple[UUID, UUID]:
    """
    Upsert a property + listing_ad + snapshot atomically.

    Returns (property_id, listing_ad_id).

    Strategy:
    - Properties:    INSERT … ON CONFLICT (fingerprint) DO NOTHING, then re-query.
    - listing_ads:   INSERT … ON CONFLICT (platform, platform_listing_id) DO UPDATE
                     last_seen_at = now(), is_active = true.
    - listing_snapshots: always INSERT (append-only price history).
    """
    engine = get_engine()

    geom_expr = (
        f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"
        if lat is not None and lon is not None
        else "NULL"
    )

    async with engine.begin() as conn:
        # 1. Upsert property
        await conn.execute(
            text(
                f"""
                INSERT INTO properties (
                    address_normalized, location, area_m2, bedrooms, bathrooms,
                    parking, usage_type, fingerprint
                ) VALUES (
                    :address_normalized,
                    {geom_expr},
                    :area_m2, :bedrooms, :bathrooms,
                    :parking, :usage_type, :fingerprint
                )
                ON CONFLICT (fingerprint) DO NOTHING
                """
            ),
            {
                "address_normalized": address_normalized,
                "area_m2": area_m2,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "parking": parking,
                "usage_type": usage_type,
                "fingerprint": fingerprint,
            },
        )

        property_row = await conn.execute(
            text("SELECT id FROM properties WHERE fingerprint = :fp"),
            {"fp": fingerprint},
        )
        property_id: UUID = property_row.scalar_one()

        # 2. Upsert listing_ad
        await conn.execute(
            text(
                """
                INSERT INTO listing_ads (
                    property_id, platform, platform_listing_id,
                    url, advertised_usage_type
                ) VALUES (
                    :property_id, :platform, :platform_listing_id,
                    :url, :advertised_usage_type
                )
                ON CONFLICT (platform, platform_listing_id) DO UPDATE
                    SET last_seen_at = now(),
                        is_active = true,
                        url = EXCLUDED.url
                """
            ),
            {
                "property_id": property_id,
                "platform": platform,
                "platform_listing_id": platform_listing_id,
                "url": url,
                "advertised_usage_type": advertised_usage_type,
            },
        )

        ad_row = await conn.execute(
            text(
                "SELECT id FROM listing_ads WHERE platform = :platform "
                "AND platform_listing_id = :plid"
            ),
            {"platform": platform, "plid": platform_listing_id},
        )
        listing_ad_id: UUID = ad_row.scalar_one()

        # 3. Append snapshot
        await conn.execute(
            text(
                """
                INSERT INTO listing_snapshots (
                    listing_ad_id, price, condo_fee, iptu, availability_state, raw_payload
                ) VALUES (
                    :listing_ad_id, :price, :condo_fee, :iptu, 'active', :raw_payload
                )
                """
            ),
            {
                "listing_ad_id": listing_ad_id,
                "price": price,
                "condo_fee": condo_fee,
                "iptu": iptu,
                "raw_payload": json.dumps(raw_payload) if raw_payload else None,
            },
        )

    return property_id, listing_ad_id


async def fetch_listing_cards_for_zone(
    zone_fingerprint: str,
    search_type: str,
    usage_type: str,
    platforms: list[str],
) -> list[dict[str, Any]]:
    """
    Return flattened listing cards for the given zone fingerprint.
    Uses ST_Within to ensure properties are inside the zone polygon.
    Computes current_best_price and second_best_price across active ads.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                WITH best_prices AS (
                    SELECT
                        la.property_id,
                        la.platform,
                        la.platform_listing_id,
                        la.url,
                        la.advertised_usage_type,
                        ls.price,
                        ls.observed_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY la.property_id
                            ORDER BY ls.price ASC NULLS LAST, ls.observed_at DESC
                        ) AS price_rank
                    FROM listing_ads la
                    JOIN listing_snapshots ls ON ls.listing_ad_id = la.id
                    WHERE la.is_active = true
                      AND la.platform = ANY(:platforms)
                      AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                ),
                zone_props AS (
                    SELECT p.id AS property_id
                    FROM properties p
                    JOIN zones z ON z.fingerprint = :zone_fp
                    WHERE ST_Within(p.location, z.isochrone_geom)
                      AND (p.usage_type = :usage_type OR :usage_type = 'all')
                )
                SELECT
                    p.id              AS property_id,
                    p.address_normalized,
                    p.area_m2,
                    p.bedrooms,
                    p.bathrooms,
                    p.parking,
                    p.usage_type,
                    bp.platform,
                    bp.platform_listing_id,
                    bp.url,
                    bp.price          AS current_best_price,
                    bp.observed_at,
                    (
                        SELECT bp2.price
                        FROM best_prices bp2
                        WHERE bp2.property_id = p.id
                          AND bp2.price_rank = 2
                        LIMIT 1
                    )                  AS second_best_price,
                    (
                        SELECT COUNT(DISTINCT la2.platform)
                        FROM listing_ads la2
                        WHERE la2.property_id = p.id
                          AND la2.is_active = true
                          AND la2.platform = ANY(:platforms)
                    )                  AS platform_count
                FROM properties p
                JOIN zone_props zp ON zp.property_id = p.id
                JOIN best_prices bp ON bp.property_id = p.id AND bp.price_rank = 1
                ORDER BY bp.price ASC NULLS LAST
                """
            ),
            {
                "zone_fp": zone_fingerprint,
                "usage_type": usage_type,
                "platforms": platforms,
            },
        )

        cards = []
        for row in rows.mappings():
            platform_count = row["platform_count"] or 1
            second_price = row["second_best_price"]
            best_price = row["current_best_price"]
            dup_badge = None
            if platform_count >= 2 and best_price is not None:
                price_fmt = f"R$ {int(best_price):,}".replace(",", ".")
                dup_badge = f"Disponível em {platform_count} plataformas · menor: {price_fmt}"

            cards.append(
                {
                    "property_id": str(row["property_id"]),
                    "address_normalized": row["address_normalized"],
                    "area_m2": row["area_m2"],
                    "bedrooms": row["bedrooms"],
                    "bathrooms": row["bathrooms"],
                    "parking": row["parking"],
                    "usage_type": row["usage_type"],
                    "platform": row["platform"],
                    "platform_listing_id": row["platform_listing_id"],
                    "url": row["url"],
                    "current_best_price": str(best_price) if best_price else None,
                    "second_best_price": str(second_price) if second_price else None,
                    "duplication_badge": dup_badge,
                    "observed_at": row["observed_at"].isoformat() if row["observed_at"] else None,
                }
            )
        return cards
