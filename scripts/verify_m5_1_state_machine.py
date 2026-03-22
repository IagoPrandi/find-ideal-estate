from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from core.db import close_db, get_engine, init_db  # noqa: E402
from modules.listings.cache import create_cache_record, transition_cache_status  # noqa: E402
from modules.listings.models import (  # noqa: E402
    InvalidStateTransition,
    ZoneCacheStatus,
)
from sqlalchemy import text  # noqa: E402


async def main() -> int:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    init_db(database_url)

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            table_exists = await conn.execute(
                text("SELECT to_regclass('public.zone_listing_caches')")
            )
            if table_exists.scalar_one() is None:
                print("[FAIL] zone_listing_caches table not found. Run alembic upgrade head.")
                return 2

        zone_fp = "m5_1_verify_fp"
        config_hash = "m5_1_verify_cfg"

        cache_id = await create_cache_record(zone_fp, config_hash)

        async with engine.connect() as conn:
            before = await conn.execute(
                text("SELECT status FROM zone_listing_caches WHERE id = :id"),
                {"id": cache_id},
            )
            before_status = before.scalar_one()

        blocked = False
        try:
            await transition_cache_status(
                cache_id,
                ZoneCacheStatus.PENDING,
                ZoneCacheStatus.COMPLETE,
            )
        except InvalidStateTransition as exc:
            blocked = True
            print(f"raised {type(exc).__name__}: {exc}")

        async with engine.begin() as conn:
            after = await conn.execute(
                text("SELECT status FROM zone_listing_caches WHERE id = :id"),
                {"id": cache_id},
            )
            after_status = after.scalar_one()
            await conn.execute(
                text("DELETE FROM zone_listing_caches WHERE id = :id"),
                {"id": cache_id},
            )

        print(f"before_status={before_status}")
        print(f"after_status={after_status}")
        print(f"blocked={blocked}")

        if blocked and before_status == ZoneCacheStatus.PENDING and after_status == ZoneCacheStatus.PENDING:
            print("[OK] M5.1 DB verification passed")
            return 0

        print("[FAIL] M5.1 DB verification failed")
        return 1
    finally:
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
