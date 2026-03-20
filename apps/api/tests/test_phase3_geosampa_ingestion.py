import os
import sys
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
from src.modules.transport import geosampa_ingestion  # noqa: E402


async def _ensure_phase3_schema() -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT to_regclass('public.dataset_versions') IS NOT NULL")
        )
        return bool(exists.scalar())


async def _reset_phase3_geosampa_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for table_name in (
            "geosampa_metro_stations",
            "geosampa_trem_stations",
            "geosampa_bus_stops",
            "geosampa_bus_terminals",
            "geosampa_bus_corridors",
        ):
            await conn.execute(text(f"TRUNCATE TABLE {table_name}"))
        await conn.execute(
            text("DELETE FROM dataset_versions WHERE dataset_type = 'geosampa_transport'")
        )


async def _read_scalar(sql: str) -> int:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        return int(result.scalar_one())


def _write_placeholder_geosampa_files(base_dir: Path) -> None:
    for _, filename in geosampa_ingestion._GEOSAMPA_DATASETS:  # noqa: SLF001
        (base_dir / filename).write_bytes(b"placeholder")


@pytest.mark.anyio
async def test_phase3_geosampa_ingestion_registers_dataset_version_and_validates_geometries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db(os.environ["DATABASE_URL"])
    try:
        if not await _ensure_phase3_schema():
            pytest.skip("Phase 3 schema not migrated. Run alembic upgrade head.")

        _write_placeholder_geosampa_files(tmp_path)
        await _reset_phase3_geosampa_tables()

        async def fake_ogr_import(
            engine,
            database_url: str,
            source_path: Path,
            destination_table: str,
        ) -> None:
            assert database_url
            assert source_path.exists()
            async with engine.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {destination_table}"))
                await conn.execute(
                    text(
                        f"""
                        CREATE TABLE {destination_table} (
                            source_name TEXT,
                            geometry geometry(Geometry, 4326) NOT NULL
                        )
                        """
                    )
                )
                await conn.execute(
                    text(
                        f"""
                        INSERT INTO {destination_table} (source_name, geometry)
                        VALUES (:source_name, ST_SetSRID(ST_MakePoint(-46.63, -23.55), 4326))
                        """
                    ),
                    {"source_name": source_path.name},
                )

        monkeypatch.setattr(geosampa_ingestion, "_run_ogr2ogr_import", fake_ogr_import)

        first = await geosampa_ingestion.ingest_geosampa_to_postgis(
            get_engine(),
            database_url=os.environ["DATABASE_URL"],
            geosampa_dir=tmp_path,
        )
        assert first.skipped is False
        assert first.row_counts["geosampa_metro_stations"] == 1

        metro_count = await _read_scalar("SELECT count(*) FROM geosampa_metro_stations")
        assert metro_count == 1

        invalid_count = await _read_scalar(
            "SELECT count(*) FROM geosampa_metro_stations WHERE NOT ST_IsValid(geometry)"
        )
        assert invalid_count == 0

        current_versions = await _read_scalar(
            "SELECT count(*) FROM dataset_versions "
            "WHERE dataset_type = 'geosampa_transport' AND is_current = true"
        )
        assert current_versions == 1

        second = await geosampa_ingestion.ingest_geosampa_to_postgis(
            get_engine(),
            database_url=os.environ["DATABASE_URL"],
            geosampa_dir=tmp_path,
        )
        assert second.skipped is True
    finally:
        await close_db()


@pytest.mark.anyio
async def test_phase3_geosampa_ingestion_fails_when_staging_has_invalid_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db(os.environ["DATABASE_URL"])
    try:
        if not await _ensure_phase3_schema():
            pytest.skip("Phase 3 schema not migrated. Run alembic upgrade head.")

        _write_placeholder_geosampa_files(tmp_path)
        await _reset_phase3_geosampa_tables()

        async def fake_ogr_import_invalid(
            engine,
            database_url: str,
            source_path: Path,
            destination_table: str,
        ) -> None:
            assert database_url
            assert source_path.exists()
            async with engine.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {destination_table}"))
                await conn.execute(
                    text(
                        f"""
                        CREATE TABLE {destination_table} (
                            source_name TEXT,
                            geometry geometry(Geometry, 4326) NOT NULL
                        )
                        """
                    )
                )
                await conn.execute(
                    text(
                        f"""
                        INSERT INTO {destination_table} (source_name, geometry)
                        VALUES (
                            :source_name,
                            ST_GeomFromText('POLYGON((0 0,1 1,1 0,0 1,0 0))', 4326)
                        )
                        """
                    ),
                    {"source_name": source_path.name},
                )

        monkeypatch.setattr(geosampa_ingestion, "_run_ogr2ogr_import", fake_ogr_import_invalid)

        with pytest.raises(
            geosampa_ingestion.GeoSampaIngestionError,
            match="ST_IsValid check failed",
        ):
            await geosampa_ingestion.ingest_geosampa_to_postgis(
                get_engine(),
                database_url=os.environ["DATABASE_URL"],
                geosampa_dir=tmp_path,
            )
    finally:
        await close_db()
