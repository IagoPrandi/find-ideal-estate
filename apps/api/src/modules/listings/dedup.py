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
                    parking, fingerprint
                ) VALUES (
                    :address_normalized,
                    {geom_expr},
                    :area_m2, :bedrooms, :bathrooms,
                    :parking, :fingerprint
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
                    url, advertised_usage_type, usage_type, usage_type_inferred
                ) VALUES (
                    :property_id, :platform, :platform_listing_id,
                    :url, :advertised_usage_type, :usage_type, :usage_type_inferred
                )
                ON CONFLICT (platform, platform_listing_id) DO UPDATE
                    SET last_seen_at = now(),
                        is_active = true,
                        url = EXCLUDED.url,
                        usage_type = COALESCE(EXCLUDED.usage_type, listing_ads.usage_type),
                        usage_type_inferred = CASE
                            WHEN EXCLUDED.usage_type IS NULL THEN listing_ads.usage_type_inferred
                            ELSE EXCLUDED.usage_type_inferred
                        END
                """
            ),
            {
                "property_id": property_id,
                "platform": platform,
                "platform_listing_id": platform_listing_id,
                "url": url,
                "advertised_usage_type": advertised_usage_type,
                "usage_type": usage_type,
                "usage_type_inferred": usage_type is not None,
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
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str,
    usage_type: str,
    platforms: list[str],
    observed_since: Any | None = None,
    spatial_scope: str = "inside_zone",
    search_location_normalized: str | None = None,
    address_scope: str = "all_addresses",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
        Return flattened listing cards for the given zone fingerprint.

        The loaded set depends on the selected address scope:
            - all_addresses: all active listings already persisted in cache/database;
            - selected_address: only listings whose scrape origin matches the seed
              address selected in Step 5.

        The zone fingerprint still controls spatial badges/order and the optional
        inside-zone filter, but cache ownership itself is address-seed based.
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
            "image_url": raw_variant.get("image_url"),
            "current_best_price": _serialize_money(raw_variant.get("current_best_price")),
            "condo_fee": _serialize_money(raw_variant.get("condo_fee")),
            "iptu": _serialize_money(raw_variant.get("iptu")),
            "observed_at": observed_at_value,
        }

    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                WITH zone_geom AS (
                    -- Fetch zone geometry once; all spatial ops reference this.
                    SELECT isochrone_geom
                    FROM zones
                    WHERE fingerprint = :zone_fp
                    LIMIT 1
                ),
                search_scope_props AS (
                    -- Address-linked properties that should remain visible even when
                    -- they fall outside the selected zone geometry.
                    --
                    -- selected_address:
                    --   keeps only the Step 5 address currently chosen by the user
                    --   (plus legacy unlabeled rows observed since the same cache cohort).
                    --
                    -- all_addresses:
                    --   keeps the expanded recently-observed address inventory so the
                    --   Step 6 panel can start with "inside zone" and still let the user
                    --   broaden to the complete persisted set.
                    SELECT DISTINCT la.property_id
                    FROM listing_ads la
                    JOIN listing_snapshots ls ON ls.listing_ad_id = la.id
                    WHERE la.is_active = true
                      AND la.platform = ANY(:platforms)
                      AND (la.advertised_usage_type = :search_type OR la.advertised_usage_type IS NULL)
                      AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                      AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                      AND (
                          (
                              :address_scope = 'selected_address'
                              AND :has_search_location = TRUE
                              AND ls.raw_payload->>'search_location_normalized' = :search_location_normalized
                          )
                          OR (
                              :address_scope = 'all_addresses'
                              AND CAST(:observed_since AS TIMESTAMPTZ) IS NOT NULL
                              AND ls.observed_at >= CAST(:observed_since AS TIMESTAMPTZ)
                          )
                          OR (
                              :address_scope = 'selected_address'
                              AND CAST(:observed_since AS TIMESTAMPTZ) IS NOT NULL
                              AND COALESCE(ls.raw_payload->>'search_location_normalized', '') = ''
                              AND ls.observed_at >= CAST(:observed_since AS TIMESTAMPTZ)
                          )
                      )
                ),
                eligible_props AS (
                    -- Restrict to properties within the zone bounding box (uses GIST index
                    -- on properties.location via && operator) plus address-scoped properties
                    -- that may lack coordinates or sit just outside the bbox.
                    SELECT p.id AS property_id
                    FROM properties p
                    CROSS JOIN zone_geom z
                    WHERE (p.location IS NOT NULL AND p.location && z.isochrone_geom)
                       OR (
                           p.id IN (SELECT property_id FROM search_scope_props)
                       )
                ),
                ranked_prices AS (
                    -- Per-listing snapshot prices, restricted to eligible properties only.
                    -- Window functions compute best-price rank per property and per platform.
                    SELECT
                        la.property_id,
                        la.platform,
                        la.platform_listing_id,
                        la.url,
                        la.usage_type,
                        la.advertised_usage_type,
                        ls.price,
                        ls.condo_fee,
                        ls.iptu,
                        CASE
                            WHEN ls.price IS NULL THEN NULL
                            ELSE COALESCE(ls.price, 0) + COALESCE(ls.condo_fee, 0) + COALESCE(ls.iptu, 0)
                        END AS total_price,
                        COALESCE(
                            NULLIF(ls.raw_payload->>'image_url', ''),
                            (
                                SELECT prev.raw_payload->>'image_url'
                                FROM listing_snapshots prev
                                WHERE prev.listing_ad_id = la.id
                                  AND COALESCE(prev.raw_payload->>'image_url', '') <> ''
                                ORDER BY prev.observed_at DESC
                                LIMIT 1
                            ),
                            (
                                SELECT prev.raw_payload->>'image_url'
                                FROM listing_snapshots prev
                                JOIN listing_ads prev_la ON prev_la.id = prev.listing_ad_id
                                WHERE prev_la.property_id = la.property_id
                                  AND prev_la.platform = la.platform
                                  AND COALESCE(prev.raw_payload->>'image_url', '') <> ''
                                ORDER BY prev.observed_at DESC
                                LIMIT 1
                            ),
                            (
                                SELECT prev.raw_payload->>'image_url'
                                FROM listing_snapshots prev
                                JOIN listing_ads prev_la ON prev_la.id = prev.listing_ad_id
                                WHERE prev_la.property_id = la.property_id
                                  AND COALESCE(prev.raw_payload->>'image_url', '') <> ''
                                ORDER BY prev.observed_at DESC
                                LIMIT 1
                            )
                        ) AS image_url,
                        ls.observed_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY la.property_id
                            ORDER BY CASE
                                WHEN ls.price IS NULL THEN NULL
                                ELSE COALESCE(ls.price, 0) + COALESCE(ls.condo_fee, 0) + COALESCE(ls.iptu, 0)
                            END ASC NULLS LAST, ls.observed_at DESC
                        ) AS price_rank,
                        ROW_NUMBER() OVER (
                            PARTITION BY la.property_id, la.platform
                            ORDER BY CASE
                                WHEN ls.price IS NULL THEN NULL
                                ELSE COALESCE(ls.price, 0) + COALESCE(ls.condo_fee, 0) + COALESCE(ls.iptu, 0)
                            END ASC NULLS LAST, ls.observed_at DESC
                        ) AS platform_rank
                    FROM listing_ads la
                    JOIN listing_snapshots ls ON ls.listing_ad_id = la.id
                    WHERE la.is_active = true
                      AND la.platform = ANY(:platforms)
                      AND (la.advertised_usage_type = :search_type OR la.advertised_usage_type IS NULL)
                      AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                      AND la.property_id IN (SELECT property_id FROM eligible_props)
                      AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                ),
                zone_props AS (
                    -- Properties restricted to eligible_props; computes inside_zone via
                    -- ST_Within (exact containment, uses GIST recheck on bbox candidates).
                    SELECT
                        p.id AS property_id,
                        p.address_normalized,
                        NULLIF(
                            BTRIM(
                                (
                                    regexp_split_to_array(
                                        regexp_replace(COALESCE(p.address_normalized, ''), '\\s*,\\s*', ',', 'g'),
                                        ','
                                    )
                                )[2]
                            ),
                            ''
                        ) AS neighborhood_name,
                        NULLIF(
                            BTRIM(
                                (
                                    regexp_split_to_array(
                                        regexp_replace(COALESCE(p.address_normalized, ''), '\\s*,\\s*', ',', 'g'),
                                        ','
                                    )
                                )[3]
                            ),
                            ''
                        ) AS city_name,
                        p.location,
                        p.area_m2,
                        p.bedrooms,
                        p.bathrooms,
                        p.parking,
                        p.location IS NOT NULL AS has_coordinates,
                        CASE
                            WHEN p.location IS NULL THEN false
                            ELSE ST_Within(p.location, z.isochrone_geom)
                        END AS inside_zone
                    FROM properties p
                    CROSS JOIN zone_geom z
                    WHERE p.id IN (SELECT property_id FROM eligible_props)
                ),
                property_price_context AS (
                    SELECT
                        zp.property_id,
                        zp.neighborhood_name,
                        zp.city_name,
                        bp.total_price AS current_total_price,
                        CASE
                            WHEN zp.area_m2 IS NOT NULL AND zp.area_m2 > 0 AND bp.total_price IS NOT NULL
                            THEN bp.total_price::DOUBLE PRECISION / zp.area_m2::DOUBLE PRECISION
                            ELSE NULL
                        END AS current_unit_price
                    FROM zone_props zp
                    JOIN ranked_prices bp ON bp.property_id = zp.property_id AND bp.price_rank = 1
                    WHERE zp.address_normalized IS NOT NULL
                ),
                neighborhood_medians AS (
                    -- Median unit price per neighbourhood, computed over all eligible zone
                    -- properties so each page shows a consistent reference value.
                    SELECT
                        ppc.city_name,
                        ppc.neighborhood_name,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY ppc.current_unit_price)::DOUBLE PRECISION AS neighborhood_median_unit_price
                    FROM property_price_context ppc
                    WHERE ppc.city_name IS NOT NULL
                      AND ppc.neighborhood_name IS NOT NULL
                      AND ppc.current_unit_price IS NOT NULL
                    GROUP BY ppc.city_name, ppc.neighborhood_name
                )
                SELECT
                    zp.property_id,
                    zp.address_normalized,
                    zp.neighborhood_name,
                    zp.city_name,
                    zp.has_coordinates,
                    zp.inside_zone,
                    ST_Y(zp.location) AS lat,
                    ST_X(zp.location) AS lon,
                    zp.area_m2,
                    zp.bedrooms,
                    zp.bathrooms,
                    zp.parking,
                    bp.usage_type,
                    bp.platform,
                    bp.platform_listing_id,
                    bp.url,
                    bp.image_url,
                    bp.price          AS current_best_price,
                    bp.total_price    AS current_total_price,
                    ppc.current_unit_price,
                    nm.neighborhood_median_unit_price,
                    CASE
                        WHEN ppc.current_unit_price IS NOT NULL
                         AND nm.neighborhood_median_unit_price IS NOT NULL
                         AND nm.neighborhood_median_unit_price <> 0
                        THEN ROUND((((ppc.current_unit_price - nm.neighborhood_median_unit_price) / nm.neighborhood_median_unit_price) * 100.0)::numeric, 2)::DOUBLE PRECISION
                        ELSE NULL
                    END AS current_vs_neighborhood_pct,
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
                                'image_url', bp2.image_url,
                                'current_best_price', bp2.price,
                                'condo_fee', bp2.condo_fee,
                                'iptu', bp2.iptu,
                                'observed_at', bp2.observed_at
                            )
                            ORDER BY bp2.total_price ASC NULLS LAST, bp2.observed_at DESC, bp2.platform
                        )
                        FROM ranked_prices bp2
                        WHERE bp2.property_id = zp.property_id
                          AND bp2.platform_rank = 1
                    )                  AS platform_variants
                FROM zone_props zp
                LEFT JOIN search_scope_props sap ON sap.property_id = zp.property_id
                JOIN ranked_prices bp ON bp.property_id = zp.property_id AND bp.price_rank = 1
                LEFT JOIN property_price_context ppc ON ppc.property_id = zp.property_id
                LEFT JOIN neighborhood_medians nm
                    ON nm.city_name = ppc.city_name
                   AND nm.neighborhood_name = ppc.neighborhood_name
                WHERE (
                    (
                        :address_scope = 'selected_address'
                        AND sap.property_id IS NOT NULL
                    )
                    OR (
                        :address_scope = 'all_addresses'
                        AND true
                    )
                )
                AND (:spatial_scope = 'all' OR zp.inside_zone = true)
                ORDER BY zp.inside_zone DESC, zp.has_coordinates DESC, bp.total_price ASC NULLS LAST
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "zone_fp": zone_fingerprint,
                "journey_id": journey_id,
                "usage_type": usage_type,
                "platforms": platforms,
                "search_type": search_type,
                "observed_since": observed_since,
                "spatial_scope": spatial_scope,
                "address_scope": address_scope,
                "has_search_location": bool(search_location_normalized),
                "search_location_normalized": search_location_normalized,
                "limit": limit,
                "offset": offset,
            },
        )

        cards = []
        for row in rows.mappings():
            platform_count = row["platform_count"] or 1
            second_price = row["second_best_price"]
            best_price = row["current_best_price"]
            best_total_price = row["current_total_price"]
            platform_variants = [
                _serialize_platform_variant(variant)
                for variant in (row["platform_variants"] or [])
            ]
            image_url = row["image_url"] or next(
                (variant.get("image_url") for variant in platform_variants if variant.get("image_url")),
                None,
            )
            dup_badge = None
            if platform_count >= 2 and best_total_price is not None:
                price_fmt = f"R$ {int(best_total_price):,}".replace(",", ".")
                dup_badge = f"Disponível em {platform_count} plataformas · menor: {price_fmt}"

            cards.append(
                {
                    "property_id": str(row["property_id"]),
                    "address_normalized": row["address_normalized"],
                    "neighborhood_name": row["neighborhood_name"],
                    "city_name": row["city_name"],
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
                    "image_url": image_url,
                    "platforms_available": list(row["platforms_available"] or []),
                    "platform_variants": platform_variants,
                    "current_best_price": str(best_price) if best_price is not None else None,
                    "current_unit_price": float(row["current_unit_price"]) if row["current_unit_price"] is not None else None,
                    "neighborhood_median_unit_price": float(row["neighborhood_median_unit_price"]) if row["neighborhood_median_unit_price"] is not None else None,
                    "current_vs_neighborhood_pct": float(row["current_vs_neighborhood_pct"]) if row["current_vs_neighborhood_pct"] is not None else None,
                    "condo_fee": str(row["condo_fee"]) if row["condo_fee"] is not None else None,
                    "iptu": str(row["iptu"]) if row["iptu"] is not None else None,
                    "second_best_price": str(second_price) if second_price is not None else None,
                    "duplication_badge": dup_badge,
                    "observed_at": row["observed_at"].isoformat() if row["observed_at"] else None,
                }
            )
        return cards
