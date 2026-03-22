"""PRD M5.5 verification script.

Acceptance criterion (PRD §M5.5):
  Inserir mesmo imóvel via 2 plataformas →
    SELECT count(*) FROM properties WHERE fingerprint = :fp = 1.

Additional invariants verified:
  - 2 distinct listing_ads linked to the same property_id.
  - current_best_price = MIN(price) across the two ads.
  - second_best_price = second lowest price.
  - duplication_badge contains "2 plataformas".
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from core.db import close_db, get_engine, init_db  # noqa: E402
from modules.listings.dedup import (  # noqa: E402
    compute_property_fingerprint,
    fetch_listing_cards_for_zone,
    upsert_property_and_ad,
)
from sqlalchemy import text  # noqa: E402

# ---------------------------------------------------------------------------
# Deterministic test fixtures
# ---------------------------------------------------------------------------

# Property identity — identical across both platforms
_ADDRESS = "Rua Vergueiro 3185, Apto 101, Vila Mariana, São Paulo"
_LAT = -23.5951
_LON = -46.6388
_AREA = 62.0
_BEDROOMS = 2

# Zone polygon that contains the above point
# A small square around (-23.5951, -46.6388)
_ZONE_POLYGON_WKT = (
    "POLYGON(("
    "-46.6500 -23.6050,"
    "-46.6250 -23.6050,"
    "-46.6250 -23.5850,"
    "-46.6500 -23.5850,"
    "-46.6500 -23.6050"
    "))"
)

_PLATFORM_A = "quintoandar"
_PLI_A = "v555_dedup_test_a"
_PRICE_A = Decimal("2800")

_PLATFORM_B = "zapimoveis"
_PLI_B = "v555_dedup_test_b"
_PRICE_B = Decimal("3100")

_ZONE_FP = "dedup_verify_zone_v555"


async def _cleanup(conn) -> None:
    await conn.execute(
        text(
            "DELETE FROM listing_snapshots "
            "WHERE listing_ad_id IN ("
            "  SELECT id FROM listing_ads "
            "  WHERE platform_listing_id IN (:pli_a, :pli_b)"
            ")"
        ),
        {"pli_a": _PLI_A, "pli_b": _PLI_B},
    )
    await conn.execute(
        text(
            "DELETE FROM listing_ads "
            "WHERE platform_listing_id IN (:pli_a, :pli_b)"
        ),
        {"pli_a": _PLI_A, "pli_b": _PLI_B},
    )
    fingerprint = compute_property_fingerprint(_ADDRESS, _LAT, _LON, _AREA, _BEDROOMS)
    await conn.execute(
        text("DELETE FROM properties WHERE fingerprint = :fp"),
        {"fp": fingerprint},
    )
    await conn.execute(
        text("DELETE FROM zones WHERE fingerprint = :fp"),
        {"fp": _ZONE_FP},
    )


async def main() -> None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    init_db(database_url)
    engine = get_engine()

    fingerprint = compute_property_fingerprint(_ADDRESS, _LAT, _LON, _AREA, _BEDROOMS)

    try:
        # ------------------------------------------------------------------
        # 1. Seed zone so fetch_listing_cards_for_zone can join on it
        # ------------------------------------------------------------------
        async with engine.begin() as conn:
            await _cleanup(conn)

            await conn.execute(
                text(
                    """
                    INSERT INTO zones (
                        fingerprint, modal, max_time_minutes, radius_meters,
                        state, isochrone_geom, created_at, updated_at
                    ) VALUES (
                        :fp, 'walking', 30, 1500,
                        'complete',
                        ST_SetSRID(ST_GeomFromText(:wkt), 4326),
                        now(), now()
                    )
                    """
                ),
                {
                    "fp": _ZONE_FP,
                    "wkt": _ZONE_POLYGON_WKT,
                },
            )

        # ------------------------------------------------------------------
        # 2. Insert same property via Platform A
        # ------------------------------------------------------------------
        pid_a, _aid_a = await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=_ADDRESS,
            lat=_LAT,
            lon=_LON,
            area_m2=_AREA,
            bedrooms=_BEDROOMS,
            bathrooms=1,
            parking=1,
            usage_type="residential",
            platform=_PLATFORM_A,
            platform_listing_id=_PLI_A,
            url=f"https://quintoandar.com.br/imovel/{_PLI_A}",
            advertised_usage_type="rent",
            price=_PRICE_A,
            condo_fee=None,
            iptu=None,
            raw_payload=None,
        )

        # ------------------------------------------------------------------
        # 3. Insert same property via Platform B
        # ------------------------------------------------------------------
        pid_b, _aid_b = await upsert_property_and_ad(
            fingerprint=fingerprint,
            address_normalized=_ADDRESS,
            lat=_LAT,
            lon=_LON,
            area_m2=_AREA,
            bedrooms=_BEDROOMS,
            bathrooms=1,
            parking=1,
            usage_type="residential",
            platform=_PLATFORM_B,
            platform_listing_id=_PLI_B,
            url=f"https://zapimoveis.com.br/imovel/{_PLI_B}",
            advertised_usage_type="rent",
            price=_PRICE_B,
            condo_fee=None,
            iptu=None,
            raw_payload=None,
        )

        # ------------------------------------------------------------------
        # 4. Verify 1 property, 2 listing_ads
        # ------------------------------------------------------------------
        async with engine.connect() as conn:
            prop_count = (
                await conn.execute(
                    text("SELECT count(*) FROM properties WHERE fingerprint = :fp"),
                    {"fp": fingerprint},
                )
            ).scalar_one()

            ad_count = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM listing_ads WHERE property_id = :pid"
                    ),
                    {"pid": pid_a},
                )
            ).scalar_one()

        assert prop_count == 1, f"Expected 1 property, got {prop_count}"
        assert pid_a == pid_b, (
            f"Both platforms must resolve to same property_id; got {pid_a} vs {pid_b}"
        )
        assert ad_count == 2, f"Expected 2 listing_ads, got {ad_count}"
        print(f"[CHECK] property_count=1  ✓  (fingerprint={fingerprint[:12]}…)")
        print(f"[CHECK] listing_ads_count=2  ✓  (property_id={pid_a})")

        # ------------------------------------------------------------------
        # 5. Verify price fields and badge via fetch_listing_cards_for_zone
        # ------------------------------------------------------------------
        cards = await fetch_listing_cards_for_zone(
            zone_fingerprint=_ZONE_FP,
            search_type="rent",
            usage_type="residential",
            platforms=[_PLATFORM_A, _PLATFORM_B],
        )

        # Only one card expected (both ads → same property → 1 row via price_rank=1)
        assert len(cards) >= 1, f"Expected ≥1 card, got {len(cards)}"

        card = next(c for c in cards if c["property_id"] == str(pid_a))

        current_best = Decimal(card["current_best_price"])
        expected_best = min(_PRICE_A, _PRICE_B)
        assert current_best == expected_best, (
            f"current_best_price={current_best} != expected {expected_best}"
        )
        print(f"[CHECK] current_best_price={current_best}  ✓  (MIN of {_PRICE_A},{_PRICE_B})")

        second_best = card.get("second_best_price")
        expected_second = max(_PRICE_A, _PRICE_B)
        assert second_best is not None, "second_best_price should not be None"
        assert Decimal(second_best) == expected_second, (
            f"second_best_price={second_best} != expected {expected_second}"
        )
        print(f"[CHECK] second_best_price={second_best}  ✓")

        badge = card.get("duplication_badge")
        assert badge is not None, "duplication_badge must be set for 2-platform property"
        assert "2 plataformas" in badge, f"Badge should mention '2 plataformas'; got: {badge!r}"
        print(f"[CHECK] duplication_badge={badge!r}  ✓")

        print("\n[OK] M5.5 verification passed")

    finally:
        async with engine.begin() as conn:
            await _cleanup(conn)
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
