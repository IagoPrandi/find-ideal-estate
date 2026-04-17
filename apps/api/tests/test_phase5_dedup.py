"""Unit tests for M5.5: property deduplication fingerprint and badge logic.

These tests cover:
  - compute_property_fingerprint determinism and collision-resistance.
  - Address normalisation (accents, case, extra whitespace).
  - lat/lon rounding to 4 decimal places.
  - area_m2 rounding to nearest int.
  - Identical inputs → identical fingerprint.
  - Different inputs → different fingerprint.

Integration tests (DB-backed) live in scripts/verify_m5_5_dedup.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.db import close_db, get_engine, init_db  # noqa: E402
from modules.listings.dedup import (  # noqa: E402
    compute_property_fingerprint,
    fetch_listing_cards_for_zone,
    upsert_property_and_ad,
)

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_fp(address: str, lat, lon, area, bedrooms) -> str:
    """Re-compute fingerprint using the same canonical logic as the module."""
    import re
    import unicodedata

    def norm_addr(addr):
        if not addr:
            return ""
        nfkd = unicodedata.normalize("NFKD", addr)
        ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
        lower = ascii_only.lower()
        return re.sub(r"\s+", " ", lower).strip()

    canonical = {
        "address": norm_addr(address),
        "area_m2": round(float(area)) if area is not None else None,
        "bedrooms": int(bedrooms) if bedrooms is not None else None,
        "lat": round(float(lat), 4) if lat is not None else None,
        "lon": round(float(lon), 4) if lon is not None else None,
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# compute_property_fingerprint
# ---------------------------------------------------------------------------


class TestComputePropertyFingerprint:
    def test_deterministic_same_inputs(self) -> None:
        """Same inputs always produce the same 64-char hex fingerprint."""
        fp1 = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        fp2 = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        assert fp1 == fp2
        assert len(fp1) == 64
        assert all(c in "0123456789abcdef" for c in fp1)

    def test_matches_canonical_computation(self) -> None:
        """Fingerprint matches independent re-computation."""
        inputs = ("Rua Vergueiro 3185", -23.5951, -46.6388, 62.4, 2)
        assert compute_property_fingerprint(*inputs) == _expected_fp(*inputs)

    def test_address_normalisation_accent_insensitive(self) -> None:
        """'Rua São João' and 'Rua Sao Joao' must hash identically."""
        fp_accented = compute_property_fingerprint("Rua São João", -23.5, -46.6, 50.0, 1)
        fp_plain = compute_property_fingerprint("Rua Sao Joao", -23.5, -46.6, 50.0, 1)
        assert fp_accented == fp_plain

    def test_address_normalisation_case_insensitive(self) -> None:
        fp_upper = compute_property_fingerprint("RUA VERGUEIRO", -23.5, -46.6, 50.0, 1)
        fp_lower = compute_property_fingerprint("rua vergueiro", -23.5, -46.6, 50.0, 1)
        assert fp_upper == fp_lower

    def test_address_normalisation_collapses_whitespace(self) -> None:
        fp_multi = compute_property_fingerprint("Rua  Vergueiro   3185", -23.5, -46.6, 50.0, 1)
        fp_single = compute_property_fingerprint("Rua Vergueiro 3185", -23.5, -46.6, 50.0, 1)
        assert fp_multi == fp_single

    def test_lat_lon_rounded_to_4dp(self) -> None:
        """Points within ~10m of each other (same 4-dp bucket) → same fingerprint."""
        fp_a = compute_property_fingerprint("Rua A", -23.59512, -46.63878, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.59514, -46.63882, 62.0, 2)
        assert fp_a == fp_b

    def test_lat_lon_different_5th_dp_still_same(self) -> None:
        """5th decimal difference must collapse to same fingerprint."""
        # Both -23.59511 and -23.59513 round to -23.5951 at 4dp
        fp_a = compute_property_fingerprint("Rua A", -23.59511, -46.63881, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.59513, -46.63883, 62.0, 2)
        assert fp_a == fp_b

    def test_different_address_different_fingerprint(self) -> None:
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua B", -23.5951, -46.6388, 62.0, 2)
        assert fp_a != fp_b

    def test_different_bedrooms_different_fingerprint(self) -> None:
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 3)
        assert fp_a != fp_b

    def test_area_rounded_to_nearest_int(self) -> None:
        """62.4 and 62.49 both round to 62 → same fingerprint."""
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.4, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.49, 2)
        assert fp_a == fp_b

    def test_area_that_rounds_differently(self) -> None:
        """62.4 rounds to 62; 63.5 rounds to 64 (Python banker's rounding: rounds to even)."""
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.4, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 63.6, 2)
        assert fp_a != fp_b

    def test_none_fields_stable(self) -> None:
        """None inputs produce a deterministic fingerprint (no crash)."""
        fp1 = compute_property_fingerprint(None, None, None, None, None)
        fp2 = compute_property_fingerprint(None, None, None, None, None)
        assert fp1 == fp2
        assert len(fp1) == 64


