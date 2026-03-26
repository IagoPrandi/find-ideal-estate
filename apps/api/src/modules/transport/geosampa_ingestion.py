from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

_GEOSAMPA_DATASETS = (
    ("geosampa_metro_stations", "geoportal_estacao_metro_v2.gpkg"),
    ("geosampa_metro_lines", "geoportal_linha_metro_v4.gpkg"),
    ("geosampa_trem_stations", "geoportal_estacao_trem_v2.gpkg"),
    ("geosampa_trem_lines", "geoportal_linha_trem_v2.gpkg"),
    ("geosampa_bus_stops", "geoportal_ponto_onibus.gpkg"),
    ("geosampa_bus_lines", "SIRGAS_GPKG_linhaonibus.gpkg"),
    ("geosampa_bus_terminals", "geoportal_terminal_onibus_v2.gpkg"),
    ("geosampa_bus_corridors", "geoportal_corredor_onibus_v2.gpkg"),
    ("geosampa_vegetacao_significativa", "SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg"),
    ("geosampa_mancha_inundacao", "geoportal_mancha_inundacao_25.gpkg"),
)
_OGR2OGR_DOCKER_IMAGE = "geographica/gdal2:latest"
_SAFE_IDENTIFIER_RE = re.compile(r"[^a-z0-9_]+")


class GeoSampaIngestionError(RuntimeError):
    """Raised when GeoSampa ingestion cannot complete safely."""


@dataclass(frozen=True)
class GeoSampaIngestionResult:
    dataset_type: str
    version_hash: str
    skipped: bool
    source_label: str
    row_counts: dict[str, int]
    elapsed_seconds: float


def _hash_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _database_url_to_ogr_dsn(database_url: str, *, docker_host_mode: bool = False) -> str:
    normalized = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise GeoSampaIngestionError("DATABASE_URL must be PostgreSQL for GeoSampa ingestion")

    dbname = parsed.path.lstrip("/")
    if not dbname:
        raise GeoSampaIngestionError("DATABASE_URL is missing database name")

    host = parsed.hostname or "localhost"
    if docker_host_mode and host in {"localhost", "127.0.0.1"}:
        host = "host.docker.internal"

    dsn_parts = [
        f"host={host}",
        f"port={parsed.port or 5432}",
        f"dbname={dbname}",
    ]
    if parsed.username:
        dsn_parts.append(f"user={parsed.username}")
    if parsed.password:
        dsn_parts.append(f"password={parsed.password}")
    return " ".join(dsn_parts)


def _safe_identifier(raw_name: str, fallback_prefix: str, index: int) -> str:
    candidate = _SAFE_IDENTIFIER_RE.sub("_", raw_name.strip().lower()).strip("_")
    if not candidate:
        candidate = f"{fallback_prefix}_{index}"
    if candidate[0].isdigit():
        candidate = f"{fallback_prefix}_{candidate}"
    return candidate[:55]


def _gpkg_blob_to_wkb(blob: bytes) -> bytes:
    if len(blob) < 8 or blob[0:2] != b"GP":
        return blob

    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0x07
    envelope_sizes = {
        0: 0,
        1: 32,
        2: 48,
        3: 48,
        4: 64,
    }
    envelope_size = envelope_sizes.get(envelope_indicator)
    if envelope_size is None:
        raise GeoSampaIngestionError("Unsupported GeoPackage envelope type")

    header_size = 8 + envelope_size
    if len(blob) <= header_size:
        raise GeoSampaIngestionError("Invalid GeoPackage geometry blob")
    return blob[header_size:]


def _read_gpkg_rows(source_path: Path) -> tuple[list[str], list[tuple[object, ...]], int]:
    with sqlite3.connect(source_path) as conn:
        layer_row = conn.execute(
            """
            SELECT table_name
            FROM gpkg_contents
            WHERE data_type = 'features'
            ORDER BY table_name
            LIMIT 1
            """
        ).fetchone()
        if layer_row is None:
            raise GeoSampaIngestionError(f"No feature layer found in {source_path.name}")
        layer_name = str(layer_row[0])

        geom_row = conn.execute(
            """
            SELECT column_name, srs_id
            FROM gpkg_geometry_columns
            WHERE table_name = ?
            LIMIT 1
            """,
            (layer_name,),
        ).fetchone()
        if geom_row is None:
            raise GeoSampaIngestionError(f"No geometry metadata found in {source_path.name}")
        geometry_column = str(geom_row[0])
        source_srid = int(geom_row[1]) if geom_row[1] is not None else 4326

        pragma_rows = conn.execute(f'PRAGMA table_info("{layer_name}")').fetchall()
        raw_columns = [str(row[1]) for row in pragma_rows if str(row[1]) != geometry_column]
        select_columns = raw_columns + [geometry_column]
        quoted = ", ".join(f'"{name}"' for name in select_columns)
        rows = conn.execute(f'SELECT {quoted} FROM "{layer_name}"').fetchall()
        return raw_columns, rows, source_srid


