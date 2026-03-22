"""PRD M5.6 verification script.

Acceptance criterion (PRD §M5.6):
  3 buscas para o mesmo endereço em 24h →
    agregação retorna demand_count = 3.

Also verifies:
  - record_search_request() persists every call.
  - get_prewarm_targets() aggregates correctly by location.
  - cache_miss requests are also counted (drives prewarm).
  - result_source variance within same address does not split the group.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from core.db import close_db, get_engine, init_db  # noqa: E402
from modules.listings.cache import compute_config_hash  # noqa: E402
from modules.listings.search_requests import (  # noqa: E402
    get_prewarm_targets,
    record_search_request,
)
from sqlalchemy import text  # noqa: E402

# ---------------------------------------------------------------------------
# Deterministic fixture values
# ---------------------------------------------------------------------------

_NORM_ADDR = "rua vergueiro 3185 vila mariana sao paulo"
_LABEL = "Rua Vergueiro 3185, Vila Mariana, São Paulo"
_ZONE_FP = "m56-verify-zone-fp"
_SEARCH_TYPE = "rent"
_USAGE_TYPE = "residential"
_PLATFORMS = ["quintoandar", "zapimoveis"]


async def _cleanup(conn) -> None:
    await conn.execute(
        text(
            "DELETE FROM listing_search_requests "
            "WHERE search_location_normalized = :n"
        ),
        {"n": _NORM_ADDR},
    )


async def main() -> None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    init_db(database_url)
    engine = get_engine()

    platforms_hash = compute_config_hash(_SEARCH_TYPE, _USAGE_TYPE, _PLATFORMS)

    try:
        async with engine.begin() as conn:
            await _cleanup(conn)

        # ------------------------------------------------------------------
        # 1. Insert 3 search requests for the same normalized address,
        #    mixing result_source to confirm aggregation is address-scoped.
        # ------------------------------------------------------------------
        for result_source in ("cache_hit", "cache_partial", "cache_miss"):
            rid = await record_search_request(
                zone_fingerprint=_ZONE_FP,
                search_location_normalized=_NORM_ADDR,
                search_location_label=_LABEL,
                search_location_type="street",
                search_type=_SEARCH_TYPE,
                usage_type=_USAGE_TYPE,
                platforms_hash=platforms_hash,
                result_source=result_source,
            )
            assert rid is not None, "record_search_request must return the new row id"

        print("[CHECK] 3 rows inserted  ✓")

        # ------------------------------------------------------------------
        # 2. Verify demand aggregation: get_prewarm_targets(lookback_hours=24)
        # ------------------------------------------------------------------
        targets = await get_prewarm_targets(lookback_hours=24, limit=50)

        matching = [
            t
            for t in targets
            if t["search_location_normalized"] == _NORM_ADDR
        ]
        assert len(matching) == 1, (
            f"Expected exactly 1 aggregated row for norm addr, got {len(matching)}"
        )

        demand_count = matching[0]["demand_count"]
        assert demand_count == 3, (
            f"Expected demand_count=3, got {demand_count}"
        )
        print(f"[CHECK] demand_count={demand_count}  ✓")

        # ------------------------------------------------------------------
        # 3. Sanity: different address produces a separate group
        # ------------------------------------------------------------------
        other_norm = "av paulista 1000 bela vista sao paulo"
        await record_search_request(
            zone_fingerprint="m56-other-zone",
            search_location_normalized=other_norm,
            search_location_label="Av. Paulista 1000",
            search_location_type="street",
            search_type=_SEARCH_TYPE,
            usage_type=_USAGE_TYPE,
            platforms_hash=platforms_hash,
            result_source="cache_miss",
        )

        targets2 = await get_prewarm_targets(lookback_hours=24, limit=50)
        addr_a = next(
            (t for t in targets2 if t["search_location_normalized"] == _NORM_ADDR),
            None,
        )
        addr_b = next(
            (t for t in targets2 if t["search_location_normalized"] == other_norm),
            None,
        )
        assert addr_a is not None, "Original address must still be present"
        assert addr_b is not None, "Second address must appear as separate group"
        assert addr_a["demand_count"] == 3, "Original address count unchanged"
        assert addr_b["demand_count"] == 1, "New address demand_count = 1"
        print("[CHECK] address isolation  ✓  (2 distinct groups)")

        print("\n[OK] M5.6 verification passed")

    finally:
        async with engine.begin() as conn:
            await _cleanup(conn)
            await conn.execute(
                text(
                    "DELETE FROM listing_search_requests "
                    "WHERE search_location_normalized = :n"
                ),
                {"n": "av paulista 1000 bela vista sao paulo"},
            )
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