async def _phase5_schema_ready() -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    to_regclass('public.properties') IS NOT NULL
                    AND to_regclass('public.listing_ads') IS NOT NULL
                    AND to_regclass('public.listing_snapshots') IS NOT NULL
                    AND to_regclass('public.zones') IS NOT NULL
                    AND EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'listing_ads'
                          AND column_name = 'usage_type'
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'listing_ads'
                          AND column_name = 'usage_type_inferred'
                    )
                """
            )
        )
        return bool(result.scalar())


async def _cleanup_fetch_listing_cards_rows(*, fingerprint: str, platform_listing_ids: list[str], zone_fingerprint: str) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DELETE FROM listing_snapshots
                WHERE listing_ad_id IN (
                    SELECT id FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)
                )
                """
            ),
            {"platform_listing_ids": platform_listing_ids},
        )
        await conn.execute(
            text("DELETE FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)"),
            {"platform_listing_ids": platform_listing_ids},
        )
        await conn.execute(
            text("DELETE FROM properties WHERE fingerprint = :fingerprint"),
            {"fingerprint": fingerprint},
        )
        await conn.execute(
            text("DELETE FROM zones WHERE fingerprint = :zone_fingerprint"),
            {"zone_fingerprint": zone_fingerprint},
        )


@pytest.mark.anyio
async def test_fetch_listing_cards_for_zone_supports_all_spatial_scope() -> None:
    init_db(os.environ["DATABASE_URL"])

    journey_id = uuid4()
    zone_fingerprint = f"zone-dedup-{uuid4().hex[:8]}"
    platform_listing_ids = [f"dedup-qa-{uuid4().hex[:8]}", f"dedup-zap-{uuid4().hex[:8]}"]
    base_lat = -22.3215
    base_lon = -45.1843
    address_label = "Rua Teste Dedup, Bairro Dedup QA, Cidade Dedup, SP"
    search_location_normalized = f"seed-dedup-{uuid4().hex[:8]}"
    fingerprint = compute_property_fingerprint(
        address_normalized=address_label,
        lat=base_lat,
        lon=base_lon,
        area_m2=70,
        bedrooms=2,
    )
    observed_since = datetime.now(timezone.utc) - timedelta(seconds=1)
    schema_ready = False

    try:
        schema_ready = await _phase5_schema_ready()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")

        await _cleanup_fetch_listing_cards_rows(
            fingerprint=fingerprint,
            platform_listing_ids=platform_listing_ids,
            zone_fingerprint=zone_fingerprint,
        )

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
                        isochrone_geom,
                        state
                    ) VALUES (
                        :fingerprint,
                        'transit',
                        30,
                        1200,
                        ST_GeomFromText(:polygon_wkt, 4326),
                        'complete'
                    )
                    """
                ),
                {
                    "fingerprint": zone_fingerprint,
                    "polygon_wkt": f"POLYGON(({base_lon - 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat - 0.01}))",
                },
            )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=70,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="quintoandar",
            platform_listing_id=platform_listing_ids[0],
            url="https://example.org/quintoandar/dedup",
            advertised_usage_type="rent",
            price=Decimal("3500"),
            condo_fee=Decimal("500"),
            iptu=Decimal("100"),
            raw_payload={"image_url": "https://example.org/quintoandar.jpg", "search_location_normalized": search_location_normalized},
        )
        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=70,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="zapimoveis",
            platform_listing_id=platform_listing_ids[1],
            url="https://example.org/zap/dedup",
            advertised_usage_type="rent",
            price=Decimal("3300"),
            condo_fee=Decimal("800"),
            iptu=Decimal("90"),
            raw_payload={"image_url": "https://example.org/zap.jpg", "search_location_normalized": search_location_normalized},
        )

        cards = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["quintoandar", "zapimoveis"],
            observed_since=observed_since,
            spatial_scope="all",
            search_location_normalized=search_location_normalized,
            address_scope="selected_address",
        )

        assert len(cards) == 1
        assert cards[0]["platform"] == "quintoandar"
        assert cards[0]["inside_zone"] is True
        assert cards[0]["has_coordinates"] is True
        assert cards[0]["platforms_available"] == ["quintoandar", "zapimoveis"]
        assert [variant["platform"] for variant in cards[0]["platform_variants"]] == ["quintoandar", "zapimoveis"]
        assert cards[0]["platform_variants"][0]["platform_listing_id"] == platform_listing_ids[0]
        assert cards[0]["platform_variants"][0]["url"] == "https://example.org/quintoandar/dedup"
        assert cards[0]["platform_variants"][0]["current_best_price"] == "3500.00"
        assert cards[0]["platform_variants"][0]["condo_fee"] == "500.00"
        assert cards[0]["platform_variants"][0]["iptu"] == "100.00"
        assert cards[0]["platform_variants"][0]["image_url"] == "https://example.org/quintoandar.jpg"
        assert cards[0]["platform_variants"][1]["platform_listing_id"] == platform_listing_ids[1]
        assert cards[0]["platform_variants"][1]["url"] == "https://example.org/zap/dedup"
        assert cards[0]["platform_variants"][1]["current_best_price"] == "3300.00"
        assert cards[0]["platform_variants"][1]["condo_fee"] == "800.00"
        assert cards[0]["platform_variants"][1]["iptu"] == "90.00"
        assert cards[0]["platform_variants"][1]["image_url"] == "https://example.org/zap.jpg"
        assert cards[0]["neighborhood_name"] == "Bairro Dedup QA"
        assert cards[0]["city_name"] == "Cidade Dedup"
        assert cards[0]["image_url"] == "https://example.org/quintoandar.jpg"
        assert cards[0]["current_unit_price"] == pytest.approx(58.57142857142857)
        assert cards[0]["neighborhood_median_unit_price"] == pytest.approx(58.57142857142857)
        assert cards[0]["current_vs_neighborhood_pct"] == pytest.approx(0.0)
        assert str(cards[0]["condo_fee"]) == "500.00"
        assert str(cards[0]["iptu"]) == "100.00"
        assert str(cards[0]["second_best_price"]) == "3300.00"
        assert cards[0]["duplication_badge"] == "Disponível em 2 plataformas · menor: R$ 4.100"
    finally:
        if schema_ready:
            await _cleanup_fetch_listing_cards_rows(
                fingerprint=fingerprint,
                platform_listing_ids=platform_listing_ids,
                zone_fingerprint=zone_fingerprint,
            )
        await close_db()


@pytest.mark.anyio
async def test_fetch_listing_cards_for_zone_falls_back_to_variant_image() -> None:
    init_db(os.environ["DATABASE_URL"])

    journey_id = uuid4()
    zone_fingerprint = f"zone-dedup-{uuid4().hex[:8]}"
    platform_listing_ids = [f"dedup-noimg-{uuid4().hex[:8]}", f"dedup-withimg-{uuid4().hex[:8]}"]
    base_lat = -22.3215
    base_lon = -45.1843
    address_label = "Rua Imagem Compartilhada, Bairro Dedup Img, Cidade Dedup, SP"
    search_location_normalized = f"seed-image-{uuid4().hex[:8]}"
    fingerprint = compute_property_fingerprint(
        address_normalized=address_label,
        lat=base_lat,
        lon=base_lon,
        area_m2=75,
        bedrooms=2,
    )
    observed_since = datetime.now(timezone.utc) - timedelta(seconds=1)
    schema_ready = False

    try:
        schema_ready = await _phase5_schema_ready()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")

        await _cleanup_fetch_listing_cards_rows(
            fingerprint=fingerprint,
            platform_listing_ids=platform_listing_ids,
            zone_fingerprint=zone_fingerprint,
        )

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
                        isochrone_geom,
                        state
                    ) VALUES (
                        :fingerprint,
                        'transit',
                        30,
                        1200,
                        ST_GeomFromText(:polygon_wkt, 4326),
                        'complete'
                    )
                    """
                ),
                {
                    "fingerprint": zone_fingerprint,
                    "polygon_wkt": f"POLYGON(({base_lon - 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat - 0.01}))",
                },
            )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=75,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="zapimoveis",
            platform_listing_id=platform_listing_ids[0],
            url="https://example.org/zap/no-image",
            advertised_usage_type="rent",
            price=Decimal("3100"),
            condo_fee=Decimal("250"),
            iptu=Decimal("80"),
            raw_payload={"image_url": None, "search_location_normalized": search_location_normalized},
        )
        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=75,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="quintoandar",
            platform_listing_id=platform_listing_ids[1],
            url="https://example.org/quinto/with-image",
            advertised_usage_type="rent",
            price=Decimal("3200"),
            condo_fee=Decimal("260"),
            iptu=Decimal("90"),
            raw_payload={"image_url": "https://example.org/shared-image.jpg", "search_location_normalized": search_location_normalized},
        )

        cards = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["zapimoveis", "quintoandar"],
            observed_since=observed_since,
            spatial_scope="all",
            search_location_normalized=search_location_normalized,
            address_scope="selected_address",
        )

        assert len(cards) == 1
        assert cards[0]["platform"] == "zapimoveis"
        assert cards[0]["image_url"] == "https://example.org/shared-image.jpg"
        assert [variant["image_url"] for variant in cards[0]["platform_variants"]] == [
            "https://example.org/shared-image.jpg",
            "https://example.org/shared-image.jpg",
        ]
    finally:
        if schema_ready:
            await _cleanup_fetch_listing_cards_rows(
                fingerprint=fingerprint,
                platform_listing_ids=platform_listing_ids,
                zone_fingerprint=zone_fingerprint,
            )
        await close_db()