async def _import_gpkg_fallback(
    engine: AsyncEngine,
    source_path: Path,
    destination_table: str,
) -> None:
    raw_columns, rows, source_srid = _read_gpkg_rows(source_path)
    normalized_columns = [
        _safe_identifier(name, "attr", idx) for idx, name in enumerate(raw_columns, start=1)
    ]

    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {destination_table}"))

        columns_sql = ", ".join(f"{column} TEXT" for column in normalized_columns)
        create_sql = f"CREATE TABLE {destination_table} ("
        if columns_sql:
            create_sql += f"{columns_sql}, "
        create_sql += "geometry geometry(Geometry, 4326) NOT NULL)"
        await conn.execute(text(create_sql))

        if not rows:
            return

        projection_sql = "ST_GeomFromWKB(:geometry_blob)"
        if source_srid > 0 and source_srid != 4326:
            projection_sql = f"ST_Transform(ST_SetSRID({projection_sql}, :source_srid), 4326)"
        else:
            projection_sql = f"ST_SetSRID({projection_sql}, 4326)"

        payload: list[dict[str, object]] = []
        for row in rows:
            attributes = row[:-1]
            geom_blob = row[-1]
            if geom_blob is None:
                continue

            record: dict[str, object] = {
                column: (str(value) if value is not None else None)
                for column, value in zip(normalized_columns, attributes)
            }
            record["geometry_blob"] = _gpkg_blob_to_wkb(geom_blob)
            record["source_srid"] = source_srid
            payload.append(record)

        if not payload:
            return

        geometry_sql = projection_sql
        placeholders = ", ".join(f":{column}" for column in normalized_columns)
        if placeholders:
            rewritten_sql = text(
                f"""
                INSERT INTO {destination_table} ({', '.join(normalized_columns)}, geometry)
                VALUES ({placeholders}, {geometry_sql})
                """
            )
        else:
            rewritten_sql = text(
                f"""
                INSERT INTO {destination_table} (geometry)
                VALUES ({geometry_sql})
                """
            )
        await conn.execute(rewritten_sql, payload)


async def _run_ogr2ogr_import(
    engine: AsyncEngine,
    database_url: str,
    source_path: Path,
    destination_table: str,
) -> None:
    dsn = _database_url_to_ogr_dsn(database_url)
    command = [
        "ogr2ogr",
        "-f",
        "PostgreSQL",
        f"PG:{dsn}",
        str(source_path),
        "-nln",
        destination_table,
        "-lco",
        "GEOMETRY_NAME=geometry",
        "-nlt",
        "PROMOTE_TO_MULTI",
        "-overwrite",
    ]
    try:
        process = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        docker_dsn = _database_url_to_ogr_dsn(database_url, docker_host_mode=True)
        source_dir = source_path.resolve().parent
        docker_command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{source_dir.as_posix()}:/data",
            _OGR2OGR_DOCKER_IMAGE,
            "ogr2ogr",
            "-f",
            "PostgreSQL",
            f"PG:{docker_dsn}",
            f"/data/{source_path.name}",
            "-nln",
            destination_table,
            "-lco",
            "GEOMETRY_NAME=geometry",
            "-nlt",
            "PROMOTE_TO_MULTI",
            "-overwrite",
        ]
        try:
            process = await asyncio.to_thread(
                subprocess.run,
                docker_command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            await _import_gpkg_fallback(engine, source_path, destination_table)
            return

    if process.returncode != 0:
        await _import_gpkg_fallback(engine, source_path, destination_table)
        return


async def _current_dataset_hash(conn: AsyncConnection, dataset_type: str) -> str | None:
    result = await conn.execute(
        text(
            """
            SELECT version_hash
            FROM dataset_versions
            WHERE dataset_type = :dataset_type
              AND is_current = true
            ORDER BY imported_at DESC
            LIMIT 1
            """
        ),
        {"dataset_type": dataset_type},
    )
    return result.scalar_one_or_none()


async def _upsert_dataset_version(
    conn: AsyncConnection,
    *,
    dataset_type: str,
    version_hash: str,
    source_label: str,
    row_counts: dict[str, int],
) -> None:
    metadata_payload = {
        "row_counts": row_counts,
        "source_label": source_label,
    }
    await conn.execute(
        text(
            """
            UPDATE dataset_versions
            SET is_current = false
            WHERE dataset_type = :dataset_type
              AND is_current = true
            """
        ),
        {"dataset_type": dataset_type},
    )
    await conn.execute(
        text(
            """
            INSERT INTO dataset_versions (
                dataset_type,
                version_hash,
                source_url,
                is_current,
                metadata
            )
            VALUES (:dataset_type, :version_hash, :source_label, true, CAST(:metadata AS JSONB))
            ON CONFLICT (dataset_type, version_hash)
            DO UPDATE
               SET source_url = EXCLUDED.source_url,
                   imported_at = now(),
                   is_current = true,
                   metadata = EXCLUDED.metadata
            """
        ),
        {
            "dataset_type": dataset_type,
            "version_hash": version_hash,
            "source_label": source_label,
            "metadata": json.dumps(metadata_payload),
        },
    )


async def _replace_production_tables(
    conn: AsyncConnection,
    table_names: tuple[str, ...],
    staging_tables: dict[str, str],
    suffix: str,
) -> None:
    for production_table in table_names:
        staging_table = staging_tables[production_table]
        old_table = f"{production_table}_old_{suffix}"
        await conn.execute(text(f"DROP TABLE IF EXISTS {old_table}"))
        exists_result = await conn.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"public.{production_table}"},
        )
        if bool(exists_result.scalar()):
            await conn.execute(text(f"ALTER TABLE {production_table} RENAME TO {old_table}"))
        await conn.execute(text(f"ALTER TABLE {staging_table} RENAME TO {production_table}"))
        await conn.execute(text(f"DROP TABLE IF EXISTS {old_table}"))


