from __future__ import annotations

import importlib.util
import hashlib
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as datetime_time, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .dataset_versioning import upsert_dataset_version
from .neighborhood_analytics import refresh_public_safety_neighborhood_analytics
from .standardization import normalize_location_display_name

ROOT = Path(__file__).resolve().parents[5]
DATASET_TYPE = "public_safety_incidents"
_SAO_PAULO_MIN_LONGITUDE = -54.0
_SAO_PAULO_MAX_LONGITUDE = -43.0
_SAO_PAULO_MIN_LATITUDE = -26.5
_SAO_PAULO_MAX_LATITUDE = -19.0
_SAO_PAULO_TIMEZONE = "America/Sao_Paulo"
_DATE_COLUMN_CANDIDATES = (
    "DATA_OCORRENCIA_BO",
    "DATA_OCORRENCIA",
    "DATA_FATO",
    "DATA_HORA_FATO",
    "DATAHORA_FATO",
    "DATA_DIA",
    "DATA_REGISTRO",
    "DATA_BO",
    "DATA_ELABORACAO",
    "DATA",
)
_TIME_COLUMN_CANDIDATES = (
    "HORA_OCORRENCIA_BO",
    "HORA_OCORRENCIA",
    "HORA_FATO",
    "HORA",
    "HORARIO",
)
_NEIGHBORHOOD_COLUMN_CANDIDATES = (
    "BAIRRO",
    "BAIRRO_FATO",
    "BAIRRO_CIRCUNSCRICAO",
    "BAIRRO_ELABORACAO",
    "NOME_BAIRRO",
    "DS_BAIRRO",
)


class PublicSafetyIngestionError(RuntimeError):
    """Raised when the SSP safety dataset cannot be ingested safely."""


@dataclass(frozen=True)
class PublicSafetyIngestionResult:
    dataset_type: str
    source_year: int
    source_label: str
    version_hash: str
    deleted_rows: int
    inserted_rows: int
    dropped_rows: int
    neighborhood_boundary_rows: int
    neighborhood_metric_rows: int
    elapsed_seconds: float