@pytest.mark.anyio
async def test_fetch_listing_cards_for_zone_reuses_previous_snapshot_image() -> None:
    init_db(os.environ["DATABASE_URL"])

    journey_id = uuid4()
    zone_fingerprint = f"zone-dedup-{uuid4().hex[:8]}"
    platform_listing_id = f"dedup-history-{uuid4().hex[:8]}"
    base_lat = -22.3715
    base_lon = -45.2343
    address_label = "Rua Histórico de Imagem, Bairro Dedup Histórico, Cidade Dedup, SP"
    search_location_normalized = f"seed-history-{uuid4().hex[:8]}"
    fingerprint = compute_property_fingerprint(
        address_normalized=address_label,
        lat=base_lat,
        lon=base_lon,
        area_m2=68,
        bedrooms=2,
    )
    observed_since = datetime.now(timezone.utc) - timedelta(minutes=30)
    schema_ready = False

    try:
        schema_ready = await _phase5_schema_ready()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")

        await _cleanup_fetch_listing_cards_rows(
            fingerprint=fingerprint,
            platform_listing_ids=[platform_listing_id],
            zone_fingerprint=zone_fingerprint,
        )

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
                        isochrone_geom,
                        state
                    ) VALUES (
                        :fingerprint,
                        'transit',
                        30,
                        1200,
                        ST_GeomFromText(:polygon_wkt, 4326),
                        'complete'
                    )
                    """
                ),
                {
                    "fingerprint": zone_fingerprint,
                    "polygon_wkt": f"POLYGON(({base_lon - 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat - 0.01}))",
                },
            )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=68,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="vivareal",
            platform_listing_id=platform_listing_id,
            url="https://example.org/vivareal/history",
            advertised_usage_type="rent",
            price=Decimal("3600"),
            condo_fee=Decimal("420"),
            iptu=Decimal("120"),
            raw_payload={"image_url": "https://example.org/previous-image.jpg", "search_location_normalized": search_location_normalized},
        )
        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=68,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="vivareal",
            platform_listing_id=platform_listing_id,
            url="https://example.org/vivareal/history",
            advertised_usage_type="rent",
            price=Decimal("3550"),
            condo_fee=Decimal("420"),
            iptu=Decimal("120"),
            raw_payload={"image_url": None, "search_location_normalized": search_location_normalized},
        )

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    WITH ordered_snapshots AS (
                        SELECT
                            ls.id,
                            ROW_NUMBER() OVER (ORDER BY ls.observed_at ASC, ls.id ASC) AS snapshot_rank
                        FROM listing_snapshots ls
                        JOIN listing_ads la ON la.id = ls.listing_ad_id
                        WHERE la.platform_listing_id = :platform_listing_id
                    )
                    UPDATE listing_snapshots ls
                    SET observed_at = CASE
                        WHEN ordered_snapshots.snapshot_rank = 1 THEN CAST(:older_observed_at AS TIMESTAMPTZ)
                        ELSE CAST(:newer_observed_at AS TIMESTAMPTZ)
                    END
                    FROM ordered_snapshots
                    WHERE ls.id = ordered_snapshots.id
                    """
                ),
                {
                    "platform_listing_id": platform_listing_id,
                    "older_observed_at": datetime.now(timezone.utc) - timedelta(minutes=20),
                    "newer_observed_at": datetime.now(timezone.utc) - timedelta(minutes=5),
                },
            )

        cards = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["vivareal"],
            observed_since=observed_since,
            spatial_scope="all",
            search_location_normalized=search_location_normalized,
            address_scope="selected_address",
        )

        assert len(cards) == 1
        assert cards[0]["platform"] == "vivareal"
        assert cards[0]["image_url"] == "https://example.org/previous-image.jpg"
        assert cards[0]["platform_variants"][0]["image_url"] == "https://example.org/previous-image.jpg"
    finally:
        if schema_ready:
            await _cleanup_fetch_listing_cards_rows(
                fingerprint=fingerprint,
                platform_listing_ids=[platform_listing_id],
                zone_fingerprint=zone_fingerprint,
            )
        await close_db()


