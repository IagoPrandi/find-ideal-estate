from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from src.core.db import close_db, get_engine, init_db  # noqa: E402
from src.modules.public_safety import ingest_public_safety_to_postgis  # noqa: E402
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

        public_safety_result = await ingest_public_safety_to_postgis(
            get_engine(),
            cache_dir=ROOT / "data_cache",
            source_year=int(os.getenv("PUBLIC_SAFETY_YEAR", "2025")),
        )
        print("public_safety_deleted_rows=", public_safety_result.deleted_rows)
        print("public_safety_inserted_rows=", public_safety_result.inserted_rows)
        print("public_safety_dropped_rows=", public_safety_result.dropped_rows)
        print("public_safety_source=", public_safety_result.source_label)
        return 0
    finally:
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
