from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from sqlalchemy import text  # noqa: E402
from src.core.db import close_db, get_engine, init_db  # noqa: E402
from src.modules.transport.geosampa_ingestion import ingest_geosampa_to_postgis  # noqa: E402


async def main() -> int:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    init_db(database_url)
    try:
        result = await ingest_geosampa_to_postgis(
            get_engine(),
            database_url=database_url,
            dataset_type="geosampa_transport",
            geosampa_dir=ROOT / "data_cache" / "geosampa",
        )
        print("ingestion_skipped=", result.skipped)
        print("ingestion_tables=", sorted(result.row_counts.keys()))

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS public_safety_incidents (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        occurred_at TIMESTAMPTZ,
                        category TEXT,
                        location geometry(Point, 4326)
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_location
                    ON public_safety_incidents USING GIST (location)
                    """
                )
            )
        print("public_safety_incidents_ready=true")
        return 0
    finally:
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