@pytest.mark.anyio
async def test_fetch_listing_cards_for_zone_reuses_image_from_same_property_history() -> None:
    init_db(os.environ["DATABASE_URL"])

    journey_id = uuid4()
    zone_fingerprint = f"zone-dedup-{uuid4().hex[:8]}"
    current_listing_id = f"zap-current-{uuid4().hex[:8]}"
    previous_listing_id = f"zap-previous-{uuid4().hex[:8]}"
    base_lat = -22.3315
    base_lon = -45.1943
    address_label = "Rua Teste Imagem, Vila Leopoldina, São Paulo, SP"
    search_location_normalized = f"seed-property-history-{uuid4().hex[:8]}"
    fingerprint = compute_property_fingerprint(
        address_normalized=address_label,
        lat=base_lat,
        lon=base_lon,
        area_m2=72,
        bedrooms=2,
    )
    observed_since = datetime.now(timezone.utc) - timedelta(minutes=1)
    schema_ready = False

    try:
        schema_ready = await _phase5_schema_ready()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")

        await _cleanup_fetch_listing_cards_rows(
            fingerprint=fingerprint,
            platform_listing_ids=[current_listing_id, previous_listing_id],
            zone_fingerprint=zone_fingerprint,
        )

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
                        isochrone_geom,
                        state
                    ) VALUES (
                        :fingerprint,
                        'transit',
                        30,
                        1200,
                        ST_GeomFromText(:polygon_wkt, 4326),
                        'complete'
                    )
                    """
                ),
                {
                    "fingerprint": zone_fingerprint,
                    "polygon_wkt": f"POLYGON(({base_lon - 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat - 0.01}, {base_lon + 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat + 0.01}, {base_lon - 0.01} {base_lat - 0.01}))",
                },
            )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=72,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="zapimoveis",
            platform_listing_id=previous_listing_id,
            url="https://example.org/zap/previous",
            advertised_usage_type="rent",
            price=Decimal("3600"),
            condo_fee=Decimal("300"),
            iptu=Decimal("100"),
            raw_payload={"image_url": "https://example.org/property-image.jpg", "search_location_normalized": search_location_normalized},
        )
        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=base_lat,
            lon=base_lon,
            area_m2=72,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="zapimoveis",
            platform_listing_id=current_listing_id,
            url="https://example.org/zap/current",
            advertised_usage_type="rent",
            price=Decimal("3500"),
            condo_fee=Decimal("300"),
            iptu=Decimal("100"),
            raw_payload={"image_url": None, "search_location_normalized": search_location_normalized},
        )

        cards = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["zapimoveis"],
            observed_since=observed_since,
            spatial_scope="all",
            search_location_normalized=search_location_normalized,
            address_scope="selected_address",
        )

        assert len(cards) == 1
        assert cards[0]["platform"] == "zapimoveis"
        assert cards[0]["platform_listing_id"] == current_listing_id
        assert cards[0]["image_url"] == "https://example.org/property-image.jpg"
        assert cards[0]["platform_variants"][0]["image_url"] == "https://example.org/property-image.jpg"
    finally:
        if schema_ready:
            await _cleanup_fetch_listing_cards_rows(
                fingerprint=fingerprint,
                platform_listing_ids=[current_listing_id, previous_listing_id],
                zone_fingerprint=zone_fingerprint,
            )
        await close_db()


@pytest.mark.anyio
async def test_fetch_listing_cards_for_zone_selected_address_scope_filters_to_step5_address() -> None:
    init_db(os.environ["DATABASE_URL"])

    journey_id = uuid4()
    zone_fingerprint = f"zone-dedup-{uuid4().hex[:8]}"
    inside_listing_id = f"inside-{uuid4().hex[:8]}"
    direct_listing_id = f"direct-{uuid4().hex[:8]}"
    unrelated_listing_id = f"outside-{uuid4().hex[:8]}"
    inside_lat = -22.4315
    inside_lon = -45.2843
    direct_lat = -22.4715
    direct_lon = -45.3243
    unrelated_lat = -22.5115
    unrelated_lon = -45.3643
    inside_fingerprint = compute_property_fingerprint(
        address_normalized="Rua Dentro, Itaim Bibi, São Paulo, SP",
        lat=inside_lat,
        lon=inside_lon,
        area_m2=70,
        bedrooms=2,
    )
    direct_fingerprint = compute_property_fingerprint(
        address_normalized="Rua Fora, Vila Olímpia, São Paulo, SP",
        lat=direct_lat,
        lon=direct_lon,
        area_m2=65,
        bedrooms=2,
    )
    unrelated_fingerprint = compute_property_fingerprint(
        address_normalized="Rua Distante, Moema, São Paulo, SP",
        lat=unrelated_lat,
        lon=unrelated_lon,
        area_m2=55,
        bedrooms=1,
    )
    direct_search_location = "rua fora, vila olimpia, sao paulo, sp"
    unrelated_search_location = "rua distante, moema, sao paulo, sp"
    observed_since = datetime.now(timezone.utc) - timedelta(minutes=10)
    schema_ready = False

    async def _cleanup() -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    DELETE FROM listing_snapshots
                    WHERE listing_ad_id IN (
                        SELECT id FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)
                    )
                    """
                ),
                {"platform_listing_ids": [inside_listing_id, direct_listing_id, unrelated_listing_id]},
            )
            await conn.execute(
                text("DELETE FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)"),
                {"platform_listing_ids": [inside_listing_id, direct_listing_id, unrelated_listing_id]},
            )
            await conn.execute(
                text("DELETE FROM properties WHERE fingerprint = ANY(:fingerprints)"),
                {"fingerprints": [inside_fingerprint, direct_fingerprint, unrelated_fingerprint]},
            )
            await conn.execute(
                text("DELETE FROM zones WHERE fingerprint = :zone_fingerprint"),
                {"zone_fingerprint": zone_fingerprint},
            )

    try:
        schema_ready = await _phase5_schema_ready()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")

        await _cleanup()

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
                        isochrone_geom,
                        state
                    ) VALUES (
                        :fingerprint,
                        'transit',
                        30,
                        1200,
                        ST_GeomFromText(:polygon_wkt, 4326),
                        'complete'
                    )
                    """
                ),
                {
                    "fingerprint": zone_fingerprint,
                    "polygon_wkt": f"POLYGON(({inside_lon - 0.01} {inside_lat - 0.01}, {inside_lon + 0.01} {inside_lat - 0.01}, {inside_lon + 0.01} {inside_lat + 0.01}, {inside_lon - 0.01} {inside_lat + 0.01}, {inside_lon - 0.01} {inside_lat - 0.01}))",
                },
            )

        await upsert_property_and_ad(
            fingerprint=inside_fingerprint,
            address_normalized="Rua Dentro, Itaim Bibi, São Paulo, SP",
            lat=inside_lat,
            lon=inside_lon,
            area_m2=70,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="quintoandar",
            platform_listing_id=inside_listing_id,
            url="https://example.org/quintoandar/inside",
            advertised_usage_type="rent",
            price=Decimal("3500"),
            condo_fee=Decimal("500"),
            iptu=Decimal("100"),
            raw_payload={"image_url": "https://example.org/inside.jpg"},
        )
        await upsert_property_and_ad(
            fingerprint=direct_fingerprint,
            address_normalized="Rua Fora, Vila Olímpia, São Paulo, SP",
            lat=direct_lat,
            lon=direct_lon,
            area_m2=65,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="zapimoveis",
            platform_listing_id=direct_listing_id,
            url="https://example.org/zap/direct",
            advertised_usage_type="rent",
            price=Decimal("4200"),
            condo_fee=Decimal("300"),
            iptu=Decimal("50"),
            raw_payload={
                "image_url": "https://example.org/direct.jpg",
                "search_location_normalized": direct_search_location,
            },
        )
        await upsert_property_and_ad(
            fingerprint=unrelated_fingerprint,
            address_normalized="Rua Distante, Moema, São Paulo, SP",
            lat=unrelated_lat,
            lon=unrelated_lon,
            area_m2=55,
            bedrooms=1,
            bathrooms=1,
            parking=0,
            usage_type="residential",
            platform="vivareal",
            platform_listing_id=unrelated_listing_id,
            url="https://example.org/vr/outside",
            advertised_usage_type="rent",
            price=Decimal("3000"),
            condo_fee=Decimal("200"),
            iptu=Decimal("25"),
            raw_payload={
                "image_url": "https://example.org/outside.jpg",
                "search_location_normalized": unrelated_search_location,
            },
        )

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE listing_snapshots
                    SET observed_at = :observed_at
                    WHERE listing_ad_id IN (
                        SELECT id FROM listing_ads WHERE platform_listing_id = ANY(:listing_ids)
                    )
                    """
                ),
                {
                    "observed_at": datetime.now(timezone.utc) - timedelta(minutes=5),
                    "listing_ids": [direct_listing_id, unrelated_listing_id],
                },
            )
            await conn.execute(
                text(
                    """
                    UPDATE listing_snapshots
                    SET observed_at = :observed_at
                    WHERE listing_ad_id IN (
                        SELECT id FROM listing_ads WHERE platform_listing_id = :listing_id
                    )
                    """
                ),
                {
                    "observed_at": datetime.now(timezone.utc) - timedelta(hours=2),
                    "listing_id": inside_listing_id,
                },
            )

        cards = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["quintoandar", "zapimoveis", "vivareal"],
            observed_since=observed_since,
            spatial_scope="all",
            search_location_normalized=direct_search_location,
            address_scope="all_addresses",
        )

        addresses = {card["address_normalized"] for card in cards}
        assert "Rua Dentro, Itaim Bibi, São Paulo, SP" in addresses
        assert "Rua Fora, Vila Olímpia, São Paulo, SP" in addresses
        assert "Rua Distante, Moema, São Paulo, SP" in addresses

        cards_selected_address = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["quintoandar", "zapimoveis", "vivareal"],
            observed_since=observed_since,
            spatial_scope="all",
            search_location_normalized=direct_search_location,
            address_scope="selected_address",
        )

        selected_address_addresses = {card["address_normalized"] for card in cards_selected_address}
        assert selected_address_addresses == {"Rua Fora, Vila Olímpia, São Paulo, SP"}
    finally:
        if schema_ready:
            await _cleanup()
        await close_db()


