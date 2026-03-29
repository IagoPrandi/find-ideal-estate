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

    zone_fingerprint = f"zone-dedup-{uuid4().hex[:8]}"
    platform_listing_ids = [f"dedup-qa-{uuid4().hex[:8]}", f"dedup-zap-{uuid4().hex[:8]}"]
    fingerprint = compute_property_fingerprint(
        address_normalized="Rua Teste Dedup, 100",
        lat=-23.5505,
        lon=-46.6333,
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
                    "polygon_wkt": "POLYGON((-46.64 -23.56, -46.62 -23.56, -46.62 -23.54, -46.64 -23.54, -46.64 -23.56))",
                },
            )

        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized="Rua Teste Dedup, 100",
            lat=-23.5505,
            lon=-46.6333,
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
            raw_payload={"image_url": "https://example.org/quintoandar.jpg"},
        )
        await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized="Rua Teste Dedup, 100",
            lat=-23.5505,
            lon=-46.6333,
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
            condo_fee=Decimal("450"),
            iptu=Decimal("90"),
            raw_payload={"image_url": "https://example.org/zap.jpg"},
        )

        cards = await fetch_listing_cards_for_zone(
            zone_fingerprint=zone_fingerprint,
            search_type="rent",
            usage_type="residential",
            platforms=["quintoandar", "zapimoveis"],
            observed_since=observed_since,
            spatial_scope="all",
        )

        assert len(cards) == 1
        assert cards[0]["platform"] == "zapimoveis"
        assert cards[0]["inside_zone"] is True
        assert cards[0]["has_coordinates"] is True
        assert cards[0]["platforms_available"] == ["quintoandar", "zapimoveis"]
        assert [variant["platform"] for variant in cards[0]["platform_variants"]] == ["zapimoveis", "quintoandar"]
        assert cards[0]["platform_variants"][0]["platform_listing_id"] == platform_listing_ids[1]
        assert cards[0]["platform_variants"][0]["url"] == "https://example.org/zap/dedup"
        assert cards[0]["platform_variants"][0]["current_best_price"] == "3300.00"
        assert cards[0]["platform_variants"][0]["condo_fee"] == "450.00"
        assert cards[0]["platform_variants"][0]["iptu"] == "90.00"
        assert cards[0]["platform_variants"][1]["platform_listing_id"] == platform_listing_ids[0]
        assert cards[0]["platform_variants"][1]["url"] == "https://example.org/quintoandar/dedup"
        assert cards[0]["platform_variants"][1]["current_best_price"] == "3500.00"
        assert cards[0]["platform_variants"][1]["condo_fee"] == "500.00"
        assert cards[0]["platform_variants"][1]["iptu"] == "100.00"
        assert str(cards[0]["condo_fee"]) == "450.00"
        assert str(cards[0]["iptu"]) == "90.00"
        assert str(cards[0]["second_best_price"]) == "3500.00"
    finally:
        if schema_ready:
            await _cleanup_fetch_listing_cards_rows(
                fingerprint=fingerprint,
                platform_listing_ids=platform_listing_ids,
                zone_fingerprint=zone_fingerprint,
            )
        await close_db()