async def ingest_geosampa_to_postgis(
    engine: AsyncEngine,
    *,
    database_url: str,
    dataset_type: str = "geosampa_transport",
    geosampa_dir: Path | None = None,
) -> GeoSampaIngestionResult:
    started = time.perf_counter()
    effective_dir = geosampa_dir or Path("data_cache") / "geosampa"
    if not effective_dir.exists():
        raise GeoSampaIngestionError(f"GeoSampa directory not found: {effective_dir}")

    source_paths = [effective_dir / filename for _, filename in _GEOSAMPA_DATASETS]
    missing = [path for path in source_paths if not path.exists()]
    if missing:
        joined = ", ".join(path.name for path in missing)
        raise GeoSampaIngestionError(f"Missing GeoSampa files: {joined}")

    version_hash = _hash_files(source_paths)
    source_label = str(effective_dir)

    async with engine.begin() as conn:
        current_hash = await _current_dataset_hash(conn, dataset_type=dataset_type)
        if current_hash == version_hash:
            elapsed = time.perf_counter() - started
            return GeoSampaIngestionResult(
                dataset_type=dataset_type,
                version_hash=version_hash,
                skipped=True,
                source_label=source_label,
                row_counts={name: 0 for name, _ in _GEOSAMPA_DATASETS},
                elapsed_seconds=elapsed,
            )

    suffix = f"s{uuid4().hex[:8]}"
    staging_tables = {name: f"{name}_staging_{suffix}" for name, _ in _GEOSAMPA_DATASETS}

    for table_name in staging_tables.values():
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

    try:
        for production_name, filename in _GEOSAMPA_DATASETS:
            await _run_ogr2ogr_import(
                engine,
                database_url,
                effective_dir / filename,
                staging_tables[production_name],
            )

        async with engine.begin() as conn:
            row_counts: dict[str, int] = {}
            for production_name, _ in _GEOSAMPA_DATASETS:
                staging_name = staging_tables[production_name]
                await conn.execute(
                    text(
                        f"CREATE INDEX ix_{staging_name}_geometry "
                        f"ON {staging_name} USING GIST (geometry)"
                    )
                )

                invalid_count_result = await conn.execute(
                    text(
                        f"""
                        SELECT count(*)
                        FROM {staging_name}
                        WHERE geometry IS NULL
                           OR NOT ST_IsValid(geometry)
                        """
                    )
                )
                invalid_count = int(invalid_count_result.scalar_one())
                if invalid_count > 0:
                    # Attempt to repair invalid geometries from upstream sources.
                    await conn.execute(
                        text(
                            f"""
                            UPDATE {staging_name}
                            SET geometry = ST_Multi(ST_CollectionExtract(ST_MakeValid(geometry), 3))
                            WHERE geometry IS NOT NULL
                              AND NOT ST_IsValid(geometry)
                            """
                        )
                    )
                    recheck_result = await conn.execute(
                        text(
                            f"""
                            SELECT count(*)
                            FROM {staging_name}
                            WHERE geometry IS NULL
                               OR NOT ST_IsValid(geometry)
                            """
                        )
                    )
                    remaining_invalid = int(recheck_result.scalar_one())
                    if remaining_invalid > 0:
                        raise GeoSampaIngestionError(
                            "ST_IsValid check failed for "
                            f"{production_name}: {remaining_invalid} "
                            "invalid geometries after repair"
                        )

                row_count_result = await conn.execute(text(f"SELECT count(*) FROM {staging_name}"))
                row_counts[production_name] = int(row_count_result.scalar_one())

            await _replace_production_tables(
                conn,
                tuple(name for name, _ in _GEOSAMPA_DATASETS),
                staging_tables,
                suffix=suffix,
            )
            await _upsert_dataset_version(
                conn,
                dataset_type=dataset_type,
                version_hash=version_hash,
                source_label=source_label,
                row_counts=row_counts,
            )
    except Exception:
        async with engine.begin() as conn:
            for staging_name in staging_tables.values():
                await conn.execute(text(f"DROP TABLE IF EXISTS {staging_name}"))
        raise

    elapsed = time.perf_counter() - started
    return GeoSampaIngestionResult(
        dataset_type=dataset_type,
        version_hash=version_hash,
        skipped=False,
        source_label=source_label,
        row_counts=row_counts,
        elapsed_seconds=elapsed,
    )