@pytest.mark.anyio
async def test_upsert_property_and_ad_stores_usage_type_per_listing_ad() -> None:
    init_db(os.environ["DATABASE_URL"])

    fingerprint = compute_property_fingerprint(
        address_normalized="Rua Teste Comercial, 50",
        lat=-23.5505,
        lon=-46.6333,
        area_m2=31,
        bedrooms=0,
    )
    residential_listing_id = f"usage-res-{uuid4().hex[:8]}"
    commercial_listing_id = f"usage-com-{uuid4().hex[:8]}"
    schema_ready = False

    try:
        schema_ready = await _phase5_schema_ready()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    DELETE FROM listing_snapshots
                    WHERE listing_ad_id IN (
                        SELECT id FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)
                    )
                    """
                ),
                {"platform_listing_ids": [residential_listing_id, commercial_listing_id]},
            )
            await conn.execute(
                text("DELETE FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)"),
                {"platform_listing_ids": [residential_listing_id, commercial_listing_id]},
            )
            await conn.execute(
                text("DELETE FROM properties WHERE fingerprint = :fingerprint"),
                {"fingerprint": fingerprint},
            )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized="Rua Teste Comercial, 50",
            lat=-23.5505,
            lon=-46.6333,
            area_m2=31,
            bedrooms=0,
            bathrooms=1,
            parking=0,
            usage_type="residential",
            platform="zapimoveis",
            platform_listing_id=residential_listing_id,
            url="https://www.zapimoveis.com.br/imovel/aluguel-apartamento-centro-sp-id-1/",
            advertised_usage_type="rent",
            price=Decimal("3100"),
            condo_fee=Decimal("200"),
            iptu=Decimal("50"),
            raw_payload={"url": "https://www.zapimoveis.com.br/imovel/aluguel-apartamento-centro-sp-id-1/"},
        )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized="Rua Teste Comercial, 50",
            lat=-23.5505,
            lon=-46.6333,
            area_m2=31,
            bedrooms=0,
            bathrooms=1,
            parking=0,
            usage_type="commercial",
            platform="zapimoveis",
            platform_listing_id=commercial_listing_id,
            url="https://www.zapimoveis.com.br/imovel/aluguel-conjunto-comercial-centro-sp-id-1/",
            advertised_usage_type="rent",
            price=Decimal("3100"),
            condo_fee=Decimal("200"),
            iptu=Decimal("50"),
            raw_payload={"url": "https://www.zapimoveis.com.br/imovel/aluguel-conjunto-comercial-centro-sp-id-1/"},
        )

        async with engine.connect() as conn:
            property_usage_type = await conn.scalar(
                text("SELECT usage_type FROM properties WHERE fingerprint = :fingerprint"),
                {"fingerprint": fingerprint},
            )
            listing_rows = (
                await conn.execute(
                    text(
                        """
                        SELECT platform_listing_id, usage_type, usage_type_inferred
                        FROM listing_ads
                        WHERE platform_listing_id = ANY(:platform_listing_ids)
                        ORDER BY platform_listing_id
                        """
                    ),
                    {"platform_listing_ids": [residential_listing_id, commercial_listing_id]},
                )
            ).mappings().all()

        usage_by_listing = {row["platform_listing_id"]: row for row in listing_rows}

        assert property_usage_type is None
        assert usage_by_listing[residential_listing_id]["usage_type"] == "residential"
        assert usage_by_listing[commercial_listing_id]["usage_type"] == "commercial"
        assert usage_by_listing[residential_listing_id]["usage_type_inferred"] is True
        assert usage_by_listing[commercial_listing_id]["usage_type_inferred"] is True
    finally:
        if schema_ready:
            engine = get_engine()
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        DELETE FROM listing_snapshots
                        WHERE listing_ad_id IN (
                            SELECT id FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)
                        )
                        """
                    ),
                    {"platform_listing_ids": [residential_listing_id, commercial_listing_id]},
                )
                await conn.execute(
                    text("DELETE FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)"),
                    {"platform_listing_ids": [residential_listing_id, commercial_listing_id]},
                )
                await conn.execute(
                    text("DELETE FROM properties WHERE fingerprint = :fingerprint"),
                    {"fingerprint": fingerprint},
                )
        await close_db()