def normalize_location_context_name(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return normalize_location_display_name(value)


def _hash_source_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    wanted_cols = getattr(module, "WANTED_COLS", None)
    if isinstance(wanted_cols, list):
        for column_name in _NEIGHBORHOOD_COLUMN_CANDIDATES:
            if column_name not in wanted_cols:
                wanted_cols.append(column_name)
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
    date_column = _pick_occurrence_date_column(dataframe)
    city_column = _pick_city_column(dataframe)
    neighborhood_column = _pick_neighborhood_column(dataframe)
    time_column = _pick_occurrence_time_column(dataframe)

    if date_column is None:
        raise PublicSafetyIngestionError(
            "SSP dataframe does not contain a recognized date column for occurred_at"
        )

    selected_columns = [date_column, "NATUREZA_APURADA", "LONGITUDE", "LATITUDE"]
    if time_column:
        selected_columns.append(time_column)
    if city_column:
        selected_columns.append(city_column)
    if neighborhood_column:
        selected_columns.append(neighborhood_column)

    working = dataframe.loc[:, selected_columns].copy()
    renamed_columns = {
        date_column: "occurred_date",
        "NATUREZA_APURADA": "category",
        "LONGITUDE": "longitude",
        "LATITUDE": "latitude",
    }
    if time_column:
        renamed_columns[time_column] = "occurred_time"
    if city_column:
        renamed_columns[city_column] = "city_name"
    if neighborhood_column:
        renamed_columns[neighborhood_column] = "neighborhood_name"
    working = working.rename(columns=renamed_columns)

    occurred_dates = pd.to_datetime(working["occurred_date"], errors="coerce").dt.tz_localize(None).dt.floor("D")
    occurred_seconds = (
        working["occurred_time"].map(_parse_occurrence_time_to_seconds)
        if "occurred_time" in working.columns
        else pd.Series(0, index=working.index, dtype="float64")
    )
    working["occurrence_hour_known"] = occurred_seconds.notna()
    working["occurred_at"] = occurred_dates + pd.to_timedelta(occurred_seconds.fillna(0), unit="s")
    working["occurred_at"] = working["occurred_at"].dt.tz_localize(
        _SAO_PAULO_TIMEZONE,
        ambiguous="NaT",
        nonexistent="shift_forward",
    ).dt.tz_convert("UTC")
    working["category"] = working["category"].astype("string").str.strip()
    working["longitude"] = pd.to_numeric(working["longitude"], errors="coerce")
    working["latitude"] = pd.to_numeric(working["latitude"], errors="coerce")
    if "city_name" in working.columns:
        working["city_name"] = working["city_name"].map(normalize_location_context_name).astype("string")
    else:
        working["city_name"] = pd.Series(pd.NA, index=working.index, dtype="string")
    if "neighborhood_name" in working.columns:
        working["neighborhood_name"] = working["neighborhood_name"].map(normalize_location_context_name).astype("string")
    else:
        working["neighborhood_name"] = pd.Series(pd.NA, index=working.index, dtype="string")

    valid_mask = (
        working["occurred_at"].notna()
        & working["category"].notna()
        & working["category"].ne("")
        & working["longitude"].between(-180.0, 180.0)
        & working["latitude"].between(-90.0, 90.0)
        & ((working["longitude"] != 0.0) | (working["latitude"] != 0.0))
        & working["longitude"].between(_SAO_PAULO_MIN_LONGITUDE, _SAO_PAULO_MAX_LONGITUDE)
        & working["latitude"].between(_SAO_PAULO_MIN_LATITUDE, _SAO_PAULO_MAX_LATITUDE)
    )
    prepared = working.loc[valid_mask].copy()
    prepared = prepared.loc[prepared["occurred_at"].dt.year == source_year].copy()
    dropped_rows = int(len(dataframe) - len(prepared))
    return prepared, dropped_rows


def _pick_city_column(dataframe: pd.DataFrame) -> str | None:
    for column_name in dataframe.columns:
        normalized = str(column_name).strip().upper()
        if normalized in {
            "MUNICIPIO_CIRCUNSCRICAO",
            "MUNICIPIO_ELABORACAO",
            "MUNICIPIO_FATO",
            "MUNICIPIO",
            "CIDADE",
            "NOME_MUNICIPIO",
        }:
            return str(column_name)
    return None


def _pick_occurrence_date_column(dataframe: pd.DataFrame) -> str | None:
    normalized_map = {str(column_name).strip().upper(): str(column_name) for column_name in dataframe.columns}
    for candidate in _DATE_COLUMN_CANDIDATES:
        if candidate in normalized_map:
            return normalized_map[candidate]
    return None


def _pick_occurrence_time_column(dataframe: pd.DataFrame) -> str | None:
    normalized_map = {str(column_name).strip().upper(): str(column_name) for column_name in dataframe.columns}
    for candidate in _TIME_COLUMN_CANDIDATES:
        if candidate in normalized_map:
            return normalized_map[candidate]
    return None


def _pick_neighborhood_column(dataframe: pd.DataFrame) -> str | None:
    for column_name in dataframe.columns:
        normalized = str(column_name).strip().upper()
        if normalized in _NEIGHBORHOOD_COLUMN_CANDIDATES or "BAIRRO" in normalized:
            return str(column_name)
    return None


def _parse_occurrence_time_to_seconds(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        value = value.timetz().replace(tzinfo=None)
    if isinstance(value, datetime_time):
        return float((value.hour * 3600) + (value.minute * 60) + value.second)
    if isinstance(value, (int, float)) and not pd.isna(value):
        numeric_value = float(value)
        if 0.0 <= numeric_value < 1.0:
            return float(round(numeric_value * 24 * 3600))
    text_value = str(value).strip()
    if not text_value or text_value.upper() == "NULL":
        return None
    matched = re.fullmatch(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{1,2}))?(?::(?P<second>\d{1,2}))?", text_value)
    if matched is None:
        return None
    hour = int(matched.group("hour"))
    minute = int(matched.group("minute") or 0)
    second = int(matched.group("second") or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    return float((hour * 3600) + (minute * 60) + second)


def _iter_incident_rows(dataframe: pd.DataFrame) -> Iterable[dict[str, Any]]:
    columns = ["occurred_at", "category", "longitude", "latitude", "city_name", "neighborhood_name", "occurrence_hour_known"]
    for occurred_at, category, longitude, latitude, city_name, neighborhood_name, occurrence_hour_known in dataframe.loc[:, columns].itertuples(index=False, name=None):
        occurred_at_value = occurred_at.to_pydatetime() if hasattr(occurred_at, "to_pydatetime") else occurred_at
        if isinstance(occurred_at_value, datetime) and occurred_at_value.tzinfo is None:
            occurred_at_value = occurred_at_value.replace(tzinfo=timezone.utc)
        yield {
            "occurred_at": occurred_at_value,
            "category": str(category),
            "longitude": float(longitude),
            "latitude": float(latitude),
            "city_name": str(city_name).strip() if city_name is not pd.NA and pd.notna(city_name) else None,
            "neighborhood_name": str(neighborhood_name).strip() if neighborhood_name is not pd.NA and pd.notna(neighborhood_name) else None,
            "occurrence_hour_known": bool(occurrence_hour_known),
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
        INSERT INTO public_safety_incidents (occurred_at, category, location, city_name, neighborhood_name, occurrence_hour_known)
        VALUES (
            :occurred_at,
            :category,
            ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326),
            :city_name,
            :neighborhood_name,
            :occurrence_hour_known
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
                location geometry(Point, 4326),
                city_name TEXT,
                neighborhood_name TEXT,
                occurrence_hour_known BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await conn.execute(text("ALTER TABLE public_safety_incidents ADD COLUMN IF NOT EXISTS city_name TEXT"))
    await conn.execute(text("ALTER TABLE public_safety_incidents ADD COLUMN IF NOT EXISTS neighborhood_name TEXT"))
    await conn.execute(text("ALTER TABLE public_safety_incidents ADD COLUMN IF NOT EXISTS occurrence_hour_known BOOLEAN NOT NULL DEFAULT FALSE"))
    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_location
            ON public_safety_incidents USING GIST (location)
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_city_neighborhood
            ON public_safety_incidents (city_name, neighborhood_name, occurred_at)
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_occurred_at
            ON public_safety_incidents (occurred_at)
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
    module = _load_public_safety_module()
    xlsx_path = cache_dir / module.XLSX_NAME.format(ano=source_year)
    version_hash = _hash_source_file(xlsx_path)
    dataframe, source_label = _load_source_dataframe(cache_dir, source_year)
    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=source_year)
    if prepared.empty:
        raise PublicSafetyIngestionError(
            f"no valid public safety incidents prepared for year {source_year} from {source_label}"
        )

    effective_dataset_type = dataset_type if dataset_type != DATASET_TYPE else f"{DATASET_TYPE}_{source_year}"

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
        await upsert_dataset_version(
            conn,
            dataset_type=effective_dataset_type,
            version_hash=version_hash,
            source_label=source_label,
            extra_meta={
                "source_year": source_year,
                "inserted_rows": inserted_rows,
                "deleted_rows": int(delete_result.rowcount or 0),
            },
        )
        analytics_result = await refresh_public_safety_neighborhood_analytics(conn)

    elapsed_seconds = time.perf_counter() - started_at
    return PublicSafetyIngestionResult(
        dataset_type=effective_dataset_type,
        source_year=source_year,
        source_label=source_label,
        version_hash=version_hash,
        deleted_rows=int(delete_result.rowcount or 0),
        inserted_rows=inserted_rows,
        dropped_rows=dropped_rows,
        neighborhood_boundary_rows=analytics_result.boundary_rows,
        neighborhood_metric_rows=analytics_result.metric_rows,
        elapsed_seconds=elapsed_seconds,
    )