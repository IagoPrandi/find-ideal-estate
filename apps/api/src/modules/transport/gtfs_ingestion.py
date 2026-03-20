from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TextIO
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection

GTFS_REQUIRED_FILES = ("stops", "routes", "trips", "stop_times")
GTFS_OPTIONAL_FILES = ("shapes",)
GTFS_TABLES = ("gtfs_stops", "gtfs_routes", "gtfs_trips", "gtfs_stop_times", "gtfs_shapes")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class GTFSIngestionError(RuntimeError):
    """Raised when GTFS ingestion cannot complete safely."""


@dataclass(frozen=True)
class GTFSIngestionResult:
    dataset_type: str
    version_hash: str
    skipped: bool
    source_label: str
    row_counts: dict[str, int]
    elapsed_seconds: float


def _normalize_identifier(identifier: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise GTFSIngestionError(f"Unsafe SQL identifier: {identifier}")
    return identifier


def _download_zip_bytes(source_url: str, timeout_seconds: float = 30.0) -> bytes:
    with urllib.request.urlopen(source_url, timeout=timeout_seconds) as response:
        return response.read()


def _hash_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _hash_directory(gtfs_dir: Path) -> str:
    digest = hashlib.sha256()
    candidates = sorted(p for p in gtfs_dir.glob("*.txt") if p.is_file())
    if not candidates:
        raise GTFSIngestionError(f"No GTFS .txt files found at {gtfs_dir}")
    for file_path in candidates:
        digest.update(file_path.name.encode("utf-8"))
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _rows_from_text_reader(handle: TextIO) -> Iterable[dict[str, str]]:
    yield from csv.DictReader(handle)


def _iter_csv_rows_from_directory(gtfs_dir: Path, filename_stem: str) -> Iterable[dict[str, str]]:
    file_path = gtfs_dir / f"{filename_stem}.txt"
    if not file_path.exists():
        if filename_stem in GTFS_OPTIONAL_FILES:
            return
        raise GTFSIngestionError(f"Missing required GTFS file: {file_path}")
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        yield from _rows_from_text_reader(handle)


def _iter_csv_rows_from_zip(zip_bytes: bytes, filename_stem: str) -> Iterable[dict[str, str]]:
    member = f"{filename_stem}.txt"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = set(archive.namelist())
        if member not in names:
            if filename_stem in GTFS_OPTIONAL_FILES:
                return
            raise GTFSIngestionError(f"Missing required GTFS file in zip: {member}")
        with archive.open(member, "r") as raw:
            wrapper = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            try:
                yield from _rows_from_text_reader(wrapper)
            finally:
                wrapper.detach()


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    parsed = value.strip()
    if parsed == "":
        return None
    return int(parsed)


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    parsed = value.strip()
    if parsed == "":
        return None
    return float(parsed)


async def _execute_buffered_inserts(
    conn: AsyncConnection,
    sql: str,
    rows: Iterable[dict[str, Any]],
    *,
    batch_size: int = 5000,
) -> int:
    buffer: list[dict[str, Any]] = []
    inserted = 0
    stmt = text(sql)

    async def flush() -> None:
        nonlocal inserted
        if not buffer:
            return
        await conn.execute(stmt, buffer)
        inserted += len(buffer)
        buffer.clear()

    for row in rows:
        buffer.append(row)
        if len(buffer) >= batch_size:
            await flush()
    await flush()
    return inserted


async def _create_staging_tables(conn: AsyncConnection, suffix: str) -> dict[str, str]:
    suffix_token = _normalize_identifier(suffix)
    table_map = {table: f"{table}_staging_{suffix_token}" for table in GTFS_TABLES}

    for staging_name in table_map.values():
        _normalize_identifier(staging_name)
        await conn.execute(text(f"DROP TABLE IF EXISTS {staging_name}"))

    await conn.execute(
        text(
            f"""
            CREATE TABLE {table_map['gtfs_stops']} (
                stop_id TEXT PRIMARY KEY,
                stop_name TEXT,
                stop_lat DOUBLE PRECISION NOT NULL,
                stop_lon DOUBLE PRECISION NOT NULL,
                location geometry(Point, 4326) NOT NULL
            )
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE TABLE {table_map['gtfs_routes']} (
                route_id TEXT PRIMARY KEY,
                route_short_name TEXT,
                route_long_name TEXT,
                route_type INT
            )
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE TABLE {table_map['gtfs_trips']} (
                trip_id TEXT PRIMARY KEY,
                route_id TEXT,
                shape_id TEXT
            )
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE TABLE {table_map['gtfs_stop_times']} (
                trip_id TEXT NOT NULL,
                stop_id TEXT NOT NULL,
                arrival_time TEXT,
                departure_time TEXT,
                stop_sequence INT NOT NULL
            )
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE TABLE {table_map['gtfs_shapes']} (
                shape_id TEXT NOT NULL,
                shape_pt_sequence INT NOT NULL,
                location geometry(Point, 4326) NOT NULL,
                PRIMARY KEY (shape_id, shape_pt_sequence)
            )
            """
        )
    )
    await conn.execute(
        text(f"CREATE INDEX ix_{table_map['gtfs_stops']}_location ON {table_map['gtfs_stops']} USING GIST (location)")
    )
    return table_map


async def _replace_production_tables(conn: AsyncConnection, staging_tables: dict[str, str], suffix: str) -> None:
    suffix_token = _normalize_identifier(suffix)
    for production_table in GTFS_TABLES:
        staging_table = staging_tables[production_table]
        old_table = f"{production_table}_old_{suffix_token}"
        _normalize_identifier(staging_table)
        _normalize_identifier(old_table)

        await conn.execute(text(f"DROP TABLE IF EXISTS {old_table}"))
        exists_result = await conn.execute(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": f"public.{production_table}"},
        )
        if bool(exists_result.scalar()):
            await conn.execute(text(f"ALTER TABLE {production_table} RENAME TO {old_table}"))
        await conn.execute(text(f"ALTER TABLE {staging_table} RENAME TO {production_table}"))
        await conn.execute(text(f"DROP TABLE IF EXISTS {old_table}"))


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
            INSERT INTO dataset_versions (dataset_type, version_hash, source_url, is_current, metadata)
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


async def ingest_gtfs_to_postgis(
    engine: AsyncEngine,
    *,
    dataset_type: str = "gtfs_sptrans",
    source_url: str | None = None,
    gtfs_zip_path: Path | None = None,
    gtfs_dir: Path | None = None,
) -> GTFSIngestionResult:
    started = time.perf_counter()

    zip_bytes: bytes | None = None
    source_label = ""
    if source_url:
        zip_bytes = _download_zip_bytes(source_url)
        source_label = source_url
    elif gtfs_zip_path is not None:
        zip_bytes = gtfs_zip_path.read_bytes()
        source_label = str(gtfs_zip_path)
    else:
        effective_dir = gtfs_dir or Path("data_cache") / "gtfs"
        if not effective_dir.exists():
            raise GTFSIngestionError(f"GTFS directory not found: {effective_dir}")
        gtfs_dir = effective_dir
        source_label = str(gtfs_dir)

    if zip_bytes is not None:
        version_hash = _hash_bytes(zip_bytes)

        def row_provider(name: str) -> Iterable[dict[str, str]]:
            return _iter_csv_rows_from_zip(zip_bytes, name)

    else:
        assert gtfs_dir is not None
        version_hash = _hash_directory(gtfs_dir)

        def row_provider(name: str) -> Iterable[dict[str, str]]:
            return _iter_csv_rows_from_directory(gtfs_dir, name)

    async with engine.begin() as conn:
        current_hash = await _current_dataset_hash(conn, dataset_type=dataset_type)
        if current_hash == version_hash:
            elapsed = time.perf_counter() - started
            return GTFSIngestionResult(
                dataset_type=dataset_type,
                version_hash=version_hash,
                skipped=True,
                source_label=source_label,
                row_counts={table: 0 for table in GTFS_TABLES},
                elapsed_seconds=elapsed,
            )

        # Prefix with a letter so temporary table identifiers always satisfy SQL naming rules.
        suffix = f"s{uuid4().hex[:8]}"
        staging_tables = await _create_staging_tables(conn, suffix=suffix)

        stops_rows = (
            {
                "stop_id": row["stop_id"].strip(),
                "stop_name": (row.get("stop_name") or "").strip() or None,
                "stop_lat": _safe_float(row.get("stop_lat")),
                "stop_lon": _safe_float(row.get("stop_lon")),
            }
            for row in row_provider("stops")
            if (row.get("stop_id") or "").strip() and _safe_float(row.get("stop_lat")) is not None and _safe_float(row.get("stop_lon")) is not None
        )
        stops_count = await _execute_buffered_inserts(
            conn,
            f"""
            INSERT INTO {staging_tables['gtfs_stops']} (stop_id, stop_name, stop_lat, stop_lon, location)
            VALUES (
                :stop_id,
                :stop_name,
                :stop_lat,
                :stop_lon,
                ST_SetSRID(ST_MakePoint(:stop_lon, :stop_lat), 4326)
            )
            """,
            stops_rows,
        )

        routes_rows = (
            {
                "route_id": row["route_id"].strip(),
                "route_short_name": (row.get("route_short_name") or "").strip() or None,
                "route_long_name": (row.get("route_long_name") or "").strip() or None,
                "route_type": _safe_int(row.get("route_type")),
            }
            for row in row_provider("routes")
            if (row.get("route_id") or "").strip()
        )
        routes_count = await _execute_buffered_inserts(
            conn,
            f"""
            INSERT INTO {staging_tables['gtfs_routes']} (route_id, route_short_name, route_long_name, route_type)
            VALUES (:route_id, :route_short_name, :route_long_name, :route_type)
            """,
            routes_rows,
        )

        trips_rows = (
            {
                "trip_id": row["trip_id"].strip(),
                "route_id": (row.get("route_id") or "").strip() or None,
                "shape_id": (row.get("shape_id") or "").strip() or None,
            }
            for row in row_provider("trips")
            if (row.get("trip_id") or "").strip()
        )
        trips_count = await _execute_buffered_inserts(
            conn,
            f"""
            INSERT INTO {staging_tables['gtfs_trips']} (trip_id, route_id, shape_id)
            VALUES (:trip_id, :route_id, :shape_id)
            """,
            trips_rows,
        )

        stop_times_rows = (
            {
                "trip_id": (row.get("trip_id") or "").strip(),
                "stop_id": (row.get("stop_id") or "").strip(),
                "arrival_time": (row.get("arrival_time") or "").strip() or None,
                "departure_time": (row.get("departure_time") or "").strip() or None,
                "stop_sequence": _safe_int(row.get("stop_sequence")),
            }
            for row in row_provider("stop_times")
            if (row.get("trip_id") or "").strip()
            and (row.get("stop_id") or "").strip()
            and _safe_int(row.get("stop_sequence")) is not None
        )
        stop_times_count = await _execute_buffered_inserts(
            conn,
            f"""
            INSERT INTO {staging_tables['gtfs_stop_times']} (trip_id, stop_id, arrival_time, departure_time, stop_sequence)
            VALUES (:trip_id, :stop_id, :arrival_time, :departure_time, :stop_sequence)
            """,
            stop_times_rows,
        )

        shapes_rows = (
            {
                "shape_id": (row.get("shape_id") or "").strip(),
                "shape_pt_sequence": _safe_int(row.get("shape_pt_sequence")),
                "shape_pt_lat": _safe_float(row.get("shape_pt_lat")),
                "shape_pt_lon": _safe_float(row.get("shape_pt_lon")),
            }
            for row in row_provider("shapes")
            if (row.get("shape_id") or "").strip()
            and _safe_int(row.get("shape_pt_sequence")) is not None
            and _safe_float(row.get("shape_pt_lat")) is not None
            and _safe_float(row.get("shape_pt_lon")) is not None
        )
        shapes_count = await _execute_buffered_inserts(
            conn,
            f"""
            INSERT INTO {staging_tables['gtfs_shapes']} (shape_id, shape_pt_sequence, location)
            VALUES (
                :shape_id,
                :shape_pt_sequence,
                ST_SetSRID(ST_MakePoint(:shape_pt_lon, :shape_pt_lat), 4326)
            )
            """,
            shapes_rows,
        )

        await _replace_production_tables(conn, staging_tables, suffix=suffix)

        row_counts = {
            "gtfs_stops": stops_count,
            "gtfs_routes": routes_count,
            "gtfs_trips": trips_count,
            "gtfs_stop_times": stop_times_count,
            "gtfs_shapes": shapes_count,
        }
        await _upsert_dataset_version(
            conn,
            dataset_type=dataset_type,
            version_hash=version_hash,
            source_label=source_label,
            row_counts=row_counts,
        )

    elapsed = time.perf_counter() - started
    return GTFSIngestionResult(
        dataset_type=dataset_type,
        version_hash=version_hash,
        skipped=False,
        source_label=source_label,
        row_counts=row_counts,
        elapsed_seconds=elapsed,
    )