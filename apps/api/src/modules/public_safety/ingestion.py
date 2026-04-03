from __future__ import annotations

import importlib.util
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

ROOT = Path(__file__).resolve().parents[5]
DATASET_TYPE = "public_safety_incidents"


class PublicSafetyIngestionError(RuntimeError):
    """Raised when the SSP safety dataset cannot be ingested safely."""


@dataclass(frozen=True)
class PublicSafetyIngestionResult:
    dataset_type: str
    source_year: int
    source_label: str
    deleted_rows: int
    inserted_rows: int
    dropped_rows: int
    elapsed_seconds: float


def _load_public_safety_module() -> ModuleType:
    script_path = ROOT / "cods_ok" / "segurancaRegiao.py"
    if not script_path.exists():
        raise PublicSafetyIngestionError(f"public safety script not found: {script_path}")

    module_name = "segurancaRegiao_ingestion"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise PublicSafetyIngestionError(f"could not load module spec for: {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    required_functions = (
        "load_crime_data_from_xlsx",
        "pick_date_column",
        "parse_date_series",
    )
    for function_name in required_functions:
        if not hasattr(module, function_name):
            raise PublicSafetyIngestionError(
                f"segurancaRegiao.py is missing required function: {function_name}"
            )
    if not hasattr(module, "XLSX_NAME"):
        raise PublicSafetyIngestionError("segurancaRegiao.py is missing XLSX_NAME")
    return module


def _load_source_dataframe(cache_dir: Path, source_year: int) -> tuple[pd.DataFrame, str]:
    module = _load_public_safety_module()
    xlsx_path = cache_dir / module.XLSX_NAME.format(ano=source_year)
    if not xlsx_path.exists():
        raise PublicSafetyIngestionError(
            f"required SSP XLSX cache not found for year {source_year}: {xlsx_path}"
        )

    dataframe = module.load_crime_data_from_xlsx(str(xlsx_path))
    if "DATA_DIA" not in dataframe.columns:
        date_col = module.pick_date_column(dataframe)
        if not date_col:
            raise PublicSafetyIngestionError(
                "SSP XLSX does not contain a recognized date column for occurred_at"
            )
        dataframe["DATA_DIA"] = module.parse_date_series(dataframe[date_col])

    try:
        source_label = xlsx_path.relative_to(ROOT).as_posix()
    except ValueError:
        source_label = xlsx_path.as_posix()
    return dataframe, source_label


def _prepare_incidents_dataframe(
    dataframe: pd.DataFrame,
    *,
    source_year: int,
) -> tuple[pd.DataFrame, int]:
    working = dataframe.loc[:, ["DATA_DIA", "NATUREZA_APURADA", "LONGITUDE", "LATITUDE"]].copy()
    working.columns = ["occurred_at", "category", "longitude", "latitude"]

    working["occurred_at"] = pd.to_datetime(working["occurred_at"], errors="coerce", utc=True).dt.floor("D")
    working["category"] = working["category"].astype("string").str.strip()
    working["longitude"] = pd.to_numeric(working["longitude"], errors="coerce")
    working["latitude"] = pd.to_numeric(working["latitude"], errors="coerce")

    valid_mask = (
        working["occurred_at"].notna()
        & working["category"].notna()
        & working["category"].ne("")
        & working["longitude"].between(-180.0, 180.0)
        & working["latitude"].between(-90.0, 90.0)
    )
    prepared = working.loc[valid_mask].copy()
    prepared = prepared.loc[prepared["occurred_at"].dt.year == source_year].copy()
    dropped_rows = int(len(dataframe) - len(prepared))
    return prepared, dropped_rows


def _iter_incident_rows(dataframe: pd.DataFrame) -> Iterable[dict[str, Any]]:
    for occurred_at, category, longitude, latitude in dataframe.itertuples(index=False, name=None):
        occurred_at_value = occurred_at.to_pydatetime() if hasattr(occurred_at, "to_pydatetime") else occurred_at
        if isinstance(occurred_at_value, datetime) and occurred_at_value.tzinfo is None:
            occurred_at_value = occurred_at_value.replace(tzinfo=timezone.utc)
        yield {
            "occurred_at": occurred_at_value,
            "category": str(category),
            "longitude": float(longitude),
            "latitude": float(latitude),
        }


async def _execute_buffered_inserts(
    conn: AsyncConnection,
    rows: Iterable[dict[str, Any]],
    *,
    batch_size: int = 5000,
) -> int:
    buffer: list[dict[str, Any]] = []
    inserted = 0
    stmt = text(
        """
        INSERT INTO public_safety_incidents (occurred_at, category, location)
        VALUES (
            :occurred_at,
            :category,
            ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)
        )
        """
    )

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


async def _ensure_public_safety_table(conn: AsyncConnection) -> None:
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
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


async def ingest_public_safety_to_postgis(
    engine: AsyncEngine,
    *,
    cache_dir: Path,
    source_year: int,
    dataset_type: str = DATASET_TYPE,
) -> PublicSafetyIngestionResult:
    started_at = time.perf_counter()
    dataframe, source_label = _load_source_dataframe(cache_dir, source_year)
    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=source_year)
    if prepared.empty:
        raise PublicSafetyIngestionError(
            f"no valid public safety incidents prepared for year {source_year} from {source_label}"
        )

    year_start = datetime(source_year, 1, 1, tzinfo=timezone.utc)
    next_year_start = datetime(source_year + 1, 1, 1, tzinfo=timezone.utc)

    async with engine.begin() as conn:
        await _ensure_public_safety_table(conn)
        delete_result = await conn.execute(
            text(
                """
                DELETE FROM public_safety_incidents
                WHERE occurred_at >= :year_start
                  AND occurred_at < :next_year_start
                """
            ),
            {"year_start": year_start, "next_year_start": next_year_start},
        )
        inserted_rows = await _execute_buffered_inserts(conn, _iter_incident_rows(prepared))

    elapsed_seconds = time.perf_counter() - started_at
    return PublicSafetyIngestionResult(
        dataset_type=dataset_type,
        source_year=source_year,
        source_label=source_label,
        deleted_rows=int(delete_result.rowcount or 0),
        inserted_rows=inserted_rows,
        dropped_rows=dropped_rows,
        elapsed_seconds=elapsed_seconds,
    )