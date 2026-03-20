import os
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import text

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from src.core.db import close_db, get_engine, init_db  # noqa: E402
from src.modules.transport.gtfs_ingestion import ingest_gtfs_to_postgis  # noqa: E402


def _write_minimal_gtfs_files(base_dir: Path) -> None:
    (base_dir / "stops.txt").write_text(
        "stop_id,stop_name,stop_lat,stop_lon\n"
        "S1,Stop One,-23.5501,-46.6301\n"
        "S2,Stop Two,-23.5602,-46.6402\n",
        encoding="utf-8",
    )
    (base_dir / "routes.txt").write_text(
        "route_id,route_short_name,route_long_name,route_type\n"
        "R1,1,Route One,3\n",
        encoding="utf-8",
    )
    (base_dir / "trips.txt").write_text(
        "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id\n"
        "R1,WK,T1,Centro,0,SH1\n",
        encoding="utf-8",
    )
    (base_dir / "stop_times.txt").write_text(
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S1,1\n"
        "T1,08:10:00,08:10:00,S2,2\n",
        encoding="utf-8",
    )
    (base_dir / "shapes.txt").write_text(
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        "SH1,-23.5501,-46.6301,1\n"
        "SH1,-23.5602,-46.6402,2\n",
        encoding="utf-8",
    )


async def _ensure_phase3_schema() -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        exists = await conn.execute(text("SELECT to_regclass('public.dataset_versions') IS NOT NULL"))
        return bool(exists.scalar())


async def _reset_phase3_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for table_name in ("gtfs_stop_times", "gtfs_trips", "gtfs_routes", "gtfs_shapes", "gtfs_stops"):
            await conn.execute(text(f"TRUNCATE TABLE {table_name}"))
        await conn.execute(text("DELETE FROM dataset_versions WHERE dataset_type = 'gtfs_sptrans'"))


async def _read_scalar(sql: str) -> int:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        return int(result.scalar_one())


@pytest.mark.anyio
async def test_phase3_gtfs_ingestion_hash_skip_and_dataset_version(tmp_path: Path) -> None:
    init_db(os.environ["DATABASE_URL"])
    try:
        if not await _ensure_phase3_schema():
            pytest.skip("Phase 3 schema not migrated. Run alembic upgrade head.")

        _write_minimal_gtfs_files(tmp_path)
        await _reset_phase3_tables()

        first = await ingest_gtfs_to_postgis(get_engine(), gtfs_dir=tmp_path)
        assert first.skipped is False
        assert first.row_counts["gtfs_stops"] == 2

        stops_count = await _read_scalar("SELECT count(*) FROM gtfs_stops")
        assert stops_count == 2

        current_versions = await (
            _read_scalar("SELECT count(*) FROM dataset_versions WHERE dataset_type = 'gtfs_sptrans' AND is_current = true")
        )
        assert current_versions == 1

        gist_indexes = await (
            _read_scalar(
                """
                SELECT count(*)
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'gtfs_stops'
                  AND indexdef ILIKE '%USING gist%'
                """
            )
        )
        assert gist_indexes >= 1

        started = time.perf_counter()
        second = await ingest_gtfs_to_postgis(get_engine(), gtfs_dir=tmp_path)
        elapsed = time.perf_counter() - started
        assert second.skipped is True
        assert elapsed < 2.0
    finally:
        await close_db()