@pytest.mark.anyio
async def test_fetch_listing_cards_for_zone_filters_by_listing_ad_usage_type() -> None:
    init_db(os.environ["DATABASE_URL"])

    journey_id = uuid4()
    zone_fingerprint = f"zone-usage-filter-{uuid4().hex[:8]}"
    residential_listing_id = f"usage-filter-res-{uuid4().hex[:8]}"
    commercial_listing_id = f"usage-filter-com-{uuid4().hex[:8]}"
    address_label = "Rua Uso Misto, Sumaré, São Paulo, SP"
    lat = -11.1111
    lon = -47.2222
    search_location_normalized = f"seed-usage-filter-{uuid4().hex[:8]}"
    fingerprint = compute_property_fingerprint(
        address_normalized=address_label,
        lat=lat,
        lon=lon,
        area_m2=80,
        bedrooms=2,
    )
    schema_ready = False

    try:
        schema_ready = await _phase5_schema_ready()
        if not schema_ready:
            pytest.skip("Phase 5 schema not migrated. Run alembic upgrade head.")

        await _cleanup_fetch_listing_cards_rows(
            fingerprint=fingerprint,
            platform_listing_ids=[residential_listing_id, commercial_listing_id],
            zone_fingerprint=zone_fingerprint,
        )

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
                        isochrone_geom,
                        state
                    )
                    VALUES (
                        :zone_fingerprint,
                        'transit',
                        30,
                        1200,
                        ST_GeomFromText(:polygon_wkt, 4326),
                        'complete'
                    )
                    """
                ),
                {
                    "zone_fingerprint": zone_fingerprint,
                    "polygon_wkt": "POLYGON((-47.2272 -11.1161, -47.2172 -11.1161, -47.2172 -11.1061, -47.2272 -11.1061, -47.2272 -11.1161))",
                },
            )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=lat,
            lon=lon,
            area_m2=80,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="residential",
            platform="zapimoveis",
            platform_listing_id=residential_listing_id,
            url="https://www.zapimoveis.com.br/imovel/aluguel-apartamento-sumare-sao-paulo-sp-80m2-id-1/",
            advertised_usage_type="rent",
            price=Decimal("4500"),
            condo_fee=Decimal("300"),
            iptu=Decimal("100"),
            raw_payload={"url": "https://www.zapimoveis.com.br/imovel/aluguel-apartamento-sumare-sao-paulo-sp-80m2-id-1/", "search_location_normalized": search_location_normalized},
        )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=address_label,
            lat=lat,
            lon=lon,
            area_m2=80,
            bedrooms=2,
            bathrooms=2,
            parking=1,
            usage_type="commercial",
            platform="vivareal",
            platform_listing_id=commercial_listing_id,
            url="https://www.vivareal.com.br/imovel/ponto-comercial-sumare-sao-paulo-80m2-aluguel-id-2/",
            advertised_usage_type="rent",
            price=Decimal("5200"),
            condo_fee=Decimal("0"),
            iptu=Decimal("0"),
            raw_payload={"url": "https://www.vivareal.com.br/imovel/ponto-comercial-sumare-sao-paulo-80m2-aluguel-id-2/", "search_location_normalized": search_location_normalized},
        )

        residential_cards = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["zapimoveis", "vivareal"],
            search_location_normalized=search_location_normalized,
            address_scope="selected_address",
        )
        commercial_cards = await fetch_listing_cards_for_zone(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="commercial",
            platforms=["zapimoveis", "vivareal"],
            search_location_normalized=search_location_normalized,
            address_scope="selected_address",
        )

        assert len(residential_cards) == 1
        assert residential_cards[0]["platform_listing_id"] == residential_listing_id
        assert residential_cards[0]["usage_type"] == "residential"

        assert len(commercial_cards) == 1
        assert commercial_cards[0]["platform_listing_id"] == commercial_listing_id
        assert commercial_cards[0]["usage_type"] == "commercial"
    finally:
        if schema_ready:
            engine = get_engine()
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        DELETE FROM listing_snapshots
                        WHERE listing_ad_id IN (
                            SELECT id FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)
                        )
                        """
                    ),
                    {"platform_listing_ids": [residential_listing_id, commercial_listing_id]},
                )
                await conn.execute(
                    text("DELETE FROM listing_ads WHERE platform_listing_id = ANY(:platform_listing_ids)"),
                    {"platform_listing_ids": [residential_listing_id, commercial_listing_id]},
                )
                await conn.execute(
                    text("DELETE FROM properties WHERE fingerprint = :fingerprint"),
                    {"fingerprint": fingerprint},
                )
                await conn.execute(
                    text("DELETE FROM zones WHERE fingerprint = :zone_fingerprint"),
                    {"zone_fingerprint": zone_fingerprint},
                )
        await close_db()
