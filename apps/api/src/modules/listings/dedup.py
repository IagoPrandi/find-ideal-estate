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
                ON CONFLICT (fingerprint) DO UPDATE
                    SET usage_type = COALESCE(EXCLUDED.usage_type, properties.usage_type)
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
    observed_since: Any | None = None,
    spatial_scope: str = "inside_zone",
) -> list[dict[str, Any]]:
    """
    Return flattened listing cards for the given zone fingerprint.
    Supports either only listings inside the selected zone or the broader set
    of scraped listings, including items without coordinates.
    """
    engine = get_engine()

    def _serialize_money(raw_value: Any) -> str | None:
        if raw_value is None:
            return None
        decimal_value = raw_value if isinstance(raw_value, Decimal) else Decimal(str(raw_value))
        return format(decimal_value.quantize(Decimal("0.01")), "f")

    def _serialize_platform_variant(raw_variant: dict[str, Any]) -> dict[str, Any]:
        observed_at = raw_variant.get("observed_at")
        if hasattr(observed_at, "isoformat"):
            observed_at_value = observed_at.isoformat()
        else:
            observed_at_value = observed_at

        return {
            "platform": raw_variant.get("platform"),
            "platform_listing_id": raw_variant.get("platform_listing_id"),
            "url": raw_variant.get("url"),
            "current_best_price": _serialize_money(raw_variant.get("current_best_price")),
            "condo_fee": _serialize_money(raw_variant.get("condo_fee")),
            "iptu": _serialize_money(raw_variant.get("iptu")),
            "observed_at": observed_at_value,
        }

    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                WITH ranked_prices AS (
                    SELECT
                        la.property_id,
                        la.platform,
                        la.platform_listing_id,
                        la.url,
                        la.advertised_usage_type,
                        ls.price,
                        ls.condo_fee,
                        ls.iptu,
                        ls.raw_payload->>'image_url' AS image_url,
                        ls.observed_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY la.property_id
                            ORDER BY ls.price ASC NULLS LAST, ls.observed_at DESC
                        ) AS price_rank,
                        ROW_NUMBER() OVER (
                            PARTITION BY la.property_id, la.platform
                            ORDER BY ls.price ASC NULLS LAST, ls.observed_at DESC
                        ) AS platform_rank
                    FROM listing_ads la
                    JOIN listing_snapshots ls ON ls.listing_ad_id = la.id
                    WHERE la.is_active = true
                      AND la.platform = ANY(:platforms)
                      AND (la.advertised_usage_type = :search_type OR la.advertised_usage_type IS NULL)
                      AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                                            AND (
                                                CAST(:observed_since AS TIMESTAMPTZ) IS NULL
                                                OR ls.observed_at >= CAST(:observed_since AS TIMESTAMPTZ)
                                            )
                ),
                zone_props AS (
                    SELECT
                        p.id AS property_id,
                        p.address_normalized,
                        p.location,
                        p.area_m2,
                        p.bedrooms,
                        p.bathrooms,
                        p.parking,
                        p.usage_type,
                        p.location IS NOT NULL AS has_coordinates,
                        CASE
                            WHEN p.location IS NULL THEN false
                            ELSE ST_Within(p.location, z.isochrone_geom)
                        END AS inside_zone
                    FROM properties p
                    JOIN zones z ON z.fingerprint = :zone_fp
                    WHERE (p.usage_type = :usage_type OR :usage_type = 'all')
                )
                SELECT
                    zp.property_id,
                    zp.address_normalized,
                    zp.has_coordinates,
                    zp.inside_zone,
                    ST_Y(zp.location) AS lat,
                    ST_X(zp.location) AS lon,
                    zp.area_m2,
                    zp.bedrooms,
                    zp.bathrooms,
                    zp.parking,
                    zp.usage_type,
                    bp.platform,
                    bp.platform_listing_id,
                    bp.url,
                    bp.image_url,
                    bp.price          AS current_best_price,
                    bp.condo_fee,
                    bp.iptu,
                    bp.observed_at,
                    (
                        SELECT bp2.price
                        FROM ranked_prices bp2
                        WHERE bp2.property_id = zp.property_id
                          AND bp2.price_rank = 2
                        LIMIT 1
                    )                  AS second_best_price,
                    (
                        SELECT COUNT(*)
                        FROM ranked_prices bp2
                        WHERE bp2.property_id = zp.property_id
                          AND bp2.platform_rank = 1
                    )                  AS platform_count
                    ,(
                        SELECT ARRAY_AGG(bp2.platform ORDER BY bp2.platform)
                        FROM ranked_prices bp2
                        WHERE bp2.property_id = zp.property_id
                          AND bp2.platform_rank = 1
                    )                  AS platforms_available
                    ,(
                        SELECT JSONB_AGG(
                            JSONB_BUILD_OBJECT(
                                'platform', bp2.platform,
                                'platform_listing_id', bp2.platform_listing_id,
                                'url', bp2.url,
                                'current_best_price', bp2.price,
                                'condo_fee', bp2.condo_fee,
                                'iptu', bp2.iptu,
                                'observed_at', bp2.observed_at
                            )
                            ORDER BY bp2.price ASC NULLS LAST, bp2.observed_at DESC, bp2.platform
                        )
                        FROM ranked_prices bp2
                        WHERE bp2.property_id = zp.property_id
                          AND bp2.platform_rank = 1
                    )                  AS platform_variants
                FROM zone_props zp
                JOIN ranked_prices bp ON bp.property_id = zp.property_id AND bp.price_rank = 1
                WHERE (:spatial_scope = 'all' OR zp.inside_zone = true)
                ORDER BY zp.inside_zone DESC, zp.has_coordinates DESC, bp.price ASC NULLS LAST
                """
            ),
            {
                "zone_fp": zone_fingerprint,
                "usage_type": usage_type,
                "platforms": platforms,
                "search_type": search_type,
                "observed_since": observed_since,
                "spatial_scope": spatial_scope,
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
                    "lat": float(row["lat"]) if row["lat"] is not None else None,
                    "lon": float(row["lon"]) if row["lon"] is not None else None,
                    "has_coordinates": bool(row["has_coordinates"]),
                    "inside_zone": bool(row["inside_zone"]),
                    "area_m2": row["area_m2"],
                    "bedrooms": row["bedrooms"],
                    "bathrooms": row["bathrooms"],
                    "parking": row["parking"],
                    "usage_type": row["usage_type"],
                    "platform": row["platform"],
                    "platform_listing_id": row["platform_listing_id"],
                    "url": row["url"],
                    "image_url": row["image_url"],
                    "platforms_available": list(row["platforms_available"] or []),
                    "platform_variants": [
                        _serialize_platform_variant(variant)
                        for variant in (row["platform_variants"] or [])
                    ],
                    "current_best_price": str(best_price) if best_price is not None else None,
                    "condo_fee": str(row["condo_fee"]) if row["condo_fee"] is not None else None,
                    "iptu": str(row["iptu"]) if row["iptu"] is not None else None,
                    "second_best_price": str(second_price) if second_price is not None else None,
                    "duplication_badge": dup_badge,
                    "observed_at": row["observed_at"].isoformat() if row["observed_at"] else None,
                }
            )
        return cards
